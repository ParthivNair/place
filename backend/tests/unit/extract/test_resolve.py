"""Entity resolution: pure decision rule, parking, and embedder gating."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from place.config import Settings
from place.extract import resolve
from place.extract.resolve import (
    Candidate,
    get_embedder,
    park_unresolved,
    pick_best,
    register_embedder,
)


def cand(name: str, sim: float, dist: float | None = None, edist: float | None = None):
    return Candidate(
        place_id=uuid.uuid4(),
        name=name,
        kind="waterfall",
        similarity=sim,
        distance_m=dist,
        embedding_distance=edist,
    )


def test_no_candidates_is_none() -> None:
    assert pick_best([]) is None


def test_below_similarity_bar_is_none() -> None:
    assert pick_best([cand("Latourell Falls", 0.3)]) is None


def test_clear_winner_is_picked() -> None:
    winner = cand("Latourell Falls", 0.9)
    assert pick_best([winner, cand("Lancaster Falls", 0.5)]) is winner


def test_ambiguous_margin_goes_to_review_queue() -> None:
    # wrong waterfall is worse than a discarded claim
    a, b = cand("Upper Latourell Falls", 0.71), cand("Latourell Falls", 0.70)
    assert pick_best([a, b]) is None


def test_single_confident_candidate_wins() -> None:
    only = cand("Elowah Falls", 0.6)
    assert pick_best([only]) is only


def test_proximity_bonus_breaks_name_ties() -> None:
    near = cand("Falls Creek Falls", 0.62, dist=1_000.0)
    far = cand("Fall Creek Falls", 0.62, dist=200_000.0)
    best = pick_best([near, far])
    assert best is near


def test_embedding_distance_reranks() -> None:
    lexical = cand("Eagle Creek", 0.66, edist=1.2)  # lexically close, semantically off
    semantic = cand("Punchbowl Falls", 0.60, edist=0.05)
    assert semantic.score > lexical.score


def test_park_unresolved_preserves_place_ref(tmp_path: Path) -> None:
    row = {
        "place_ref": "the falls past the second bridge on Eagle Creek",
        "activity": "waterfall_view",
        "cclass": "geomorphic",
        "status": "review",
    }
    path = tmp_path / "unresolved.jsonl"
    park_unresolved(row, "no confident place match", path)
    park_unresolved(row, "no confident place match", path)
    lines = path.read_text().splitlines()
    assert len(lines) == 2
    parked = json.loads(lines[0])
    assert parked["place_ref"] == row["place_ref"]
    assert parked["unresolved_reason"] == "no confident place match"
    assert parked["parked_at"]


# -- embedder gating ---------------------------------------------------------


def test_get_embedder_is_none_without_key() -> None:
    assert get_embedder(Settings(_env_file=None)) is None


def test_get_embedder_requires_registration_even_with_key() -> None:
    register_embedder(None)
    assert get_embedder(Settings(_env_file=None, anthropic_api_key="k")) is None


def test_registered_embedder_is_returned_only_with_key() -> None:
    class FakeEmbedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.0] * 1024 for _ in texts]

    fake = FakeEmbedder()
    register_embedder(fake)
    try:
        assert get_embedder(Settings(_env_file=None, anthropic_api_key="k")) is fake
        assert get_embedder(Settings(_env_file=None)) is None  # key gate holds
    finally:
        register_embedder(None)
    assert resolve._registered_embedder is None
