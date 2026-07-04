"""GNIS DomesticNames parser against real recorded rows (OR file, 2026-05)."""

from __future__ import annotations

from pathlib import Path

import pytest

from place.ingest.geo import in_polygon
from place.ingest.gnis import CLASS_TO_KIND, parse_text

FIXTURE = Path(__file__).parent / "fixtures" / "gnis_sample.txt"


@pytest.fixture(scope="module")
def features():
    return parse_text(FIXTURE.read_text())


class TestParseText:
    def test_only_target_classes_survive(self, features):
        # fixture deliberately includes Stream rows — they must be dropped
        assert features
        assert {f.kind for f in features} <= set(CLASS_TO_KIND.values())

    def test_real_row_parsed_correctly(self, features):
        bonnie = next(f for f in features if f.name == "Bonnie Falls")
        assert bonnie.kind == "waterfall"
        assert bonnie.gnis_id.isdigit()
        assert bonnie.lat == pytest.approx(45.804, abs=0.001)
        assert bonnie.lng == pytest.approx(-122.9377, abs=0.001)
        assert bonnie.elev_m is None  # DomesticNames format has no elevation

    def test_fixture_contains_out_of_polygon_rows(self, features):
        """State files carry statewide (and stray out-of-state) rows; the
        polygon filter is the loader's job, not the parser's."""
        inside = [f for f in features if in_polygon(f.lat, f.lng)]
        outside = [f for f in features if not in_polygon(f.lat, f.lng)]
        assert inside and outside

    def test_null_island_rows_dropped(self):
        content = (
            "feature_id|feature_name|feature_class|state_name|state_numeric|county_name|"
            "county_numeric|map_name|date_created|date_edited|bgn_type|bgn_authority|"
            "bgn_date|prim_lat_dms|prim_long_dms|prim_lat_dec|prim_long_dec|"
            "source_lat_dms|source_long_dms|source_lat_dec|source_long_dec\n"
            "111|Ghost Falls|Falls|Oregon|41|Clackamas|005|X|01/01/1981|||||0000000N|"
            "0000000W|0.0|0.0|||0.0|0.0\n"
        )
        assert parse_text(content) == []

    def test_legacy_national_file_header_supported(self):
        content = (
            "FEATURE_ID|FEATURE_NAME|FEATURE_CLASS|STATE_ALPHA|STATE_NUMERIC|COUNTY_NAME|"
            "COUNTY_NUMERIC|PRIMARY_LAT_DMS|PRIM_LONG_DMS|PRIM_LAT_DEC|PRIM_LONG_DEC|"
            "SOURCE_LAT_DMS|SOURCE_LONG_DMS|SOURCE_LAT_DEC|SOURCE_LONG_DEC|ELEV_IN_M|"
            "ELEV_IN_FT|MAP_NAME|DATE_CREATED|DATE_EDITED\n"
            "1136847|Latourell Falls|Falls|OR|41|Multnomah|051|453214N|1221306W|45.5372|"
            "-122.2178|||||15|49|Bridal Veil|11/28/1980|\n"
        )
        (falls,) = parse_text(content)
        assert falls.name == "Latourell Falls"
        assert falls.kind == "waterfall"
        assert falls.elev_m == 15

    def test_missing_columns_raise(self):
        with pytest.raises(ValueError, match="missing expected columns"):
            parse_text("foo|bar\n1|2\n")

    def test_empty_input(self):
        assert parse_text("") == []
