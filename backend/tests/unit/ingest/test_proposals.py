"""Proposals schema validation + in-file dedup (pure — no database)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
import yaml

from place.extract.schema import MAX_QUOTE_CHARS
from place.ingest.proposals import (
    LOG_ODDS,
    ProposalError,
    dedup,
    load,
    parse_proposals,
)

KNOWN = {"wild_swim", "tidepool", "hike"}


def _entry(**overrides) -> dict:
    e = {
        "place": {
            "name": "High Rocks",
            "lat": 45.44,
            "lng": -122.62,
            "kind": "swim_hole",
        },
        "activity_id": "wild_swim",
        "claim": {
            "text": "Deep pool below the ledges; locals jump here in July.",
            "source_url": "https://www.oregonhikers.org/field_guide/High_Rocks",
            "source_type": "llm_extracted",
            "observed_date": "2025-07-15",
        },
    }
    e.update(overrides)
    return e


class TestParseProposals:
    def test_valid_bare_list(self):
        (p,) = parse_proposals([_entry()], KNOWN)
        assert p.place_name == "High Rocks"
        assert p.activity_id == "wild_swim"
        assert p.cclass == "geomorphic"  # default class
        assert p.observed_date == dt.date(2025, 7, 15)
        assert p.dog_ok is None and p.kid_ok is None

    def test_wrapper_mapping_accepted(self):
        assert len(parse_proposals({"proposals": [_entry()]}, KNOWN)) == 1

    def test_yaml_roundtrip_parses_dates_either_way(self):
        """yaml.safe_load turns ISO dates into date objects; both spellings work."""
        doc = yaml.safe_load(
            "- place: {name: High Rocks, lat: 45.44, lng: -122.62, kind: swim_hole}\n"
            "  activity_id: wild_swim\n"
            "  claim:\n"
            "    text: deep pool\n"
            "    source_url: https://example.org/a\n"
            "    source_type: user_reported\n"
            "    observed_date: 2025-07-15\n"
        )
        (p,) = parse_proposals(doc, KNOWN)
        assert p.observed_date == dt.date(2025, 7, 15)

    def test_unknown_activity_rejected(self):
        """The vocabulary is closed — proposals cannot mint activities."""
        with pytest.raises(ProposalError, match="closed"):
            parse_proposals([_entry(activity_id="jetski")], KNOWN)

    @pytest.mark.parametrize("stype", ["founder_verified", "sensor_derived", "made_up"])
    def test_privileged_source_types_rejected(self, stype: str):
        e = _entry()
        e["claim"]["source_type"] = stype
        with pytest.raises(ProposalError, match="source_type"):
            parse_proposals([e], KNOWN)

    def test_relative_source_url_rejected(self):
        e = _entry()
        e["claim"]["source_url"] = "/field_guide/High_Rocks"
        with pytest.raises(ProposalError, match="absolute"):
            parse_proposals([e], KNOWN)

    def test_blank_claim_text_rejected(self):
        e = _entry()
        e["claim"]["text"] = "  "
        with pytest.raises(ProposalError, match="claim.text"):
            parse_proposals([e], KNOWN)

    def test_overlong_claim_text_rejected(self):
        """quote_internal carries minimal evidence, capped like the frozen
        extraction schema's verbatim_quote — not whole scraped articles."""
        e = _entry()
        e["claim"]["text"] = "x" * (MAX_QUOTE_CHARS + 1)
        with pytest.raises(ProposalError, match=str(MAX_QUOTE_CHARS)):
            parse_proposals([e], KNOWN)

    def test_claim_text_at_cap_allowed(self):
        e = _entry()
        e["claim"]["text"] = "x" * MAX_QUOTE_CHARS
        assert len(parse_proposals([e], KNOWN)) == 1

    def test_future_observed_date_rejected(self):
        e = _entry()
        e["claim"]["observed_date"] = (dt.date.today() + dt.timedelta(days=2)).isoformat()
        with pytest.raises(ProposalError, match="future"):
            parse_proposals([e], KNOWN)

    def test_ancient_observed_date_rejected(self):
        e = _entry()
        e["claim"]["observed_date"] = "1975-06-01"
        with pytest.raises(ProposalError, match="predates"):
            parse_proposals([e], KNOWN)

    def test_null_observed_date_allowed(self):
        e = _entry()
        e["claim"]["observed_date"] = None
        (p,) = parse_proposals([e], KNOWN)
        assert p.observed_date is None

    def test_coordinates_outside_oregon_rejected(self):
        e = _entry()
        e["place"]["lat"] = 21.3  # a hallucinated Hawaii waterfall
        with pytest.raises(ProposalError, match="never invent coordinates"):
            parse_proposals([e], KNOWN)

    def test_non_bool_dog_ok_rejected(self):
        with pytest.raises(ProposalError, match="dog_ok"):
            parse_proposals([_entry(dog_ok="yes")], KNOWN)

    def test_bad_claim_class_rejected(self):
        e = _entry()
        e["claim"]["class"] = "vibes"
        with pytest.raises(ProposalError, match="claim.class"):
            parse_proposals([e], KNOWN)

    def test_empty_file_rejected(self):
        with pytest.raises(ProposalError, match="non-empty"):
            parse_proposals([], KNOWN)

    def test_error_names_the_offending_entry(self):
        with pytest.raises(ProposalError, match=r"proposals\[1\]"):
            parse_proposals([_entry(), _entry(activity_id="jetski")], KNOWN)

    def test_log_odds_priors_match_docs01(self):
        """docs/01 §5 table: llm_extracted logit(0.35), user_reported logit(0.55)."""
        assert LOG_ODDS["llm_extracted"] == pytest.approx(-0.619, abs=1e-3)
        assert LOG_ODDS["user_reported"] == pytest.approx(0.2007, abs=1e-3)


