"""RIDB (Recreation.gov) facilities loader — key-gated (RIDB_API_KEY).

Pages /api/v1/facilities for OR + WA (the documented ``radius`` param caps
at 50 miles, so state paging + local polygon filter covers the 130 km circle),
resolves each facility through the crosswalk (places.ridb_id), and records
permit entries — facilities whose type is "Permit", e.g. the Multnomah Falls
timed-use permit — as structured access constraints: an access_points row
(kind='permit_info') attached to the canonical place.

Without RIDB_API_KEY this raises MissingCredential; the CLI logs the skip.
Never faked.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx
from sqlalchemy import Connection, text

from place.config import get_settings
from place.ingest import crosswalk
from place.ingest.geo import in_polygon

log = logging.getLogger(__name__)

BASE_URL = "https://ridb.recreation.gov/api/v1"
PAGE_SIZE = 50  # RIDB maximum
STATES = ("OR", "WA")

# boilerplate stripped from permit-product names before place matching
_PERMIT_WORDS = re.compile(
    r"\b(timed|use|entry|day|permits?|reservations?|lottery|tickets?)\b", re.IGNORECASE
)

TYPE_TO_KIND = {
    "campground": "campground",
    "camping": "campground",
    "trailhead": "trailhead",
    "day use area": "day_use",
    "permit": "permit",
}


@dataclass(frozen=True)
class RidbFacility:
    ridb_id: str
    name: str
    kind: str
    lat: float
    lng: float
    permit_required: bool


def parse_facilities(payload: dict) -> list[RidbFacility]:
    out: list[RidbFacility] = []
    for fac in payload.get("RECDATA", []):
        name = (fac.get("FacilityName") or "").strip()
        lat, lng = fac.get("FacilityLatitude"), fac.get("FacilityLongitude")
        if not name or not lat or not lng:  # RIDB uses 0/None for missing coords
            continue
        ftype = (fac.get("FacilityTypeDescription") or "").strip().lower()
        out.append(
            RidbFacility(
                ridb_id=str(fac.get("FacilityID")),
                name=name.title() if name.isupper() else name,
                kind=TYPE_TO_KIND.get(ftype, "facility"),
                lat=float(lat),
                lng=float(lng),
                permit_required="permit" in ftype,
            )
        )
    return out


def _fetch_pages(api_key: str) -> list[RidbFacility]:
    settings = get_settings()
    headers = {"apikey": api_key, "User-Agent": settings.http_user_agent}
    facilities: list[RidbFacility] = []
    with httpx.Client(base_url=BASE_URL, headers=headers, timeout=60.0) as client:
        for state in STATES:
            offset = 0
            while True:
                resp = client.get(
                    "/facilities",
                    params={"state": state, "limit": PAGE_SIZE, "offset": offset},
                )
                resp.raise_for_status()
                payload = resp.json()
                facilities.extend(parse_facilities(payload))
                results = payload.get("METADATA", {}).get("RESULTS", {})
                count = int(results.get("CURRENT_COUNT", 0))
                total = int(results.get("TOTAL_COUNT", 0))
                offset += count
                if count == 0 or offset >= total:
                    break
    return facilities


def _record_permit(conn: Connection, place_id, fac: RidbFacility) -> None:
    """Permit entries as machine-readable access constraints (idempotent)."""
    note = f"Recreation.gov permit required: {fac.name} (RIDB facility {fac.ridb_id})"
    exists = conn.execute(
        text(
            "SELECT 1 FROM access_points WHERE place_id = :pid "
            "AND kind = 'permit_info' AND notes = :note"
        ),
        {"pid": place_id, "note": note},
    ).first()
    if not exists:
        conn.execute(
            text(
                "INSERT INTO access_points (place_id, kind, geom, notes) VALUES "
                "(:pid, 'permit_info', ST_SetSRID(ST_MakePoint(:lng, :lat), 4326), :note)"
            ),
            {"pid": place_id, "lat": fac.lat, "lng": fac.lng, "note": note},
        )


def load(conn: Connection, *, limit: int | None = None) -> dict[str, int]:
    api_key = get_settings().require("RIDB_API_KEY")
    facilities = _fetch_pages(api_key)
    log.info("ridb: %d facilities fetched (OR+WA)", len(facilities))

    created = merged = skipped = permits = 0
    processed = 0
    for fac in facilities:
        if limit is not None and processed >= limit:
            break
        if not in_polygon(fac.lat, fac.lng):
            skipped += 1
            continue
        processed += 1
        # A permit facility is an access constraint on an existing place
        # (e.g. "Multnomah Falls Timed Use Permit" -> Multnomah Falls):
        # match-only, wider reach, permit boilerplate words stripped; never
        # create a place named after the permit product.
        if fac.permit_required:
            match_name = _PERMIT_WORDS.sub(" ", fac.name)
            place_id = crosswalk.find_match(
                conn,
                name=match_name,
                lat=fac.lat,
                lng=fac.lng,
                min_similarity=0.35,
                max_distance_m=2000.0,
            )
            if place_id is None:
                log.info("ridb: no canonical place for permit %r — skipped", fac.name)
                skipped += 1
                continue
            _record_permit(conn, place_id, fac)
            permits += 1
            merged += 1
            continue
        _, was_created = crosswalk.resolve_place(
            conn,
            name=fac.name,
            kind=fac.kind,
            lat=fac.lat,
            lng=fac.lng,
            source_col="ridb_id",
            source_id=fac.ridb_id,
        )
        created += was_created
        merged += not was_created
    return {
        "processed": processed,
        "created": created,
        "existing_or_merged": merged,
        "outside_polygon": skipped,
        "permits": permits,
    }
