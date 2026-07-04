"""Entity resolution — free-text place_ref -> canonical place (docs/03 §2 stage 3).

The model's ``place_ref`` is free text; the graph needs a canonical place.
Resolution strategy, in order:

1. Candidate generation: pg_trgm name similarity against ``places.name``,
   optionally blended with geographic proximity to a hint point (keyless —
   always available).
2. Embedding rerank against ``places.name_embedding`` (pgvector) — ONLY when
   an embedding backend is available, which is key-gated. The interface is
   pluggable (:class:`Embedder`); without a key resolution degrades cleanly
   to step 1.
3. Confidence bar: matches below the bar go to the human queue rather than
   guessing — a claim attached to the wrong waterfall is worse than a
   discarded claim. Unresolved claims are PARKED with ``place_ref``
   preserved verbatim (they also signal places the skeleton is missing).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import Connection, text
from sqlalchemy.engine import Engine

from place.config import Settings, get_settings

log = logging.getLogger(__name__)

# Conservative bars — favor the review queue over wrong attachment.
MIN_SIMILARITY = 0.45
MIN_MARGIN = 0.08
CANDIDATE_LIMIT = 10
# Beyond this the proximity bonus is zero; inside it, bonus scales linearly.
PROXIMITY_RADIUS_M = 50_000.0
PROXIMITY_WEIGHT = 0.10
EMBEDDING_WEIGHT = 0.5

UNRESOLVED_FILENAME = "unresolved.jsonl"


@dataclass(frozen=True)
class Candidate:
    place_id: uuid.UUID
    name: str
    kind: str
    similarity: float
    distance_m: float | None = None
    embedding_distance: float | None = None  # cosine distance in [0, 2]

    @property
    def score(self) -> float:
        """Blend of trigram similarity, proximity, and (if set) embeddings."""
        score = self.similarity
        if self.distance_m is not None:
            closeness = max(0.0, 1.0 - self.distance_m / PROXIMITY_RADIUS_M)
            score += PROXIMITY_WEIGHT * closeness
        if self.embedding_distance is not None:
            # cosine distance -> similarity in [0, 1]
            score = (1 - EMBEDDING_WEIGHT) * score + EMBEDDING_WEIGHT * (
                1.0 - min(self.embedding_distance, 2.0) / 2.0
            )
        return score


# ---------------------------------------------------------------------------
# pluggable, key-gated embedding rerank
# ---------------------------------------------------------------------------


class Embedder(Protocol):
    """Anything that can embed short texts to the places.name_embedding space."""

    def embed(self, texts: list[str]) -> list[list[float]]: ...


_registered_embedder: Embedder | None = None


def register_embedder(embedder: Embedder | None) -> None:
    """Plug in an embedding backend (called by whoever owns the provider)."""
    global _registered_embedder
    _registered_embedder = embedder


def get_embedder(settings: Settings | None = None) -> Embedder | None:
    """Return the embedding backend, or None (keyless fallback engages).

    Gated on ANTHROPIC_API_KEY per the build contract; even with the key
    present, a concrete backend must have been registered — the Anthropic
    API itself exposes no embeddings endpoint, so the provider is pluggable.
    """
    settings = settings or get_settings()
    if not settings.anthropic_api_key:
        return None
    if _registered_embedder is None:
        log.info("embedding key present but no embedder registered; using pg_trgm only")
    return _registered_embedder


# ---------------------------------------------------------------------------
# candidate generation (keyless: pg_trgm + geo proximity)
# ---------------------------------------------------------------------------

_CANDIDATE_SQL = text(
    """
    SELECT id, name, kind,
           similarity(name, :ref) AS sim,
           CASE WHEN :use_near
                THEN ST_DistanceSphere(
                        geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
           END AS distance_m
      FROM places
     WHERE similarity(name, :ref) >= :min_sim
     ORDER BY sim DESC
     LIMIT :lim
    """
)


def find_candidates(
    conn: Connection,
    place_ref: str,
    *,
    near: tuple[float, float] | None = None,  # (lon, lat) hint
    min_similarity: float = 0.25,
    limit: int = CANDIDATE_LIMIT,
) -> list[Candidate]:
    rows = conn.execute(
        _CANDIDATE_SQL,
        {
            "ref": place_ref,
            "min_sim": min_similarity,
            "lim": limit,
            "use_near": near is not None,
            "lon": near[0] if near else 0.0,
            "lat": near[1] if near else 0.0,
        },
    ).all()
    return [
        Candidate(
            place_id=r.id,
            name=r.name,
            kind=r.kind,
            similarity=float(r.sim),
            distance_m=float(r.distance_m) if r.distance_m is not None else None,
        )
        for r in rows
    ]


def rerank_with_embeddings(
    conn: Connection, place_ref: str, candidates: list[Candidate], embedder: Embedder
) -> list[Candidate]:
    """Attach pgvector cosine distances for candidates that carry embeddings."""
    if not candidates:
        return candidates
    qvec = embedder.embed([place_ref])[0]
    rows = conn.execute(
        text(
            """
            SELECT id, (name_embedding <=> CAST(:vec AS vector)) AS edist
              FROM places
             WHERE id = ANY(:ids) AND name_embedding IS NOT NULL
            """
        ),
        {"vec": "[" + ",".join(f"{x:.6f}" for x in qvec) + "]",
         "ids": [c.place_id for c in candidates]},
    ).all()
    distances = {r.id: float(r.edist) for r in rows}
    return [
        replace(c, embedding_distance=distances.get(c.place_id))
        for c in candidates
    ]


def pick_best(
    candidates: list[Candidate],
    *,
    min_similarity: float = MIN_SIMILARITY,
    min_margin: float = MIN_MARGIN,
) -> Candidate | None:
    """Pure decision rule: confident single winner or nothing.

    Requires the winner to clear the similarity bar AND beat the runner-up
    by a margin — ambiguity goes to the human queue, not to a coin flip.
    """
    if not candidates:
        return None
    ranked = sorted(candidates, key=lambda c: c.score, reverse=True)
    best = ranked[0]
    if best.similarity < min_similarity:
        return None
    if len(ranked) > 1 and best.score - ranked[1].score < min_margin:
        return None
    return best


# ---------------------------------------------------------------------------
# claim attachment + parking
# ---------------------------------------------------------------------------


def park_unresolved(row: dict[str, Any], reason: str, path: Path) -> None:
    """Append the claim row (place_ref preserved verbatim) to the parked file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    record = dict(row)
    record["unresolved_reason"] = reason
    record["parked_at"] = dt.datetime.now(dt.UTC).isoformat()
    with path.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _get_or_create_affordance(
    conn: Connection, place_id: uuid.UUID, activity_id: str
) -> uuid.UUID:
    existing = conn.execute(
        text("SELECT id FROM affordances WHERE place_id = :p AND activity_id = :a"),
        {"p": place_id, "a": activity_id},
    ).scalar()
    if existing is not None:
        return existing
    # New affordances born from extraction start at 'draft' — publication
    # gates (docs/01 §4) decide anything further.
    return conn.execute(
        text(
            """
            INSERT INTO affordances (place_id, activity_id, status)
            VALUES (:p, :a, 'draft') RETURNING id
            """
        ),
        {"p": place_id, "a": activity_id},
    ).scalar_one()


def _insert_claim(conn: Connection, affordance_id: uuid.UUID, row: dict[str, Any]) -> uuid.UUID:
    observed = row.get("observed_date")
    if isinstance(observed, str):
        observed = dt.date.fromisoformat(observed)
    return conn.execute(
        text(
            """
            INSERT INTO claims
                (affordance_id, cclass, stype, source_url, source_domain,
                 quote_internal, observed_date, extractor_ver, self_conf,
                 status, log_odds)
            VALUES
                (:affordance_id, :cclass, :stype, :source_url, :source_domain,
                 :quote_internal, :observed_date, :extractor_ver, :self_conf,
                 :status, :log_odds)
            RETURNING id
            """
        ),
        {
            "affordance_id": affordance_id,
            "cclass": row["cclass"],
            "stype": row["stype"],
            "source_url": row["source_url"],
            "source_domain": row["source_domain"],
            "quote_internal": row["quote_internal"],
            "observed_date": observed,
            "extractor_ver": row["extractor_ver"],
            "self_conf": row["self_conf"],
            "status": row["status"],
            "log_odds": row["log_odds"],
        },
    ).scalar_one()


def resolve_claim_row(
    conn: Connection,
    row: dict[str, Any],
    *,
    embedder: Embedder | None = None,
    near: tuple[float, float] | None = None,
    unresolved_path: Path | None = None,
) -> uuid.UUID | None:
    """Resolve one extracted claim row; insert it or park it.

    Returns the inserted claim id, or None when parked.
    """
    unresolved_path = unresolved_path or (
        get_settings().data_cache_dir / "extracted" / UNRESOLVED_FILENAME
    )
    activity_ok = conn.execute(
        text("SELECT 1 FROM activities WHERE id = :a"), {"a": row["activity"]}
    ).scalar()
    if not activity_ok:
        park_unresolved(row, f"unknown activity {row['activity']!r}", unresolved_path)
        return None

    candidates = find_candidates(conn, row["place_ref"], near=near)
    if embedder is not None:
        candidates = rerank_with_embeddings(conn, row["place_ref"], candidates, embedder)
    best = pick_best(candidates)
    if best is None:
        park_unresolved(row, "no confident place match", unresolved_path)
        return None

    affordance_id = _get_or_create_affordance(conn, best.place_id, row["activity"])
    claim_id = _insert_claim(conn, affordance_id, row)
    log.info(
        "resolved %r -> place %s (%s, sim=%.2f) claim %s",
        row["place_ref"], best.place_id, best.name, best.similarity, claim_id,
    )
    return claim_id


def resolve_extracted(
    engine: Engine,
    *,
    extracted_dir: Path | None = None,
    embedder: Embedder | None = None,
    near: tuple[float, float] | None = None,
) -> dict[str, int]:
    """Resolve every claim row stored by the worker; returns summary counts."""
    settings = get_settings()
    extracted_dir = extracted_dir or settings.data_cache_dir / "extracted"
    unresolved_path = extracted_dir / UNRESOLVED_FILENAME
    if embedder is None:
        embedder = get_embedder(settings)
    resolved = parked = 0
    with engine.begin() as conn:
        for path in sorted(extracted_dir.rglob("*.json")):
            record = json.loads(path.read_text())
            for row in record.get("claims", []):
                claim_id = resolve_claim_row(
                    conn, row, embedder=embedder, near=near, unresolved_path=unresolved_path
                )
                if claim_id is None:
                    parked += 1
                else:
                    resolved += 1
    summary = {"resolved": resolved, "parked": parked}
    log.info("resolution complete: %s", summary)
    return summary
