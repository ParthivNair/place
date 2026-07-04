"""GNIS (USGS Domestic Names) skeleton loader.

Downloads the OR + WA DomesticNames state text files (pipe-delimited, one
zip per state), caches them under data/cache/gnis/, filters to classes
Falls/Summit/Spring/Lake inside the launch polygon, and resolves each
feature through the crosswalk (places.gnis_id).

Reality deltas from the docs-era sketch of GNIS:
- The post-2021 "DomesticNames" format has a lowercase header row and NO
  elevation columns (the legacy NationalFile had ELEV_IN_M). We parse by
  header name and accept both vintages; elevation comes from OSM instead.
- State files include a few out-of-state rows (multi-state features), so
  membership is decided by the polygon test, not the file's state.
"""

from __future__ import annotations

import io
import logging
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx
from sqlalchemy import Connection

from place.config import get_settings
from place.ingest import crosswalk
from place.ingest.geo import in_polygon

log = logging.getLogger(__name__)

DOWNLOAD_URL = (
    "https://prd-tnm.s3.amazonaws.com/StagedProducts/GeographicNames/"
    "DomesticNames/DomesticNames_{state}_Text.zip"
)
STATES = ("OR", "WA")

CLASS_TO_KIND = {
    "falls": "waterfall",
    "summit": "peak",
    "spring": "spring",
    "lake": "lake",
}

# header-name aliases: (new DomesticNames name, legacy NationalFile name)
_COL_ALIASES = {
    "feature_id": ("feature_id",),
    "feature_name": ("feature_name",),
    "feature_class": ("feature_class",),
    "lat": ("prim_lat_dec",),
    "lng": ("prim_long_dec",),
    "elev_m": ("elev_in_m",),  # legacy only
}


@dataclass(frozen=True)
class GnisFeature:
    gnis_id: str
    name: str
    kind: str
    lat: float
    lng: float
    elev_m: int | None


def _column_index(header: list[str]) -> dict[str, int]:
    lower = [h.strip().lstrip("﻿").lower() for h in header]
    idx: dict[str, int] = {}
    for key, aliases in _COL_ALIASES.items():
        for alias in aliases:
            if alias in lower:
                idx[key] = lower.index(alias)
                break
    missing = {"feature_id", "feature_name", "feature_class", "lat", "lng"} - set(idx)
    if missing:
        raise ValueError(f"GNIS file missing expected columns: {sorted(missing)}")
    return idx


def parse_text(content: str) -> list[GnisFeature]:
    """Parse a DomesticNames pipe-delimited file (header row required)."""
    lines = content.splitlines()
    if not lines:
        return []
    idx = _column_index(lines[0].split("|"))
    out: list[GnisFeature] = []
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split("|")
        try:
            fclass = parts[idx["feature_class"]].strip().lower()
            kind = CLASS_TO_KIND.get(fclass)
            if kind is None:
                continue
            lat = float(parts[idx["lat"]])
            lng = float(parts[idx["lng"]])
        except (IndexError, ValueError):
            continue
        if lat == 0.0 and lng == 0.0:  # GNIS null-island convention for unknown coords
            continue
        elev_m: int | None = None
        if "elev_m" in idx and idx["elev_m"] < len(parts):
            raw = parts[idx["elev_m"]].strip()
            if raw:
                try:
                    elev_m = round(float(raw))
                except ValueError:
                    elev_m = None
        out.append(
            GnisFeature(
                gnis_id=parts[idx["feature_id"]].strip(),
                name=parts[idx["feature_name"]].strip(),
                kind=kind,
                lat=lat,
                lng=lng,
                elev_m=elev_m,
            )
        )
    return out


def _cached_download(state: str) -> Path:
    settings = get_settings()
    cache_dir = settings.data_cache_dir / "gnis"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"DomesticNames_{state}_Text.zip"
    if path.exists() and path.stat().st_size > 0:
        return path
    url = DOWNLOAD_URL.format(state=state)
    log.info("gnis: downloading %s", url)
    with httpx.stream(
        "GET", url, headers={"User-Agent": settings.http_user_agent}, timeout=120.0
    ) as resp:
        resp.raise_for_status()
        tmp = path.with_suffix(".part")
        with open(tmp, "wb") as f:
            for chunk in resp.iter_bytes():
                f.write(chunk)
        tmp.rename(path)
    return path


def read_state_file(state: str) -> list[GnisFeature]:
    path = _cached_download(state)
    with zipfile.ZipFile(path) as zf:
        txt_names = [n for n in zf.namelist() if n.lower().endswith(".txt")]
        if not txt_names:
            raise ValueError(f"no .txt member in {path}")
        with zf.open(txt_names[0]) as f:
            content = io.TextIOWrapper(f, encoding="utf-8-sig").read()
    return parse_text(content)


def load(conn: Connection, *, limit: int | None = None) -> dict[str, int]:
    created = merged = skipped = 0
    processed = 0
    for state in STATES:
        if limit is not None and processed >= limit:
            break
        features = read_state_file(state)
        log.info("gnis %s: %d features in target classes", state, len(features))
        for feat in features:
            if limit is not None and processed >= limit:
                break
            if not in_polygon(feat.lat, feat.lng):
                skipped += 1
                continue
            processed += 1
            _, was_created = crosswalk.resolve_place(
                conn,
                name=feat.name,
                kind=feat.kind,
                lat=feat.lat,
                lng=feat.lng,
                source_col="gnis_id",
                source_id=feat.gnis_id,
                elev_m=feat.elev_m,
            )
            created += was_created
            merged += not was_created
    return {
        "processed": processed,
        "created": created,
        "existing_or_merged": merged,
        "outside_polygon": skipped,
    }
