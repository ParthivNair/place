"""RIDB facilities parser (fixture mirrors the documented RECDATA shape)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from place.config import MissingCredential, Settings
from place.ingest.ridb import parse_facilities

FIXTURE = Path(__file__).parent / "fixtures" / "ridb_facilities.json"


@pytest.fixture(scope="module")
def payload() -> dict:
    return json.loads(FIXTURE.read_text())


class TestParseFacilities:
    def test_parses_facilities(self, payload):
        facs = parse_facilities(payload)
        names = {f.name for f in facs}
        assert "Multnomah Falls" in names
        assert "Multnomah Falls Timed Use Permit" in names

    def test_permit_flag_from_facility_type(self, payload):
        facs = {f.name: f for f in parse_facilities(payload)}
        assert facs["Multnomah Falls Timed Use Permit"].permit_required
        assert not facs["Multnomah Falls"].permit_required

    def test_kind_mapping_and_shouting_names_tamed(self, payload):
        facs = {f.ridb_id: f for f in parse_facilities(payload)}
        assert facs["232876"].kind == "campground"
        assert facs["232876"].name == "Oxbow Regional Park Campground"
        assert facs["251434"].kind == "facility"

    def test_zero_coordinate_rows_dropped(self, payload):
        assert all(f.ridb_id != "244444" for f in parse_facilities(payload))

    def test_ridb_ids_are_strings(self, payload):
        assert all(isinstance(f.ridb_id, str) for f in parse_facilities(payload))


class TestKeyGate:
    def test_missing_key_raises_missing_credential(self, monkeypatch):
        monkeypatch.delenv("RIDB_API_KEY", raising=False)
        settings = Settings(_env_file=None)
        with pytest.raises(MissingCredential, match="RIDB_API_KEY"):
            settings.require("RIDB_API_KEY")
