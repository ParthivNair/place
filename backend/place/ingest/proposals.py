"""Agent-research proposals loader — the bridge into the review queue.

The populate-region skill (.claude/skills/populate-region) web-researches a
region and writes a proposals YAML; this loader is the ONLY path from that
research into the graph, and everything it writes lands at status='review'.
It never sets 'published': the publication gates (docs/00-THESIS.md §7
"Claim" — ≥2 independent sources or founder/user verification, DB-enforced
by the trigger in alembic 0001) run on the founder's review, not here.

Validation is pure and strict, mirroring the extraction pipeline's frozen
schema constraints (place.extract.schema): a closed activity vocabulary
(unknown ids are rejected, not created — the vocabulary grows by founder
edit to activities.yaml), absolute source URLs, observed_date never in the
future and never pre-1980. source_type is limited to llm_extracted |
user_reported — founder_verified and sensor_derived are *earned* through
the verdict and evaluator paths and can never arrive as a proposal.

Idempotent two ways: duplicates within one file collapse before loading, and
a claim whose (affordance, cclass, source_url) already exists in the DB is
skipped — re-running a file converges instead of duplicating. cclass is part
of claim identity: one field-guide page routinely supports both a geomorphic
and an access claim, and keying on URL alone would silently drop the second
(and keep dropping it on every re-run). Place resolution reuses
the ingest crosswalk (trigram name + distance) with a tighter 500 m radius
than cross-source skeleton merges: proposals carry researched coordinates,
so a farther same-name row is more likely a neighboring feature than drift.
"""

from __future__ import annotations

import datetime as dt
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yaml
from sqlalchemy import Connection, text

from place.extract.schema import MAX_QUOTE_CHARS, MIN_OBSERVED_YEAR, source_domain_from_url
from place.ingest import crosswalk
from place.ingest.regions import LAT_RANGE, LNG_RANGE

log = logging.getLogger(__name__)

# Proposals may only carry the two low-trust source types (docs/01 §5 priors).
SOURCE_TYPES = ("llm_extracted", "user_reported")
CLAIM_CLASSES = ("geomorphic", "seasonal_bio", "access", "hazard_calibration")

# Source-type priors, L0 = logit(p0) (docs/01 §5 table).
LOG_ODDS = {
    "llm_extracted": round(math.log(0.35 / 0.65), 4),  # -0.619
    "user_reported": round(math.log(0.55 / 0.45), 4),  # +0.2007
}

# claims.extractor_ver tag for rows born here — distinguishes agent-research
# proposals from batch/loop extraction when diffing extractor vintages.
PROPOSALS_VERSION = "proposals/v1"

# Tighter than crosswalk.DEFAULT_MAX_DISTANCE_M (1 km): see module docstring.
MAX_MATCH_DISTANCE_M = 500.0


class ProposalError(ValueError):
    """The proposals file failed validation; nothing was written."""


@dataclass(frozen=True)
class Proposal:
    place_name: str
    place_kind: str
    lat: float
    lng: float
    activity_id: str
    cclass: str
    text: str
    source_url: str
    source_type: str
    observed_date: dt.date | None
    dog_ok: bool | None
    kid_ok: bool | None


# ---------------------------------------------------------------------------
# validation (pure — unit-testable without a database)
# ---------------------------------------------------------------------------


def _parse_observed_date(raw: object, ctx: str) -> dt.date | None:
    if raw is None:
        return None
    if isinstance(raw, dt.date) and not isinstance(raw, dt.datetime):
        date = raw
    elif isinstance(raw, str):
        try:
            date = dt.date.fromisoformat(raw)
        except ValueError as exc:
            raise ProposalError(f"{ctx}: observed_date {raw!r} is not an ISO date") from exc
    else:
        raise ProposalError(f"{ctx}: observed_date must be an ISO date or null")
    # Same credibility bounds as the frozen extraction schema.
    if date > dt.date.today():
        raise ProposalError(f"{ctx}: observed_date {date} is in the future")
    if date.year < MIN_OBSERVED_YEAR:
        raise ProposalError(f"{ctx}: observed_date {date} predates {MIN_OBSERVED_YEAR}")
    return date


def _parse_optional_bool(entry: dict, key: str, ctx: str) -> bool | None:
    v = entry.get(key)
    if v is not None and not isinstance(v, bool):
        raise ProposalError(f"{ctx}: {key} must be a boolean if present")
    return v


