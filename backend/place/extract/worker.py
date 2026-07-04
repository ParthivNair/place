"""Extraction worker — Claude batch API over the cached corpus (docs/03 §2).

Stage 2 of the pipeline. Batch-tier, offline, no latency requirement:
each cached document becomes one batch request against a Haiku-class model
(docs/03 cost math: ~150k docs ≈ 60M input tokens ≈ <=$200 one-time) with the
frozen claim JSON schema. Nothing auto-publishes — every extracted claim is
stored with status='review', source_type='llm_extracted', and an
extractor_version tag so the corpus can be cheaply re-extracted as models
improve.

Key-gated: request BUILDING is pure and runs without any credential;
submitting/collecting a batch requires ANTHROPIC_API_KEY and raises
MissingCredential otherwise.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import math
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from place.config import Settings, get_settings
from place.extract.schema import (
    SCHEMA_VERSION,
    ExtractedClaim,
    claim_json_schema,
    parse_claims_json,
    source_domain_from_url,
)

log = logging.getLogger(__name__)

# Stored on every claim (claims.extractor_ver); bump when the prompt or model
# changes materially — re-extraction diffs run on this tag (docs/03 §2).
EXTRACTOR_VERSION = f"haiku45-batch-v1-schema{SCHEMA_VERSION}"

# docs/03 §2: "a Haiku-class model on the batch API".
DEFAULT_MODEL = "claude-haiku-4-5"
MAX_OUTPUT_TOKENS = 4096
# Documents beyond this are truncated; community posts are rarely this long.
MAX_DOC_CHARS = 24_000

# Source-type prior from docs/01 §5: llm_extracted p0=0.35 -> L0=logit(0.35).
LLM_EXTRACTED_LOG_ODDS = round(math.log(0.35 / 0.65), 4)  # -0.6190

EXTRACTION_SYSTEM_PROMPT = f"""\
You extract structured claims about outdoor places near Portland, Oregon from \
community documents (Reddit posts/comments, Oregon Hikers field-guide pages and \
forum trip reports).

Extract CLAIMS, not prose. A claim is one atomic, checkable assertion joining a \
specific place to a specific activity, optionally with a condition. Do not \
summarize the document; do not extract opinions with no place ("great weekend!"), \
generic advice, or anything not grounded in the text.

Output: a JSON array of claim objects and NOTHING else — no markdown fences, no \
commentary. If the document contains no extractable claims, output exactly [].

Each claim object must match this JSON Schema:
{json.dumps(claim_json_schema(), indent=1)}

Field rules — read carefully:

- place_ref: the place as the author referenced it. Keep descriptive references \
intact ("the falls past the second bridge on Eagle Creek") — entity resolution \
happens downstream; never invent a canonical name the author did not use.

- activity: one snake_case verb, e.g. wild_swim, cliff_jump, waterfall_view, \
tidepool, snowshoe, wildflower_view, hike, paddle, fish, stargaze, camp, forage.

- claim_type, one of:
  - geomorphic: durable physical facts ("there is a deep pool below the falls").
  - seasonal_bio: seasonal/biological timing ("balsamroot peaks late April").
  - access: access state that rots ("rope swing intact", "gate open", "log \
crossing washed out", "road gated in winter").
  - hazard_calibration: condition thresholds relevant to safety ("too pushy \
above 1800 cfs", "fine for kids by late July").

- observed_date: the date the EXPERIENCE HAPPENED, never the posting date. \
"Last July we swam at High Rocks" posted 2020-01-15 means observed_date \
2019-07-15 (mid-month when only a month is known; mid-year when only a year is \
known). A trip report dated in its own text uses that date. If the text is a \
present-tense report with no other dating, you may use the posted date supplied \
in the document header. If the experience genuinely cannot be dated, use null — \
do not guess.

- verbatim_quote: the SHORTEST verbatim span (<= 500 chars) that evidences the \
claim. Internal audit evidence only; never paraphrase, never stitch separate \
sentences together.

- source_url: copy the document URL from the header exactly.

- self_confidence: your honest probability (0..1) that the claim is correctly \
extracted AND true of the world. Hedged/secondhand text ("I heard the swing is \
gone") warrants <= 0.4. Direct dated first-person reports warrant 0.6-0.85. \
Reserve > 0.9 for unambiguous, specific, first-person statements. Do not \
inflate; downstream confidence math depends on calibration.

