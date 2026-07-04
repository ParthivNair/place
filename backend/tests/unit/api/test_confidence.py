"""Confidence math against the worked numbers in docs/01 section 5."""

from __future__ import annotations

import datetime as dt

import pytest

from place.api import confidence as conf


def test_source_priors_sigmoid() -> None:
    # priors table: llm_extracted p0=0.35 (L=-0.62), founder 0.95 (L=+2.94)
    assert conf.sigmoid(-0.62) == pytest.approx(0.35, abs=0.01)
    assert conf.sigmoid(2.94) == pytest.approx(0.95, abs=0.01)


def test_two_source_corroboration_example() -> None:
    # one reddit extraction -0.62 + one corroborator +0.5 = -0.12 -> 0.47
    assert conf.sigmoid(-0.12) == pytest.approx(0.47, abs=0.01)


def test_effective_confidence_fresh_is_sigmoid() -> None:
    now = dt.datetime.now(dt.UTC)
    c = conf.effective_confidence(-0.12, "access", now, now)
    assert c == pytest.approx(conf.sigmoid(-0.12), abs=1e-9)


def test_effective_confidence_halves_at_half_life() -> None:
    now = dt.datetime.now(dt.UTC)
    then = now - dt.timedelta(days=60)
    c = conf.effective_confidence(1.76, "hazard_calibration", then, now)
    assert c == pytest.approx(conf.sigmoid(1.76) * 0.5, rel=1e-6)


def test_lifecycle_founder_confirm() -> None:
    # docs/01 section 5: L = -0.12 + 1.25 x 1.50 = +1.76, confidence 0.85
    delta = conf.verdict_delta("confirm", power_verifier=True)
    assert delta == pytest.approx(1.875, abs=0.01)  # exact: 1.25 * ln(0.90/0.20)
    new_l = -0.12 + delta
    assert conf.sigmoid(new_l) == pytest.approx(0.85, abs=0.01)


def test_refute_delta_unweighted() -> None:
    assert conf.verdict_delta("refute", power_verifier=False) == pytest.approx(-2.08, abs=0.01)


def test_decay_never_negative_age() -> None:
    now = dt.datetime.now(dt.UTC)
    future = now + dt.timedelta(days=5)  # clock skew: never boosts
    c = conf.effective_confidence(0.0, "access", future, now)
    assert c == pytest.approx(0.5)