def _parse_one(entry: object, known_activities: set[str], ctx: str) -> Proposal:
    if not isinstance(entry, dict):
        raise ProposalError(f"{ctx}: must be a mapping")
    place = entry.get("place")
    if not isinstance(place, dict):
        raise ProposalError(f"{ctx}: place must be a mapping")
    name = place.get("name")
    kind = place.get("kind")
    if not isinstance(name, str) or not name.strip():
        raise ProposalError(f"{ctx}: place.name must be a non-empty string")
    if not isinstance(kind, str) or not kind.strip():
        raise ProposalError(f"{ctx}: place.kind must be a non-empty string")
    for key in ("lat", "lng"):
        v = place.get(key)
        if not isinstance(v, int | float) or isinstance(v, bool):
            raise ProposalError(f"{ctx}: place.{key} must be a number")
    lat, lng = float(place["lat"]), float(place["lng"])
    if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1]) or not (LNG_RANGE[0] <= lng <= LNG_RANGE[1]):
        raise ProposalError(
            f"{ctx}: ({lat}, {lng}) outside the Oregon sanity window — "
            "never invent coordinates; cross-check against ingested places"
        )

    activity_id = entry.get("activity_id")
    if activity_id not in known_activities:
        raise ProposalError(
            f"{ctx}: unknown activity_id {activity_id!r} — the vocabulary is closed "
            "(backend/data/activities.yaml); proposals cannot mint activities"
        )

    claim = entry.get("claim")
    if not isinstance(claim, dict):
        raise ProposalError(f"{ctx}: claim must be a mapping")
    claim_text = claim.get("text")
    if not isinstance(claim_text, str) or not claim_text.strip():
        raise ProposalError(f"{ctx}: claim.text must be a non-empty string")
    if len(claim_text.strip()) > MAX_QUOTE_CHARS:
        # Same cap as the frozen extraction schema's verbatim_quote: the text
        # lands in claims.quote_internal, which carries minimal evidence for
        # founder review, not article dumps.
        raise ProposalError(
            f"{ctx}: claim.text exceeds {MAX_QUOTE_CHARS} chars — quote the minimal evidence"
        )
    source_type = claim.get("source_type")
    if source_type not in SOURCE_TYPES:
        raise ProposalError(
            f"{ctx}: claim.source_type must be one of {SOURCE_TYPES} — "
            "founder_verified/sensor_derived are earned, never proposed"
        )
    source_url = claim.get("source_url")
    if not isinstance(source_url, str):
        raise ProposalError(f"{ctx}: claim.source_url must be a string")
    parsed = urlparse(source_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ProposalError(f"{ctx}: claim.source_url must be an absolute http(s) URL")
    cclass = claim.get("class", "geomorphic")
    if cclass not in CLAIM_CLASSES:
        raise ProposalError(f"{ctx}: claim.class must be one of {CLAIM_CLASSES}")

    return Proposal(
        place_name=name.strip(),
        place_kind=kind.strip(),
        lat=lat,
        lng=lng,
        activity_id=activity_id,
        cclass=cclass,
        text=claim_text.strip(),
        source_url=source_url.strip(),
        source_type=source_type,
        observed_date=_parse_observed_date(claim.get("observed_date"), ctx),
        dog_ok=_parse_optional_bool(entry, "dog_ok", ctx),
        kid_ok=_parse_optional_bool(entry, "kid_ok", ctx),
    )


def parse_proposals(doc: object, known_activities: set[str]) -> list[Proposal]:
    """Validate the whole file; raises ProposalError naming the bad entry.

    The canonical shape is a top-level list; a {proposals: [...]} wrapper is
    accepted so files can carry a comment header mapping.
    """
    if isinstance(doc, dict):
        doc = doc.get("proposals")
    if not isinstance(doc, list) or not doc:
        raise ProposalError("proposals file must be a non-empty list (or {proposals: [...]})")
    return [
        _parse_one(entry, known_activities, f"proposals[{i}]")
        for i, entry in enumerate(doc)
    ]


def dedup(proposals: list[Proposal]) -> tuple[list[Proposal], int]:
    """Collapse in-file duplicates; first occurrence wins.

    The key is (normalized place name, coordinates, activity, claim class,
    source_url) — deliberately FINER than the DB skip's (affordance, cclass,
    source_url), because one source page routinely carries several distinct
    claims: a field-guide page pairing a geomorphic claim with an access
    claim, or two same-named places cited by one roundup (Oregon has two
    Punch Bowl Falls ~20 km apart). Only literal repeats collapse here;
    near-duplicates that survive resolve to the same affordance and are
    skipped by _claim_exists instead.
    """
    seen: set[tuple[str, float, float, str, str, str]] = set()
    unique: list[Proposal] = []
    for p in proposals:
        key = (
            crosswalk.normalize_name(p.place_name),
            p.lat,
            p.lng,
            p.activity_id,
            p.cclass,
            p.source_url,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique, len(proposals) - len(unique)


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------


def _known_activities(conn: Connection) -> set[str]:
    return set(conn.execute(text("SELECT id FROM activities")).scalars())


def _get_or_create_affordance(
    conn: Connection, place_id: object, p: Proposal
) -> tuple[object, bool]:
    row = conn.execute(
        text(
            "SELECT id, status::text FROM affordances "
            "WHERE place_id = :p AND activity_id = :a"
        ),
        {"p": place_id, "a": p.activity_id},
    ).first()
    if row is not None:
        existing, status = row
        # Fill dog_ok/kid_ok only where NULL — never clobber values the
        # founder (or a binding) already set — and only on rows still ahead
        # of founder triage. A published affordance is live-served (/feed
        # filters on these columns directly), so an agent-researched flag
        # must not reach it without review — this loader's whole contract is
        # that nothing it writes skips the review queue. Suppressed rows are
        # a founder decision this loader must not touch either. The claim
        # itself still lands (at status='review') for any status: new
        # evidence for a published affordance is exactly what triage is for.
        if status in ("draft", "review"):
            for col, val in (("dog_ok", p.dog_ok), ("kid_ok", p.kid_ok)):
                if val is not None:
                    conn.execute(
                        text(f"UPDATE affordances SET {col} = :v WHERE id = :i AND {col} IS NULL"),  # noqa: S608
                        {"v": val, "i": existing},
                    )
        return existing, False
    # Born straight into the review queue — unlike extraction's 'draft'
    # (resolve.py), a proposal is a deliberate candidate for founder review.
    created = conn.execute(
        text(
            "INSERT INTO affordances (place_id, activity_id, dog_ok, kid_ok, status) "
            "VALUES (:p, :a, :dog, :kid, 'review') RETURNING id"
        ),
        {"p": place_id, "a": p.activity_id, "dog": p.dog_ok, "kid": p.kid_ok},
    ).scalar_one()
    return created, True


def _claim_exists(conn: Connection, affordance_id: object, p: Proposal) -> bool:
    # cclass is part of claim identity: skipping on (affordance, source_url)
    # alone would permanently drop the second of two distinct claims one page
    # supports (e.g. geomorphic 'deep pool' + access 'gate closed') — every
    # re-run citing the URL would keep counting it as already present.
    return bool(
        conn.execute(
            text(
                "SELECT 1 FROM claims WHERE affordance_id = :a "
                "AND cclass = CAST(:c AS claim_class) AND source_url = :u LIMIT 1"
            ),
            {"a": affordance_id, "c": p.cclass, "u": p.source_url},
        ).scalar()
    )


def _insert_claim(conn: Connection, affordance_id: object, p: Proposal) -> None:
    conn.execute(
        text(
            "INSERT INTO claims (affordance_id, cclass, stype, source_url, source_domain, "
            "quote_internal, observed_date, extractor_ver, status, log_odds) "
            "VALUES (:a, CAST(:cclass AS claim_class), CAST(:stype AS source_type), "
            ":url, :domain, :quote, :observed, :ver, 'review', :lo)"
        ),
        {
            "a": affordance_id,
            "cclass": p.cclass,
            "stype": p.source_type,
            "url": p.source_url,
            "domain": source_domain_from_url(p.source_url),
            "quote": p.text,  # internal evidence only; no API serializes it
            "observed": p.observed_date,
            "ver": PROPOSALS_VERSION,
            "lo": LOG_ODDS[p.source_type],
        },
    )


def load(conn: Connection, path: Path) -> dict[str, int]:
    """Validate then load one proposals file. Returns counters for the CLI."""
    # A bad path or broken YAML is a rejected file, not a traceback — same
    # exit path as any other validation failure (nothing written).
    try:
        raw = path.read_text()
    except FileNotFoundError as exc:
        raise ProposalError(f"proposals file not found: {path}") from exc
    try:
        doc = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ProposalError(f"proposals file is not valid YAML: {exc}") from exc
    proposals = parse_proposals(doc, _known_activities(conn))
    unique, in_file_dupes = dedup(proposals)

    stats = {
        "proposals": len(proposals),
        "in_file_dupes": in_file_dupes,
        "places_created": 0,
        "places_matched": 0,
        "affordances_created": 0,
        "affordances_existing": 0,
        "claims_created": 0,
        "claims_skipped": 0,
    }
    seen_places: set[object] = set()
    for p in unique:
        place_id, place_created = crosswalk.resolve_place(
            conn,
            name=p.place_name,
            kind=p.place_kind,
            lat=p.lat,
            lng=p.lng,
            max_distance_m=MAX_MATCH_DISTANCE_M,
        )
        # several proposals per place is the norm; count each place once
        if place_id not in seen_places:
            seen_places.add(place_id)
            stats["places_created" if place_created else "places_matched"] += 1
        affordance_id, aff_created = _get_or_create_affordance(conn, place_id, p)
        stats["affordances_created" if aff_created else "affordances_existing"] += 1
        if _claim_exists(conn, affordance_id, p):
            stats["claims_skipped"] += 1
            continue
        _insert_claim(conn, affordance_id, p)
        stats["claims_created"] += 1
        log.info(
            "proposal: %r/%s -> place %s (%s), claim from %s",
            p.place_name, p.activity_id, place_id,
            "new" if place_created else "matched", source_domain_from_url(p.source_url),
        )
    return stats
