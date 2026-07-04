"""Condition-predicate DSL (docs/01-EXPERIENCE-GRAPH.md §3).

Pure functions: no I/O, no clock reads — callers supply readings and ``now``.

Grammar::

    node  := leaf | {"all": [node, ...]} | {"any": [node, ...]} | {"not": node}
    leaf  := feed-leaf | month-leaf
    feed-leaf := {
      "feed": "<feeds.id>",
      "op": "<" | "<=" | ">" | ">=" | "=" | "between",
      "value": number | [lo, hi],
      "agg": "latest" | "sum" | "min" | "max",   # default "latest"
      "window_h": int,                            # required iff agg != "latest"
      "exit_value": number                        # optional hysteresis
    }
    month-leaf := {"month": [start, end]}         # 1..12 inclusive; wraps the
                                                  # year boundary when start > end
    months-leaf := {"months": [m, ...]}           # explicit list of months 1..12
                                                  # (shape used by launch.yaml)

The docs do not pin a JSON shape for seasonal (month-range) priors; two are
accepted: the range month-leaf and the list months-leaf. Both are evaluated
against ``now`` in America/Los_Angeles (the launch metro's timezone) when
``now`` is tz-aware; a naive ``now`` is used as-is.

Three-valued logic: every node evaluates to True, False, or None (unknown).
A feed-leaf is unknown when its reading is missing — the caller implements the
stale-as-unknown rule (docs/04 §4 rule 1) by returning None from the provider.
Unknown propagates with Kleene semantics:

  all: any False -> False; else any unknown -> unknown; else True
  any: any True  -> True;  else any unknown -> unknown; else False
  not: unknown stays unknown

Hysteresis (``exit_value``): once the window is in-state, the leaf stays
satisfied until the reading crosses ``exit_value``. The in-state flag is the
*window's* previously evaluated state (``condition_windows.state``) — per-leaf
state is not stored. When the window was not previously true (False or
unknown), the leaf requires the entry threshold again; that conservatism is
the safe side for ``is_gate`` windows.

Safe-side rule (docs/01 §3): ``value`` is the conservative entry and
``exit_value`` the hard bound. For "<"/"<=" leaves ``exit_value`` must be
>= ``value``; for ">"/">=" it must be <= ``value``. An inverted band is
rejected at validation for every window (it makes anti-flap incoherent) and
would be a safety bug on gates — anti-flap must never hold a hazard window
open past its hard bound.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol
from zoneinfo import ZoneInfo

_LOCAL_TZ = ZoneInfo("America/Los_Angeles")

__all__ = [
    "DSLError",
    "EvalResult",
    "ReadingsProvider",
    "StaticProvider",
    "evaluate",
    "feeds_referenced",
    "validate_predicate",
]

_OPS = ("<", "<=", ">", ">=", "=", "between")
_AGGS = ("latest", "sum", "min", "max")
_HYSTERESIS_OPS = ("<", "<=", ">", ">=")
_LEAF_KEYS = frozenset({"feed", "op", "value", "agg", "window_h", "exit_value"})


class DSLError(ValueError):
    """A predicate failed validation (or could not be evaluated structurally)."""


class ReadingsProvider(Protocol):
    """Read-side contract the evaluator (or a test) supplies to `evaluate`.

    Both methods return None for "no usable data" — missing feed, no readings
    in range, or stale per docs/04 §4 rule 1 (the provider owns staleness).
    """

    def latest(self, feed_id: str) -> float | None:
        """Most recent usable reading value for the feed, or None."""
        ...

    def window(self, feed_id: str, window_h: int) -> Sequence[float] | None:
        """Values observed within the trailing window_h hours, or None."""
        ...


@dataclass(frozen=True)
class StaticProvider:
    """Dict-backed ReadingsProvider for tests and previews."""

    latest_values: Mapping[str, float | None] = field(default_factory=dict)
    window_values: Mapping[tuple[str, int], Sequence[float]] = field(default_factory=dict)

    def latest(self, feed_id: str) -> float | None:
        return self.latest_values.get(feed_id)

    def window(self, feed_id: str, window_h: int) -> Sequence[float] | None:
        return self.window_values.get((feed_id, window_h))


@dataclass(frozen=True)
class EvalResult:
    """Outcome of evaluating one predicate tree.

    state:  True / False / None (unknown).
    inputs: the exact values used, keyed by feeds.id (aggregated value for
            agg leaves; None for missing/stale) plus "month" for month leaves.
            This is what condition_states.inputs and verification snapshots
            store (docs/01 §2).
    """

    state: bool | None
    inputs: dict[str, Any]


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_predicate(node: Any, *, is_gate: bool = False) -> None:
    """Raise DSLError unless `node` is a well-formed predicate tree.

    `is_gate` only sharpens error messages (the safe-side band-direction rule
    is enforced for every window; on gates it is a safety property).
    """
    _validate_node(node, is_gate=is_gate, path="$")


def _validate_node(node: Any, *, is_gate: bool, path: str) -> None:
    if not isinstance(node, Mapping):
        raise DSLError(f"{path}: node must be a JSON object, got {type(node).__name__}")
    if "all" in node or "any" in node:
        key = "all" if "all" in node else "any"
        if len(node) != 1:
            raise DSLError(f"{path}: '{key}' node must have exactly one key")
        children = node[key]
        if not isinstance(children, Sequence) or isinstance(children, (str, bytes)):
            raise DSLError(f"{path}.{key}: must be a list of nodes")
        if not children:
            raise DSLError(f"{path}.{key}: must not be empty")
        for i, child in enumerate(children):
            _validate_node(child, is_gate=is_gate, path=f"{path}.{key}[{i}]")
    elif "not" in node:
        if len(node) != 1:
            raise DSLError(f"{path}: 'not' node must have exactly one key")
        _validate_node(node["not"], is_gate=is_gate, path=f"{path}.not")
    elif "month" in node:
        _validate_month_leaf(node, path=path)
    elif "months" in node:
        _validate_months_leaf(node, path=path)
    elif "feed" in node:
        _validate_feed_leaf(node, is_gate=is_gate, path=path)
    else:
        raise DSLError(
            f"{path}: expected one of 'all', 'any', 'not', 'feed', 'month', 'months'"
        )


def _validate_month_leaf(node: Mapping[str, Any], *, path: str) -> None:
    if set(node) != {"month"}:
        raise DSLError(f"{path}: month leaf must have exactly the key 'month'")
    rng = node["month"]
    if (
        not isinstance(rng, Sequence)
        or isinstance(rng, (str, bytes))
        or len(rng) != 2
        or not all(isinstance(m, int) and not isinstance(m, bool) for m in rng)
    ):
        raise DSLError(f"{path}.month: must be a [start, end] pair of integers")
    if not all(1 <= m <= 12 for m in rng):
        raise DSLError(f"{path}.month: months must be in 1..12")


def _validate_months_leaf(node: Mapping[str, Any], *, path: str) -> None:
    if set(node) != {"months"}:
        raise DSLError(f"{path}: months leaf must have exactly the key 'months'")
    months = node["months"]
    if (
        not isinstance(months, Sequence)
        or isinstance(months, (str, bytes))
        or not months
        or not all(
            isinstance(m, int) and not isinstance(m, bool) and 1 <= m <= 12
            for m in months
        )
    ):
        raise DSLError(f"{path}.months: must be a non-empty list of integers in 1..12")


def _validate_feed_leaf(node: Mapping[str, Any], *, is_gate: bool, path: str) -> None:
    extra = set(node) - _LEAF_KEYS
    if extra:
        raise DSLError(f"{path}: unknown leaf keys {sorted(extra)}")
    feed = node.get("feed")
    if not isinstance(feed, str) or not feed:
        raise DSLError(f"{path}.feed: must be a non-empty feeds.id string")
    op = node.get("op")
    if op not in _OPS:
        raise DSLError(f"{path}.op: must be one of {list(_OPS)}, got {op!r}")

    value = node.get("value")
    if op == "between":
        if (
            not isinstance(value, Sequence)
            or isinstance(value, (str, bytes))
            or len(value) != 2
            or not all(_is_number(v) for v in value)
        ):
            raise DSLError(f"{path}.value: 'between' needs [lo, hi] numbers")
        if value[0] > value[1]:
            raise DSLError(f"{path}.value: 'between' needs lo <= hi")
    elif not _is_number(value):
        raise DSLError(f"{path}.value: must be a number")

    agg = node.get("agg", "latest")
    if agg not in _AGGS:
        raise DSLError(f"{path}.agg: must be one of {list(_AGGS)}, got {agg!r}")
    window_h = node.get("window_h")
    if agg == "latest":
        if window_h is not None:
            raise DSLError(f"{path}.window_h: only valid when agg != 'latest'")
    else:
        if not isinstance(window_h, int) or isinstance(window_h, bool) or window_h <= 0:
            raise DSLError(f"{path}.window_h: required positive integer when agg={agg!r}")

    if "exit_value" in node:
        exit_value = node["exit_value"]
        if not _is_number(exit_value):
            raise DSLError(f"{path}.exit_value: must be a number")
        if op not in _HYSTERESIS_OPS:
            raise DSLError(f"{path}.exit_value: hysteresis only valid with {_HYSTERESIS_OPS}")
        inverted = exit_value < value if op in ("<", "<=") else exit_value > value
        if inverted:
            msg = (
                f"{path}.exit_value: band is inverted — for op {op!r} exit_value must sit "
                f"{'at or above' if op in ('<', '<=') else 'at or below'} value"
            )
            if is_gate:
                msg += (
                    " (safe-side rule for is_gate windows: value is the conservative"
                    " entry, exit_value the earned hard bound)"
                )
            raise DSLError(msg)


# ---------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------


def evaluate(
    node: Mapping[str, Any],
    provider: ReadingsProvider,
    *,
    now: dt.datetime,
    prev_state: bool | None = None,
) -> EvalResult:
    """Evaluate a (validated) predicate tree with three-valued logic.

    prev_state is the window's previous evaluated state (condition_windows
    .state); it drives hysteresis leaves. All children of a composite are
    evaluated (no short-circuit) so `inputs` is a complete snapshot.
    """
    inputs: dict[str, Any] = {}
    state = _eval_node(node, provider, now, prev_state, inputs)
    return EvalResult(state=state, inputs=inputs)


def _eval_node(
    node: Mapping[str, Any],
    provider: ReadingsProvider,
    now: dt.datetime,
    prev_state: bool | None,
    inputs: dict[str, Any],
) -> bool | None:
    if "all" in node:
        states = [_eval_node(c, provider, now, prev_state, inputs) for c in node["all"]]
        if any(s is False for s in states):
            return False
        if any(s is None for s in states):
            return None
        return True
    if "any" in node:
        states = [_eval_node(c, provider, now, prev_state, inputs) for c in node["any"]]
        if any(s is True for s in states):
            return True
        if any(s is None for s in states):
            return None
        return False
    if "not" in node:
        inner = _eval_node(node["not"], provider, now, prev_state, inputs)
        return None if inner is None else not inner
    if "month" in node:
        return _eval_month_leaf(node, now, inputs)
    if "months" in node:
        return _eval_months_leaf(node, now, inputs)
    if "feed" in node:
        return _eval_feed_leaf(node, provider, prev_state, inputs)
    raise DSLError("unrecognized node; run validate_predicate first")


def _local_month(now: dt.datetime) -> int:
    """Month in America/Los_Angeles (launch metro); naive datetimes used as-is."""
    if now.tzinfo is not None:
        return now.astimezone(_LOCAL_TZ).month
    return now.month


def _eval_month_leaf(
    node: Mapping[str, Any], now: dt.datetime, inputs: dict[str, Any]
) -> bool:
    start, end = node["month"]
    month = _local_month(now)
    inputs["month"] = month
    if start <= end:
        return start <= month <= end
    return month >= start or month <= end  # wraps the year boundary, e.g. [11, 2]


def _eval_months_leaf(
    node: Mapping[str, Any], now: dt.datetime, inputs: dict[str, Any]
) -> bool:
    month = _local_month(now)
    inputs["month"] = month
    return month in node["months"]


def _eval_feed_leaf(
    node: Mapping[str, Any],
    provider: ReadingsProvider,
    prev_state: bool | None,
    inputs: dict[str, Any],
) -> bool | None:
    feed = node["feed"]
    agg = node.get("agg", "latest")
    if agg == "latest":
        raw = provider.latest(feed)
        value_used = None if raw is None else float(raw)
    else:
        series = provider.window(feed, node["window_h"])
        if not series:  # None or empty: no usable data in the window -> unknown
            value_used = None
        else:
            vals = [float(v) for v in series]
            value_used = {"sum": sum, "min": min, "max": max}[agg](vals)
    inputs[feed] = value_used
    if value_used is None:
        return None

    op = node["op"]
    if _compare(op, value_used, node["value"]):
        return True
    # Hysteresis: only holds while the *window* was previously true; a False
    # or unknown prior state falls back to the entry threshold (safe side).
    if "exit_value" in node and prev_state is True:
        return _compare(op, value_used, node["exit_value"])
    return False


def _compare(op: str, lhs: float, rhs: Any) -> bool:
    if op == "<":
        return lhs < rhs
    if op == "<=":
        return lhs <= rhs
    if op == ">":
        return lhs > rhs
    if op == ">=":
        return lhs >= rhs
    if op == "=":
        return lhs == rhs
    if op == "between":
        return rhs[0] <= lhs <= rhs[1]
    raise DSLError(f"unknown op {op!r}")


# ---------------------------------------------------------------------------
# introspection
# ---------------------------------------------------------------------------


def feeds_referenced(node: Mapping[str, Any]) -> set[str]:
    """Every feeds.id the predicate reads (month leaves reference none)."""
    out: set[str] = set()
    _collect_feeds(node, out)
    return out


def _collect_feeds(node: Mapping[str, Any], out: set[str]) -> None:
    if "all" in node or "any" in node:
        for child in node.get("all") or node.get("any") or []:
            _collect_feeds(child, out)
    elif "not" in node:
        _collect_feeds(node["not"], out)
    elif "feed" in node:
        out.add(node["feed"])
