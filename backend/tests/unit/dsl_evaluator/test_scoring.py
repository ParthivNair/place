"""Scoring math pinned to the worked numbers in docs/01 §5 and the
three-factor now_score with hazard kill switches (docs/01 §7 Q1, docs/04 §4)."""

from __future__ import annotations

import datetime as dt

import pytest

from place import scoring

NOW = dt.datetime(2026, 7, 3, 12, 0, tzinfo=dt.UTC)


def days(n: float) -> dt.timedelta:
    return dt.timedelta(days=n)


# ---------------------------------------------------------------------------
# source-type priors (docs table: p0 / L0)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stype", "p0", "l0"),
    [
        ("llm_extracted", 0.35, -0.62),
        ("user_reported", 0.55, 0.20),
        ("sensor_derived", 0.90, 2.20),
        ("founder_verified", 0.95, 2.94),
    ],
)
def test_source_type_priors(stype, p0, l0):
    L = scoring.prior_log_odds(stype)
    assert L == pytest.approx(l0, abs=0.005)
    assert scoring.sigmoid(L) == pytest.approx(p0, abs=1e-12)


def test_unknown_source_type_raises():
    with pytest.raises(ValueError):
        scoring.prior_log_odds("astrology")


# ---------------------------------------------------------------------------
# corroboration: +0.5 nats per independent domain, capped at +1.5
# docs worked chain: 0.35 -> 0.47 -> 0.59
# ---------------------------------------------------------------------------


def test_corroboration_worked_chain():
    one_source = scoring.initial_log_odds("llm_extracted", 0)
    assert scoring.sigmoid(one_source) == pytest.approx(0.35, abs=0.005)

    two_sources = scoring.initial_log_odds("llm_extracted", 1)
    assert two_sources == pytest.approx(-0.12, abs=0.005)
    assert scoring.sigmoid(two_sources) == pytest.approx(0.47, abs=0.005)

    three_sources = scoring.initial_log_odds("llm_extracted", 2)
    assert three_sources == pytest.approx(0.38, abs=0.005)
    assert scoring.sigmoid(three_sources) == pytest.approx(0.59, abs=0.005)

    # two independent extractions clear the 0.45 publish bar; one never does
    assert scoring.sigmoid(two_sources) >= 0.45
    assert scoring.sigmoid(one_source) < 0.45


def test_corroboration_cap_at_three():
    assert scoring.corroboration_boost(0) == 0.0
    assert scoring.corroboration_boost(3) == 1.5
    assert scoring.corroboration_boost(4) == 1.5  # capped
    assert scoring.corroboration_boost(100) == 1.5
    with pytest.raises(ValueError):
        scoring.corroboration_boost(-1)


# ---------------------------------------------------------------------------
# verification updates (sensitivity .90 / specificity .80, power x1.25)
# docs lifecycle: L=-0.12 --founder confirm--> +1.76 (conf 0.85)
#                 --unweighted refute--> -0.32
# ---------------------------------------------------------------------------


def test_verdict_log_likelihood_ratios_match_docs():
    assert scoring.CONFIRM_LOG_LR == pytest.approx(1.50, abs=0.005)
    assert scoring.REFUTE_LOG_LR == pytest.approx(-2.08, abs=0.005)


def test_docs_lifecycle_confirm_then_refute():
    L = scoring.initial_log_odds("llm_extracted", 1)  # ~= -0.12
    L = scoring.apply_verdict(L, "confirm", power_verifier=True)
    assert L == pytest.approx(1.76, abs=0.005)
    assert scoring.sigmoid(L) == pytest.approx(0.85, abs=0.005)

    L = scoring.apply_verdict(L, "refute")  # unweighted refute after channel shift
    assert L == pytest.approx(-0.32, abs=0.005)
    # back below the 0.45 publish bar: pulled from serving until re-verified
    assert scoring.sigmoid(L) < 0.45


def test_changed_verdict_leaves_log_odds_untouched():
    assert scoring.apply_verdict(1.23, "changed") == 1.23
    assert scoring.apply_verdict(1.23, "changed", power_verifier=True) == 1.23


def test_unknown_verdict_raises():
    with pytest.raises(ValueError):
        scoring.apply_verdict(0.0, "maybe")


# ---------------------------------------------------------------------------
# decay: confidence(t) = sigma(L) * exp(-ln2/half_life * dt)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cclass", "half_life"),
    [
        ("geomorphic", 3650),
        ("seasonal_bio", 730),
        ("access", 180),
        ("hazard_calibration", 60),
    ],
)
def test_decay_halves_at_the_class_half_life(cclass, half_life):
    assert scoring.decay_factor(cclass, days(0)) == 1.0
    assert scoring.decay_factor(cclass, days(half_life)) == pytest.approx(0.5)
    assert scoring.decay_factor(cclass, days(2 * half_life)) == pytest.approx(0.25)


def test_decay_clamps_future_evidence():
    assert scoring.decay_factor("access", days(-3)) == 1.0


