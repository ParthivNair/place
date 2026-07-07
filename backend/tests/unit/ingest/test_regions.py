"""Region priority list: bbox math, priority.yaml validation, NEXT pick."""

from __future__ import annotations

import math

import pytest

from place.ingest import geo
from place.ingest.regions import (
    Coverage,
    Region,
    RegionError,
    format_coverage_table,
    load_regions,
    parse_regions,
    pick_next,
    region_by_slug,
)


def _region(**overrides) -> Region:
    base = dict(
        slug="pdx-west",
        name="Portland West",
        anchor_zip="97229",
        lat=45.559,
        lng=-122.827,
        radius_mi=20.0,
        notes="Forest Park",
        target_places=150,
        target_affordances=30,
    )
    base.update(overrides)
    return Region(**base)


def _entry(**overrides) -> dict:
    e = {
        "slug": "pdx-west",
        "name": "Portland West",
        "anchor_zip": "97229",
        "lat": 45.559,
        "lng": -122.827,
        "radius_mi": 20,
        "notes": "Forest Park",
    }
    e.update(overrides)
    return e


class TestBBoxMath:
    def test_longitude_span_is_cos_corrected(self):
        """At 45.5°N a degree of longitude is shorter, so the box is wider
        in degrees east-west than north-south by exactly 1/cos(lat)."""
        r = _region()
        box = r.bbox()
        lat_span = box.north - box.south
        lng_span = box.east - box.west
        assert lng_span > lat_span
        assert lng_span / lat_span == pytest.approx(1 / math.cos(math.radians(r.lat)), rel=1e-6)

    def test_bbox_circumscribes_the_region_circle(self):
        """Cardinal extremes of the 20 mi circle land on (not outside) the box."""
        r = _region()
        box = r.bbox()
        # north/south edges sit at radius distance from the center
        assert geo.haversine_m(r.lat, r.lng, box.north, r.lng) == pytest.approx(
            r.radius_m, rel=0.01
        )
        # east/west edges: cos-correction keeps them at ~radius too
        assert geo.haversine_m(r.lat, r.lng, r.lat, box.east) == pytest.approx(
            r.radius_m, rel=0.01
        )
        assert box.south < r.lat < box.north
        assert box.west < r.lng < box.east

    def test_radius_units(self):
        assert _region().radius_km == pytest.approx(32.19, abs=0.01)
        assert _region().radius_m == pytest.approx(32_186.9, abs=10)

    def test_no_priority_region_crosses_the_antimeridian(self):
        """Oregon is nowhere near ±180°; the sanity window guarantees it."""
        for r in load_regions():
            box = r.bbox()
            assert -180.0 < box.west < box.east < 180.0


class TestShippedPriorityFile:
    def test_parses_with_expected_order_and_defaults(self):
        regions = load_regions()
        assert [r.slug for r in regions] == [
            "pdx-west", "corvallis", "gorge-west", "hood-river", "mt-hood",
            "clackamas", "coast-north", "coast-central", "salem-silverfalls",
            "bend", "eugene",
        ]
        first = regions[0]
        assert first.anchor_zip == "97229"
        assert first.radius_mi == 20
        assert all(r.target_places == 150 for r in regions)
        assert all(r.target_affordances == 30 for r in regions)

    def test_region_by_slug(self):
        regions = load_regions()
        assert region_by_slug(regions, "gorge-west").anchor_zip == "97014"
        with pytest.raises(RegionError, match="no region"):
            region_by_slug(regions, "seattle")


class TestParseRegions:
    def test_duplicate_slug_rejected(self):
        doc = {"regions": [_entry(), _entry()]}
        with pytest.raises(RegionError, match="duplicate slug"):
            parse_regions(doc)

    def test_missing_field_rejected(self):
        e = _entry()
        del e["name"]
        with pytest.raises(RegionError, match="name"):
            parse_regions({"regions": [e]})

    def test_centroid_outside_oregon_window_rejected(self):
        with pytest.raises(RegionError, match="sanity window"):
            parse_regions({"regions": [_entry(lat=47.61, lng=-122.33, slug="seattle")]})

    def test_bad_slug_rejected(self):
        with pytest.raises(RegionError, match="slug"):
            parse_regions({"regions": [_entry(slug="PDX West")]})

    def test_nonpositive_radius_rejected(self):
        with pytest.raises(RegionError, match="radius_mi"):
            parse_regions({"regions": [_entry(radius_mi=0)]})

    def test_non_numeric_radius_rejected(self):
        """'twenty' in the founder-owned YAML is a validation failure with the
        offending region named, not a bare ValueError traceback."""
        with pytest.raises(RegionError, match=r"regions\[pdx-west\]"):
            parse_regions({"regions": [_entry(radius_mi="twenty")]})

    def test_non_numeric_default_target_rejected(self):
        with pytest.raises(RegionError, match="must be numbers"):
            parse_regions({"defaults": {"target_places": "lots"}, "regions": [_entry()]})

    def test_empty_regions_rejected(self):
        with pytest.raises(RegionError, match="non-empty"):
            parse_regions({"regions": []})

    def test_defaults_apply_and_per_region_override_wins(self):
        doc = {
            "defaults": {"target_places": 99, "target_affordances": 7},
            "regions": [_entry(), _entry(slug="corvallis", target_places=40)],
        }
        first, second = parse_regions(doc)
        assert (first.target_places, first.target_affordances) == (99, 7)
        assert (second.target_places, second.target_affordances) == (40, 7)


def _cov(region: Region, places: int, review: int = 0, published: int = 0) -> Coverage:
    return Coverage(
        region=region,
        places=places,
        affordances={"draft": 0, "review": review, "published": published, "suppressed": 0},
    )


class TestPickNext:
    def test_first_region_below_target_wins(self):
        r1, r2 = _region(), _region(slug="corvallis")
        covs = [_cov(r1, places=150, review=30), _cov(r2, places=3)]
        nxt = pick_next(covs)
        assert nxt is not None and nxt.region.slug == "corvallis"

    def test_affordance_shortfall_alone_keeps_a_region_next(self):
        """150 places but only 5 affordances (any status) is still below target."""
        covs = [_cov(_region(), places=200, review=5)]
        assert pick_next(covs) is not None

    def test_any_status_counts_toward_the_affordance_target(self):
        covs = [_cov(_region(), places=150, review=15, published=15)]
        assert pick_next(covs) is None

    def test_all_regions_at_target_returns_none(self):
        covs = [_cov(_region(), places=150, review=30)]
        assert pick_next(covs) is None

    def test_table_marks_next(self):
        r1, r2 = _region(), _region(slug="corvallis")
        table = format_coverage_table([_cov(r1, 150, review=30), _cov(r2, 3)])
        lines = table.splitlines()
        assert any("pdx-west" in ln and "ok" in ln for ln in lines)
        assert any("corvallis" in ln and "NEXT" in ln for ln in lines)
