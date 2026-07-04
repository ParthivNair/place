"""Launch-bindings loader: backend/data/bindings/launch.yaml -> the graph.

Idempotent end to end:
- activities.yaml upserts the closed activity vocabulary (hazard_class flags);
- each binding creates-if-missing its place (crosswalk name+distance match,
  so a binding lands on the OSM/GNIS-seeded row instead of duplicating it),
  upserts the affordance (natural key: place_id+activity_id), and upserts
  condition windows (natural key: affordance_id+wtype+is_gate — thresholds
  in the yaml update the existing window's predicate rather than adding one);
- feed rows referenced by predicates are upserted (never clobbering
  last_value/last_observed_at the evaluator maintains).

Validation happens before any write: predicate grammar (docs/01 §3 plus the
`months` seasonal leaf), every referenced feed declared, and the safe-side
hysteresis rule on is_gate windows (`value` conservative entry, `exit_value`
the hard bound on the far side — a mis-banded hazard gate refuses to load).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import Connection, text

log = logging.getLogger(__name__)

_REPO_BACKEND = Path(__file__).resolve().parent.parent.parent
DEFAULT_BINDINGS_PATH = _REPO_BACKEND / "data" / "bindings" / "launch.yaml"
DEFAULT_ACTIVITIES_PATH = _REPO_BACKEND / "data" / "activities.yaml"

_OPS = {"<", "<=", ">", ">=", "=", "between"}
_AGGS = {"latest", "sum", "min", "max"}
_WTYPES = {"seasonal", "weather_triggered", "hydrological", "tidal", "astronomical", "snow"}


class BindingError(ValueError):
    """launch.yaml failed validation; nothing was written."""


# ---------------------------------------------------------------------------
# validation (pure — unit-testable without a database)
# ---------------------------------------------------------------------------


def _validate_leaf(leaf: dict, known_feeds: set[str], is_gate: bool, ctx: str) -> None:
    if "months" in leaf:
        months = leaf["months"]
        if (
            not isinstance(months, list)
            or not months
            or not all(isinstance(m, int) and 1 <= m <= 12 for m in months)
        ):
            raise BindingError(f"{ctx}: months leaf must be a non-empty list of 1..12")
        extra = set(leaf) - {"months"}
        if extra:
            raise BindingError(f"{ctx}: unexpected keys on months leaf: {sorted(extra)}")
        return

    feed = leaf.get("feed")
    if not feed:
        raise BindingError(f"{ctx}: leaf needs a 'feed' (or 'months')")
    if feed not in known_feeds:
        raise BindingError(f"{ctx}: feed {feed!r} not declared in the feeds section")
    op = leaf.get("op")
    if op not in _OPS:
        raise BindingError(f"{ctx}: bad op {op!r}")
    value = leaf.get("value")
    if op == "between":
        if not (isinstance(value, list) and len(value) == 2):
            raise BindingError(f"{ctx}: 'between' takes value [lo, hi]")
    elif not isinstance(value, int | float):
        raise BindingError(f"{ctx}: value must be a number")
    agg = leaf.get("agg", "latest")
    if agg not in _AGGS:
        raise BindingError(f"{ctx}: bad agg {agg!r}")
    if agg != "latest" and not isinstance(leaf.get("window_h"), int):
        raise BindingError(f"{ctx}: agg={agg} requires integer window_h")

    exit_value = leaf.get("exit_value")
    if exit_value is not None:
        if not isinstance(exit_value, int | float):
            raise BindingError(f"{ctx}: exit_value must be a number")
        if op in {"=", "between"}:
            raise BindingError(f"{ctx}: exit_value is meaningless with op {op!r}")
        # Hysteresis band must sit past the entry threshold; on gates this is
        # the safe-side rule (docs/01 §3): value = conservative entry,
        # exit_value = earned hard bound.
        if op in {"<", "<="} and not exit_value > value:
            raise BindingError(
                f"{ctx}: exit_value must exceed value for op {op!r} "
                f"(safe-side hysteresis{' on is_gate' if is_gate else ''})"
            )
        if op in {">", ">="} and not exit_value < value:
            raise BindingError(
                f"{ctx}: exit_value must be below value for op {op!r} "
                f"(safe-side hysteresis{' on is_gate' if is_gate else ''})"
            )


def validate_predicate(node: Any, known_feeds: set[str], is_gate: bool, ctx: str) -> None:
    """Recursive grammar check for one predicate tree."""
    if not isinstance(node, dict):
        raise BindingError(f"{ctx}: predicate nodes must be objects")
    combinators = [k for k in ("all", "any", "not") if k in node]
    if len(combinators) > 1:
        raise BindingError(f"{ctx}: node mixes {combinators}")
    if combinators:
        key = combinators[0]
        if set(node) != {key}:
            raise BindingError(f"{ctx}: combinator node must have only {key!r}")
        if key == "not":
            validate_predicate(node["not"], known_feeds, is_gate, ctx)
        else:
            kids = node[key]
            if not isinstance(kids, list) or not kids:
                raise BindingError(f"{ctx}: {key!r} takes a non-empty list")
            for kid in kids:
                validate_predicate(kid, known_feeds, is_gate, ctx)
        return
    _validate_leaf(node, known_feeds, is_gate, ctx)


def _has_feed_leaf(node: Any) -> bool:
    """True when the predicate tree contains at least one live feed leaf."""
    if not isinstance(node, dict):
        return False
    if "feed" in node:
        return True
    for key in ("all", "any"):
        if key in node and isinstance(node[key], list):
            if any(_has_feed_leaf(child) for child in node[key]):
                return True
    return "not" in node and _has_feed_leaf(node["not"])


def validate_spec(spec: dict) -> None:
    """Whole-file validation; raises BindingError with the offending key."""
    feeds = spec.get("feeds") or []
    known = set()
    for f in feeds:
        for req in ("id", "provider", "parameter", "unit"):
            if not f.get(req):
                raise BindingError(f"feeds[{f.get('id', '?')}]: missing {req}")
        known.add(f["id"])
    bindings = spec.get("bindings") or []
    if not bindings:
        raise BindingError("no bindings in file")
    seen_keys: set[str] = set()
    for b in bindings:
        key = b.get("key")
        if not key or key in seen_keys:
            raise BindingError(f"binding key missing or duplicate: {key!r}")
        seen_keys.add(key)
        place = b.get("place") or {}
        for req in ("name", "kind", "lat", "lng"):
            if place.get(req) in (None, ""):
                raise BindingError(f"{key}: place.{req} missing")
        if not b.get("activity"):
            raise BindingError(f"{key}: activity missing")
        windows = b.get("windows") or []
        if not windows:
            raise BindingError(f"{key}: at least one condition window required")
        for i, w in enumerate(windows):
            ctx = f"{key}.windows[{i}]"
            if w.get("wtype") not in _WTYPES:
                raise BindingError(f"{ctx}: bad wtype {w.get('wtype')!r}")
            if "predicate" not in w:
                raise BindingError(f"{ctx}: predicate missing")
            validate_predicate(w["predicate"], known, bool(w.get("is_gate")), ctx)
        # docs/04 §4 rule 2: live windows should be paired with a seasonal
        # prior so a dead feed degrades to the prior, not to silence.
        has_seasonal = any(w.get("wtype") == "seasonal" for w in windows)
        has_live = any(_has_feed_leaf(w.get("predicate")) for w in windows)
        if has_live and not has_seasonal:
            log.warning(
                "binding %s has live windows but no seasonal prior window "
                "(docs/04 §4 rule 2 degradation path cannot engage)", key
            )


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------


def load_activities(conn: Connection, path: Path | None = None) -> int:
    path = path or DEFAULT_ACTIVITIES_PATH
    doc = yaml.safe_load(path.read_text())
    count = 0
    for act in doc["activities"]:
        conn.execute(
            text(
                "INSERT INTO activities (id, display_name, hazard_class) "
                "VALUES (:id, :dn, :hz) "
                "ON CONFLICT (id) DO UPDATE SET "
                "display_name = EXCLUDED.display_name, "
                "hazard_class = EXCLUDED.hazard_class"
            ),
            {"id": act["id"], "dn": act["display_name"], "hz": bool(act["hazard_class"])},
        )
        count += 1
    return count


def _upsert_feed(conn: Connection, feed: dict) -> None:
    # poll_interval default comes from the evaluator's cadence registry
    # (docs/04 §4 table) so e.g. NWIS rows report 15 min, not the column's
    # generic '1 hour' server default. An explicit YAML value still wins.
    from place.evaluator.registry import cadence_for

    poll = feed.get("poll_interval")
    if poll is None:
        poll = f"{int(cadence_for(feed['provider']).total_seconds())} seconds"
    conn.execute(
        text(
            "INSERT INTO feeds (id, provider, station_ref, parameter, unit, poll_interval) "
            "VALUES (:id, :provider, :station_ref, :parameter, :unit, "
            "CAST(:poll AS interval)) "
            "ON CONFLICT (id) DO UPDATE SET "
            "provider = EXCLUDED.provider, station_ref = EXCLUDED.station_ref, "
            "parameter = EXCLUDED.parameter, unit = EXCLUDED.unit, "
            "poll_interval = EXCLUDED.poll_interval"
        ),
        {
            "id": feed["id"],
            "provider": feed["provider"],
            "station_ref": feed.get("station_ref"),
            "parameter": feed["parameter"],
            "unit": feed["unit"],
            "poll": poll,
        },
    )


def _upsert_affordance(conn: Connection, place_id: object, binding: dict) -> object:
    aff = binding.get("affordance") or {}
    row = conn.execute(
        text(
            "INSERT INTO affordances (place_id, activity_id, difficulty, typical_duration, "
            "dog_ok, kid_ok, base_quality) "
            "VALUES (:pid, :act, :diff, CAST(:dur AS interval), :dog, :kid, :bq) "
            "ON CONFLICT (place_id, activity_id) DO UPDATE SET "
            "difficulty = EXCLUDED.difficulty, typical_duration = EXCLUDED.typical_duration, "
            "dog_ok = EXCLUDED.dog_ok, kid_ok = EXCLUDED.kid_ok, "
            "base_quality = EXCLUDED.base_quality "
            "RETURNING id"
        ),
        {
            "pid": place_id,
            "act": binding["activity"],
            "diff": aff.get("difficulty"),
            "dur": aff.get("typical_duration"),
            "dog": aff.get("dog_ok"),
            "kid": aff.get("kid_ok"),
            "bq": aff.get("base_quality", 0.5),
        },
    ).first()
    assert row is not None
    return row[0]


def _upsert_window(conn: Connection, affordance_id: object, window: dict) -> bool:
    """Natural key (affordance_id, wtype, is_gate): threshold edits update
    the window in place — the binding tightens, it doesn't multiply."""
    params = {
        "aid": affordance_id,
        "wtype": window["wtype"],
        "gate": bool(window.get("is_gate")),
        "pred": json.dumps(window["predicate"]),
        "mult": window.get("multiplier", 1.5),
    }
    updated = conn.execute(
        text(
            "UPDATE condition_windows SET predicate = CAST(:pred AS jsonb), multiplier = :mult "
            "WHERE affordance_id = :aid AND wtype = CAST(:wtype AS window_type) "
            "AND is_gate = :gate RETURNING id"
        ),
        params,
    ).first()
    if updated:
        return False
    conn.execute(
        text(
            "INSERT INTO condition_windows (affordance_id, wtype, predicate, multiplier, is_gate) "
            "VALUES (:aid, CAST(:wtype AS window_type), CAST(:pred AS jsonb), :mult, :gate)"
        ),
        params,
    )
    return True


