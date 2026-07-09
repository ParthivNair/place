"""Feed registry: per-provider poll cadences (docs/04 §4 table), the
stale-as-unknown rule (docs/04 §4 rule 1), and adapter construction.

The cadence table here is the authority; ``feeds.poll_interval`` mirrors it
for observability but is not read back by the sweep.
"""

from __future__ import annotations

import datetime as dt
import importlib
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from place.config import MissingCredential, Settings

if TYPE_CHECKING:  # pragma: no cover
    from place.evaluator.adapters.base import FeedAdapter

log = logging.getLogger(__name__)

__all__ = [
    "CADENCES",
    "DEFAULT_CADENCE",
    "STALENESS_FACTOR",
    "STALENESS_OVERRIDES",
    "SWEEP_CADENCE",
    "SkippedFeed",
    "cadence_for",
    "is_stale",
    "load_adapters",
    "provider_of",
    "staleness_cutoff",
]

# The docs/04 §4 evaluation/materialization sweep interval. Single authority:
# the run.py loop default, the astro pseudo-feed cadence, and the pack
# publisher's conditions expires_at horizon (2x this, rule 1) all derive from
# it, so the sweep and the artifacts it publishes can never disagree about
# what "one sweep late" means.
SWEEP_CADENCE = dt.timedelta(minutes=30)

# docs/04 §4 cadence table. `nws` grid-point precip is served by the
# open_meteo adapter module (the docs pair "NWS / Open-Meteo" at 1 h).
# `astro` is a free local computation emitting *instantaneous* values
# (is_daylight, sun_elevation at fetch time), so it must be recomputed every
# sweep — the docs' "daily precompute" refers to the day's event times, not
# to serving a frozen midday snapshot for 24 h (a 24 h cadence would let a
# noon `is_daylight=1` satisfy nighttime windows).
CADENCES: dict[str, dt.timedelta] = {
    "usgs_nwis": dt.timedelta(minutes=15),
    "nws": dt.timedelta(hours=1),
    "open_meteo": dt.timedelta(hours=1),
    "noaa_coops": dt.timedelta(hours=6),
    "snotel": dt.timedelta(hours=6),
    "nwac": dt.timedelta(hours=6),
    "airnow": dt.timedelta(hours=1),
    "astro": SWEEP_CADENCE,  # = the sweep interval
}

# Unknown providers poll (and go stale) on a conservative 1-hour cadence
# rather than crashing the sweep on a novel feed id.
DEFAULT_CADENCE = dt.timedelta(hours=1)

# Rule 1: a reading older than 2x its feed's cadence is shown as unknown.
STALENESS_FACTOR = 2

# Staleness overrides for feeds whose *data* cadence is coarser than their
# poll cadence: SNOTEL values are daily, anchored at station-local 00:00, and
# NWAC forecasts carry one start_date per day — under the 2x-poll-cadence rule
# (12 h) both would flip to unknown every afternoon and flap the snow gate
# daily all season. A daily value legitimately describes its whole day; 36 h
# tolerates that (00:00 value valid through noon next day) while still going
# unknown within a day and a half of a dead feed. Sub-daily feeds keep the
# 2x-poll-cadence rule.
STALENESS_OVERRIDES: dict[str, dt.timedelta] = {
    "snotel": dt.timedelta(hours=36),
    "nwac": dt.timedelta(hours=36),
}

_ADAPTER_MODULES: dict[str, str] = {
    "usgs_nwis": "usgs_nwis",
    "open_meteo": "open_meteo",
    "nws": "open_meteo",
    "noaa_coops": "noaa_coops",
    "snotel": "snotel",
    "nwac": "nwac",
    "airnow": "airnow",
    "astro": "sunmoon",
}


def provider_of(feed_id: str) -> str:
    """'usgs_nwis:14210000:00060' -> 'usgs_nwis'."""
    return feed_id.split(":", 1)[0]


def cadence_for(provider_or_feed_id: str) -> dt.timedelta:
    provider = (
        provider_of(provider_or_feed_id) if ":" in provider_or_feed_id else provider_or_feed_id
    )
    return CADENCES.get(provider, DEFAULT_CADENCE)


def staleness_cutoff(provider_or_feed_id: str) -> dt.timedelta:
    provider = (
        provider_of(provider_or_feed_id) if ":" in provider_or_feed_id else provider_or_feed_id
    )
    override = STALENESS_OVERRIDES.get(provider)
    if override is not None:
        return override
    return STALENESS_FACTOR * cadence_for(provider_or_feed_id)


def is_stale(
    observed_at: dt.datetime, provider_or_feed_id: str, now: dt.datetime
) -> bool:
    """True when a reading is too old to show as current (docs/04 §4 rule 1).

    Future-dated readings (tide *predictions*) are never stale.
    """
    return now - observed_at > staleness_cutoff(provider_or_feed_id)


@dataclass(frozen=True)
class SkippedFeed:
    feed_id: str
    reason: str


def load_adapters(
    feed_rows: Iterable[Mapping[str, Any]], settings: Settings
) -> tuple[list[FeedAdapter], list[SkippedFeed]]:
    """Build one adapter per feeds-table row via each module's ``build``.

    Skips (with a log line, never an abort): unknown providers, adapter
    modules not yet implemented or lacking ``build``, and key-gated adapters
    whose credential is absent (MissingCredential).
    """
    adapters: list[FeedAdapter] = []
    skipped: list[SkippedFeed] = []
    for row in feed_rows:
        feed_id = row["id"]
        provider = row.get("provider") or provider_of(feed_id)
        module_name = _ADAPTER_MODULES.get(provider)
        if module_name is None:
            skipped.append(SkippedFeed(feed_id, f"unknown provider {provider!r}"))
            log.warning("feed %s skipped: unknown provider %r", feed_id, provider)
            continue
        try:
            module = importlib.import_module(f"place.evaluator.adapters.{module_name}")
        except ImportError as exc:
            skipped.append(SkippedFeed(feed_id, f"adapter module unavailable: {exc}"))
            log.warning("feed %s skipped: adapter module %s unavailable: %s",
                        feed_id, module_name, exc)
            continue
        build = getattr(module, "build", None)
        if build is None:
            skipped.append(SkippedFeed(feed_id, f"adapter {module_name} has no build()"))
            log.warning("feed %s skipped: adapter %s does not expose build(feed_row, settings)",
                        feed_id, module_name)
            continue
        try:
            adapters.append(build(row, settings))
        except MissingCredential as exc:
            skipped.append(SkippedFeed(feed_id, str(exc)))
            log.info("feed %s skipped (key-gated): %s", feed_id, exc)
    return adapters, skipped
