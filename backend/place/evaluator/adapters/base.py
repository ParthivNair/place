"""Feed-adapter interface — the contract between the evaluator sweep and the
concrete adapter modules (usgs_nwis.py, open_meteo.py, noaa_coops.py,
snotel.py, nwac.py, airnow.py, sunmoon.py).

CONTRACT (binding for every concrete adapter module):

1.  One FeedAdapter instance serves exactly one feeds.id (e.g.
    ``usgs_nwis:14210000:00060``). A provider that returns several parameters
    per HTTP call still exposes one adapter per feed id; share transport
    internally. Module-level ``fetch(...)/parse(...)`` helpers (as the
    concrete modules already provide) are fine — the class is the uniform
    wrapper the sweep consumes.

2.  Each concrete adapter *module* must expose a factory::

        def build(feed_row: Mapping[str, Any], settings: Settings) -> FeedAdapter

    ``feed_row`` is a mapping of the feeds-table row (keys: id, provider,
    station_ref, parameter, unit, poll_interval). The registry
    (place.evaluator.registry) maps the feed's provider to a module and calls
    ``build``. Raise ``place.config.MissingCredential`` from ``build`` (or
    ``fetch``) when a required key is absent — the sweep logs and skips the
    feed; it never fakes data. A module without ``build`` is skipped with a
    log line (not an error) so components can land independently.

3.  ``FeedAdapter.fetch()`` is async, makes the real network call, and
    returns one or more Reading objects. It must:
      - be side-effect free with respect to the database (the sweep owns all
        writes: feed_readings, feeds.last_value, feed_health);
      - use timezone-aware ``observed_at`` values taken from the API payload,
        never from ``now()`` — tide predictions may be future-dated;
      - return values already converted to the feed's declared unit;
      - raise AdapterError (or let httpx/tenacity exceptions escape) on
        failure. The sweep isolates adapters (docs/04 §4 rule 4): one adapter
        throwing never aborts the run; failures land in feed_health and three
        consecutive failures fire an alert.
      - It may return readings for sibling feed ids (same provider call);
        the sweep stores whatever comes back, keyed by Reading.feed_id.

4.  ``cadence`` is the poll interval from the docs/04 §4 table (see
    place.evaluator.registry.CADENCES). Readings older than 2x cadence are
    treated as unknown by the evaluator (rule 1) — adapters need not enforce
    this.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class Reading:
    """One observed (or predicted) value of a named external feed.

    `feed_id` follows the docs/01 `feeds.id` convention:
    ``<provider>:<station_ref>:<parameter>`` — e.g. ``usgs_nwis:14210000:00060``,
    ``open_meteo:45.45,-121.65:air_temp_f``, ``noaa_coops:9437540:tide_pred_ft_mllw``,
    ``snotel:651:swe_in``, ``nwac:mt_hood:danger_level``, ``airnow:portland:aqi``,
    ``astro:45.45,-121.65:is_daylight``.

    `observed_at` is always taken from the API payload (or, for local astro
    computation, the caller-supplied instant) — never from ``now()``.
    """

    feed_id: str
    value: float
    observed_at: datetime  # tz-aware
    unit: str | None = None

    @property
    def provider(self) -> str:
        return self.feed_id.split(":", 1)[0]

    @property
    def station_ref(self) -> str:
        return self.feed_id.split(":")[1] if self.feed_id.count(":") >= 2 else ""

    @property
    def parameter(self) -> str:
        return self.feed_id.rsplit(":", 1)[-1]


class AdapterError(RuntimeError):
    """A feed adapter failed after retries; the run must isolate it (docs/04 §4 rule 4)."""


def make_feed_id(provider: str, station_ref: str, parameter: str) -> str:
    return f"{provider}:{station_ref}:{parameter}"


class FeedAdapter(ABC):
    """One live data feed: identity + cadence + an async fetch. See the
    module docstring for the full contract."""

    def __init__(
        self,
        feed_id: str,
        *,
        unit: str,
        station_ref: str | None = None,
        cadence: timedelta | None = None,
    ) -> None:
        # local import: registry imports nothing from this module at runtime,
        # but keep the load order dependency-free anyway.
        from place.evaluator import registry

        self.feed_id = feed_id
        self.provider = feed_id.split(":", 1)[0]
        self.parameter = feed_id.rsplit(":", 1)[-1]
        self.station_ref = station_ref if station_ref is not None else (
            feed_id.split(":")[1] if feed_id.count(":") >= 2 else None
        )
        self.unit = unit
        self.cadence = cadence if cadence is not None else registry.cadence_for(self.provider)

    @abstractmethod
    async def fetch(self) -> Sequence[Reading]:
        """Fetch fresh readings for this feed (see the module-level contract)."""
        raise NotImplementedError

    def feed_row(self) -> dict[str, object]:
        """Column values for an idempotent upsert into the feeds table."""
        return {
            "id": self.feed_id,
            "provider": self.provider,
            "station_ref": self.station_ref,
            "parameter": self.parameter,
            "unit": self.unit,
            "poll_interval": self.cadence,
        }

    def __repr__(self) -> str:  # pragma: no cover — debugging nicety
        return f"<{type(self).__name__} {self.feed_id} every {self.cadence}>"
