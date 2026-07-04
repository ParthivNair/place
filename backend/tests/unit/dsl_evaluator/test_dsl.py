"""DSL operators, aggregation, composition, unknown propagation, month
windows, and validation (docs/01 §3)."""

from __future__ import annotations

import datetime as dt

import pytest

from place.dsl import (
    DSLError,
    StaticProvider,
    evaluate,
    feeds_referenced,
    validate_predicate,
)

NOW = dt.datetime(2026, 7, 3, 12, 0, tzinfo=dt.UTC)
F = "usgs_nwis:14210000:00060"


def ev(pred, latest=None, windows=None, now=NOW, prev_state=None):
    provider = StaticProvider(latest_values=latest or {}, window_values=windows or {})
    return evaluate(pred, provider, now=now, prev_state=prev_state)


# ---------------------------------------------------------------------------
# leaf operators
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("op", "value", "reading", "expected"),
    [
        ("<", 1050, 1049.9, True),
        ("<", 1050, 1050.0, False),
        ("<", 1050, 1200.0, False),
        ("<=", 1050, 1050.0, True),
        ("<=", 1050, 1050.1, False),
        (">", 75, 75.1, True),
        (">", 75, 75.0, False),
        (">=", 75, 75.0, True),
        (">=", 75, 74.9, False),
        ("=", 1, 1.0, True),
        ("=", 1, 0.0, False),
        ("between", [0, 2], 0.0, True),
        ("between", [0, 2], 2.0, True),
        ("between", [0, 2], 1.0, True),
        ("between", [0, 2], 2.1, False),
        ("between", [0, 2], -0.1, False),
    ],
)
def test_every_operator(op, value, reading, expected):
    pred = {"feed": F, "op": op, "value": value}
    validate_predicate(pred)
    result = ev(pred, latest={F: reading})
    assert result.state is expected
    assert result.inputs == {F: reading}


def test_missing_reading_is_unknown_and_recorded():
    result = ev({"feed": F, "op": "<", "value": 1050}, latest={})
    assert result.state is None
    assert result.inputs == {F: None}


# ---------------------------------------------------------------------------
# aggregation over a trailing window (72-h precip accumulation etc.)
# ---------------------------------------------------------------------------

P = "nws:45.40,-121.57:precip_in"


def test_sum_window_tamanawas_example():
    # docs/01 §3 example (b): 72-h accumulated precip >= 1.0
    pred = {"feed": P, "agg": "sum", "window_h": 72, "op": ">=", "value": 1.0}
    validate_predicate(pred)
    result = ev(pred, windows={(P, 72): [0.5, 0.7, 0.4]})
    assert result.state is True
    assert result.inputs == {P: pytest.approx(1.6)}
    assert ev(pred, windows={(P, 72): [0.2, 0.3]}).state is False


@pytest.mark.parametrize(
    ("agg", "series", "expected_value"),
    [("sum", [1.0, 2.0, 3.0], 6.0), ("min", [3.0, 1.0, 2.0], 1.0), ("max", [3.0, 1.0, 2.0], 3.0)],
)
def test_agg_functions(agg, series, expected_value):
    pred = {"feed": P, "agg": agg, "window_h": 24, "op": "=", "value": expected_value}
    assert ev(pred, windows={(P, 24): series}).state is True


def test_empty_or_missing_window_is_unknown():
    pred = {"feed": P, "agg": "sum", "window_h": 72, "op": ">=", "value": 1.0}
    assert ev(pred, windows={}).state is None
    assert ev(pred, windows={(P, 72): []}).state is None


def test_latest_is_the_default_agg():
    result = ev({"feed": F, "op": "<", "value": 1050}, latest={F: 900.0})
    assert result.state is True


# ---------------------------------------------------------------------------
# composition + Kleene unknown propagation
# ---------------------------------------------------------------------------

