"""DeepSeek extraction provider — chat-completions loop (docs/03 §2).

The pre-revenue default provider. DeepSeek has NO batch API and no off-peak
discount, so extraction runs as a concurrency-limited loop of synchronous
chat-completions requests instead of the Anthropic batch path in
place.extract.worker. Cost math at official pricing (input $0.435/M cache
miss, $0.0036/M cache hit, output $0.87/M): the docs/03 seed corpus lands
around a $35-class run — prefix caching is automatic server-side, so the
system prompt is kept byte-identical across documents (same discipline as the
Anthropic builder) and per-doc content rides in the user message.

Output-shape delta: DeepSeek's JSON mode (`response_format: json_object`)
yields a JSON OBJECT, never a bare array. The shared EXTRACTION_SYSTEM_PROMPT
demands an array, so a DeepSeek-only addendum (a second, also-constant system
message — the main prompt is never forked) asks for ``{"claims": [...]}``,
unwrapped here before schema validation. Records land in the same
``data/cache/extracted/<run_id>/<doc_id>.json`` shape collect_results writes,
so entity resolution and the review queue read both providers identically.

Key-gated: request BUILDING is pure and runs without any credential; running
extraction requires DEEPSEEK_API_KEY and raises MissingCredential otherwise.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from place.config import Settings, get_settings
from place.extract.schema import parse_claims_json
from place.extract.worker import (
    EXTRACTION_SYSTEM_PROMPT,
    MAX_OUTPUT_TOKENS,
    CachedDoc,
    _document_prompt,
    claim_row,
    extractor_version,
)

log = logging.getLogger(__name__)

# API caveat (api-docs.deepseek.com): json_object mode "may occasionally
# return empty content" — retry a bounded number of times, then record an
# error rather than aborting the run.
EMPTY_CONTENT_RETRIES = 2
HTTP_RETRY_ATTEMPTS = 5
REQUEST_TIMEOUT_S = 120.0

# Official DeepSeek pricing (USD per token), for end-of-run cost logging.
PRICE_INPUT_MISS = 0.435 / 1_000_000
PRICE_INPUT_HIT = 0.0036 / 1_000_000
PRICE_OUTPUT = 0.87 / 1_000_000

# Second system message, constant across documents (still prefix-cacheable).
# json_object mode requires the word "json" in the prompt and returns an
# object, not an array — so ask for the array wrapped under "claims".
DEEPSEEK_JSON_ADDENDUM = (
    'Output format override: return a single json object of the shape {"claims": [...]} '
    "where the value of \"claims\" is the JSON array of claim objects described above "
    "(an empty array when there are no claims). No other keys, no commentary."
)

# Closing line of the per-doc user message. The shared _document_prompt default
# ("Extract the claims as a JSON array.") would contradict the addendum above —
# json_object mode cannot emit a bare array, and conflicting format instructions
# are a known trigger for its documented empty-content responses. The user
# message is not part of the constant system prefix, so overriding it here costs
# nothing in prefix-cache hits ("json" also satisfies the json-in-prompt rule).
DEEPSEEK_USER_INSTRUCTION = (
    "Extract the claims as the json object described in the system messages."
)


# ---------------------------------------------------------------------------
# request building / response unwrapping (pure — no API, no credential)
# ---------------------------------------------------------------------------


def build_deepseek_request(doc: CachedDoc, *, model: str) -> dict[str, Any]:
    """One chat-completions request body for one cached document.

    The first system message is the shared EXTRACTION_SYSTEM_PROMPT,
    byte-identical across documents AND with the Anthropic path — that keeps
    the two providers' core prompt in lockstep and maximizes DeepSeek's
    automatic prefix-cache hits. Thinking is ON by default on v4 models and
    unneeded for schema-bound extraction, so it is explicitly disabled.
    """
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "system", "content": DEEPSEEK_JSON_ADDENDUM},
            {
                "role": "user",
                "content": _document_prompt(doc, instruction=DEEPSEEK_USER_INSTRUCTION),
            },
        ],
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
        "stream": False,
        "max_tokens": MAX_OUTPUT_TOKENS,
    }


def unwrap_claims_object(text: str) -> str:
    """Undo the {"claims": [...]} wrapper so parse_claims_json sees an array.

    Anything that is not the expected wrapper passes through unchanged —
    parse_claims_json reports the malformation per-document.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text
    if isinstance(data, dict) and isinstance(data.get("claims"), list):
        return json.dumps(data["claims"])
    return text


# ---------------------------------------------------------------------------
# extraction run (key-gated)
# ---------------------------------------------------------------------------


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and (
        exc.response.status_code == 429 or exc.response.status_code >= 500
    )


@retry(
    retry=retry_if_exception(_retryable),
    wait=wait_exponential(multiplier=0.5, max=30),
    stop=stop_after_attempt(HTTP_RETRY_ATTEMPTS),
    reraise=True,
)
async def _post_chat(client: httpx.AsyncClient, body: dict[str, Any]) -> dict[str, Any]:
    response = await client.post("/chat/completions", json=body)
    response.raise_for_status()
    return response.json()


def _add_usage(totals: dict[str, int], usage: dict[str, Any]) -> None:
    for key in ("prompt_tokens", "completion_tokens", "prompt_cache_hit_tokens"):
        totals[key] += int(usage.get(key) or 0)


def estimate_cost_usd(totals: dict[str, int]) -> float:
    """Estimated run cost; cache-hit input tokens are ~120x cheaper than misses."""
    hit = totals["prompt_cache_hit_tokens"]
    miss = max(totals["prompt_tokens"] - hit, 0)
    out = totals["completion_tokens"]
    return miss * PRICE_INPUT_MISS + hit * PRICE_INPUT_HIT + out * PRICE_OUTPUT