class TestDedup:
    def test_exact_duplicates_collapse(self):
        unique, dupes = dedup(parse_proposals([_entry(), _entry()], KNOWN))
        assert len(unique) == 1 and dupes == 1

    def test_name_normalization_collapses_case_and_punctuation(self):
        """'High Rocks!' and 'high rocks' are one candidate — the same
        normalization the DB-side crosswalk match would apply."""
        e2 = _entry()
        e2["place"]["name"] = "high rocks!"
        unique, dupes = dedup(parse_proposals([_entry(), e2], KNOWN))
        assert len(unique) == 1 and dupes == 1

    def test_distinct_source_urls_survive(self):
        """Two sources for one affordance are corroboration, not duplication."""
        e2 = _entry()
        e2["claim"]["source_url"] = "https://www.reddit.com/r/Portland/comments/abc"
        unique, dupes = dedup(parse_proposals([_entry(), e2], KNOWN))
        assert len(unique) == 2 and dupes == 0

    def test_distinct_activities_survive(self):
        e2 = _entry(activity_id="hike")
        unique, _ = dedup(parse_proposals([_entry(), e2], KNOWN))
        assert len(unique) == 2

    def test_distinct_claim_classes_survive(self):
        """One field-guide page routinely supports several distinct claims —
        a geomorphic 'deep pool' plus an access 'gate closed' from the same
        URL are corroborating different facts, not duplicating one."""
        e2 = _entry()
        e2["claim"]["text"] = "Trail gate closed until June; bridge out."
        e2["claim"]["class"] = "access"
        unique, dupes = dedup(parse_proposals([_entry(), e2], KNOWN))
        assert len(unique) == 2 and dupes == 0

    def test_same_named_places_far_apart_survive(self):
        """Oregon has two Punch Bowl Falls ~20 km apart; a roundup page citing
        both must not collapse them — coordinates are part of the key."""
        e1, e2 = _entry(), _entry()
        e1["place"]["name"] = e2["place"]["name"] = "Punch Bowl Falls"
        e2["place"]["lat"] = e1["place"]["lat"] + 0.18  # ~20 km north
        unique, dupes = dedup(parse_proposals([e1, e2], KNOWN))
        assert len(unique) == 2 and dupes == 0


class TestLoadFileErrors:
    """A bad path or broken YAML must surface as ProposalError (the CLI's
    rejected-file exit path), not a raw traceback. Neither case reaches the
    database, so conn=None proves the failure happens before any DB work."""

    def test_missing_file_is_a_proposal_error(self, tmp_path: Path):
        with pytest.raises(ProposalError, match="not found"):
            load(None, tmp_path / "nope.yaml")

    def test_invalid_yaml_is_a_proposal_error(self, tmp_path: Path):
        path = tmp_path / "broken.yaml"
        path.write_text("proposals: [unclosed\n  - place: {")
        with pytest.raises(ProposalError, match="not valid YAML"):
            load(None, path)
