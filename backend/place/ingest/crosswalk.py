"""Entity resolution at ingest time — the OSM/GNIS/RIDB crosswalk.

Every loader funnels through :func:`resolve_place`. Resolution order:

1. **Crosswalk id hit** — a place already carries this source's id
   (places.osm_id / gnis_id / ridb_id): idempotent re-run, return it.
2. **Name + distance match** — trigram similarity on normalized names against
   candidates within a search radius (SQL fetches candidates via ST_DWithin;
   the pick itself is a pure function so it unit-tests without postgres).
   A match *merges*: the new source's id is written onto the existing row
   instead of duplicating the place.
3. **Miss** — insert a new canonical place.

The keyless fallback mandated by the brief: pg_trgm-style similarity +
distance. Embedding rerank (name_embedding) is a later, key-gated upgrade.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import Connection, text

from place.ingest.geo import haversine_m

log = logging.getLogger(__name__)

CROSSWALK_COLUMNS = ("osm_id", "gnis_id", "ridb_id")

# Same falls from two sources sit within a few hundred meters; 1 km absorbs
# GNIS-vs-OSM node placement drift without merging neighboring falls on the
# same creek (Upper/Lower pairs are typically caught by the name check).
DEFAULT_MAX_DISTANCE_M = 1000.0
DEFAULT_MIN_SIMILARITY = 0.45

_GENERIC_TOKENS = {"the", "of"}


def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation/diacritics-adjacent noise, collapse spaces."""
    s = name.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    tokens = [t for t in s.split() if t not in _GENERIC_TOKENS]
    return " ".join(tokens)


def _trigrams(s: str) -> set[str]:
    """pg_trgm-compatible trigram set: each word padded '  word '."""
    grams: set[str] = set()
    for word in s.split():
        padded = f"  {word} "
        grams.update(padded[i : i + 3] for i in range(len(padded) - 2))
    return grams


def trigram_similarity(a: str, b: str) -> float:
    """Jaccard over pg_trgm-style trigrams of the *normalized* names."""
    ta, tb = _trigrams(normalize_name(a)), _trigrams(normalize_name(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


@dataclass(frozen=True)
class Candidate:
    place_id: uuid.UUID
    name: str
    lat: float
    lng: float


def pick_match(
    name: str,
    lat: float,
    lng: float,
    candidates: list[Candidate],
    *,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
    max_distance_m: float = DEFAULT_MAX_DISTANCE_M,
) -> Candidate | None:
    """Best same-entity candidate, or None.

    Pure function: rank by name similarity, tie-break by distance; both
    thresholds must hold. Wrong-merge is worse than a duplicate, so thresholds
    are conservative (docs/03 §2 stage 3: guessing is worse than discarding).
    """
    best: tuple[float, float, Candidate] | None = None
    for c in candidates:
        d = haversine_m(lat, lng, c.lat, c.lng)
        if d > max_distance_m:
            continue
        sim = trigram_similarity(name, c.name)
        if sim < min_similarity:
            continue
        key = (sim, -d)
        if best is None or key > (best[0], best[1]):
            best = (sim, -d, c)
    return best[2] if best else None


# ---------------------------------------------------------------------------
# DB side
# ---------------------------------------------------------------------------


def _fetch_candidates(
    conn: Connection, lat: float, lng: float, search_m: float
) -> list[Candidate]:
    rows = conn.execute(
        text(
            "SELECT id, name, ST_Y(geom) AS lat, ST_X(geom) AS lng FROM places "
            "WHERE ST_DWithin(geom::geography, "
            "ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, :dist)"
        ),
        {"lat": lat, "lng": lng, "dist": search_m},
    ).mappings()
    return [Candidate(r["id"], r["name"], r["lat"], r["lng"]) for r in rows]


def find_match(
    conn: Connection,
    *,
    name: str,
    lat: float,
    lng: float,
    max_distance_m: float = DEFAULT_MAX_DISTANCE_M,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
) -> uuid.UUID | None:
    """Match-only resolution (no insert) — for records that annotate an
    existing place rather than defining one (e.g. RIDB permit entries)."""
    match = pick_match(
        name,
        lat,
        lng,
        _fetch_candidates(conn, lat, lng, max_distance_m),
        min_similarity=min_similarity,
        max_distance_m=max_distance_m,
    )
    return match.place_id if match else None


def resolve_place(
    conn: Connection,
    *,
    name: str,
    kind: str,
    lat: float,
    lng: float,
    source_col: str | None = None,
    source_id: int | str | None = None,
    elev_m: int | None = None,
    max_distance_m: float = DEFAULT_MAX_DISTANCE_M,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
) -> tuple[uuid.UUID, bool]:
    """Resolve-or-insert one canonical place. Returns (place_id, created).

    ``source_col`` is one of places' crosswalk columns; passing it makes the
    call idempotent on that id and makes cross-source merges stick.
    """
    if source_col is not None and source_col not in CROSSWALK_COLUMNS:
        raise ValueError(f"unknown crosswalk column: {source_col}")

    if source_col and source_id is not None:
        row = conn.execute(
            text(f"SELECT id FROM places WHERE {source_col} = :sid"),  # noqa: S608
            {"sid": source_id},
        ).first()
        if row:
            return row[0], False

    match = pick_match(
        name,
        lat,
        lng,
        _fetch_candidates(conn, lat, lng, max_distance_m),
        min_similarity=min_similarity,
        max_distance_m=max_distance_m,
    )
    if match:
        if source_col and source_id is not None:
            conn.execute(
                text(
                    f"UPDATE places SET {source_col} = :sid "  # noqa: S608
                    f"WHERE id = :pid AND {source_col} IS NULL"
                ),
                {"sid": source_id, "pid": match.place_id},
            )
        if elev_m is not None:
            conn.execute(
                text("UPDATE places SET elev_m = :e WHERE id = :pid AND elev_m IS NULL"),
                {"e": elev_m, "pid": match.place_id},
            )
        log.debug("crosswalk merge: %r -> existing place %s (%r)", name, match.place_id, match.name)
        return match.place_id, False

    cols = "name, kind, geom, elev_m" + (f", {source_col}" if source_col else "")
    vals = ":name, :kind, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326), :elev" + (
        ", :sid" if source_col else ""
    )
    params: dict[str, object] = {
        "name": name, "kind": kind, "lat": lat, "lng": lng, "elev": elev_m,
    }
    if source_col:
        params["sid"] = source_id
    row = conn.execute(
        text(f"INSERT INTO places ({cols}) VALUES ({vals}) RETURNING id"),  # noqa: S608
        params,
    ).first()
    assert row is not None
    return row[0], True
