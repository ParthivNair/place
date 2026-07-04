"""Scoring math (docs/01-EXPERIENCE-GRAPH.md §5 and §7 Q1). Pure functions.

Confidence model::

    confidence(t) = sigma(L) * exp(-lambda_class * dt)
    sigma(L) = 1 / (1 + e^-L),  lambda_class = ln 2 / half_life_class

Decay multiplies the *probability*, never the log-odds: an unrefreshed claim
tends toward "unknown", not toward "false".

Constants are computed from first principles (logit of the source-type prior
probabilities; log likelihood-ratios from sensitivity 0.90 / specificity
0.80). The docs print them rounded to 2 dp (-0.62, +1.50, -2.08, ...); the
exact values reproduce every worked number in docs/01 §5 to 2 dp, and the
tests pin that.

now_score (docs/01 §7 Q1, three-factor)::

    now_score = base_quality
              * product(multipliers of currently-satisfied windows)
              * decayed top-claim confidence

with two multiplicative *kill switches* for hazard serving (docs/04 §4):
an unsatisfied (or unknown) is_gate window zeroes the score, and so does a
hazard-class affordance lacking a recent CONFIRMS verification.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Iterable

__all__ = [
    "CONFIRM_LOG_LR",
    "CORROBORATION_CAP_NATS",
    "CORROBORATION_NATS",
    "HALF_LIFE_DAYS",
    "HAZARD_CONFIRM_WINDOW_DAYS",
    "POWER_VERIFIER_WEIGHT",
    "REFUTE_LOG_LR",
    "SERVING_CONFIDENCE_BAR",
    "SOURCE_PRIORS",
    "apply_verdict",
    "corroboration_boost",
    "decay_factor",
    "effective_confidence",
    "has_recent_confirm",
    "initial_log_odds",
    "logit",
    "multiplier_product",
    "now_score",
    "prior_log_odds",
    "sigmoid",
]

# --- source-type priors (docs/01 §5 table; stored as p0, used as logit(p0)) ---
SOURCE_PRIORS: dict[str, float] = {
    "llm_extracted": 0.35,
    "user_reported": 0.55,
    "sensor_derived": 0.90,
    "founder_verified": 0.95,
}

# --- verification updates: noisy test, sensitivity 0.90 / specificity 0.80 ---
CONFIRM_LOG_LR: float = math.log(0.90 / 0.20)  # +1.504...  (docs: +1.50)
REFUTE_LOG_LR: float = math.log(0.10 / 0.80)  # -2.079...  (docs: -2.08)
POWER_VERIFIER_WEIGHT: float = 1.25

# --- corroboration: +0.5 nats per additional independent source_domain ---
CORROBORATION_NATS: float = 0.5
CORROBORATION_CAP_NATS: float = 1.5  # three corroborators

# docs/01 §4 gate 2: top-claim effective confidence must clear this bar to
# serve. Enforced at query time in the good_now materialization (the docs'
# lifecycle: a refute below the bar is "pulled from serving until re-verified").
SERVING_CONFIDENCE_BAR: float = 0.45

# --- per-class decay half-lives (hand-set launch priors, docs/01 §5) ---
HALF_LIFE_DAYS: dict[str, float] = {
    "geomorphic": 3650.0,
    "seasonal_bio": 730.0,
    "access": 180.0,
    "hazard_calibration": 60.0,
}

# Hazard serving gate: a confirm within the hazard_calibration half-life.
HAZARD_CONFIRM_WINDOW_DAYS: float = HALF_LIFE_DAYS["hazard_calibration"]

_SECONDS_PER_DAY = 86400.0


def sigmoid(log_odds: float) -> float:
    """sigma(L) = 1 / (1 + e^-L)."""
    if log_odds >= 0:
        return 1.0 / (1.0 + math.exp(-log_odds))
    # numerically stable for very negative L
    e = math.exp(log_odds)
    return e / (1.0 + e)


def logit(p: float) -> float:
    if not 0.0 < p < 1.0:
        raise ValueError(f"logit requires 0 < p < 1, got {p}")
    return math.log(p / (1.0 - p))


def prior_log_odds(source_type: str) -> float:
    """Initial L for a fresh claim of the given source_type."""
    try:
        return logit(SOURCE_PRIORS[source_type])
    except KeyError:
        raise ValueError(f"unknown source_type {source_type!r}") from None


def corroboration_boost(additional_independent_domains: int) -> float:
    """+0.5 nats per *additional* independent source_domain, capped at +1.5."""
    if additional_independent_domains < 0:
        raise ValueError("corroborator count must be >= 0")
    return min(
        CORROBORATION_NATS * additional_independent_domains, CORROBORATION_CAP_NATS
    )


def initial_log_odds(source_type: str, additional_independent_domains: int = 0) -> float:
    return prior_log_odds(source_type) + corroboration_boost(additional_independent_domains)


def apply_verdict(log_odds: float, verdict: str, *, power_verifier: bool = False) -> float:
    """Bayesian log-odds update for one verification verdict.

    'changed' leaves L untouched — supersession (superseded_by + a spawned
    user_reported claim) is a data operation, not a belief update (docs/01 §5).
    """
    weight = POWER_VERIFIER_WEIGHT if power_verifier else 1.0
    if verdict == "confirm":
        return log_odds + weight * CONFIRM_LOG_LR
    if verdict == "refute":
        return log_odds + weight * REFUTE_LOG_LR
    if verdict == "changed":
        return log_odds
    raise ValueError(f"unknown verdict {verdict!r}")


def decay_factor(claim_class: str, age: dt.timedelta) -> float:
    """exp(-ln2/half_life * age). Future-dated evidence (age < 0) clamps to 1."""
    try:
        half_life = HALF_LIFE_DAYS[claim_class]
    except KeyError:
        raise ValueError(f"unknown claim_class {claim_class!r}") from None
    days = age.total_seconds() / _SECONDS_PER_DAY
    if days <= 0:
        return 1.0
    return math.exp(-math.log(2.0) / half_life * days)


def effective_confidence(
    log_odds: float,
    claim_class: str,
    last_evidence_at: dt.datetime,
    now: dt.datetime,
) -> float:
    """confidence(t) = sigma(L) * exp(-lambda_class * (now - last_evidence_at))."""
    return sigmoid(log_odds) * decay_factor(claim_class, now - last_evidence_at)


def has_recent_confirm(
    last_confirm_at: dt.datetime | None,
    now: dt.datetime,
    *,
    window_days: float = HAZARD_CONFIRM_WINDOW_DAYS,
) -> bool:
    """Hazard gate prong 2: a confirm verification within the class half-life."""
    if last_confirm_at is None:
        return False
    return (now - last_confirm_at).total_seconds() < window_days * _SECONDS_PER_DAY


def multiplier_product(multipliers: Iterable[float]) -> float:
    """Product of the multipliers of currently-satisfied windows (empty -> 1.0)."""
    product = 1.0
    for m in multipliers:
        if m <= 0:
            raise ValueError(f"window multipliers must be > 0, got {m}")
        product *= m
    return product


def now_score(
    base_quality: float,
    active_multipliers: Iterable[float],
    top_claim_confidence: float | None,
    *,
    gates_satisfied: bool = True,
    hazard_class: bool = False,
    recent_confirm: bool = True,
) -> float:
    """Three-factor now_score with the two hazard kill switches (docs/01 §7 Q1).

    - gates_satisfied: every is_gate window has state = True (unknown counts
      as unsatisfied — `state IS DISTINCT FROM true` in Q1). False -> 0.
    - hazard_class + no recent confirm -> 0 (degrade DOWN only, docs/04 §4).
    - top_claim_confidence is the max decayed effective confidence over the
      affordance's published, non-superseded claims; None (claimless edge,
      e.g. mid-supersession) floors to 0.0, never aborts.
    """
    if not gates_satisfied:
        return 0.0
    if hazard_class and not recent_confirm:
        return 0.0
    confidence = 0.0 if top_claim_confidence is None else top_claim_confidence
    return base_quality * multiplier_product(active_multipliers) * confidence
