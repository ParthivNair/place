"""Portland launch polygon + small geodesic helpers shared by the ingest loaders.

The 90-minute drive polygon is approximated at MVP as a 130 km geodesic circle
around downtown Portland (docs/01 §7). Loaders pre-filter with the bounding box
(cheap, and what Overpass/ArcGIS accept) and post-filter with haversine.
"""

from __future__ import annotations

import math
from typing import NamedTuple

PORTLAND_LAT = 45.512
PORTLAND_LNG = -122.658
RADIUS_KM = 130.0

_EARTH_R_M = 6_371_008.8


class BBox(NamedTuple):
    south: float
    west: float
    north: float
    east: float


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in meters."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_R_M * math.asin(math.sqrt(a))


def portland_bbox(radius_km: float = RADIUS_KM) -> BBox:
    """Bounding box circumscribing the launch circle."""
    dlat = radius_km / 111.32
    dlng = radius_km / (111.32 * math.cos(math.radians(PORTLAND_LAT)))
    return BBox(
        south=PORTLAND_LAT - dlat,
        west=PORTLAND_LNG - dlng,
        north=PORTLAND_LAT + dlat,
        east=PORTLAND_LNG + dlng,
    )


def in_polygon(lat: float, lng: float, radius_km: float = RADIUS_KM) -> bool:
    """True when the point falls inside the launch circle."""
    return haversine_m(PORTLAND_LAT, PORTLAND_LNG, lat, lng) <= radius_km * 1000.0
