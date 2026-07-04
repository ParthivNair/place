"""Ingestion CLI: `python -m place.ingest.cli <source> [--limit N] [--bbox S W N E]`.

Sources: overpass | gnis | ridb | usfs | bindings | all.
Every loader is idempotent — re-running converges instead of duplicating.
Key-gated sources (ridb) skip with a log line when the credential is absent;
under `all` that is a skip, standalone it is a hard error.
"""

from __future__ import annotations

import argparse
import logging
import sys

from place.config import MissingCredential, get_settings
from place.db import get_sync_engine
from place.ingest import bindings, gnis, overpass, ridb, seed_demo, usfs

log = logging.getLogger("place.ingest")

SOURCES = ("overpass", "gnis", "ridb", "usfs", "bindings", "seed-demo", "all")


def _run_source(name: str, args: argparse.Namespace) -> dict[str, int] | None:
    engine = get_sync_engine()
    with engine.begin() as conn:
        if name == "overpass":
            return overpass.load(
                conn,
                limit=args.limit,
                tags=args.tags.split(",") if args.tags else None,
                bbox=tuple(args.bbox) if args.bbox else None,
            )
        if name == "gnis":
            return gnis.load(conn, limit=args.limit)
        if name == "ridb":
            return ridb.load(conn, limit=args.limit)
        if name == "usfs":
            return usfs.load(conn, limit=args.limit)
        if name == "bindings":
            return bindings.load(conn)
        if name == "seed-demo":
            return seed_demo.load(conn)
    raise ValueError(f"unknown source: {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="place.ingest.cli", description=__doc__)
    parser.add_argument("source", choices=SOURCES)
    parser.add_argument("--limit", type=int, default=None, help="max records to ingest")
    parser.add_argument(
        "--bbox",
        type=float,
        nargs=4,
        metavar=("S", "W", "N", "E"),
        default=None,
        help="override the launch polygon (overpass only)",
    )
    parser.add_argument(
        "--tags",
        type=str,
        default=None,
        help="comma-separated overpass tag groups "
        f"({','.join(k for k in overpass.TAG_QUERIES if k != 'waterfall_legacy')})",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=get_settings().log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # bindings last under `all`: places from the public sources should exist
    # first so bindings crosswalk-merge onto them instead of the reverse.
    if args.source == "all":
        names = ["overpass", "gnis", "ridb", "usfs", "bindings"]
    else:
        names = [args.source]
    exit_code = 0
    for name in names:
        try:
            stats = _run_source(name, args)
        except MissingCredential as exc:
            if args.source == "all":
                log.warning("%s: skipped (%s)", name, exc)
                continue
            log.error("%s: %s", name, exc)
            exit_code = 2
            continue
        log.info("%s: %s", name, stats)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
