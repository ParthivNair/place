"""Concrete feed adapters (docs/04 §4 cadence table).

Each module exposes an async ``fetch(...) -> list[Reading]`` plus a pure
``parse(payload, ...)`` unit-tested against recorded real responses.
"""

from place.evaluator.adapters.base import AdapterError, FeedAdapter, Reading, make_feed_id

__all__ = ["AdapterError", "FeedAdapter", "Reading", "make_feed_id"]