def _error_record(doc_id: str, run_id: str, version: str, error: str) -> dict[str, Any]:
    return {
        "custom_id": doc_id,
        "batch_id": run_id,
        "extractor_ver": version,
        "result_type": "errored",
        "claims": [],
        "errors": [error],
    }


def _write_record(out_dir: Path, record: dict[str, Any]) -> None:
    (out_dir / f"{record['custom_id']}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=1)
    )


async def _extract_doc(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    doc: CachedDoc,
    *,
    model: str,
    version: str,
    run_id: str,
    out_dir: Path,
    totals: dict[str, int],
) -> dict[str, Any]:
    """Extract one document; failures become error records, never exceptions.

    The record is persisted to ``out_dir/{doc_id}.json`` the moment it exists,
    so a multi-hour run that aborts keeps every already-paid-for document and
    can be resumed under the same run_id. The ``except Exception`` boundary is
    deliberate: any surprise in the response body (``{"choices": null}``, a
    non-list ``choices``, non-numeric usage, ...) must cost one document, not
    the run.
    """
    record: dict[str, Any] = {
        "custom_id": doc.doc_id,
        "batch_id": run_id,
        "extractor_ver": version,
        "result_type": "errored",
        "claims": [],
        "errors": [],
    }
    try:
        body = build_deepseek_request(doc, model=model)
        content = ""
        async with semaphore:
            for _ in range(1 + EMPTY_CONTENT_RETRIES):
                data = await _post_chat(client, body)
                _add_usage(totals, data.get("usage") or {})
                content = (data["choices"][0]["message"].get("content") or "").strip()
                if content:
                    break
        if content:
            claims, errors = parse_claims_json(unwrap_claims_object(content))
            record["result_type"] = "succeeded"
            record["claims"] = [claim_row(c, doc, version) for c in claims]
            record["errors"] = errors
        else:
            record["errors"] = [
                f"empty model output after {1 + EMPTY_CONTENT_RETRIES} attempts"
            ]
    except Exception as exc:  # noqa: BLE001 — per-doc isolation boundary (see docstring)
        record["errors"] = [f"deepseek request failed: {exc!r}"]
    _write_record(out_dir, record)
    return record


async def run_deepseek_extraction(
    docs_by_id: dict[str, CachedDoc],
    *,
    model: str | None = None,
    settings: Settings | None = None,
    out_dir: Path | None = None,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    """Extract the given documents through DeepSeek; returns all claim rows.

    Concurrency-limited by DEEPSEEK_CONCURRENCY; per-document failures are
    recorded and skipped, never fatal to the run. Each record is written to
    ``data/cache/extracted/{run_id}/{doc_id}.json`` as soon as it completes
    (collect_results' shape — "batch_id" carries the run id so both providers'
    records read alike), so an aborted run loses nothing already paid for.
    Re-running with the same explicit ``run_id`` resumes: documents whose
    record already exists on disk are reused, not re-requested.
    Requires DEEPSEEK_API_KEY (MissingCredential otherwise).
    """
    settings = settings or get_settings()
    api_key = settings.require("deepseek_api_key")  # raises MissingCredential
    model = model or settings.deepseek_model
    run_id = run_id or f"deepseek-{dt.datetime.now(dt.UTC).strftime('%Y%m%dT%H%M%SZ')}"
    out_dir = (out_dir or settings.data_cache_dir / "extracted") / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    version = extractor_version("deepseek", model)
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "prompt_cache_hit_tokens": 0}
    semaphore = asyncio.Semaphore(settings.deepseek_concurrency)
    records: list[dict[str, Any]] = []
    pending: list[CachedDoc] = []
    for doc in docs_by_id.values():
        path = out_dir / f"{doc.doc_id}.json"
        if path.exists():
            try:
                records.append(json.loads(path.read_text()))
                continue  # resume: already extracted (and paid for) in a prior run
            except json.JSONDecodeError:
                pass  # torn write from an aborted run — re-extract
        pending.append(doc)
    if records:
        log.info(
            "deepseek run %s: resuming — %d/%d records already on disk",
            run_id,
            len(records),
            len(docs_by_id),
        )
    async with httpx.AsyncClient(
        base_url=settings.deepseek_base_url,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=REQUEST_TIMEOUT_S,
    ) as client:
        results = await asyncio.gather(
            *(
                _extract_doc(
                    client,
                    semaphore,
                    doc,
                    model=model,
                    version=version,
                    run_id=run_id,
                    out_dir=out_dir,
                    totals=totals,
                )
                for doc in pending
            ),
            # Backstop only: _extract_doc catches Exception itself, but a stray
            # failure in one task must never sink the other tasks' results.
            return_exceptions=True,
        )
    for doc, result in zip(pending, results, strict=True):
        if isinstance(result, BaseException):
            log.error("deepseek extraction task for %s raised: %r", doc.doc_id, result)
            record = _error_record(
                doc.doc_id, run_id, version, f"extraction task raised: {result!r}"
            )
            _write_record(out_dir, record)
            records.append(record)
        else:
            records.append(result)
    rows: list[dict[str, Any]] = []
    errored = 0
    for record in records:
        rows.extend(record["claims"])
        errored += record["result_type"] != "succeeded"
    log.info(
        "deepseek run %s: %d docs (%d errored), %d claim rows; "
        "tokens in=%d (cache-hit=%d) out=%d, est. cost $%.4f",
        run_id,
        len(records),
        errored,
        len(rows),
        totals["prompt_tokens"],
        totals["prompt_cache_hit_tokens"],
        totals["completion_tokens"],
        estimate_cost_usd(totals),
    )
    return rows
