"""Ingestion CLI: `python -m place.ingest.cli <mode> [options]`.

Source modes (idempotent — re-running converges instead of duplicating):
overpass | gnis | ridb | usfs | bindings | seed-demo | all.
Key-gated sources (ridb) skip with a log line when the credential is absent;
under `all`/`region` that is a skip, standalone it is a hard error.

Region tooling (the population program, docs/03 §6 applied within the metro):
  region --slug SLUG | --next   scope an ingest run to one priority region:
                                overpass bbox-scoped to the region circle,
                                then gnis/ridb/usfs AS-IS (they are launch-
                                polygon-wide, not bbox-scoped — harmless
                                because idempotent), then bindings.
  coverage                      per-region place/affordance counts (PostGIS
                                ST_DWithin), priority order, NEXT marked.
  proposals --file F            load agent-research proposals into the
                                review queue (never publishes — docs/00 §7).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from place.config import MissingCredential, get_settings
from place.db import get_sync_engine
from place.ingest import bindings, gnis, overpass, proposals, regions, ridb, seed_demo, usfs

log = logging.getLogger("place.ingest")

SOURCES = ("overpass", "gnis", "ridb", "usfs", "bindings", "seed-demo", "all")
REGION_MODES = ("region", "coverage", "proposals")


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


def _run_region(args: argparse.Namespace) -> int:
    """One region's ingest: overpass scoped to its circle, the launch-wide
    loaders as-is, bindings last (same ordering rationale as `all`)."""
    region_list = regions.load_regions()
    engine = get_sync_engine()
    if args.slug:
        try:
            region = regions.region_by_slug(region_list, args.slug)
        except regions.RegionError as exc:
            log.error("%s", exc)
            return 2
    elif args.next:
        with engine.connect() as conn:
            nxt = regions.pick_next(regions.coverage_report(conn, region_list))
        if nxt is None:
            log.info("every region meets target; nothing to do")
            return 0
        region = nxt.region
    else:
        log.error("region mode needs --slug or --next")
        return 2
    log.info(
        "region %s (%s, %s mi around %s,%s): %s",
        region.slug, region.name, region.radius_mi, region.lat, region.lng, region.notes,
    )

    if args.bbox:
        log.warning("region mode ignores --bbox: the region's own circle scopes overpass")

    exit_code = 0
    with engine.begin() as conn:
        stats = overpass.load(
            conn,
            limit=args.limit,
            tags=args.tags.split(",") if args.tags else None,
            bbox=tuple(region.bbox()),
            within=(region.lat, region.lng, region.radius_km),
        )
        log.info("overpass[%s]: %s", region.slug, stats)
    # gnis/ridb/usfs are not bbox-scoped: they always cover the launch
    # polygon. Running them whole is fine — idempotent — and keeps regions
    # inside the polygon fed by all sources; regions outside it (e.g. bend)
    # get skeleton from the scoped overpass pull only.
    for name in ("gnis", "ridb", "usfs", "bindings"):
        try:
            stats = _run_source(name, args)
        except MissingCredential as exc:
            log.warning("%s: skipped (%s)", name, exc)
            continue
        log.info("%s: %s", name, stats)
    return exit_code


def _run_coverage() -> int:
    region_list = regions.load_regions()
    engine = get_sync_engine()
    with engine.connect() as conn:
        report = regions.coverage_report(conn, region_list)
    print(regions.format_coverage_table(report))
    return 0


def _run_proposals(args: argparse.Namespace) -> int:
    if not args.file:
        log.error("proposals mode needs --file <yaml>")
        return 2
    engine = get_sync_engine()
    try:
        # one transaction: a validation error anywhere writes nothing
        with engine.begin() as conn:
            stats = proposals.load(conn, Path(args.file))
    except proposals.ProposalError as exc:
        log.error("proposals rejected: %s", exc)
        return 2
    log.info("proposals: %s", stats)
    print(
        "proposals: {proposals} read ({in_file_dupes} in-file dupes) | "
        "places {places_created} created / {places_matched} matched | "
        "affordances {affordances_created} created / {affordances_existing} existing | "
        "claims {claims_created} created / {claims_skipped} skipped (already present)".format(
            **stats
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="place.ingest.cli",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("source", choices=SOURCES + REGION_MODES)
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
    parser.add_argument("--slug", type=str, default=None, help="region slug (region mode)")
    parser.add_argument(
        "--next",
        action="store_true",
        help="region mode: pick the first priority region below target",
    )
    parser.add_argument("--file", type=str, default=None, help="proposals YAML (proposals mode)")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=get_settings().log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.source == "region":
        return _run_region(args)
    if args.source == "coverage":
        return _run_coverage()
    if args.source == "proposals":
        return _run_proposals(args)

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
