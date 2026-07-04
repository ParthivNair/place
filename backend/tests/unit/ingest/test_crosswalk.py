"""Pure entity-resolution matching (the keyless trgm+distance fallback)."""

from __future__ import annotations

import uuid

from place.ingest.crosswalk import (
    Candidate,
    normalize_name,
    pick_match,
    trigram_similarity,
)

LATOURELL = (45.5372, -122.2178)


def _cand(name: str, lat: float, lng: float) -> Candidate:
    return Candidate(uuid.uuid4(), name, lat, lng)


class TestNormalizeName:
    def test_lowercases_and_strips_punctuation(self):
        assert normalize_name("Angel's Rest Trailhead") == "angel s rest trailhead"

    def test_drops_generic_tokens_and_collapses_space(self):
        assert normalize_name("Falls of the  Columbia") == "falls columbia"


class TestTrigramSimilarity:
    def test_identical_names_are_1(self):
        assert trigram_similarity("Latourell Falls", "Latourell Falls") == 1.0

    def test_case_and_punctuation_insensitive(self):
        assert trigram_similarity("LATOURELL FALLS", "Latourell Falls") == 1.0

    def test_unrelated_names_are_low(self):
        assert trigram_similarity("Latourell Falls", "Haystack Rock") < 0.1

    def test_shared_word_partial(self):
        sim = trigram_similarity("Upper Latourell Falls", "Latourell Falls")
        assert 0.4 < sim < 1.0

    def test_empty_is_zero(self):
        assert trigram_similarity("", "Latourell Falls") == 0.0


class TestPickMatch:
    def test_same_falls_from_two_sources_resolves(self):
        """GNIS 'Latourell Falls' lands ~120 m from the OSM node -> merge."""
        osm = _cand("Latourell Falls", *LATOURELL)
        got = pick_match("Latourell Falls", 45.5382, -122.2172, [osm])
        assert got is osm

    def test_same_name_too_far_apart_does_not_merge(self):
        """Two 'Horsetail Falls' 30 km apart are different falls."""
        other = _cand("Horsetail Falls", 45.59, -122.115)
        assert pick_match("Horsetail Falls", 45.35, -121.9, [other]) is None

    def test_nearby_but_different_name_does_not_merge(self):
        """Upper/Lower pairs on the same creek stay distinct places."""
        lower = _cand("Latourell Falls", *LATOURELL)
        got = pick_match("Henderson Creek Falls", 45.5379, -122.2180, [lower])
        assert got is None

    def test_best_of_several_candidates_wins(self):
        exact = _cand("Wahclella Falls", 45.6284, -121.9540)
        fuzzy = _cand("Wahclella Falls Viewpoint", 45.6290, -121.9545)
        got = pick_match("Wahclella Falls", 45.6285, -121.9541, [fuzzy, exact])
        assert got is exact

    def test_distance_breaks_similarity_ties(self):
        near = _cand("Blue Lake", 45.554, -122.449)
        far = _cand("Blue Lake", 45.559, -122.452)
        got = pick_match("Blue Lake", 45.5541, -122.4491, [far, near])
        assert got is near
