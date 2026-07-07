"""Static pack compiler — the sweep's shadow publish phase (docs/04 §4).

The read path is moving to versioned static artifacts; the database stays the
build-side system of record. Each sweep compiles three content-addressed
brotli files plus one mutable manifest under ``{packs_dir}/{region_slug}/``:

- ``graph-{sha256[:12]}.json.br`` — the interactive core: non-sensitive
  places, activities, published affordances, condition-window metadata, the
  feed registry, last-confirm credits, and the scoring constants block
  (sourced from :mod:`place.scoring`, so client math and build math cannot
  drift).
- ``claims-{sha256[:12]}.json.br`` — published claims only, through the SAME
  statement + projection the card routes use (:mod:`place.api.cards`), so one
  gate guards both paths: unpublished/superseded claims and quote_internal
  are structurally unreachable.
- ``conditions-{sha256[:12]}.json.br`` — the perishable layer, pinned to the
  graph build it was computed against (version skew is detectable offline).
- ``manifest.json`` — the ONLY mutable file.

The docs/04 §4 degradation rules are encoded INTO the artifacts, because a
pack-mode client may be offline with no server left to ask:

- rule 1 (never show stale as fresh): ``expires_at = generated_at + 2x sweep
  cadence`` — the same 2x staleness factor the readings provider applies to
  feeds. Past it, every live state in the pack is "unknown", never current.
- rule 2 (degrade to seasonal priors, not silence): ``seasonal_prior_score``
  is the month-range fallback score an expired pack may still rank with.
- rule 3 (hazard degrades DOWN only): ``hazard_serve_until`` is a wall-clock
  wall computed by the same two-prong logic as the good_now hazard gate;
  past that instant the client suppresses the card unconditionally.

Write pattern (crash safety): content-hashed files first, fsynced, then the
manifest via tmp-write + ``os.replace`` — a crash mid-publish leaves the old
manifest pointing at old, still-present files. The last ``KEEP_GENERATIONS``
generations per artifact class survive pruning, so a client mid-download of
generation N-1 keeps working while N lands.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import logging
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import brotli
from sqlalchemy import Connection, bindparam, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine

from place import scoring
from place.api import cards, snapshots
from place.api.reasons import iter_leaves, normalize_reading
from place.config import Settings, get_settings
from place.evaluator import registry
from place.models import feeds

log = logging.getLogger(__name__)

__all__ = [
    "KEEP_GENERATIONS",
    "PACK_SCHEMA_VERSION",
    "PUBLISHER_PROVIDER",
    "Artifact",
    "PublishResult",
    "compile_packs",
    "ensure_publisher_feed",
    "hazard_serve_until",
    "make_artifact",
    "publish_packs",
    "publisher_feed_id",
    "write_generation",
]

PACK_SCHEMA_VERSION = 1
KEEP_GENERATIONS = 3
ARTIFACT_KINDS = ("graph", "claims", "conditions")

# Pseudo-feed under which publish outcomes land in feed_health, so the
# existing three-consecutive-failures alert (health.check_and_alert) covers
# the publisher with zero new alerting machinery. run.py excludes this
# provider from the fetch phase — there is nothing to fetch.
PUBLISHER_PROVIDER = "publisher"


def publisher_feed_id(region_slug: str) -> str:
    return f"{PUBLISHER_PROVIDER}:{region_slug}:packs"


def ensure_publisher_feed(conn: Connection, region_slug: str) -> str:
    """Idempotently create the publisher pseudo-feed row (feed_health FK)."""
    feed_id = publisher_feed_id(region_slug)
    conn.execute(
        pg_insert(feeds)
        .values(
            id=feed_id,
            provider=PUBLISHER_PROVIDER,
            station_ref=region_slug,
            parameter="packs",
            unit="publish",
            poll_interval=registry.SWEEP_CADENCE,
        )
        .on_conflict_do_nothing(index_elements=["id"])
    )
    return feed_id


# ---------------------------------------------------------------------------
# canonical serialization + artifacts
# ---------------------------------------------------------------------------


def canonical_json(payload: dict[str, Any]) -> bytes:
    """Deterministic bytes for hashing: sorted keys, minimal separators.

    Every value must already be a plain JSON type — a TypeError here is a
    compile bug. There is deliberately no ``default=`` coercion hook: silent
    coercion is exactly where hash nondeterminism would creep in.
    """
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


@dataclass(frozen=True)
class Artifact:
    kind: str  # "graph" | "claims" | "conditions"
    filename: str  # {kind}-{sha256[:12]}.json.br
    sha256: str  # of the .br file bytes as served (client-verifiable)
    data: bytes  # brotli-compressed canonical JSON


def make_artifact(kind: str, payload: dict[str, Any]) -> Artifact:
    data = brotli.compress(canonical_json(payload))
    sha = hashlib.sha256(data).hexdigest()
    return Artifact(kind=kind, filename=f"{kind}-{sha[:12]}.json.br", sha256=sha, data=data)


@dataclass(frozen=True)
class PublishResult:
    region_dir: Path
    manifest: dict[str, Any]
    artifacts: tuple[Artifact, ...]


# ---------------------------------------------------------------------------
# plain-type conversion helpers (Decimal/UUID/timestamps never reach json)
# ---------------------------------------------------------------------------


def _iso(ts: dt.datetime | dt.date | None) -> str | None:
    return None if ts is None else ts.isoformat()


def _num(value: Any) -> float | None:
    return None if value is None else float(value)


def _seconds(delta: dt.timedelta) -> int:
    return int(delta.total_seconds())


# ---------------------------------------------------------------------------
# rule 3: the hazard serving wall
# ---------------------------------------------------------------------------


def hazard_serve_until(
    now: dt.datetime,
    last_power_confirm_at: dt.datetime | None,
    gate_windows: Sequence[Mapping[str, Any]],
) -> dt.datetime:
    """The wall-clock instant past which a hazard card is suppressed
    unconditionally (docs/04 §4 rule 3, encoded so it holds offline).

    Same two prongs as the good_now hazard gate (run.py kill switches):

    - confirm prong: a power-verifier confirm on a published claim is good
      for the hazard_calibration half-life; none on record -> the wall is
      ``now`` (a hazard card never serves on priors alone).
    - gate prong: every is_gate window must be live-true, and "true" is only
      trustable while the newest reading behind each of its feeds is inside
      its staleness cutoff (rule 1's 2x-cadence rule). A gate not currently
      true, or one whose reading age cannot be established, walls at ``now``.

    The result may already be in the past; the client contract is
    ``serve iff wall_clock < hazard_serve_until`` — degrade DOWN only.
    """
    if last_power_confirm_at is None:
        return now
    horizon = last_power_confirm_at + dt.timedelta(days=scoring.HAZARD_CONFIRM_WINDOW_DAYS)
    for window in gate_windows:
        if window.get("state") is not True:
            return min(horizon, now)
        inputs: Mapping[str, Any] = window.get("inputs") or {}
        feed_ids = sorted(
            {
                str(leaf["feed"])
                for leaf in iter_leaves(window.get("predicate") or {})
                if leaf.get("feed")
            }
        )
        # Pure-calendar gates (no feed leaves) contribute no staleness bound.
        for feed_id in feed_ids:
            _, observed_at = normalize_reading(inputs.get(feed_id))
            # Fall back to the evaluation instant when the stored input has
            # no reading timestamp — the reading is at least that old.
            anchor = observed_at or window.get("evaluated_at") or window.get("last_eval")
            if anchor is None:
                return min(horizon, now)
            horizon = min(horizon, anchor + registry.staleness_cutoff(feed_id))
    return horizon


# ---------------------------------------------------------------------------
# rule 2: the seasonal-prior fallback score
# ---------------------------------------------------------------------------


def _top_claim_confidence(
    claim_rows: Sequence[Mapping[str, Any]], now: dt.datetime
) -> float | None:
    """Max decayed effective confidence over the affordance's served claims —
    the same corroboration-boosted math as good_now's top_claim lateral."""
    best: float | None = None
    for c in claim_rows:
        conf = scoring.sigmoid(c["log_odds"] + c["corroboration_nats"]) * scoring.decay_factor(
            c["cclass"], now - c["last_evidence_at"]
        )
        if best is None or conf > best:
            best = conf
    return best


def _seasonal_prior_score(
    affordance: Mapping[str, Any],
    window_rows: Sequence[Mapping[str, Any]],
    claim_rows: Sequence[Mapping[str, Any]],
    now: dt.datetime,
) -> float:
    """docs/04 §4 rule 2: the score a card may fall back to when the pack's
    live layer has expired. 0.0 encodes "never falls back":

    - hazard-class affordances (rule 3: never shown on priors alone);
    - affordances carrying any is_gate window — gates are multiplicative
      kill switches (docs/01 §7 Q1), and a prior fallback must not bypass
      one that could have gone false while offline;
    - a top claim under the serving bar (docs/01 §4 gate 2: pulled from
      serving is pulled from the fallback too).
    """
    if affordance["hazard_class"] or any(w["is_gate"] for w in window_rows):
        return 0.0
    confidence = _top_claim_confidence(claim_rows, now)
    if confidence is None or confidence < scoring.SERVING_CONFIDENCE_BAR:
        return 0.0
    multipliers = [
        float(w["multiplier"])
        for w in window_rows
        if w["wtype"] == "seasonal" and w["state"] is True
    ]
    return float(affordance["base_quality"]) * scoring.multiplier_product(multipliers) * confidence


# ---------------------------------------------------------------------------
# compile (DB -> artifact payloads)
# ---------------------------------------------------------------------------

_PLACES_SQL = text(
    """
    SELECT p.id, p.name, p.kind, p.elev_m, ST_Y(p.geom) AS lat, ST_X(p.geom) AS lng
    FROM places p
    WHERE NOT p.sensitive
    """
)

_ACTIVITIES_SQL = text("SELECT id, display_name, hazard_class FROM activities")

_AFFORDANCES_SQL = text(
    """
    SELECT a.id, a.place_id, a.activity_id, a.difficulty,
           EXTRACT(epoch FROM a.typical_duration) / 60 AS typical_duration_min,
           a.dog_ok, a.kid_ok, a.base_quality, act.hazard_class
    FROM affordances a
    JOIN places p ON p.id = a.place_id
    JOIN activities act ON act.id = a.activity_id
    WHERE a.status = 'published' AND NOT p.sensitive
    """
)

# Everything the registry knows about, minus the publisher pseudo-feed
# (health bookkeeping only — meaningless to a client).
_FEEDS_SQL = text(
    """
    SELECT id, provider, station_ref, parameter, unit,
           EXTRACT(epoch FROM poll_interval) AS poll_interval_s,
           last_value, last_observed_at
    FROM feeds
    WHERE provider IS DISTINCT FROM :publisher
    """
)

# The hazard confirm prong verbatim from the good_now materialization
# (run.py kill switch 2): power verifier, confirm verdict, published claim.
_POWER_CONFIRM_SQL = text(
    """
    SELECT c.affordance_id, MAX(v.verified_at) AS confirmed_at
    FROM verifications v
    JOIN claims c ON c.id = v.claim_id
    JOIN users u ON u.id = v.user_id
    WHERE v.verdict = 'confirm' AND u.power_verifier AND c.status = 'published'
      AND c.affordance_id IN :ids
    GROUP BY c.affordance_id
    """
).bindparams(bindparam("ids", expanding=True))

# good_now verbatim — but joined back to published affordances on
# non-sensitive places so a row whose place flipped sensitive (or whose
# affordance was suppressed) after materialization cannot leak even a bare id.
_GOOD_NOW_SQL = text(
    """
    SELECT gn.affordance_id, gn.now_score, gn.reasons, gn.computed_at
    FROM good_now gn
    JOIN affordances a ON a.id = gn.affordance_id
    JOIN places p ON p.id = a.place_id
    WHERE a.status = 'published' AND NOT p.sensitive
    """
)


def _window_feed_ids(predicate: Mapping[str, Any] | None) -> list[str]:
    return sorted(
        {str(leaf["feed"]) for leaf in iter_leaves(predicate or {}) if leaf.get("feed")}
    )


def _window_staleness_s(feed_ids: Sequence[str]) -> int | None:
    """The window's own freshness horizon: it evaluates unknown as soon as
    its *most perishable* feed goes stale (min, not max). None = calendar
    window, never stale."""
    if not feed_ids:
        return None
    return min(_seconds(registry.staleness_cutoff(fid)) for fid in feed_ids)


def compile_packs(
    conn: Connection, region: str, now: dt.datetime
) -> tuple[list[Artifact], dt.datetime]:
    """Query the graph + perishable state and build the three artifacts.

    Determinism contract (the golden test pins it): every list is sorted by
    id, every value is a plain JSON type, and no build-time timestamp enters
    the graph or claims payloads — republishing unchanged data must yield
    byte-identical hashed artifacts.
    """
    place_rows = conn.execute(_PLACES_SQL).mappings().all()
    activity_rows = conn.execute(_ACTIVITIES_SQL).mappings().all()
    aff_rows = conn.execute(_AFFORDANCES_SQL).mappings().all()
    aff_ids = [row["id"] for row in aff_rows]

    window_rows: list[Mapping[str, Any]] = []
    claims_by_aff: dict[Any, list[dict[str, Any]]] = {}
    confirm_rows: Sequence[Mapping[str, Any]] = []
    power_confirms: dict[Any, dt.datetime] = {}
    if aff_ids:
        window_rows = conn.execute(
            snapshots.WINDOW_STATES_SQL, {"ids": aff_ids, "at": None}
        ).mappings().all()
        claim_rows = conn.execute(cards.CLAIMS_SQL, {"ids": aff_ids}).mappings().all()
        claims_by_aff = cards.project_claims(claim_rows, now)
        confirm_rows = conn.execute(cards.LAST_CONFIRM_SQL, {"ids": aff_ids}).mappings().all()
        power_confirms = {
            row["affordance_id"]: row["confirmed_at"]
            for row in conn.execute(_POWER_CONFIRM_SQL, {"ids": aff_ids}).mappings()
        }
    feed_rows = conn.execute(_FEEDS_SQL, {"publisher": PUBLISHER_PROVIDER}).mappings().all()
    good_rows = conn.execute(_GOOD_NOW_SQL).mappings().all()

    windows_by_aff: dict[Any, list[Mapping[str, Any]]] = {}
    for row in window_rows:
        windows_by_aff.setdefault(row["affordance_id"], []).append(row)

    # --- graph: the interactive core ---------------------------------------
    graph_payload: dict[str, Any] = {
        "schema_version": PACK_SCHEMA_VERSION,
        "region": region,
        "places": sorted(
            (
                {
                    "id": str(row["id"]),
                    "name": row["name"],
                    "kind": row["kind"],
                    "elev_m": row["elev_m"],
                    "lat": _num(row["lat"]),
                    "lng": _num(row["lng"]),
                }
                for row in place_rows
            ),
            key=lambda item: item["id"],
        ),
        "activities": sorted(
            (
                {
                    "id": row["id"],
                    "display_name": row["display_name"],
                    "hazard_class": row["hazard_class"],
                }
                for row in activity_rows
            ),
            key=lambda item: item["id"],
        ),
        "affordances": sorted(
            (
                {
                    "id": str(row["id"]),
                    "place_id": str(row["place_id"]),
                    "activity_id": row["activity_id"],
                    "difficulty": row["difficulty"],
                    "typical_duration_min": _num(row["typical_duration_min"]),
                    "dog_ok": row["dog_ok"],
                    "kid_ok": row["kid_ok"],
                    "base_quality": _num(row["base_quality"]),
                }
                for row in aff_rows
            ),
            key=lambda item: item["id"],
        ),
        "windows": sorted(
            (
                {
                    "id": str(row["window_id"]),
                    "affordance_id": str(row["affordance_id"]),
                    "wtype": row["wtype"],
                    "is_gate": row["is_gate"],
                    "multiplier": _num(row["multiplier"]),
                    "predicate": row["predicate"],
                    "feeds": _window_feed_ids(row["predicate"]),
                    "staleness_cutoff_s": _window_staleness_s(
                        _window_feed_ids(row["predicate"])
                    ),
                }
                for row in window_rows
            ),
            key=lambda item: item["id"],
        ),
        "feeds": sorted(
            (
                {
                    "id": row["id"],
                    "provider": row["provider"],
                    "station_ref": row["station_ref"],
                    "parameter": row["parameter"],
                    "unit": row["unit"],
                    "poll_interval_s": _num(row["poll_interval_s"]),
                    "cadence_s": _seconds(registry.cadence_for(row["provider"])),
                    "staleness_cutoff_s": _seconds(registry.staleness_cutoff(row["provider"])),
                }
                for row in feed_rows
            ),
            key=lambda item: item["id"],
        ),
        # verified_at here is a *data* timestamp (a verification row), not a
        # build timestamp — it does not break republish determinism.
        "last_confirm": {
            str(row["affordance_id"]): {
                "verified_at": _iso(row["verified_at"]),
                "display_name": row["display_name"],
            }
            for row in confirm_rows
        },
        # Sourced from scoring.py so client-side confidence/decay math and
        # the build-side good_now math cannot drift apart.
        "constants": {
            "half_life_days": dict(scoring.HALF_LIFE_DAYS),
            "corroboration_nats": scoring.CORROBORATION_NATS,
            "corroboration_cap_nats": scoring.CORROBORATION_CAP_NATS,
            "serving_confidence_bar": scoring.SERVING_CONFIDENCE_BAR,
            "hazard_confirm_window_days": scoring.HAZARD_CONFIRM_WINDOW_DAYS,
            "staleness_factor": registry.STALENESS_FACTOR,
            "sweep_cadence_s": _seconds(registry.SWEEP_CADENCE),
        },
    }
    graph = make_artifact("graph", graph_payload)

    # --- claims: the belief layer -------------------------------------------
    # The request-time `confidence` field is deliberately dropped: it depends
    # on `now`, and the claims pack must hash identically across sweeps when
    # no claim changed. The client re-derives it from log_odds +
    # corroboration_nats + last_evidence_at + the graph constants block.
    claim_items: list[dict[str, Any]] = []
    for aff_claims in claims_by_aff.values():
        for c in aff_claims:
            claim_items.append(
                {
                    "id": str(c["id"]),
                    "affordance_id": str(c["affordance_id"]),
                    "cclass": c["cclass"],
                    "source_type": c["source_type"],
                    "source_domain": c["source_domain"],
                    "source_url": c["source_url"],
                    "observed_date": _iso(c["observed_date"]),
                    "log_odds": c["log_odds"],
                    "corroboration_nats": c["corroboration_nats"],
                    "last_evidence_at": _iso(c["last_evidence_at"]),
                }
            )
    claim_items.sort(key=lambda item: (item["affordance_id"], item["id"]))
    claims_artifact = make_artifact(
        "claims",
        {"schema_version": PACK_SCHEMA_VERSION, "region": region, "claims": claim_items},
    )

    # --- conditions: the perishable layer ------------------------------------
    expires_at = now + registry.STALENESS_FACTOR * registry.SWEEP_CADENCE  # rule 1
    seasonal_priors: dict[str, float] = {}
    hazard_walls: dict[str, str] = {}
    for row in aff_rows:
        aff_windows = windows_by_aff.get(row["id"], [])
        aff_claims = claims_by_aff.get(row["id"], [])
        seasonal_priors[str(row["id"])] = round(
            _seasonal_prior_score(row, aff_windows, aff_claims, now), 6
        )
        if row["hazard_class"]:
            wall = hazard_serve_until(
                now,
                power_confirms.get(row["id"]),
                [w for w in aff_windows if w["is_gate"]],
            )
            hazard_walls[str(row["id"])] = wall.isoformat()

    conditions_payload: dict[str, Any] = {
        "schema_version": PACK_SCHEMA_VERSION,
        "region": region,
        "generated_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "sweep_cadence_s": _seconds(registry.SWEEP_CADENCE),
        # The graph build this state was computed against: a client holding a
        # different graph generation must refetch, not join across skew.
        "graph_build": graph.sha256,
        "windows": {
            str(row["window_id"]): {
                "state": row["state"],
                "state_since": _iso(row["state_since"]),
                "last_eval": _iso(row["last_eval"]),
                "inputs": row["inputs"],
                "staleness_cutoff_s": _window_staleness_s(_window_feed_ids(row["predicate"])),
            }
            for row in window_rows
        },
        "feeds": {
            row["id"]: {
                "last_value": _num(row["last_value"]),
                "last_observed_at": _iso(row["last_observed_at"]),
            }
            for row in feed_rows
        },
        "good_now": sorted(
            (
                {
                    "affordance_id": str(row["affordance_id"]),
                    "now_score": _num(row["now_score"]),
                    "reasons": row["reasons"],
                    "computed_at": _iso(row["computed_at"]),
                }
                for row in good_rows
            ),
            key=lambda item: item["affordance_id"],
        ),
        "seasonal_prior_score": seasonal_priors,
        "hazard_serve_until": hazard_walls,
    }
    conditions = make_artifact("conditions", conditions_payload)

    return [graph, claims_artifact, conditions], expires_at


# ---------------------------------------------------------------------------
# write (atomic generation swap + pruning)
# ---------------------------------------------------------------------------


def _write_bytes(path: Path, data: bytes) -> None:
    """tmp-write + fsync + os.replace: readers only ever see complete files."""
    tmp = path.with_name(f"{path.name}.tmp{os.getpid()}")
    try:
        with open(tmp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _prune(region_dir: Path, referenced: set[str], generations: int = KEEP_GENERATIONS) -> None:
    """Keep the newest `generations` files per artifact class; never touch a
    file the just-written manifest references, however old its mtime."""
    for kind in ARTIFACT_KINDS:
        candidates = sorted(
            region_dir.glob(f"{kind}-*.json.br"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        budget = generations - sum(1 for p in candidates if p.name in referenced)
        for path in candidates:
            if path.name in referenced:
                continue
            if budget > 0:
                budget -= 1
                continue
            with contextlib.suppress(FileNotFoundError):
                path.unlink()


def write_generation(
    region_dir: Path,
    region: str,
    artifacts: Sequence[Artifact],
    *,
    now: dt.datetime,
    expires_at: dt.datetime,
    graph_build: str,
) -> dict[str, Any]:
    """Land one publish generation atomically and return its manifest.

    Order matters for crash safety: content-hashed files land (and are
    durable) before the manifest swap, so a crash at any point leaves
    manifest.json — old or new — pointing only at complete, present files.
    """
    region_dir.mkdir(parents=True, exist_ok=True)
    for artifact in artifacts:
        target = region_dir / artifact.filename
        if not target.exists():  # content-addressed: same name == same bytes
            _write_bytes(target, artifact.data)
    _fsync_dir(region_dir)

    manifest: dict[str, Any] = {
        "schema_version": PACK_SCHEMA_VERSION,
        "region": region,
        "published_at": now.isoformat(),
        "artifacts": {
            artifact.kind: {
                "url": f"/packs/{region}/{artifact.filename}",
                "sha256": artifact.sha256,
                "bytes": len(artifact.data),
                "generated_at": now.isoformat(),
            }
            for artifact in artifacts
        },
        "conditions": {
            "expires_at": expires_at.isoformat(),
            "sweep_cadence_s": _seconds(registry.SWEEP_CADENCE),
            "graph_build": graph_build,
        },
    }
    _write_bytes(
        region_dir / "manifest.json",
        json.dumps(manifest, sort_keys=True, indent=2).encode() + b"\n",
    )
    _fsync_dir(region_dir)

    _prune(region_dir, {artifact.filename for artifact in artifacts})
    return manifest


def publish_packs(
    engine: Engine,
    *,
    settings: Settings | None = None,
    now: dt.datetime | None = None,
) -> PublishResult:
    """Compile and land one pack generation for the configured region."""
    settings = settings or get_settings()
    now = now or dt.datetime.now(dt.UTC)
    with engine.connect() as conn:
        artifacts, expires_at = compile_packs(conn, settings.region_slug, now)
    graph_build = next(a.sha256 for a in artifacts if a.kind == "graph")
    region_dir = Path(settings.packs_dir) / settings.region_slug
    manifest = write_generation(
        region_dir,
        settings.region_slug,
        artifacts,
        now=now,
        expires_at=expires_at,
        graph_build=graph_build,
    )
    log.info(
        "published packs %s: %s",
        region_dir,
        ", ".join(f"{a.kind}={a.sha256[:12]} ({len(a.data)}B)" for a in artifacts),
    )
    return PublishResult(region_dir=region_dir, manifest=manifest, artifacts=tuple(artifacts))