T = {"feed": "t", "op": "=", "value": 1}  # true when t=1
U = {"feed": "u", "op": "=", "value": 1}  # u never supplied -> unknown


def known(t: float):
    return {"t": t}


@pytest.mark.parametrize(
    ("pred", "latest", "expected"),
    [
        ({"all": [T, T]}, {"t": 1}, True),
        ({"all": [T, {"feed": "t", "op": "=", "value": 0}]}, {"t": 1}, False),
        ({"all": [T, U]}, {"t": 1}, None),  # unknown propagates through AND
        ({"all": [{"feed": "t", "op": "=", "value": 0}, U]}, {"t": 1}, False),  # False dominates
        ({"any": [T, U]}, {"t": 1}, True),  # True dominates
        ({"any": [{"feed": "t", "op": "=", "value": 0}, U]}, {"t": 1}, None),
        ({"any": [{"feed": "t", "op": "=", "value": 0}] * 2}, {"t": 1}, False),
        ({"not": T}, {"t": 1}, False),
        ({"not": {"feed": "t", "op": "=", "value": 0}}, {"t": 1}, True),
        ({"not": U}, {"t": 1}, None),  # unknown propagates through NOT
        ({"all": [{"any": [U, T]}, {"not": {"feed": "t", "op": "=", "value": 0}}]}, {"t": 1}, True),
        ({"any": [{"all": [T, U]}, {"all": [T, U]}]}, {"t": 1}, None),
    ],
)
def test_composition_and_unknown_propagation(pred, latest, expected):
    validate_predicate(pred)
    assert ev(pred, latest=latest).state is expected


def test_all_children_evaluated_for_the_inputs_snapshot():
    # no short-circuit: even after a False, remaining leaves land in inputs
    pred = {"all": [{"feed": "a", "op": "=", "value": 1}, {"feed": "b", "op": "=", "value": 1}]}
    result = ev(pred, latest={"a": 0, "b": 1})
    assert result.state is False
    assert result.inputs == {"a": 0.0, "b": 1.0}


def test_high_rocks_canonical_predicate():
    # docs/01 §3 example (a)
    temp = "open_meteo:45.44,-122.62:air_temp_f"
    pred = {
        "all": [
            {"feed": F, "op": "<", "value": 1050, "exit_value": 1200},
            {"feed": temp, "op": ">", "value": 75},
        ]
    }
    validate_predicate(pred, is_gate=True)
    assert ev(pred, latest={F: 410, temp: 84}).state is True
    assert ev(pred, latest={F: 410, temp: 60}).state is False
    assert ev(pred, latest={F: 410}).state is None  # temp feed down -> unknown
    assert feeds_referenced(pred) == {F, temp}


# ---------------------------------------------------------------------------
# month windows (seasonal priors), incl. the year boundary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rng", "month", "expected"),
    [
        ([7, 9], 7, True),
        ([7, 9], 8, True),
        ([7, 9], 9, True),
        ([7, 9], 6, False),
        ([7, 9], 10, False),
        ([11, 2], 11, True),  # wraps the year boundary
        ([11, 2], 12, True),
        ([11, 2], 1, True),
        ([11, 2], 2, True),
        ([11, 2], 3, False),
        ([11, 2], 10, False),
        ([4, 4], 4, True),  # single-month window
        ([4, 4], 5, False),
        ([1, 12], 6, True),  # all-year
    ],
)
def test_month_windows(rng, month, expected):
    pred = {"month": rng}
    validate_predicate(pred)
    now = dt.datetime(2026, month, 15, tzinfo=dt.UTC)
    result = ev(pred, now=now)
    assert result.state is expected
    assert result.inputs == {"month": month}