def test_unknown_claim_class_raises():
    with pytest.raises(ValueError):
        scoring.decay_factor("vibes", days(1))


def test_effective_confidence_worked_example():
    # founder-confirmed High Rocks claim, hazard class (60-day half-life)
    L = 1.76
    fresh = scoring.effective_confidence(L, "hazard_calibration", NOW, NOW)
    assert fresh == pytest.approx(scoring.sigmoid(1.76))
    assert fresh == pytest.approx(0.85, abs=0.005)

    one_half_life = scoring.effective_confidence(
        L, "hazard_calibration", NOW - days(60), NOW
    )
    assert one_half_life == pytest.approx(0.5 * scoring.sigmoid(1.76))


def test_decay_tends_to_unknown_never_false():
    """Decay multiplies the probability, not the log-odds: an unrefreshed
    claim drifts toward 0 (unknown), while its log-odds state is untouched."""
    L = 2.0
    conf = scoring.effective_confidence(L, "hazard_calibration", NOW - days(3650), NOW)
    assert 0.0 < conf < 1e-15
    # the underlying belief state did not move toward "false"
    assert scoring.sigmoid(L) == pytest.approx(0.88, abs=0.005)


def test_verification_resets_the_decay_clock_semantics():
    # one Sunday tap beats ten stale sources: refreshed evidence removes decay
    L = scoring.initial_log_odds("llm_extracted", 1)
    stale = scoring.effective_confidence(L, "hazard_calibration", NOW - days(120), NOW)
    confirmed = scoring.apply_verdict(L, "confirm", power_verifier=True)
    refreshed = scoring.effective_confidence(confirmed, "hazard_calibration", NOW, NOW)
    assert refreshed > 4 * stale


# ---------------------------------------------------------------------------
# now_score: base_quality x active multipliers x decayed top-claim confidence,
# with both hazard kill switches
# ---------------------------------------------------------------------------


def test_now_score_worked_example_high_rocks():
    # base 0.8, satisfied gate window multiplier 2.0, seasonal prior 1.2,
    # founder-confirmed claim at L=+1.76 (fresh)
    conf = scoring.effective_confidence(1.76, "hazard_calibration", NOW, NOW)
    score = scoring.now_score(0.8, [2.0, 1.2], conf, hazard_class=True)
    assert score == pytest.approx(0.8 * 2.0 * 1.2 * scoring.sigmoid(1.76))
    assert score == pytest.approx(1.638, abs=0.01)


def test_now_score_three_factor_shape():
    assert scoring.now_score(0.7, [1.8], 0.59) == pytest.approx(0.7 * 1.8 * 0.59)
    # no satisfied windows: multiplier product is 1.0
    assert scoring.now_score(0.7, [], 0.59) == pytest.approx(0.7 * 0.59)


def test_kill_switch_unsatisfied_gate_zeroes():
    conf = 0.99
    assert scoring.now_score(0.9, [2.0], conf, gates_satisfied=False) == 0.0
    # unknown gate state counts as unsatisfied (state IS DISTINCT FROM true):
    # the caller maps unknown -> gates_satisfied=False; the score is zero either way
    assert scoring.now_score(0.9, [2.0], conf, gates_satisfied=False, hazard_class=True) == 0.0


def test_kill_switch_missing_recent_confirm_zeroes_hazard_only():
    conf = 0.99
    assert scoring.now_score(0.9, [2.0], conf, hazard_class=True, recent_confirm=False) == 0.0
    # a non-hazard affordance is untouched by the verification prong
    assert scoring.now_score(0.9, [2.0], conf, hazard_class=False, recent_confirm=False) == (
        pytest.approx(0.9 * 2.0 * conf)
    )


def test_kill_switches_are_multiplicative_not_penalties():
    # both prongs lapsed: still exactly zero, not merely small
    assert scoring.now_score(
        1.0, [5.0], 1.0, gates_satisfied=False, hazard_class=True, recent_confirm=False
    ) == 0.0


def test_claimless_edge_floors_to_zero():
    assert scoring.now_score(0.9, [2.0], None) == 0.0


def test_unverified_cannot_outrank_verified():
    # same base and windows: the confidence factor orders them
    unverified = scoring.now_score(0.8, [2.0], scoring.sigmoid(-0.12))
    verified = scoring.now_score(0.8, [2.0], scoring.sigmoid(1.76))
    assert verified > unverified


def test_multiplier_validation():
    with pytest.raises(ValueError):
        scoring.now_score(0.8, [0.0], 0.5)
    assert scoring.multiplier_product([2.0, 1.8]) == pytest.approx(3.6)


def test_has_recent_confirm_window():
    assert scoring.has_recent_confirm(NOW - days(59), NOW) is True
    assert scoring.has_recent_confirm(NOW - days(61), NOW) is False
    assert scoring.has_recent_confirm(None, NOW) is False
    assert scoring.HAZARD_CONFIRM_WINDOW_DAYS == 60
