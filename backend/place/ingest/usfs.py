"""USFS trailheads loader (FSGeodata / ArcGIS REST, keyless).

Reality note: FSGeodata's EDW ArcGIS catalog has no standalone "trailhead"
service; trailheads live in EDW_InfraRecreationSites_01 (point layer) as
site_subtype = 'TRAILHEAD'. We filter to Mt Hood NF + CRGNSA by managing_org
prefix (Forest Service org codes: 0606xx = Mt Hood NF, 0622xx = Columbia
River Gorge NSA) inside the launch bbox.

Trailheads are AccessPoints — where you park, distinct from the place — so
each one attaches to the nearest canonical place within 2 km. Trailheads
with no nearby place become places of kind 'trailhead' (resolved through
the name+distance crosswalk, so re-runs don't duplicate them).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx
from sqlalchemy import Connection, text

from place.config import get_settings
from place.ingest import crosswalk
from place.ingest.geo import in_polygon, portland_bbox

log = logging.getLogger(__name__)

QUERY_URL = (
    "https://apps.fs.usda.gov/arcx/rest/services/EDW/"
    "EDW_InfraRecreationSites_01/MapServer/0/query"
)
PAGE_SIZE = 1000
# managing_org prefixes: Mt Hood NF + Columbia River Gorge NSA
ORG_PREFIXES = ("0606", "0622")
ATTACH_RADIUS_M = 2000.0


@dataclass(frozen=True)
class Trailhead:
    site_cn: str
    name: str
    lat: float
    lng: float
    permit_info: str | None


def _clean_name(attrs: dict) -> str | None:
    name = (attrs.get("public_site_name") or attrs.get("site_name") or "").strip()
    if not name:
        return None
    if name.isupper():
        name = name.title()
    # the source title-cases possessives as "Angel'S" — fix the apostrophe case
    return re.sub(r"'S\b", "'s", name)


def parse_features(payload: dict) -> list[Trailhead]:
    out: list[Trailhead] = []
    for feat in payload.get("features", []):
        attrs = feat.get("attributes", {})
        geom = feat.get("geometry") or {}
        name = _clean_name(attrs)
        lat = attrs.get("latitude") or geom.get("y")
        lng = attrs.get("longitude") or geom.get("x")
        if not name or lat is None or lng is None:
            continue
        permit = (attrs.get("permit_information") or "").strip() or None
        out.append(
            Trailhead(
                site_cn=str(attrs.get("site_cn")),
                name=name,
                lat=float(lat),
                lng=float(lng),
                permit_info=permit,
            )
        )
    return out


def _fetch_pages() -> list[Trailhead]:
    settings = get_settings()
    bbox = portland_bbox()
    org_filter = " OR ".join(f"managing_org LIKE '{p}%'" for p in ORG_PREFIXES)
    where = f"UPPER(site_subtype) LIKE '%TRAILHEAD%' AND ({org_filter})"
    trailheads: list[Trailhead] = []
    offset = 0
    with httpx.Client(
        headers={"User-Agent": settings.http_user_agent}, timeout=120.0
    ) as client:
        while True:
            resp = client.get(
                QUERY_URL,
                params={
                    "where": where,
                    "geometry": f"{bbox.west},{bbox.south},{bbox.east},{bbox.north}",
                    "geometryType": "esriGeometryEnvelope",
                    "inSR": 4326,
                    "spatialRel": "esriSpatialRelIntersects",
                    "outFields": "site_cn,public_site_name,site_name,site_subtype,"
                    "managing_org,latitude,longitude,permit_information",
                    "outSR": 4326,
                    "resultOffset": offset,
                    "resultRecordCount": PAGE_SIZE,
                    "f": "json",
                },
            )
            resp.raise_for_status()
            payload = resp.json()
            if "error" in payload:
                raise RuntimeError(f"USFS ArcGIS error: {payload['error']}")
            page = parse_features(payload)
            trailheads.extend(page)
            if not payload.get("exceededTransferLimit") or not page:
                break
            offset += PAGE_SIZE
    return trailheads


def _nearest_place(conn: Connection, lat: float, lng: float) -> object | None:
    row = conn.execute(
        text(
            "SELECT id FROM places "
            "WHERE kind <> 'trailhead' AND ST_DWithin(geom::geography, "
            "ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, :dist) "
            "ORDER BY geom::geography <-> "
            "ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography LIMIT 1"
        ),
        {"lat": lat, "lng": lng, "dist": ATTACH_RADIUS_M},
    ).first()
    return row[0] if row else None


def _upsert_access_point(conn: Connection, place_id, th: Trailhead) -> bool:
    note = f"USFS trailhead: {th.name} (site_cn {th.site_cn})"
    if th.permit_info:
        note += f"; permit: {th.permit_info}"
    exists = conn.execute(
        text(
            "SELECT 1 FROM access_points WHERE place_id = :pid AND kind = 'trailhead' "
            "AND notes LIKE :cn"
        ),
        {"pid": place_id, "cn": f"%site_cn {th.site_cn}%"},
    ).first()
    if exists:
        return False
    conn.execute(
        text(
            "INSERT INTO access_points (place_id, kind, geom, notes) VALUES "
            "(:pid, 'trailhead', ST_SetSRID(ST_MakePoint(:lng, :lat), 4326), :note)"
        ),
        {"pid": place_id, "lat": th.lat, "lng": th.lng, "note": note},
    )
    return True


def load(conn: Connection, *, limit: int | None = None) -> dict[str, int]:
    trailheads = _fetch_pages()
    log.info("usfs: %d trailheads fetched (Mt Hood NF + CRGNSA)", len(trailheads))

    attached = standalone = skipped = existing = 0
    processed = 0
    for th in trailheads:
        if limit is not None and processed >= limit:
            break
        if not in_polygon(th.lat, th.lng):
            skipped += 1
            continue
        processed += 1
        place_id = _nearest_place(conn, th.lat, th.lng)
        if place_id is not None:
            if _upsert_access_point(conn, place_id, th):
                attached += 1
            else:
                existing += 1
        else:
            _, was_created = crosswalk.resolve_place(
                conn, name=th.name, kind="trailhead", lat=th.lat, lng=th.lng
            )
            standalone += was_created
            existing += not was_created
    return {
        "processed": processed,
        "access_points_created": attached,
        "standalone_places_created": standalone,
        "already_present": existing,
        "outside_polygon": skipped,
    }
