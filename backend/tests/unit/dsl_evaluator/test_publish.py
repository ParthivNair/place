"""Pure-function tests for the pack compiler (evaluator/publish.py):
hazard_serve_until math (docs/04 §4 rule 3 as a wall-clock wall), canonical
serialization determinism, and the crash-safe write/prune pattern. No DB —
the DB-facing half is covered by tests/integration/test_pack_publish.py."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os

import brotli
import pytest

from place import scoring
from place.evaluator import publish

NOW = dt.datetime(2026, 7, 6, 12, 0, tzinfo=dt.UTC)
FLOW = "usgs_nwis:14210000:00060"  # staleness cutoff 2 x 15 min = 30 min
TEMP = "open_meteo:45.44,-122.62:air_temp_f"  # cutoff 2 x 1 h = 2 h


def _gate(state, inputs, predicate=None, evaluated_at=None):
    return {
        "state": state,
        "predicate": predicate if predicate is not None else {"feed": FLOW, "op": "<", "value": 1},
        "inputs": inputs,
        "evaluated_at": evaluated_at,
        "last_eval": evaluated_at,
    }


def _reading(value, observed_at):
    return {"value": value, "observed_at": observed_at.isoformat()}


# ---------------------------------------------------------------------------
# hazard_serve_until
# ---------------------------------------------------------------------------


def test_no_power_confirm_walls_at_now():
    # rule 3: a hazard card never serves on priors alone
    assert publish.hazard_serve_until(NOW, None, []) == NOW


def test_confirm_horizon_without_gates():
    confirm = NOW - dt.timedelta(days=5)
    expected = confirm + dt.timedelta(days=scoring.HAZARD_CONFIRM_WINDOW_DAYS)
    assert publish.hazard_serve_until(NOW, confirm, []) == expected


def test_gate_staleness_horizon_wins_over_confirm():
    # fresh confirm (now-5d + 60d ~ now+55d) vs flow reading observed 10 min
    # ago with a 30-min cutoff: the gate prong walls first, at now+20min.
    confirm = NOW - dt.timedelta(days=5)
    observed = NOW - dt.timedelta(minutes=10)
    gate = _gate(True, {FLOW: _reading(900.0, observed)})
    wall = publish.hazard_serve_until(NOW, confirm, [gate])
    assert wall == observed + dt.timedelta(minutes=30)


def test_confirm_horizon_wins_when_older_than_gate():
    # 10 min of confirm budget left vs 29 min of gate budget: confirm walls
    confirm = NOW - dt.timedelta(days=scoring.HAZARD_CONFIRM_WINDOW_DAYS) + dt.timedelta(minutes=10)
    observed = NOW - dt.timedelta(minutes=1)
    gate = _gate(True, {FLOW: _reading(900.0, observed)})
    wall = publish.hazard_serve_until(NOW, confirm, [gate])
    assert wall == confirm + dt.timedelta(days=scoring.HAZARD_CONFIRM_WINDOW_DAYS)
    assert wall == NOW + dt.timedelta(minutes=10)


def test_untrue_or_unknown_gate_walls_at_now():
    confirm = NOW - dt.timedelta(days=5)
    for state in (False, None):
        gate = _gate(state, {FLOW: _reading(900.0, NOW)})
        assert publish.hazard_serve_until(NOW, confirm, [gate]) <= NOW


def test_expired_confirm_stays_in_the_past_even_with_untrue_gate():
    # min(horizon, now) must not "revive" an already-expired confirm prong
    confirm = NOW - dt.timedelta(days=90)
    gate = _gate(False, {})
    wall = publish.hazard_serve_until(NOW, confirm, [gate])
    assert wall == confirm + dt.timedelta(days=scoring.HAZARD_CONFIRM_WINDOW_DAYS)
    assert wall < NOW


def test_multi_feed_gate_takes_most_perishable_bound():
    confirm = NOW - dt.timedelta(days=5)
    gate = _gate(
        True,
        {
            FLOW: _reading(900.0, NOW - dt.timedelta(minutes=5)),
            TEMP: _reading(80.0, NOW - dt.timedelta(minutes=5)),
        },
        predicate={"all": [
            {"feed": FLOW, "op": "<", "value": 1050},
            {"feed": TEMP, "op": ">", "value": 75},
        ]},
    )
    # flow: -5min + 30min = +25min; temp: -5min + 2h = +115min -> flow wins
    wall = publish.hazard_serve_until(NOW, confirm, [gate])
    assert wall == NOW + dt.timedelta(minutes=25)


def test_calendar_gate_contributes_no_staleness_bound():
    confirm = NOW - dt.timedelta(days=5)
    gate = _gate(True, {"month": 7}, predicate={"month": [6, 9]})
    wall = publish.hazard_serve_until(NOW, confirm, [gate])
    assert wall == confirm + dt.timedelta(days=scoring.HAZARD_CONFIRM_WINDOW_DAYS)


def test_missing_observed_at_falls_back_to_evaluated_at():
    confirm = NOW - dt.timedelta(days=5)
    evaluated = NOW - dt.timedelta(minutes=12)
    gate = _gate(True, {FLOW: 900.0}, evaluated_at=evaluated)  # bare scalar input
    wall = publish.hazard_serve_until(NOW, confirm, [gate])
    assert wall == evaluated + dt.timedelta(minutes=30)


def test_unanchorable_gate_reading_walls_at_now():
    confirm = NOW - dt.timedelta(days=5)
    gate = _gate(True, {})  # gate true but no input and no evaluated_at
    assert publish.hazard_serve_until(NOW, confirm, [gate]) <= NOW


# ---------------------------------------------------------------------------
# canonical serialization + artifact naming
# ---------------------------------------------------------------------------


def test_artifact_hash_is_key_order_independent():
    a = publish.make_artifact("graph", {"b": 1, "a": {"y": [1, 2], "x": None}})
    b = publish.make_artifact("graph", {"a": {"x": None, "y": [1, 2]}, "b": 1})
    assert a.sha256 == b.sha256
    assert a.filename == f"graph-{a.sha256[:12]}.json.br"
    assert json.loads(brotli.decompress(a.data)) == {"b": 1, "a": {"y": [1, 2], "x": None}}


def test_canonical_json_refuses_non_plain_types():
    # no default= coercion hook: a Decimal/UUID reaching serialization is a
    # compile bug, and silent coercion is where hash nondeterminism creeps in
    with pytest.raises(TypeError):
        publish.canonical_json({"when": NOW})


def test_write_generation_manifest_verifies(tmp_path):
    arts, manifest = _publish_generation(tmp_path, version=1)
    for kind, entry in manifest["artifacts"].items():
        path = tmp_path / entry["url"].rsplit("/", 1)[-1]
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        assert len(data) == entry["bytes"]
        payload = json.loads(brotli.decompress(data))
        assert payload["kind"] == kind
    assert manifest["conditions"]["graph_build"] == arts[0].sha256


def _publish_generation(region_dir, version: int):
    arts = [
        publish.make_artifact(kind, {"kind": kind, "version": version})
        for kind in publish.ARTIFACT_KINDS
    ]
    manifest = publish.write_generation(
        region_dir, "pdx", arts,
        now=NOW + dt.timedelta(minutes=version),
        expires_at=NOW + dt.timedelta(minutes=version, hours=1),
        graph_build=arts[0].sha256,
    )
    return arts, manifest


def test_prune_keeps_last_three_generations(tmp_path):
    for version in range(1, 6):
        arts, _ = _publish_generation(tmp_path, version)
        # distinct mtimes so "newest" is well-defined on coarse filesystems
        for a in arts:
            os.utime(tmp_path / a.filename, (NOW.timestamp() + version,) * 2)
    for kind in publish.ARTIFACT_KINDS:
        remaining = sorted(p.name for p in tmp_path.glob(f"{kind}-*.json.br"))
        assert len(remaining) == publish.KEEP_GENERATIONS
    # the current generation always survives
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    for entry in manifest["artifacts"].values():
        assert (tmp_path / entry["url"].rsplit("/", 1)[-1]).exists()


def test_crash_before_manifest_swap_leaves_old_generation_valid(tmp_path, monkeypatch):
    _, manifest_v1 = _publish_generation(tmp_path, version=1)

    real_replace = os.replace

    def crash_on_manifest(src, dst):
        if str(dst).endswith("manifest.json"):
            raise OSError("simulated crash before manifest swap")
        real_replace(src, dst)

    monkeypatch.setattr(publish.os, "replace", crash_on_manifest)
    with pytest.raises(OSError, match="simulated crash"):
        _publish_generation(tmp_path, version=2)
    monkeypatch.undo()

    # old manifest untouched, and every file it references is still present
    # and hash-valid — a client mid-refresh never sees a broken generation
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest == manifest_v1
    for entry in manifest["artifacts"].values():
        path = tmp_path / entry["url"].rsplit("/", 1)[-1]
        assert path.exists()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
    # no stray tmp files leak from the failed swap
    assert not list(tmp_path.glob("*.tmp*"))
