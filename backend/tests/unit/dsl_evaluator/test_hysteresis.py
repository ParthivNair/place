"""Hysteresis (exit_value) in both directions, and the safe-side rule for
is_gate windows (docs/01 §3)."""

from __future__ import annotations

import datetime as dt

import pytest

from place.dsl import DSLError, StaticProvider, evaluate, validate_predicate

NOW = dt.datetime(2026, 7, 3, 12, 0, tzinfo=dt.UTC)
FLOW = "usgs_nwis:14210000:00060"
SNOW = "snotel:mt_hood:snow_depth_in"

# High Rocks: conservative entry < 1050, earned hard bound 1200
LT_BAND = {"feed": FLOW, "op": "<", "value": 1050, "exit_value": 1200}
# Snow depth: entry >= 30, stays open down to the exit bound 24
GT_BAND = {"feed": SNOW, "op": ">=", "value": 30, "exit_value": 24}


def ev(pred, reading, prev_state):
    feed = pred["feed"]
    provider = StaticProvider(latest_values={feed: reading})
    return evaluate(pred, provider, now=NOW, prev_state=prev_state).state


# --- "less-than" direction (entry below, band up to the exit bound) ---------


@pytest.mark.parametrize(
    ("reading", "prev", "expected"),
    [
        (1000, None, True),    # entry satisfied, no prior state needed
        (1000, False, True),
        (1000, True, True),
        (1100, None, False),   # in the band but window wasn't open: entry required
        (1100, False, False),  # (safe side: unknown/false prior never holds a gate open)
        (1100, True, True),    # anti-flap: open window stays open inside the band
        (1199.9, True, True),
        (1200, True, False),   # crossing the exit bound closes it — exactly at the bound
        (1250, True, False),   # never held open past the hard bound
        (1049.9, True, True),
    ],
)
def test_hysteresis_less_than(reading, prev, expected):
    assert ev(LT_BAND, reading, prev) is expected


# --- "greater-than" direction (entry above, band down to the exit bound) ----


@pytest.mark.parametrize(
    ("reading", "prev", "expected"),
    [
        (31, None, True),
        (31, False, True),
        (25, None, False),   # in the band, but no prior open state
        (25, False, False),
        (25, True, True),    # stays open down to the bound
        (24, True, True),    # ">=" exit comparison: 24 >= 24 still holds
        (23.9, True, False),  # crossed below the bound: closed
        (23, False, False),
    ],
)
def test_hysteresis_greater_than(reading, prev, expected):
    assert ev(GT_BAND, reading, prev) is expected


def test_unknown_prior_state_falls_back_to_entry_threshold():
    """Safe side: a window whose previous state is unknown (None) must
    re-earn the entry threshold; hysteresis never opens from unknown."""
    assert ev(LT_BAND, 1100, None) is False
    assert ev(GT_BAND, 25, None) is False


def test_hysteresis_inside_composition_uses_window_state():
    temp = "open_meteo:45.44,-122.62:air_temp_f"
    pred = {"all": [LT_BAND, {"feed": temp, "op": ">", "value": 75}]}

    def ev2(flow, temp_f, prev):
        provider = StaticProvider(latest_values={FLOW: flow, temp: temp_f})
        return evaluate(pred, provider, now=NOW, prev_state=prev).state

    assert ev2(1100, 80, True) is True    # band holds while the window was open
    assert ev2(1100, 70, True) is False   # the other conjunct fails regardless
    assert ev2(1100, 80, False) is False  # closed window: entry required again
    assert ev2(1200, 80, True) is False   # hard bound closes the gate


def test_missing_reading_is_unknown_even_with_hysteresis():
    provider = StaticProvider(latest_values={})
    assert evaluate(LT_BAND, provider, now=NOW, prev_state=True).state is None


# --- safe-side validation ----------------------------------------------------


def test_inverted_band_rejected_lt():
    with pytest.raises(DSLError, match="inverted"):
        validate_predicate({"feed": FLOW, "op": "<", "value": 1200, "exit_value": 1050})


def test_inverted_band_rejected_gt():
    with pytest.raises(DSLError, match="inverted"):
        validate_predicate({"feed": SNOW, "op": ">=", "value": 24, "exit_value": 30})


def test_inverted_band_on_gate_names_the_safe_side_rule():
    with pytest.raises(DSLError, match="safe-side"):
        validate_predicate(
            {"feed": FLOW, "op": "<", "value": 1200, "exit_value": 1050}, is_gate=True
        )


def test_degenerate_band_is_allowed():
    # exit_value == value: hysteresis disabled, not an error
    validate_predicate({"feed": FLOW, "op": "<", "value": 1050, "exit_value": 1050})


def test_gate_band_direction_accepts_the_canonical_example():
    validate_predicate(
        {"feed": FLOW, "op": "<", "value": 1050, "exit_value": 1200}, is_gate=True
    )