def _upsert_access_note(conn: Connection, place_id: object, note: dict) -> None:
    exists = conn.execute(
        text(
            "SELECT 1 FROM access_points WHERE place_id = :pid AND kind = :kind "
            "AND notes = :notes"
        ),
        {"pid": place_id, "kind": note["kind"], "notes": note["notes"]},
    ).first()
    if exists:
        return
    conn.execute(
        text(
            "INSERT INTO access_points (place_id, kind, geom, notes) VALUES "
            "(:pid, :kind, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326), :notes)"
        ),
        {
            "pid": place_id,
            "kind": note["kind"],
            "lat": note["lat"],
            "lng": note["lng"],
            "notes": note["notes"],
        },
    )


def load(
    conn: Connection,
    path: Path | None = None,
    activities_path: Path | None = None,
) -> dict[str, int]:
    """Validate then load launch.yaml. Returns counters for the CLI."""
    from place.ingest import crosswalk  # local import: keeps validation import-light

    path = path or DEFAULT_BINDINGS_PATH
    spec = yaml.safe_load(path.read_text())
    validate_spec(spec)

    n_activities = load_activities(conn, activities_path)
    for feed in spec.get("feeds", []):
        _upsert_feed(conn, feed)

    places_created = windows_created = windows_updated = 0
    for binding in spec["bindings"]:
        p = binding["place"]
        place_id, created = crosswalk.resolve_place(
            conn,
            name=p["name"],
            kind=p["kind"],
            lat=float(p["lat"]),
            lng=float(p["lng"]),
        )
        places_created += created
        affordance_id = _upsert_affordance(conn, place_id, binding)
        for window in binding["windows"]:
            if _upsert_window(conn, affordance_id, window):
                windows_created += 1
            else:
                windows_updated += 1
        if binding.get("access_note"):
            _upsert_access_note(conn, place_id, binding["access_note"])
        log.info("binding %s -> place %s", binding["key"], place_id)

    return {
        "bindings": len(spec["bindings"]),
        "feeds": len(spec.get("feeds", [])),
        "activities": n_activities,
        "places_created": places_created,
        "windows_created": windows_created,
        "windows_updated": windows_updated,
    }
