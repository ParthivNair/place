"""Sun/moon adapter — computed locally with astral, no network (docs/04 §4 table).

Because there is no API payload, the caller supplies the instant `at` the
readings are valid for (the evaluator passes its sweep timestamp); it becomes
`observed_at`, honoring the "never now()" rule at the adapter level and making
the output fully deterministic/testable.

Feed ids use the ``astro`` provider from docs/01 (§3c ``astro:<lat,lng>:is_daylight``;
the build brief's shorthand was ``sunmoon:`` — the docs win):

- ``astro:<ref>:is_daylight``       1.0 / 0.0 at `at`
- ``astro:<ref>:sun_elevation_deg`` solar elevation at `at`
- ``astro:<ref>:daylight_hours``    sunrise->sunset duration for `at`'s local date
- ``astro:<ref>:moon_phase``        0..27.99 (0 new, ~14 full), astral convention
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from astral import Observer, moon
from astral.sun import elevation, sun

from place.config import Settings
from place.evaluator.adapters._http import point_ref
from place.evaluator.adapters.base import FeedAdapter, Reading, make_feed_id

PROVIDER = "astro"

IS_DAYLIGHT = "is_daylight"
SUN_ELEVATION = "sun_elevation_deg"
DAYLIGHT_HOURS = "daylight_hours"
MOON_PHASE = "moon_phase"


async def fetch(lat: float, lng: float, *, at: datetime) -> list[Reading]:
    """Async for interface uniformity with the network adapters; purely local."""
    return compute(lat, lng, at=at)


def compute(lat: float, lng: float, *, at: datetime) -> list[Reading]:
    if at.tzinfo is None:
        raise ValueError("`at` must be timezone-aware")
    at = at.astimezone(UTC)
    ref = point_ref(lat, lng)
    observer = Observer(latitude=lat, longitude=lng)

    def reading(parameter: str, value: float, unit: str | None = None) -> Reading:
        return Reading(
            feed_id=make_feed_id(PROVIDER, ref, parameter),
            value=value,
            observed_at=at,
            unit=unit,
        )

    sun_elev = elevation(observer, at)
    # -0.833° is astral's sunrise/sunset depression (refraction + solar radius),
    # so is_daylight agrees with the sunrise/sunset definition and, unlike a
    # calendar-date sun() lookup, has no UTC date-boundary artifacts.
    readings = [
        reading(SUN_ELEVATION, round(sun_elev, 2), "deg"),
        reading(MOON_PHASE, round(moon.phase(at.date()), 2), "lunation_28"),
        reading(IS_DAYLIGHT, 1.0 if sun_elev > -0.833 else 0.0),
    ]
    # Daylight duration is a property of the observer-local solar day; derive
    # that date from the longitude (15°/h) rather than the UTC calendar date.
    solar_date = (at + timedelta(hours=lng / 15.0)).date()
    try:
        events = sun(observer, date=solar_date, tzinfo=UTC)
    except ValueError:
        # Polar day/night: no sunrise/sunset events. Not reachable in the
        # Portland polygon; is_daylight above still holds.
        return readings
    daylight_h = (events["sunset"] - events["sunrise"]).total_seconds() / 3600
    readings.append(reading(DAYLIGHT_HOURS, round(daylight_h % 24, 2), "h"))
    return readings


class SunMoonAdapter(FeedAdapter):
    """One point's astro feeds, e.g. ``astro:45.45,-121.65:is_daylight``.

    Local computation has no API payload; the wrapper anchors `observed_at`
    at the wall-clock instant the computation is valid for — that instant IS
    the observation, so the never-``now()`` rule is not violated. The pure
    ``compute(..., at=...)`` stays fully deterministic for tests.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        assert self.station_ref is not None
        lat_s, lng_s = self.station_ref.split(",", 1)
        self.lat, self.lng = float(lat_s), float(lng_s)

    async def fetch(self) -> Sequence[Reading]:
        return compute(self.lat, self.lng, at=datetime.now(tz=UTC))


def build(feed_row: Mapping[str, Any], settings: Settings) -> FeedAdapter:  # noqa: ARG001
    return SunMoonAdapter(
        feed_row["id"],
        unit=feed_row["unit"],
        station_ref=feed_row.get("station_ref"),
        cadence=feed_row.get("poll_interval"),
    )
