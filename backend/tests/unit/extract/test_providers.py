"""DeepSeek provider: request shape, unwrapping, retries, isolation — respx, no key."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
import respx

from place.config import MissingCredential, Settings, resolve_extraction_provider
from place.extract import worker
from place.extract.providers import (
    DEEPSEEK_JSON_ADDENDUM,
    DEEPSEEK_USER_INSTRUCTION,
    EMPTY_CONTENT_RETRIES,
    build_deepseek_request,
    run_deepseek_extraction,
    unwrap_claims_object,
)
from place.extract.worker import (
    EXTRACTION_SYSTEM_PROMPT,
    MAX_OUTPUT_TOKENS,
    CachedDoc,
    extractor_version,
)

BASE_URL = "https://api.deepseek.com"
CHAT_URL = f"{BASE_URL}/chat/completions"

DOC = CachedDoc(
    "reddit-doc1",
    "reddit",
    "https://www.reddit.com/r/Portland/comments/aa1/high_rocks/",
    None,
    "We cliff-jumped at High Rocks last Saturday. Perfect.",
)
DOC2 = CachedDoc(
    "reddit-doc2",
    "reddit",
    "https://www.reddit.com/r/Portland/comments/bb2/other/",
    None,
    "Flow was around 900 cfs and it felt safe.",
)

GOOD_CLAIM = {
    "place_ref": "High Rocks",
    "activity": "cliff_jump",
    "claim_type": "access",
    "condition_text": None,
    "observed_date": "2024-07-13",
    "verbatim_quote": "We cliff-jumped at High Rocks last Saturday.",
    "source_url": DOC.url,
    "self_confidence": 0.8,
}


def _settings(tmp_path: Path, **kwargs) -> Settings:
    settings = Settings(_env_file=None, deepseek_api_key="sk-test", **kwargs)
    settings.data_cache_dir = tmp_path
    return settings


def _chat_json(content: str, usage: dict | None = None) -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": usage
        or {"prompt_tokens": 1000, "completion_tokens": 100, "prompt_cache_hit_tokens": 900},
    }


def _wrapped(claims: list[dict]) -> str:
    return json.dumps({"claims": claims})


# ---------------------------------------------------------------------------
# pure pieces
# ---------------------------------------------------------------------------


def test_build_deepseek_request_shape() -> None:
    body = build_deepseek_request(DOC, model="deepseek-v4-pro")
    assert body["model"] == "deepseek-v4-pro"
    assert body["thinking"] == {"type": "disabled"}
    assert body["response_format"] == {"type": "json_object"}
    assert body["stream"] is False
    assert body["max_tokens"] == MAX_OUTPUT_TOKENS
    system, addendum, user = body["messages"]
    # the shared prompt is byte-identical to the Anthropic path (prefix cache)
    assert system == {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT}
    assert addendum["content"] == DEEPSEEK_JSON_ADDENDUM
    # json_object mode requires the word "json" in the prompt
    assert "json" in DEEPSEEK_JSON_ADDENDUM
    assert '{"claims": [...]}' in DEEPSEEK_JSON_ADDENDUM
    assert user["role"] == "user"
    assert DOC.url in user["content"]
    # the user message must not contradict the json_object addendum: no
    # bare-array instruction (a known empty-content trigger), "json" present
    assert user["content"].endswith(DEEPSEEK_USER_INSTRUCTION)
    assert "JSON array" not in user["content"]
    assert "json" in user["content"]
    json.dumps(body)  # must be wire-serializable


def test_unwrap_claims_object() -> None:
    assert json.loads(unwrap_claims_object(_wrapped([GOOD_CLAIM]))) == [GOOD_CLAIM]
    assert unwrap_claims_object('{"claims": []}') == "[]"
    # anything else passes through for parse_claims_json to report
    for text in ("[1, 2]", '{"other": 1}', "not json", ""):
        assert unwrap_claims_object(text) == text


def test_extractor_version_tags() -> None:
    assert extractor_version("deepseek", "deepseek-v4-pro") == "deepseek:deepseek-v4-pro/v1-schema1"
    assert (
        extractor_version("anthropic", "claude-haiku-4-5")
        == "anthropic:claude-haiku-4-5/batch-v1-schema1"
    )


# ---------------------------------------------------------------------------
# provider resolution (no keys in the environment)
# ---------------------------------------------------------------------------


@pytest.fixture()
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "EXTRACTION_PROVIDER"):
        monkeypatch.delenv(var, raising=False)


@pytest.mark.usefixtures("clean_env")
@pytest.mark.parametrize(
    ("provider", "deepseek_key", "anthropic_key", "expected"),
    [
        ("auto", "d", None, "deepseek"),
        ("auto", None, "a", "anthropic"),
        ("auto", "d", "a", "deepseek"),  # deepseek wins pre-revenue
        ("deepseek", "d", None, "deepseek"),
        ("deepseek", "d", "a", "deepseek"),
        ("anthropic", None, "a", "anthropic"),
        ("anthropic", "d", "a", "anthropic"),
    ],
)
def test_provider_resolution(
    provider: str, deepseek_key: str | None, anthropic_key: str | None, expected: str
) -> None:
    settings = Settings(
        _env_file=None, deepseek_api_key=deepseek_key, anthropic_api_key=anthropic_key
    )
    assert resolve_extraction_provider(settings, provider) == expected


@pytest.mark.usefixtures("clean_env")
@pytest.mark.parametrize(
    ("provider", "deepseek_key", "anthropic_key", "missing"),
    [
        ("auto", None, None, "DEEPSEEK_API_KEY or ANTHROPIC_API_KEY"),
        ("deepseek", None, "a", "DEEPSEEK_API_KEY"),
        ("anthropic", "d", None, "ANTHROPIC_API_KEY"),
    ],
)
def test_provider_resolution_missing_key(
    provider: str, deepseek_key: str | None, anthropic_key: str | None, missing: str
) -> None:
    settings = Settings(
        _env_file=None, deepseek_api_key=deepseek_key, anthropic_api_key=anthropic_key
    )
    with pytest.raises(MissingCredential) as exc:
        resolve_extraction_provider(settings, provider)
    assert missing in str(exc.value)


@pytest.mark.usefixtures("clean_env")
def test_provider_resolution_unknown_name() -> None:
    with pytest.raises(ValueError, match="unknown extraction provider"):
        resolve_extraction_provider(Settings(_env_file=None), "openai")


def test_run_deepseek_extraction_requires_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    settings = Settings(_env_file=None)
    settings.data_cache_dir = tmp_path
    with pytest.raises(MissingCredential):
        asyncio.run(run_deepseek_extraction({DOC.doc_id: DOC}, settings=settings))


# ---------------------------------------------------------------------------
# the request loop against a respx-mocked API
# ---------------------------------------------------------------------------


@respx.mock
async def test_request_shape_on_the_wire(tmp_path: Path) -> None:
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_chat_json(_wrapped([GOOD_CLAIM])))
    )
    rows = await run_deepseek_extraction(
        {DOC.doc_id: DOC}, settings=_settings(tmp_path), run_id="run1"
    )
    assert len(rows) == 1
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer sk-test"
    body = json.loads(request.content)
    assert body["model"] == "deepseek-v4-pro"
    assert body["thinking"] == {"type": "disabled"}
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"][0]["content"] == EXTRACTION_SYSTEM_PROMPT


@respx.mock
async def test_claims_unwrapped_and_rows_tagged(tmp_path: Path) -> None:
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_chat_json(_wrapped([GOOD_CLAIM])))
    )
    rows = await run_deepseek_extraction(
        {DOC.doc_id: DOC}, settings=_settings(tmp_path), run_id="run1"
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["place_ref"] == "High Rocks"
    assert row["status"] == "review"
    assert row["stype"] == "llm_extracted"
    assert row["extractor_ver"] == "deepseek:deepseek-v4-pro/v1-schema1"
    # record on disk mirrors collect_results' shape for the review queue
    record = json.loads((tmp_path / "extracted" / "run1" / f"{DOC.doc_id}.json").read_text())
    assert record["result_type"] == "succeeded"
    assert record["batch_id"] == "run1"
    assert record["custom_id"] == DOC.doc_id
    assert record["claims"] == rows
    assert record["errors"] == []


@respx.mock
async def test_empty_content_retried_then_success(tmp_path: Path) -> None:
    route = respx.post(CHAT_URL).mock(
        side_effect=[
            httpx.Response(200, json=_chat_json("")),
            httpx.Response(200, json=_chat_json(_wrapped([GOOD_CLAIM]))),
        ]
    )
    rows = await run_deepseek_extraction(
        {DOC.doc_id: DOC}, settings=_settings(tmp_path), run_id="run1"
    )
    assert route.call_count == 2
    assert len(rows) == 1


@respx.mock
async def test_empty_content_retries_exhausted(tmp_path: Path) -> None:
    route = respx.post(CHAT_URL).mock(return_value=httpx.Response(200, json=_chat_json("")))
    rows = await run_deepseek_extraction(
        {DOC.doc_id: DOC}, settings=_settings(tmp_path), run_id="run1"
    )
    assert route.call_count == 1 + EMPTY_CONTENT_RETRIES
    assert rows == []
    record = json.loads((tmp_path / "extracted" / "run1" / f"{DOC.doc_id}.json").read_text())
    assert record["result_type"] == "errored"
    assert "empty model output" in record["errors"][0]


@respx.mock
async def test_429_backed_off_then_success(tmp_path: Path) -> None:
    route = respx.post(CHAT_URL).mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(200, json=_chat_json(_wrapped([GOOD_CLAIM]))),
        ]
    )
    rows = await run_deepseek_extraction(
        {DOC.doc_id: DOC}, settings=_settings(tmp_path), run_id="run1"
    )
    assert route.call_count == 2
    assert len(rows) == 1


@respx.mock
async def test_per_doc_failure_does_not_abort_run(tmp_path: Path) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if DOC.url in body["messages"][-1]["content"]:
            return httpx.Response(400, json={"error": "bad request"})
        return httpx.Response(200, json=_chat_json(_wrapped([GOOD_CLAIM])))

    respx.post(CHAT_URL).mock(side_effect=respond)
    rows = await run_deepseek_extraction(
        {d.doc_id: d for d in (DOC, DOC2)}, settings=_settings(tmp_path), run_id="run1"
    )
    assert len(rows) == 1  # DOC2 still extracted
    bad = json.loads((tmp_path / "extracted" / "run1" / f"{DOC.doc_id}.json").read_text())
    assert bad["result_type"] == "errored"
    assert "deepseek request failed" in bad["errors"][0]
    good = json.loads((tmp_path / "extracted" / "run1" / f"{DOC2.doc_id}.json").read_text())
    assert good["result_type"] == "succeeded"


@respx.mock
async def test_malformed_200_body_does_not_abort_run(tmp_path: Path) -> None:
    """HTTP 200 with an unexpected shape (choices: null) costs one doc, not the run."""

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if DOC.url in body["messages"][-1]["content"]:
            return httpx.Response(200, json={"choices": None, "usage": {}})
        return httpx.Response(200, json=_chat_json(_wrapped([GOOD_CLAIM])))

    respx.post(CHAT_URL).mock(side_effect=respond)
    rows = await run_deepseek_extraction(
        {d.doc_id: d for d in (DOC, DOC2)}, settings=_settings(tmp_path), run_id="run1"
    )
    assert len(rows) == 1  # DOC2 still extracted
    bad = json.loads((tmp_path / "extracted" / "run1" / f"{DOC.doc_id}.json").read_text())
    assert bad["result_type"] == "errored"
    assert "deepseek request failed" in bad["errors"][0]


@respx.mock
async def test_resume_skips_docs_already_on_disk(tmp_path: Path) -> None:
    """Re-running under the same run_id reuses on-disk records instead of re-paying."""
    out_dir = tmp_path / "extracted" / "run1"
    out_dir.mkdir(parents=True)
    existing = {
        "custom_id": DOC.doc_id,
        "batch_id": "run1",
        "extractor_ver": "deepseek:deepseek-v4-pro/v1-schema1",
        "result_type": "succeeded",
        "claims": [{"place_ref": "High Rocks", "status": "review"}],
        "errors": [],
    }
    (out_dir / f"{DOC.doc_id}.json").write_text(json.dumps(existing))
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_chat_json(_wrapped([GOOD_CLAIM])))
    )
    rows = await run_deepseek_extraction(
        {d.doc_id: d for d in (DOC, DOC2)}, settings=_settings(tmp_path), run_id="run1"
    )
    assert route.call_count == 1  # only DOC2 hit the API
    assert len(rows) == 2  # resumed claims still returned
    assert {r["place_ref"] for r in rows} == {"High Rocks"}


@respx.mock
def test_run_extraction_dispatches_to_deepseek(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "cache"
    reddit = cache / "reddit"
    reddit.mkdir(parents=True)
    (reddit / "t3_aa1.json").write_text(
        json.dumps(
            {
                "url": DOC.url,
                "data": {"kind": "t3", "data": {"title": "High Rocks", "selftext": DOC.text}},
            }
        )
    )
    settings = _settings(tmp_path)
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_chat_json(_wrapped([GOOD_CLAIM])))
    )
    rows = worker.run_extraction(cache_dir=cache)
    assert len(rows) == 1
    assert rows[0]["extractor_ver"] == "deepseek:deepseek-v4-pro/v1-schema1"