def test_month_composes_with_feeds():
    pred = {"all": [{"month": [7, 9]}, {"feed": F, "op": "<", "value": 1050}]}
    assert ev(pred, latest={F: 900}, now=dt.datetime(2026, 8, 1, tzinfo=dt.UTC)).state is True
    assert ev(pred, latest={F: 900}, now=dt.datetime(2026, 3, 1, tzinfo=dt.UTC)).state is False
    # out-of-season is decisively False even when the feed is unknown
    assert ev(pred, latest={}, now=dt.datetime(2026, 3, 1, tzinfo=dt.UTC)).state is False


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "not a dict",
        {},
        {"bogus": 1},
        {"all": []},  # empty composite
        {"all": "nope"},
        {"all": [{"feed": F, "op": "<", "value": 1}], "any": []},  # two keys
        {"not": {"feed": F, "op": "<", "value": 1}, "all": []},
        {"feed": "", "op": "<", "value": 1},
        {"feed": F, "op": "~", "value": 1},
        {"feed": F, "op": "<", "value": "high"},
        {"feed": F, "op": "<", "value": True},  # bools are not numbers
        {"feed": F, "op": "between", "value": 5},
        {"feed": F, "op": "between", "value": [2, 1]},  # lo > hi
        {"feed": F, "op": "between", "value": [1]},
        {"feed": F, "op": "<", "value": 1, "agg": "avg"},
        {"feed": F, "op": "<", "value": 1, "agg": "sum"},  # window_h required
        {"feed": F, "op": "<", "value": 1, "agg": "sum", "window_h": 0},
        {"feed": F, "op": "<", "value": 1, "agg": "sum", "window_h": 1.5},
        {"feed": F, "op": "<", "value": 1, "window_h": 72},  # window_h with latest
        {"feed": F, "op": "=", "value": 1, "exit_value": 2},  # hysteresis needs an ordered op
        {"feed": F, "op": "between", "value": [0, 1], "exit_value": 2},
        {"feed": F, "op": "<", "value": 1, "exit_value": "x"},
        {"feed": F, "op": "<", "value": 1, "typo": 9},
        {"month": [0, 5]},
        {"month": [1, 13]},
        {"month": [1]},
        {"month": [1.5, 2]},
        {"month": [1, 2], "feed": F},
        {"all": [{"feed": F, "op": "<", "value": 1}, {"nope": 1}]},  # nested error
    ],
)
def test_validation_rejects(bad):
    with pytest.raises(DSLError):
        validate_predicate(bad)


def test_canonical_docs_predicates_validate():
    # docs/01 §3 examples (a)-(d)
    validate_predicate(
        {
            "all": [
                {"feed": "usgs_nwis:14210000:00060", "op": "<", "value": 1050, "exit_value": 1200},
                {"feed": "open_meteo:45.44,-122.62:air_temp_f", "op": ">", "value": 75},
            ]
        },
        is_gate=True,
    )
    validate_predicate(
        {"feed": "nws:45.40,-121.57:precip_in", "agg": "sum", "window_h": 72,
         "op": ">=", "value": 1.0}
    )
    validate_predicate(
        {
            "all": [
                {"feed": "noaa_coops:haystack_rock:tide_pred_ft_mllw", "op": "<=", "value": 0.0},
                {"feed": "astro:45.88,-123.97:is_daylight", "op": "=", "value": 1},
            ]
        }
    )
    validate_predicate(
        {
            "all": [
                {"feed": "snotel:mt_hood:snow_depth_in", "op": ">=", "value": 30},
                {"feed": "nws:45.33,-121.71:precip_in", "agg": "sum", "window_h": 24,
                 "op": "<", "value": 1.5},
                {"feed": "nwac:mt_hood:danger_level", "op": "<=", "value": 2},
            ]
        },
        is_gate=True,
    )


def test_feeds_referenced_walks_the_tree():
    pred = {
        "any": [
            {"not": {"feed": "a:1:x", "op": "<", "value": 1}},
            {"all": [{"feed": "b:2:y", "op": ">", "value": 2}, {"month": [1, 3]}]},
        ]
    }
    assert feeds_referenced(pred) == {"a:1:x", "b:2:y"}
