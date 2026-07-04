"""launch.yaml structure + the loader's predicate/hysteresis validation."""

from __future__ import annotations

import copy

import pytest
import yaml

from place.ingest.bindings import (
    DEFAULT_ACTIVITIES_PATH,
    DEFAULT_BINDINGS_PATH,
    BindingError,
    validate_predicate,
    validate_spec,
)

FEEDS = {"usgs_nwis:14210000:00060", "open_meteo:45.44,-122.62:air_temp_f"}


@pytest.fixture(scope="module")
def spec() -> dict:
    return yaml.safe_load(DEFAULT_BINDINGS_PATH.read_text())


class TestLaunchYaml:
    def test_the_launch_bindings_present(self, spec):
        keys = [b["key"] for b in spec["bindings"]]
        assert len(keys) == 11
        for expected in (
            "high-rocks-wild-swim", "dodge-park-wild-swim", "oxbow-park-wild-swim",
            "tamanawas-falls-view", "elowah-falls-view", "latourell-falls-view",
            "wahclella-falls-view", "haystack-rock-tidepool",
            "trillium-lake-snowshoe", "dog-mountain-wildflower", "larch-mountain-stargaze",
        ):
            assert expected in keys

    def test_file_validates(self, spec):
        validate_spec(spec)  # raises on failure

    def test_real_gauge_ids(self, spec):
        feed_ids = {f["id"] for f in spec["feeds"]}
        assert "usgs_nwis:14210000:00060" in feed_ids  # Clackamas @ Estacada
        assert "usgs_nwis:14137000:00060" in feed_ids  # Sandy blw Bull Run
        coops = next(f for f in spec["feeds"] if f["provider"] == "noaa_coops")
        assert coops["station_ref"] == "9437540"  # Garibaldi predictions
        snotel = next(f for f in spec["feeds"] if f["provider"] == "snotel")
        assert snotel["station_ref"] == "651:OR:SNTL"  # Mt Hood Test Site

    def test_every_wild_swim_gate_has_safe_side_hysteresis(self, spec):
        swim = [b for b in spec["bindings"] if b["activity"] == "wild_swim"]
        assert len(swim) == 3
        for b in swim:
            gates = [w for w in b["windows"] if w.get("is_gate")]
            assert len(gates) == 1, b["key"]
            flow_leaves = [
                leaf for leaf in gates[0]["predicate"]["all"]
                if leaf.get("feed", "").startswith("usgs_nwis:")
            ]
            assert len(flow_leaves) == 1, b["key"]
            leaf = flow_leaves[0]
            assert leaf["op"] == "<"
            assert leaf["exit_value"] > leaf["value"], (
                f"{b['key']}: entry must be the conservative bound"
            )

    def test_high_rocks_matches_docs_canonical_thresholds(self, spec):
        hr = next(b for b in spec["bindings"] if b["key"] == "high-rocks-wild-swim")
        gate = next(w for w in hr["windows"] if w["is_gate"])
        flow, temp = gate["predicate"]["all"]
        assert (flow["value"], flow["exit_value"]) == (1050, 1200)
        assert (temp["op"], temp["value"]) == (">", 75)
        seasonal = next(w for w in hr["windows"] if w["wtype"] == "seasonal")
        assert seasonal["predicate"] == {"months": [7, 8, 9]}

    def test_waterfall_bindings_are_boosts_not_gates(self, spec):
        views = [b for b in spec["bindings"] if b["activity"] == "waterfall_view"]
        assert len(views) == 4
        for b in views:
            assert not any(w.get("is_gate") for w in b["windows"]), b["key"]
            wt = next(w for w in b["windows"] if w["wtype"] == "weather_triggered")
            pred = wt["predicate"]
            assert (pred["agg"], pred["window_h"]) == ("sum", 72)
            assert pred["op"] == ">=" and pred["value"] == 1.0

    def test_tidepool_threshold_is_true_minus_tide(self, spec):
        hs = next(b for b in spec["bindings"] if b["key"] == "haystack-rock-tidepool")
        tide = hs["windows"][0]["predicate"]["all"][0]
        assert tide["op"] == "<" and tide["value"] == -1.0

    def test_activities_vocabulary_covers_bindings(self, spec):
        vocab = yaml.safe_load(DEFAULT_ACTIVITIES_PATH.read_text())
        ids = {a["id"] for a in vocab["activities"]}
        assert {b["activity"] for b in spec["bindings"]} <= ids
        hazard = {a["id"] for a in vocab["activities"] if a["hazard_class"]}
        assert "wild_swim" in hazard


class TestValidatePredicate:
    def test_wrong_side_hysteresis_on_lt_rejected(self):
        with pytest.raises(BindingError, match="safe-side"):
            validate_predicate(
                {"feed": "usgs_nwis:14210000:00060", "op": "<", "value": 1200,
                 "exit_value": 1050},
                FEEDS, True, "t",
            )

    def test_wrong_side_hysteresis_on_gt_rejected(self):
        with pytest.raises(BindingError, match="safe-side"):
            validate_predicate(
                {"feed": "open_meteo:45.44,-122.62:air_temp_f", "op": ">", "value": 70,
                 "exit_value": 75},
                FEEDS, True, "t",
            )

    def test_exit_value_on_equality_rejected(self):
        with pytest.raises(BindingError, match="meaningless"):
            validate_predicate(
                {"feed": "usgs_nwis:14210000:00060", "op": "=", "value": 1,
                 "exit_value": 2},
                FEEDS, False, "t",
            )

    def test_undeclared_feed_rejected(self):
        with pytest.raises(BindingError, match="not declared"):
            validate_predicate({"feed": "usgs_nwis:999:00060", "op": "<", "value": 1},
                               FEEDS, False, "t")

    def test_agg_requires_window_h(self):
        with pytest.raises(BindingError, match="window_h"):
            validate_predicate(
                {"feed": "usgs_nwis:14210000:00060", "agg": "sum", "op": ">", "value": 1},
                FEEDS, False, "t",
            )

    def test_months_leaf(self):
        validate_predicate({"months": [7, 8, 9]}, FEEDS, False, "t")
        with pytest.raises(BindingError, match="months"):
            validate_predicate({"months": [0, 13]}, FEEDS, False, "t")

    def test_nested_composition(self):
        validate_predicate(
            {"all": [
                {"any": [{"months": [7]},
                         {"feed": "usgs_nwis:14210000:00060", "op": "between",
                          "value": [100, 500]}]},
                {"not": {"feed": "open_meteo:45.44,-122.62:air_temp_f", "op": ">",
                         "value": 100}},
            ]},
            FEEDS, False, "t",
        )

    def test_empty_combinator_rejected(self):
        with pytest.raises(BindingError, match="non-empty"):
            validate_predicate({"all": []}, FEEDS, False, "t")


class TestValidateSpec:
    def test_duplicate_binding_key_rejected(self, spec):
        broken = copy.deepcopy(spec)
        broken["bindings"].append(copy.deepcopy(broken["bindings"][0]))
        with pytest.raises(BindingError, match="duplicate"):
            validate_spec(broken)

    def test_binding_without_windows_rejected(self, spec):
        broken = copy.deepcopy(spec)
        broken["bindings"][0]["windows"] = []
        with pytest.raises(BindingError, match="window"):
            validate_spec(broken)

    def test_bad_wtype_rejected(self, spec):
        broken = copy.deepcopy(spec)
        broken["bindings"][0]["windows"][0]["wtype"] = "vibes"
        with pytest.raises(BindingError, match="wtype"):
            validate_spec(broken)
