"""Schema invariants: quote_internal never serialized; hazard fields present."""

from __future__ import annotations

import inspect

from pydantic import BaseModel

from place.api import schemas


def test_no_schema_carries_quote_internal() -> None:
    for _, model in inspect.getmembers(schemas, inspect.isclass):
        if issubclass(model, BaseModel):
            assert "quote_internal" not in model.model_fields, model.__name__


def test_feed_card_has_hazard_rendering_fields() -> None:
    fields = schemas.FeedCard.model_fields
    for required in ("assumption_of_risk", "last_verified_at", "reasons", "conditions",
                     "verdict_controls", "now_score"):
        assert required in fields


def test_verdict_control_defaults_to_full_verdict_set() -> None:
    import uuid

    control = schemas.VerdictControl(claim_id=uuid.uuid4())
    assert control.allowed_verdicts == ["confirm", "refute", "changed"]


def test_event_alias_mapping_is_total() -> None:
    assert schemas.EVENT_ALIASES["shown"] == "impression"
    assert schemas.EVENT_ALIASES["saved"] == "save"
    assert schemas.EVENT_ALIASES["went"] == "going"
    assert schemas.EVENT_ALIASES["verified"] == "verified"
