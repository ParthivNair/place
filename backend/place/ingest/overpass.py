"""OpenStreetMap skeleton loader (Overpass API).

POSTs a union query to the public interpreter with a polite User-Agent
(GETs against /api/status returned 406 in this environment — POST works).
Tag set per docs/05 Phase 0, with one reality delta: waterfalls in current
OSM are tagged ``waterway=waterfall``; ``natural=waterfall`` is legacy and
returns zero elements in the launch polygon. We query both.

Upserts are idempotent, keyed on the OSM id via the crosswalk
(places.osm_id); node/way/relation id spaces are disambiguated with the
standard 2.4B/3.6B offsets before storage.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import httpx
import tenacity
from sqlalchemy import Connection

from place.config import get_settings
from place.ingest import crosswalk
from place.ingest.geo import PORTLAND_LAT, PORTLAND_LNG, RADIUS_KM, in_polygon

log = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# node ids, way ids, and relation ids overlap; places.osm_id is one bigint.
_WAY_OFFSET = 2_400_000_000
_REL_OFFSET = 3_600_000_000

# (overpass filter, place kind) — docs/05 Phase 0 tag set.
TAG_QUERIES: dict[str, tuple[str, str]] = {
    "waterfall": ('nwr["waterway"="waterfall"]', "waterfall"),
    "waterfall_legacy": ('nwr["natural"="waterfall"]', "waterfall"),
    "hot_spring": ('nwr["natural"="hot_spring"]', "hot_spring"),
    "viewpoint": ('nwr["tourism"="viewpoint"]', "viewpoint"),
    "swimming_area": ('nwr["leisure"="swimming_area"]', "swim_area"),
    "peak": ('nwr["natural"="peak"]', "peak"),
    "hiking": ('relation["route"="hiking"]', "trail"),
}


@dataclass(frozen=True)
class OsmPlace:
    osm_id: int  # offset-encoded
    name: str
    kind: str
    lat: float
    lng: float
    elev_m: int | None


def build_query(
    tags: list[str] | None = None,
    *,
    lat: float = PORTLAND_LAT,
    lng: float = PORTLAND_LNG,
    radius_km: float = RADIUS_KM,
    bbox: tuple[float, float, float, float] | None = None,
) -> str:
    """Union query over the requested tag groups, area-limited.

    ``bbox`` is (south, west, north, east); when given it replaces the
    default around-circle (used by --bbox on the CLI).
    """
    # copy: never mutate a caller-supplied list (appends would accumulate
    # across calls and silently widen later queries)
    keys = list(tags) if tags else list(TAG_QUERIES)
    if "waterfall" in keys and "waterfall_legacy" not in keys:
        keys.append("waterfall_legacy")
    area = (
        f"({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]})"
        if bbox
        else f"(around:{int(radius_km * 1000)},{lat},{lng})"
    )
    unknown = set(keys) - set(TAG_QUERIES)
    if unknown:
        raise ValueError(f"unknown overpass tag groups: {sorted(unknown)}")
    lines = "\n".join(f"  {TAG_QUERIES[k][0]}{area};" for k in keys)
    return f"[out:json][timeout:180];\n(\n{lines}\n);\nout center tags;"


def _encode_osm_id(etype: str, raw_id: int) -> int:
    if etype == "way":
        return raw_id + _WAY_OFFSET
    if etype == "relation":
        return raw_id + _REL_OFFSET
    return raw_id


def _kind_for(tags: dict[str, str], etype: str) -> str | None:
    if tags.get("waterway") == "waterfall" or tags.get("natural") == "waterfall":
        return "waterfall"
    if tags.get("natural") == "hot_spring":
        return "hot_spring"
    if tags.get("tourism") == "viewpoint":
        return "viewpoint"
    if tags.get("leisure") == "swimming_area":
        return "swim_area"
    if tags.get("natural") == "peak":
        return "peak"
    if etype == "relation" and tags.get("route") == "hiking":
        return "trail"
    return None


def _parse_elev_m(tags: dict[str, str]) -> int | None:
    ele = tags.get("ele")
    if not ele:
        return None
    try:
        return round(float(ele.replace("m", "").strip()))
    except ValueError:
        return None


def parse_elements(payload: dict) -> list[OsmPlace]:
    """Overpass JSON -> OsmPlace list. Unnamed elements are skipped — the
    skeleton exists for entity resolution, which needs a name to resolve."""
    out: list[OsmPlace] = []
    for el in payload.get("elements", []):
        tags = el.get("tags") or {}
        name = tags.get("name")
        if not name:
            continue
        kind = _kind_for(tags, el.get("type", "node"))
        if kind is None:
            continue
        if "lat" in el:
            lat, lng = el["lat"], el["lon"]
        elif "center" in el:
            lat, lng = el["center"]["lat"], el["center"]["lon"]
        else:
            continue
        out.append(
            OsmPlace(
                osm_id=_encode_osm_id(el["type"], el["id"]),
                name=name.strip(),
                kind=kind,
                lat=lat,
                lng=lng,
                elev_m=_parse_elev_m(tags),
            )
        )
    return out


def _retryable(exc: BaseException) -> bool:
    """The public interpreter 429s/504s under load; those are worth waiting out."""
    if isinstance(exc, httpx.TransportError):
        return True
    return (
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response.status_code in (429, 502, 503, 504)
    )


@tenacity.retry(
    retry=tenacity.retry_if_exception(_retryable),
    wait=tenacity.wait_exponential(multiplier=5, max=60),
    stop=tenacity.stop_after_attempt(4),
    reraise=True,
)
def fetch(query: str) -> dict:
    settings = get_settings()
    resp = httpx.post(
        OVERPASS_URL,
        data={"data": query},
        headers={"User-Agent": settings.http_user_agent},
        timeout=210.0,
    )
    resp.raise_for_status()
    return resp.json()


def load(
    conn: Connection,
    *,
    limit: int | None = None,
    tags: list[str] | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> dict[str, int]:
    """Fetch + upsert. Returns counters for the CLI summary line."""
    query = build_query(tags, bbox=bbox)
    payload = fetch(query)
    osm_places = parse_elements(payload)
    log.info(
        "overpass: %d elements, %d named+typed",
        len(payload.get("elements", [])),
        len(osm_places),
    )

    created = merged = skipped = 0
    for i, p in enumerate(osm_places):
        if limit is not None and i >= limit:
            break
        if not in_polygon(p.lat, p.lng):
            skipped += 1
            continue
        _, was_created = crosswalk.resolve_place(
            conn,
            name=p.name,
            kind=p.kind,
            lat=p.lat,
            lng=p.lng,
            source_col="osm_id",
            source_id=p.osm_id,
            elev_m=p.elev_m,
        )
        created += was_created
        merged += not was_created
    return {
        "elements": len(payload.get("elements", [])),
        "parsed": len(osm_places),
        "created": created,
        "existing_or_merged": merged,
        "outside_polygon": skipped,
    }


def record_fixture(path: str, tags: list[str] | None = None, max_elements: int = 25) -> None:
    """Dev helper: fetch a real response and truncate it into a test fixture."""
    payload = fetch(build_query(tags))
    payload["elements"] = payload.get("elements", [])[:max_elements]
    with open(path, "w") as f:
        json.dump(payload, f, indent=1)
