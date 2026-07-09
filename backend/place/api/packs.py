"""Static pack serving: /packs/{region}/... (the shadow read path).

Two cache classes, matching the publish write pattern (evaluator/publish.py):

- ``manifest.json`` — the ONLY mutable file. Short TTL plus
  stale-while-revalidate so clients converge on a new generation within a
  minute of a sweep, while a briefly-unreachable origin degrades to the last
  known generation instead of an error (docs/04 §4 rule 2's spirit: degrade,
  never go silent).
- content-hashed ``*.json.br`` artifacts — immutable by construction (the
  name embeds the sha256), so a year + ``immutable``.

Artifacts are stored brotli-compressed and served as-is with
``Content-Encoding: br`` + ``Content-Type: application/json``: a browser
``fetch()`` transparently decodes them into JSON. There is deliberately no
identity-encoding negotiation — every PWA-capable browser accepts br, and
re-encoding on a $10 VPS would defeat the point of precompressed artifacts.
"""

from __future__ import annotations

import os
from typing import Any

from starlette.staticfiles import StaticFiles

MANIFEST_CACHE_CONTROL = "public, max-age=60, stale-while-revalidate=1800"
IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"


class PackStaticFiles(StaticFiles):
    """StaticFiles with per-file-class cache/encoding headers for packs."""

    def file_response(self, full_path: Any, stat_result: Any, scope: Any,
                      status_code: int = 200) -> Any:
        response = super().file_response(full_path, stat_result, scope, status_code)
        name = os.path.basename(str(full_path))
        if name == "manifest.json":
            response.headers["Cache-Control"] = MANIFEST_CACHE_CONTROL
        elif name.endswith(".json.br"):
            response.headers["Cache-Control"] = IMMUTABLE_CACHE_CONTROL
            # mimetypes maps .json.br to (application/json, br) but Starlette
            # only uses the type half; the encoding header must be explicit
            # or browsers would try to parse raw brotli bytes as JSON.
            response.headers["Content-Type"] = "application/json"
            response.headers["Content-Encoding"] = "br"
        return response