Extract every distinct claim; corroborating claims from one document about \
different places or activities are separate objects.
"""


# ---------------------------------------------------------------------------
# cached-corpus loading
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CachedDoc:
    """One cached source document, normalized for the extraction prompt."""

    doc_id: str
    source: str  # 'reddit' | 'oregonhikers'
    url: str
    posted_date: dt.date | None
    text: str


class _HTMLTextExtractor(HTMLParser):
    """Crude but dependency-free HTML -> text (scripts/styles dropped)."""

    _SKIP = {"script", "style", "noscript"}

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and data.strip():
            self._chunks.append(data.strip())

    def text(self) -> str:
        return "\n".join(self._chunks)


def html_to_text(html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return parser.text()


def _doc_id(source: str, url: str) -> str:
    # custom_id must be 1-64 chars of [A-Za-z0-9_-]; this is <= 46.
    return f"{source}-{hashlib.sha256(url.encode()).hexdigest()[:32]}"


def _load_reddit_doc(path: Path) -> CachedDoc | None:
    record = json.loads(path.read_text())
    child = record.get("data", {})
    kind, data = child.get("kind"), child.get("data", {})
    if kind == "t3":
        text = "\n\n".join(p for p in (data.get("title"), data.get("selftext")) if p)
    elif kind == "t1":
        text = data.get("body") or ""
    else:
        return None
    url = record.get("url") or (
        f"https://www.reddit.com{data.get('permalink', '')}" if data.get("permalink") else ""
    )
    if not text.strip() or not url:
        return None
    posted = None
    if created := data.get("created_utc"):
        posted = dt.datetime.fromtimestamp(float(created), tz=dt.UTC).date()
    return CachedDoc(_doc_id("reddit", url), "reddit", url, posted, text)


def _load_oregonhikers_doc(path: Path) -> CachedDoc | None:
    record = json.loads(path.read_text())
    url = record.get("url", "")
    body = record.get("body", "")
    text = html_to_text(body) if "<" in body else body
    if not text.strip() or not url:
        return None
    return CachedDoc(_doc_id("oregonhikers", url), "oregonhikers", url, None, text)


def iter_cached_docs(cache_dir: Path | None = None) -> Iterator[CachedDoc]:
    """Walk data/cache/{reddit,oregonhikers}/ and yield normalized documents."""
    cache_dir = cache_dir or get_settings().data_cache_dir
    loaders = {"reddit": _load_reddit_doc, "oregonhikers": _load_oregonhikers_doc}
    for source, loader in loaders.items():
        root = cache_dir / source
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.json")):
            try:
                doc = loader(path)
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                log.warning("skipping unreadable cache file %s: %s", path, exc)
                continue
            if doc is not None:
                yield doc


# ---------------------------------------------------------------------------
# batch request building (pure — no API, no credential)
# ---------------------------------------------------------------------------


def _document_prompt(doc: CachedDoc) -> str:
    posted = doc.posted_date.isoformat() if doc.posted_date else "unknown"
    body = doc.text[:MAX_DOC_CHARS]
    return (
        f"source: {doc.source}\n"
        f"url: {doc.url}\n"
        f"posted_date: {posted}\n"
        f"---\n"
        f"{body}\n"
        f"---\n"
        "Extract the claims as a JSON array."
    )


def build_batch_requests(
    docs: Iterable[CachedDoc], *, model: str = DEFAULT_MODEL
) -> list[dict[str, Any]]:
    """Build Message Batches request entries for the given documents.

    Pure and credential-free: returns plain JSON-serializable dicts in the
    ``{custom_id, params}`` shape the batches endpoint takes. The system
    prompt is byte-identical across requests and carries a cache_control
    breakpoint so it is cacheable at batch-tier pricing (docs/03 cost math).
    """
    requests: list[dict[str, Any]] = []
    for doc in docs:
        requests.append(
            {
                "custom_id": doc.doc_id,
                "params": {
                    "model": model,
                    "max_tokens": MAX_OUTPUT_TOKENS,
                    "system": [
                        {
                            "type": "text",
                            "text": EXTRACTION_SYSTEM_PROMPT,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    "messages": [{"role": "user", "content": _document_prompt(doc)}],
                },
            }
        )
    return requests


# ---------------------------------------------------------------------------
# claim-row shaping (pure)
# ---------------------------------------------------------------------------


def claim_row(claim: ExtractedClaim, doc: CachedDoc) -> dict[str, Any]:
    """Shape one validated claim into a pre-resolution claims-table row.

    ``affordance_id`` is intentionally absent — entity resolution
    (place.extract.resolve) attaches it or parks the row. ``place_ref`` and
    ``activity`` ride along for the resolver and are preserved verbatim on
    parked rows.
    """
    return {
        "place_ref": claim.place_ref,
        "activity": claim.activity,
        "cclass": claim.claim_type.value,
        "stype": "llm_extracted",
        "source_url": claim.source_url,
        "source_domain": source_domain_from_url(claim.source_url),
        "quote_internal": claim.verbatim_quote,
        "condition_text": claim.condition_text,
        "observed_date": claim.observed_date.isoformat() if claim.observed_date else None,
        "extractor_ver": EXTRACTOR_VERSION,
        "self_conf": claim.self_confidence,
        "status": "review",
        "log_odds": LLM_EXTRACTED_LOG_ODDS,
        "doc_id": doc.doc_id,
    }


# ---------------------------------------------------------------------------
# batch submission / collection (key-gated)
# ---------------------------------------------------------------------------


def _anthropic_client(settings: Settings | None = None) -> Any:
    """Key gate: importable without a key; calling this without one raises."""
    settings = settings or get_settings()
    api_key = settings.require("anthropic_api_key")  # raises MissingCredential
    import anthropic

    return anthropic.Anthropic(api_key=api_key)


def submit_batch(requests: list[dict[str, Any]], *, client: Any = None) -> str:
    """Submit built requests as one Message Batch; returns the batch id."""
    client = client or _anthropic_client()
    batch = client.messages.batches.create(requests=requests)
    log.info("submitted batch %s with %d requests", batch.id, len(requests))
    return batch.id


def wait_for_batch(batch_id: str, *, client: Any = None, poll_s: float = 60.0) -> None:
    client = client or _anthropic_client()
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended":
            return
        log.info("batch %s: %s", batch_id, batch.processing_status)
        time.sleep(poll_s)


def collect_results(
    batch_id: str,
    docs_by_id: dict[str, CachedDoc],
    *,
    client: Any = None,
    out_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Stream batch results, validate against the frozen schema, store rows.

    Results arrive in arbitrary order — everything is keyed by custom_id.
    Each document's validated claims are written to
    ``data/cache/extracted/{batch_id}/{custom_id}.json`` as claim rows with
    status='review' and stype='llm_extracted'; parse/validation errors are
    kept alongside for the review queue. Returns all claim rows.
    """
    client = client or _anthropic_client()
    out_dir = (out_dir or get_settings().data_cache_dir / "extracted") / batch_id
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for result in client.messages.batches.results(batch_id):
        custom_id = result.custom_id
        doc = docs_by_id.get(custom_id)
        record: dict[str, Any] = {
            "custom_id": custom_id,
            "batch_id": batch_id,
            "extractor_ver": EXTRACTOR_VERSION,
            "result_type": result.result.type,
            "claims": [],
            "errors": [],
        }
        if result.result.type == "succeeded" and doc is not None:
            text = "".join(
                b.text for b in result.result.message.content if b.type == "text"
            )
            claims, errors = parse_claims_json(text)
            record["claims"] = [claim_row(c, doc) for c in claims]
            record["errors"] = errors
            rows.extend(record["claims"])
        elif doc is None:
            record["errors"] = [f"no cached doc for custom_id {custom_id}"]
        else:
            record["errors"] = [f"batch result: {result.result.type}"]
        (out_dir / f"{custom_id}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=1)
        )
    log.info("batch %s produced %d claim rows", batch_id, len(rows))
    return rows


def run_extraction(
    *, cache_dir: Path | None = None, model: str = DEFAULT_MODEL, poll_s: float = 60.0
) -> list[dict[str, Any]]:
    """End-to-end: cached corpus -> batch -> validated claim rows on disk.

    Requires ANTHROPIC_API_KEY (MissingCredential otherwise).
    """
    docs = {doc.doc_id: doc for doc in iter_cached_docs(cache_dir)}
    if not docs:
        log.warning("no cached documents found; nothing to extract")
        return []
    client = _anthropic_client()
    requests = build_batch_requests(docs.values(), model=model)
    batch_id = submit_batch(requests, client=client)
    wait_for_batch(batch_id, client=client, poll_s=poll_s)
    return collect_results(batch_id, docs, client=client)
