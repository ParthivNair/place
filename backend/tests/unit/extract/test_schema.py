"""Schema validation edges for the frozen claim JSON schema."""

from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from place.extract.schema import (
    MAX_QUOTE_CHARS,
    ClaimType,
    ExtractedClaim,
    claim_json_schema,
    normalize_activity,
    parse_claims_json,
    source_domain_from_url,
)

VALID = {
    "place_ref": "the falls past the second bridge on Eagle Creek",
    "activity": "wild-swim",
    "claim_type": "access",
    "condition_text": "pool deep enough to jump mid-June through September",
    "observed_date": "2019-07-14",
    "verbatim_quote": "we jumped from the ledge on the right, water was perfect",
    "source_url": "https://www.oregonhikers.org/forum/viewtopic.php?t=123",
    "self_confidence": 0.72,
}


def make(**overrides):
    return ExtractedClaim.model_validate({**VALID, **overrides})


def test_valid_claim_parses() -> None:
    claim = make()
    assert claim.claim_type is ClaimType.access
    assert claim.observed_date == dt.date(2019, 7, 14)
    assert claim.source_domain == "oregonhikers.org"


def test_activity_is_normalized() -> None:
    assert make(activity="Wild-swim").activity == "wild_swim"
    assert make(activity="waterfall  view").activity == "waterfall_view"


def test_invalid_activity_rejected() -> None:
    with pytest.raises(ValidationError):
        make(activity="!!!")


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        make(bonus_field="nope")


def test_claims_are_frozen() -> None:
    claim = make()
    with pytest.raises(ValidationError):
        claim.place_ref = "something else"  # type: ignore[misc]


@pytest.mark.parametrize("conf", [-0.1, 1.01, 2])
def test_confidence_out_of_range_rejected(conf: float) -> None:
    with pytest.raises(ValidationError):
        make(self_confidence=conf)


def test_confidence_bounds_inclusive() -> None:
    assert make(self_confidence=0.0).self_confidence == 0.0
    assert make(self_confidence=1.0).self_confidence == 1.0


def test_future_observed_date_rejected() -> None:
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    with pytest.raises(ValidationError):
        make(observed_date=tomorrow)


def test_ancient_observed_date_rejected() -> None:
    with pytest.raises(ValidationError):
        make(observed_date="1971-01-01")


def test_observed_date_none_allowed() -> None:
    assert make(observed_date=None).observed_date is None


def test_condition_text_optional() -> None:
    assert make(condition_text=None).condition_text is None


@pytest.mark.parametrize(
    "url", ["ftp://oregonhikers.org/x", "/relative/path", "not a url", ""]
)
def test_bad_source_url_rejected(url: str) -> None:
    with pytest.raises(ValidationError):
        make(source_url=url)


def test_quote_too_long_rejected() -> None:
    with pytest.raises(ValidationError):
        make(verbatim_quote="x" * (MAX_QUOTE_CHARS + 1))


def test_blank_quote_rejected() -> None:
    with pytest.raises(ValidationError):
        make(verbatim_quote="")


def test_unknown_claim_type_rejected() -> None:
    with pytest.raises(ValidationError):
        make(claim_type="vibes")


def test_blank_place_ref_rejected() -> None:
    with pytest.raises(ValidationError):
        make(place_ref="   ")


def test_source_domain_from_url_strips_www_and_port() -> None:
    assert source_domain_from_url("https://www.reddit.com/r/Portland/x") == "reddit.com"
    assert source_domain_from_url("http://oregonhikers.org:8080/y") == "oregonhikers.org"


def test_normalize_activity() -> None:
    assert normalize_activity("  Cliff Jump ") == "cliff_jump"


def test_claim_json_schema_covers_all_fields() -> None:
    schema = claim_json_schema()
    assert set(schema["required"]) == set(VALID.keys())
    assert schema["properties"]["claim_type"]["enum"] == [c.value for c in ClaimType]


# -- parse_claims_json -------------------------------------------------------


def test_parse_valid_array() -> None:
    claims, errors = parse_claims_json(f"[{__import__('json').dumps(VALID)}]")
    assert len(claims) == 1 and not errors


def test_parse_tolerates_markdown_fences() -> None:
    import json

    claims, errors = parse_claims_json(f"```json\n[{json.dumps(VALID)}]\n```")
    assert len(claims) == 1 and not errors


def test_parse_empty_array_is_no_claims_no_errors() -> None:
    claims, errors = parse_claims_json("[]")
    assert claims == [] and errors == []


def test_parse_invalid_json_reports_error() -> None:
    claims, errors = parse_claims_json("{not json")
    assert claims == [] and errors and "invalid JSON" in errors[0]


def test_parse_non_array_reports_error() -> None:
    claims, errors = parse_claims_json('{"claims": []}')
    assert claims == [] and "expected a JSON array" in errors[0]


def test_parse_empty_output_reports_error() -> None:
    claims, errors = parse_claims_json("   ")
    assert claims == [] and errors == ["empty model output"]


def test_one_bad_claim_does_not_sink_good_ones() -> None:
    import json

    bad = {**VALID, "self_confidence": 7}
    claims, errors = parse_claims_json(json.dumps([VALID, bad]))
    assert len(claims) == 1
    assert len(errors) == 1 and "claim[1]" in errors[0]
