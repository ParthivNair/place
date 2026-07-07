"""Proposals schema validation + in-file dedup (pure — no database)."""

from __future__ import annotations

import datetime as dt

import pytest
import yaml

from place.ingest.proposals import (
    LOG_ODDS,
    ProposalError,
    dedup,
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
