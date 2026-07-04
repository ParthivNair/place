"""Provenance-line rendering: leaf walking, freshness, degradation."""

from __future__ import annotations

import datetime as dt
import uuid

from place.api import reasons

NOW = dt.datetime(2026, 7, 3, 18, 0, tzinfo=dt.UTC)

FLOW_FEED = "usgs_nwis:14210000:00060"
TEMP_FEED = "open_meteo:45.44,-122.62:air_temp_f"
PRECIP_FEED = "nws:45.40,-121.57:precip_in"

METAS = {
    FLOW_FEED: {
        "provider": "usgs_nwis",
        "station_ref": "14210000",
        "parameter": "discharge_cfs",
        "unit": "cfs",
        "poll_interval_s": 900,
    },
    PRECIP_FEED: {
        "provider": "nws",
        "station_ref": None,
        "parameter": "precip_in",
        "unit": "in",
        "poll_interval_s": 3600,
    },
}


def test_iter_leaves_flattens_nested_composition() -> None:
    tree = {
        "all": [
            {"feed": FLOW_FEED, "op": "<", "value": 1050, "exit_value": 1200},
            {
                "any": [
                    {"feed": TEMP_FEED, "op": ">", "value": 75},
                    {"not": {"feed": "x", "op": "=", "value": 1}},
                ]
            },
        ]
    }
    leaves = reasons.iter_leaves(tree)
    assert [leaf.get("feed") for leaf in leaves] == [FLOW_FEED, TEMP_FEED, "x"]


def test_latest_leaf_renders_value_unit_and_provenance() -> None:
    out = reasons.render_reason(
        window_id=uuid.uuid4(),
        wtype="hydrological",
        predicate={"feed": FLOW_FEED, "op": "<", "value": 1050},
        inputs={FLOW_FEED: 980},
        feeds_meta=METAS,
        evaluated_at=NOW - dt.timedelta(minutes=10),
        now=NOW,
    )
    assert "980" in out["text"] and "cfs" in out["text"]
    assert out["fresh"] is True
    assert out["source"] == "usgs_nwis 14210000"
    assert out["provenance"][0]["value"] == 980


def test_sum_leaf_prints_window_h() -> None:
    out = reasons.render_reason(
        window_id=uuid.uuid4(),
        wtype="weather_triggered",
        predicate={"feed": PRECIP_FEED, "agg": "sum", "window_h": 72, "op": ">=", "value": 1.0},
        inputs={PRECIP_FEED: 1.6},
        feeds_meta=METAS,
        evaluated_at=NOW - dt.timedelta(minutes=30),
        now=NOW,
    )
    assert "1.6" in out["text"]
    assert "72 h" in out["text"]
    assert out["source"] == "nws"


def test_stale_reading_marked_as_of_never_shown_fresh() -> None:
    # 15-min feed, reading 2 hours old: > 2x cadence -> not fresh, "as of"
    stale_at = NOW - dt.timedelta(hours=2)
    out = reasons.render_reason(
        window_id=uuid.uuid4(),
        wtype="hydrological",
        predicate={"feed": FLOW_FEED, "op": "<", "value": 1050},
        inputs={FLOW_FEED: {"value": 980, "observed_at": stale_at.isoformat()}},
        feeds_meta=METAS,
        evaluated_at=NOW,
        now=NOW,
    )
    assert out["fresh"] is False
    assert "as of" in out["text"]
    assert out["as_of"] == stale_at


def test_dict_reading_normalized() -> None:
    value, observed = reasons.normalize_reading(
        {"value": 1.25, "observed_at": "2026-07-03T10:00:00+00:00"}
    )
    assert value == 1.25
    assert observed == dt.datetime(2026, 7, 3, 10, tzinfo=dt.UTC)
    assert reasons.normalize_reading(410) == (410, None)


def test_seasonal_window_without_feed_leaves_degrades_to_prior_copy() -> None:
    out = reasons.render_reason(
        window_id=uuid.uuid4(),
        wtype="seasonal",
        predicate={"months": [7, 8, 9]},  # DSL agent may extend grammar; stay tolerant
        inputs={},
        feeds_meta={},
        evaluated_at=NOW,
        now=NOW,
    )
    assert out["text"] == "in season"
    assert out["provenance"] == []
    assert out["source"] is None
