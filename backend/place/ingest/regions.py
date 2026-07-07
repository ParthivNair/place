"""Region priority list + coverage counts for the population program.

docs/03 §6 (the per-metro replication playbook) works metro by metro; this is
the same recipe applied fractally *within* the metro: a founder-editable
priority list (backend/data/regions/priority.yaml — file order IS priority
order), bbox math to scope the Overpass pull, and PostGIS coverage counts that
decide which region the populate-region skill works next.

The YAML is founder-owned: this module validates it and never reorders or
rewrites it. Targets default per docs/03 §6 step 8 (depth over breadth —
150 dense places beat 400 shallow ones) and are overridable per region.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import Connection, text

from place.ingest import geo

_REPO_BACKEND = Path(__file__).resolve().parent.parent.parent
DEFAULT_PRIORITY_PATH = _REPO_BACKEND / "data" / "regions" / "priority.yaml"

DEFAULT_RADIUS_MI = 20.0
DEFAULT_TARGET_PLACES = 150
DEFAULT_TARGET_AFFORDANCES = 30

MI_TO_KM = 1.609344

# Oregon-and-neighbors sanity window. A fat-fingered centroid outside this box
# would silently scope the Overpass pull at the wrong corner of the planet;
# it also guarantees no region bbox can cross the antimeridian.
LAT_RANGE = (41.0, 47.5)
LNG_RANGE = (-125.5, -116.0)

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# affordances.status values, in the order the coverage table prints them.
STATUSES = ("draft", "review", "published", "suppressed")


class RegionError(ValueError):
    """priority.yaml failed validation; nothing was read from it."""


@dataclass(frozen=True)
class Region:
    slug: str
    name: str
    anchor_zip: str
    lat: float
    lng: float
    radius_mi: float
    notes: str
    target_places: int
    target_affordances: int

    @property
    def radius_km(self) -> float:
        return self.radius_mi * MI_TO_KM

    @property
    def radius_m(self) -> float:
        return self.radius_km * 1000.0

    def bbox(self) -> geo.BBox:
        """Circumscribing bbox for the Overpass pre-filter (S W N E)."""
        return geo.bbox_around(self.lat, self.lng, self.radius_km)


def _require_number(entry: dict, key: str, ctx: str) -> float:
    v = entry.get(key)
    if not isinstance(v, int | float) or isinstance(v, bool):
        raise RegionError(f"{ctx}: {key} must be a number, got {v!r}")
    return float(v)


def parse_regions(doc: object) -> list[Region]:
    """Validate + shape the priority.yaml document (pure — unit-testable)."""
    if not isinstance(doc, dict):
        raise RegionError("priority.yaml must be a mapping with a 'regions' list")
    defaults = doc.get("defaults") or {}
    if not isinstance(defaults, dict):
        raise RegionError("defaults must be a mapping")
    entries = doc.get("regions")
    if not isinstance(entries, list) or not entries:
        raise RegionError("regions must be a non-empty list")

    out: list[Region] = []
    seen: set[str] = set()
    for i, entry in enumerate(entries):
        ctx = f"regions[{i}]"
        if not isinstance(entry, dict):
            raise RegionError(f"{ctx}: must be a mapping")
        slug = entry.get("slug")
        if not isinstance(slug, str) or not _SLUG_RE.match(slug):
            raise RegionError(f"{ctx}: slug must be lowercase-kebab, got {slug!r}")
        if slug in seen:
            raise RegionError(f"{ctx}: duplicate slug {slug!r}")
        seen.add(slug)
        ctx = f"regions[{slug}]"
        for key in ("name", "anchor_zip", "notes"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise RegionError(f"{ctx}: {key} must be a non-empty string")
        lat = _require_number(entry, "lat", ctx)
        lng = _require_number(entry, "lng", ctx)
        if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1]) or not (LNG_RANGE[0] <= lng <= LNG_RANGE[1]):
            raise RegionError(
                f"{ctx}: centroid ({lat}, {lng}) outside the Oregon sanity window "
                f"lat {LAT_RANGE} lng {LNG_RANGE}"
            )
        radius_mi = float(
            entry["radius_mi"] if "radius_mi" in entry
            else defaults.get("radius_mi", DEFAULT_RADIUS_MI)
        )
        if radius_mi <= 0:
            raise RegionError(f"{ctx}: radius_mi must be positive")
        # per-region override > defaults block > code default
        target_places = int(
            entry.get("target_places", defaults.get("target_places", DEFAULT_TARGET_PLACES))
        )
        target_affordances = int(
            entry.get(
                "target_affordances",
                defaults.get("target_affordances", DEFAULT_TARGET_AFFORDANCES),
            )
        )
        if target_places <= 0 or target_affordances <= 0:
            raise RegionError(f"{ctx}: targets must be positive")
        out.append(
            Region(
                slug=slug,
                name=entry["name"].strip(),
                anchor_zip=str(entry["anchor_zip"]).strip(),
                lat=lat,
                lng=lng,
                radius_mi=radius_mi,
                notes=entry["notes"].strip(),
                target_places=target_places,
                target_affordances=target_affordances,
            )
        )
    return out


def load_regions(path: Path | None = None) -> list[Region]:
    path = path or DEFAULT_PRIORITY_PATH
    return parse_regions(yaml.safe_load(path.read_text()))


def region_by_slug(regions: list[Region], slug: str) -> Region:
    for r in regions:
        if r.slug == slug:
            return r
    raise RegionError(f"no region {slug!r} in priority list ({[r.slug for r in regions]})")


# ---------------------------------------------------------------------------
# coverage (PostGIS counts within each region circle)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Coverage:
    region: Region
    places: int
    affordances: dict[str, int]  # status -> count

    @property
    def affordances_total(self) -> int:
        # target counts ANY status: review-queue depth is progress; publication
        # is gated elsewhere (docs/00 §7 "Claim").
        return sum(self.affordances.values())

    @property
    def meets_target(self) -> bool:
        return (
            self.places >= self.region.target_places
            and self.affordances_total >= self.region.target_affordances
        )


_PLACES_SQL = text(
    "SELECT count(*) FROM places "
    "WHERE ST_DWithin(geom::geography, "
    "ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, :dist)"
)

_AFFORDANCES_SQL = text(
    "SELECT a.status::text AS status, count(*) AS n "
    "FROM affordances a JOIN places p ON p.id = a.place_id "
    "WHERE ST_DWithin(p.geom::geography, "
    "ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, :dist) "
    "GROUP BY a.status"
)


def region_coverage(conn: Connection, region: Region) -> Coverage:
    params = {"lat": region.lat, "lng": region.lng, "dist": region.radius_m}
    places = conn.execute(_PLACES_SQL, params).scalar_one()
    by_status = dict.fromkeys(STATUSES, 0)
    for row in conn.execute(_AFFORDANCES_SQL, params).mappings():
        by_status[row["status"]] = row["n"]
    return Coverage(region=region, places=places, affordances=by_status)


def coverage_report(conn: Connection, regions: list[Region]) -> list[Coverage]:
    return [region_coverage(conn, r) for r in regions]


def pick_next(coverages: list[Coverage]) -> Coverage | None:
    """First region in priority order below target — the skill's work queue.

    Pure: priority is the file order the founder set, nothing cleverer.
    Returns None when every region meets target (the program is 'done' until
    the founder raises targets or appends regions).
    """
    for cov in coverages:
        if not cov.meets_target:
            return cov
    return None


def format_coverage_table(coverages: list[Coverage]) -> str:
    """The CLI table: one row per region, priority order, NEXT marked."""
    nxt = pick_next(coverages)
    header = (
        f"{'region':<18} {'zip':<6} {'places':>7} {'afford':>7} "
        f"{'draft':>6} {'review':>7} {'publ':>6} {'suppr':>6}  {'target(p/a)':<12} {'':<4}"
    )
    lines = [header, "-" * len(header)]
    for cov in coverages:
        r = cov.region
        a = cov.affordances
        mark = "NEXT" if nxt is not None and cov.region.slug == nxt.region.slug else (
            "ok" if cov.meets_target else ""
        )
        lines.append(
            f"{r.slug:<18} {r.anchor_zip:<6} {cov.places:>7} {cov.affordances_total:>7} "
            f"{a['draft']:>6} {a['review']:>7} {a['published']:>6} {a['suppressed']:>6}  "
            f"{f'{r.target_places}/{r.target_affordances}':<12} {mark:<4}"
        )
    return "\n".join(lines)
