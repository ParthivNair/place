"""The frozen claim JSON schema (docs/03 §2).

This schema is FROZEN: claims extracted in 2026 and claims re-extracted in
2028 must be row-compatible. Add nothing here without bumping SCHEMA_VERSION
and providing a migration for cached extraction output.

Two fields are load-bearing (docs/03 §2):
- ``observed_date`` is when the experience HAPPENED, not when it was posted.
- ``verbatim_quote`` is minimal internal evidence, never republished
  (it lands in ``claims.quote_internal``, which no API serializer exposes).
"""

from __future__ import annotations

import datetime as dt
import json
import re
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = "1"

# Keep quotes minimal: enough to audit the claim, never enough to republish.
MAX_QUOTE_CHARS = 500
# Community archives predating this are noise for our purposes.
MIN_OBSERVED_YEAR = 1980

_ACTIVITY_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


class ClaimType(StrEnum):
    """Mirrors the ``claim_class`` enum in docs/01 §2 exactly."""

    geomorphic = "geomorphic"
    seasonal_bio = "seasonal_bio"
    access = "access"
    hazard_calibration = "hazard_calibration"


def source_domain_from_url(url: str) -> str:
    """'https://www.reddit.com/r/x/y' -> 'reddit.com' (independence checks)."""
    host = urlparse(url).netloc.lower().split(":")[0]
    return host.removeprefix("www.")


def normalize_activity(value: str) -> str:
    """Fold model output ('Wild-swim', 'wild swim') into vocabulary ids."""
    return re.sub(r"[\s\-]+", "_", value.strip().lower())


class ExtractedClaim(BaseModel):
    """One atomic claim as emitted by the extraction model.

    Strict by design: unknown fields are rejected, instances are immutable,
    and every constraint the pipeline depends on is enforced here rather
    than downstream.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    place_ref: str = Field(min_length=1, max_length=500)
    activity: str = Field(min_length=1, max_length=100)
    claim_type: ClaimType
    condition_text: str | None = Field(default=None, max_length=1000)
    observed_date: dt.date | None = None
    verbatim_quote: str = Field(min_length=1, max_length=MAX_QUOTE_CHARS)
    source_url: str = Field(min_length=1, max_length=2000)
    self_confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("place_ref")
    @classmethod
    def _place_ref_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("place_ref must not be blank")
        return v

    @field_validator("activity")
    @classmethod
    def _activity_normalized(cls, v: str) -> str:
        v = normalize_activity(v)
        if not _ACTIVITY_RE.match(v):
            raise ValueError(f"activity {v!r} is not a valid vocabulary id")
        return v

    @field_validator("observed_date")
    @classmethod
    def _observed_date_sane(cls, v: dt.date | None) -> dt.date | None:
        if v is None:
            return None
        if v > dt.date.today():
            raise ValueError("observed_date must not be in the future")
        if v.year < MIN_OBSERVED_YEAR:
            raise ValueError(f"observed_date before {MIN_OBSERVED_YEAR} is not credible")
        return v

    @field_validator("source_url")
    @classmethod
    def _source_url_http(cls, v: str) -> str:
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("source_url must be an absolute http(s) URL")
        return v

    @property
    def source_domain(self) -> str:
        return source_domain_from_url(self.source_url)


def claim_json_schema() -> dict[str, Any]:
    """JSON Schema for one claim object, embedded in the extraction prompt."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "place_ref",
            "activity",
            "claim_type",
            "condition_text",
            "observed_date",
            "verbatim_quote",
            "source_url",
            "self_confidence",
        ],
        "properties": {
            "place_ref": {
                "type": "string",
                "description": "The place as referenced in the text, verbatim or lightly "
                "normalized (e.g. 'the falls past the second bridge on Eagle Creek').",
            },
            "activity": {
                "type": "string",
                "description": "snake_case activity verb, e.g. wild_swim, cliff_jump, "
                "waterfall_view, tidepool, snowshoe, hike.",
            },
            "claim_type": {
                "type": "string",
                "enum": [c.value for c in ClaimType],
            },
            "condition_text": {
                "type": ["string", "null"],
                "description": "The condition asserted, if any "
                "(e.g. 'pool deep enough to jump mid-June through September').",
            },
            "observed_date": {
                "type": ["string", "null"],
                "description": "ISO date the experience HAPPENED (not the posting date). "
                "null when the text gives no basis for dating the experience.",
            },
            "verbatim_quote": {
                "type": "string",
                "description": f"Minimal verbatim evidence, <= {MAX_QUOTE_CHARS} chars.",
            },
            "source_url": {"type": "string"},
            "self_confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "Honest probability that this claim is correctly extracted "
                "AND correct about the world.",
            },
        },
    }


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_claims_json(text: str) -> tuple[list[ExtractedClaim], list[str]]:
    """Parse model output into validated claims.

    Returns (valid_claims, errors). Tolerates markdown code fences; anything
    else malformed is reported per-item so one bad claim never sinks a
    document's good ones.
    """
    cleaned = _FENCE_RE.sub("", text.strip()).strip()
    if not cleaned:
        return [], ["empty model output"]
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        return [], [f"invalid JSON: {exc}"]
    if not isinstance(data, list):
        return [], [f"expected a JSON array, got {type(data).__name__}"]

    claims: list[ExtractedClaim] = []
    errors: list[str] = []
    for i, item in enumerate(data):
        try:
            claims.append(ExtractedClaim.model_validate(item))
        except Exception as exc:  # pydantic.ValidationError, but keep robust
            errors.append(f"claim[{i}]: {exc}")
    return claims, errors
