"""Worker: request-building over a fake cached corpus — no API call, no key."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from place.config import MissingCredential, Settings
from place.extract import worker
from place.extract.schema import ExtractedClaim
from place.extract.worker import (
    DEFAULT_MODEL,
    EXTRACTION_SYSTEM_PROMPT,
    EXTRACTOR_VERSION,
    LLM_EXTRACTED_LOG_ODDS,
    CachedDoc,
    build_batch_requests,
    claim_row,
    collect_results,
    html_to_text,
    iter_cached_docs,
)

# ---------------------------------------------------------------------------
# fake cached corpus
# ---------------------------------------------------------------------------


@pytest.fixture()
def corpus(tmp_path: Path) -> Path:
    reddit = tmp_path / "reddit" / "Portland"
    reddit.mkdir(parents=True)
    (reddit / "t3_aa1.json").write_text(
        json.dumps(
            {
                "source": "reddit",
                "url": "https://www.reddit.com/r/Portland/comments/aa1/high_rocks/",
                "fetched_at": "2026-07-01T00:00:00+00:00",
                "robots_ok": True,
                "data": {
                    "kind": "t3",
                    "data": {
                        "id": "aa1",
                        "title": "High Rocks in July",
                        "selftext": "We cliff-jumped at High Rocks last Saturday. Perfect.",
                        "permalink": "/r/Portland/comments/aa1/high_rocks/",
                        "created_utc": 1720915200,  # 2024-07-14
                    },
                },
            }
        )
    )
    (reddit / "t1_c1.json").write_text(
        json.dumps(
            {
                "source": "reddit",
                "url": "https://www.reddit.com/r/Portland/comments/aa1/high_rocks/c1/",
                "fetched_at": "2026-07-01T00:00:00+00:00",
                "robots_ok": True,
                "data": {
                    "kind": "t1",
                    "data": {
                        "id": "c1",
                        "body": "Flow was around 900 cfs and it felt safe.",
                        "permalink": "/r/Portland/comments/aa1/high_rocks/c1/",
                        "created_utc": 1721000000,
                    },
                },
            }
        )
    )
    oh = tmp_path / "oregonhikers" / "field_guide"
    oh.mkdir(parents=True)
    (oh / "abc.json").write_text(
        json.dumps(
            {
                "source": "oregonhikers",
                "url": "https://www.oregonhikers.org/field_guide/Tamanawas_Falls_Hike",
                "fetched_at": "2026-07-01T00:00:00+00:00",
                "robots_ok": True,
                "kind": "field_guide",
                "content_type": "text/html",
                "body": "<html><script>x()</script><body><p>Tamanawas was "
                "roaring after that storm.</p></body></html>",
            }
        )
    )
    # an unreadable file must be skipped, not fatal
    (oh / "broken.json").write_text("{not json")
    return tmp_path


def test_iter_cached_docs_loads_both_sources(corpus: Path) -> None:
    docs = list(iter_cached_docs(corpus))
    assert len(docs) == 3
    by_source = {d.source for d in docs}
    assert by_source == {"reddit", "oregonhikers"}

    post = next(d for d in docs if "aa1/high_rocks/" == d.url[-len("aa1/high_rocks/"):])
    assert "High Rocks in July" in post.text
    assert "cliff-jumped" in post.text
    assert post.posted_date == dt.date(2024, 7, 14)

    guide = next(d for d in docs if d.source == "oregonhikers")
    assert "roaring after that storm" in guide.text
    assert "x()" not in guide.text  # scripts stripped
    assert guide.posted_date is None


def test_html_to_text_strips_scripts() -> None:
    assert html_to_text("<p>keep</p><script>drop()</script>") == "keep"


def test_doc_ids_are_valid_custom_ids(corpus: Path) -> None:
    for doc in iter_cached_docs(corpus):
        assert 1 <= len(doc.doc_id) <= 64
        assert all(c.isalnum() or c in "-_" for c in doc.doc_id)


def test_build_batch_requests_shape(corpus: Path) -> None:
    docs = list(iter_cached_docs(corpus))
    requests = build_batch_requests(docs)
    assert len(requests) == 3
    assert {r["custom_id"] for r in requests} == {d.doc_id for d in docs}
    for req, doc in zip(requests, docs, strict=True):
        params = req["params"]
        assert params["model"] == DEFAULT_MODEL
        assert params["system"][0]["text"] == EXTRACTION_SYSTEM_PROMPT
        assert params["system"][0]["cache_control"] == {"type": "ephemeral"}
        user = params["messages"][0]
        assert user["role"] == "user"
        assert doc.url in user["content"]
        assert "posted_date:" in user["content"]
    # everything must be JSON-serializable (goes over the wire verbatim)
    json.dumps(requests)


def test_prompt_carries_the_load_bearing_instructions() -> None:
    for needle in (
        "observed_date",
        "not the posting date",
        "verbatim",
        "self_confidence",
        "JSON array",
        "place_ref",
    ):
        assert needle in EXTRACTION_SYSTEM_PROMPT


def test_claim_row_shape() -> None:
    doc = CachedDoc("reddit-x", "reddit", "https://www.reddit.com/r/Portland/1", None, "t")
    claim = ExtractedClaim.model_validate(
        {
            "place_ref": "High Rocks",
            "activity": "wild_swim",
            "claim_type": "hazard_calibration",
            "condition_text": "felt safe around 900 cfs",
            "observed_date": "2024-07-13",
            "verbatim_quote": "Flow was around 900 cfs and it felt safe.",
            "source_url": "https://www.reddit.com/r/Portland/comments/aa1/",
            "self_confidence": 0.7,
        }
    )
    row = claim_row(claim, doc)
    assert row["status"] == "review"
    assert row["stype"] == "llm_extracted"
    assert row["extractor_ver"] == EXTRACTOR_VERSION
    assert row["cclass"] == "hazard_calibration"
    assert row["source_domain"] == "reddit.com"
    assert row["place_ref"] == "High Rocks"  # preserved for resolution/parking
    assert row["observed_date"] == "2024-07-13"
    # docs/01 §5: llm_extracted prior p0=0.35 -> L0 ~= -0.62
    assert math.isclose(row["log_odds"], math.log(0.35 / 0.65), abs_tol=1e-3)
    assert math.isclose(row["log_odds"], -0.62, abs_tol=0.005)


def test_submit_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(MissingCredential):
        worker._anthropic_client(Settings(_env_file=None))


def test_run_extraction_without_key_and_empty_cache(tmp_path: Path) -> None:
    # no docs -> returns [] before ever needing a client or key
    assert worker.run_extraction(cache_dir=tmp_path) == []


# ---------------------------------------------------------------------------
# result collection against a fake batch client (no API call)
# ---------------------------------------------------------------------------


class FakeBatchClient:
    def __init__(self, results):
        self._results = results
        self.messages = SimpleNamespace(
            batches=SimpleNamespace(results=lambda batch_id: iter(self._results))
        )


def _succeeded(custom_id: str, text: str):
    return SimpleNamespace(
        custom_id=custom_id,
        result=SimpleNamespace(
            type="succeeded",
            message=SimpleNamespace(content=[SimpleNamespace(type="text", text=text)]),
        ),
    )


def test_collect_results_validates_and_stores(corpus: Path, tmp_path: Path) -> None:
    docs = {d.doc_id: d for d in iter_cached_docs(corpus)}
    doc_ids = list(docs)
    good_claim = {
        "place_ref": "High Rocks",
        "activity": "cliff_jump",
        "claim_type": "access",
        "condition_text": None,
        "observed_date": "2024-07-13",
        "verbatim_quote": "We cliff-jumped at High Rocks last Saturday.",
        "source_url": docs[doc_ids[0]].url,
        "self_confidence": 0.8,
    }
    results = [
        _succeeded(doc_ids[0], json.dumps([good_claim])),
        _succeeded(doc_ids[1], "[]"),  # no claims in doc: fine
        SimpleNamespace(  # provider-side error: recorded, not fatal
            custom_id=doc_ids[2], result=SimpleNamespace(type="errored")
        ),
    ]
    out_dir = tmp_path / "extracted"
    rows = collect_results(
        "batch_x", docs, client=FakeBatchClient(results), out_dir=out_dir
    )
    assert len(rows) == 1
    assert rows[0]["place_ref"] == "High Rocks"
    assert rows[0]["status"] == "review"

    stored = sorted((out_dir / "batch_x").glob("*.json"))
    assert len(stored) == 3
    records = {json.loads(p.read_text())["custom_id"]: json.loads(p.read_text()) for p in stored}
    assert len(records[doc_ids[0]]["claims"]) == 1
    assert records[doc_ids[1]]["claims"] == []
    assert records[doc_ids[2]]["errors"] == ["batch result: errored"]
    assert records[doc_ids[0]]["extractor_ver"] == EXTRACTOR_VERSION


def test_collect_results_reports_validation_errors(corpus: Path, tmp_path: Path) -> None:
    docs = {d.doc_id: d for d in iter_cached_docs(corpus)}
    doc_id = next(iter(docs))
    results = [_succeeded(doc_id, "utter nonsense, not json")]
    rows = collect_results(
        "batch_y", docs, client=FakeBatchClient(results), out_dir=tmp_path / "extracted"
    )
    assert rows == []
    record = json.loads((tmp_path / "extracted" / "batch_y" / f"{doc_id}.json").read_text())
    assert record["errors"]


def test_llm_prior_constant_matches_docs() -> None:
    assert math.isclose(LLM_EXTRACTED_LOG_ODDS, -0.619, abs_tol=0.001)
