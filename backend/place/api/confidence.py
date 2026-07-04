"""Claim-confidence math for API serving (docs/01 section 5).

Thin seam over :mod:`place.scoring` (the canonical implementation) — this
module keeps the API-local names/signatures the routes were built against.
Constants are the exact first-principles values (logit / log likelihood
ratios); they reproduce every docs/01 §5 worked number to 2 dp.
"""

from __future__ import annotations

import datetime as dt

from place import scoring

# Per-class decay half-lives (docs/01 section 5 table).
HALF_LIFE_DAYS: dict[str, float] = scoring.HALF_LIFE_DAYS

# Verdict as a noisy test: sensitivity 0.90, specificity 0.80.
LOG_ODDS_CONFIRM = scoring.CONFIRM_LOG_LR  # +1.504... (docs: +1.50)
LOG_ODDS_REFUTE = scoring.REFUTE_LOG_LR  # -2.079... (docs: -2.08)
POWER_VERIFIER_WEIGHT = scoring.POWER_VERIFIER_WEIGHT
USER_REPORTED_PRIOR_L = scoring.prior_log_odds("user_reported")  # logit(0.55)

HAZARD_CONFIRM_WINDOW_DAYS = scoring.HAZARD_CONFIRM_WINDOW_DAYS  # docs/01 §4 rule 3


def sigmoid(x: float) -> float:
    return scoring.sigmoid(x)


def effective_confidence(
    log_odds: float,
    cclass: str,
    last_evidence_at: dt.datetime,
    now: dt.datetime | None = None,
) -> float:
    now = now or dt.datetime.now(dt.UTC)
    return scoring.effective_confidence(float(log_odds), str(cclass), last_evidence_at, now)


def verdict_delta(verdict: str, power_verifier: bool) -> float:
    """Log-odds delta for a confirm/refute verdict ('changed' spawns a claim instead)."""
    if verdict not in ("confirm", "refute"):
        raise KeyError(verdict)
    return scoring.apply_verdict(0.0, verdict, power_verifier=power_verifier)
