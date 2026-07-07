"""The pack-compiler golden test (PR-B contract).

The point of the static packs is that a pure client-side computation over the
artifacts must reproduce what the server routes serve today — that equality
is what later lets us delete the read routes. So: seed a representative
graph, publish, recompute the feed FROM THE PACK in pure Python (haversine
radius, dog/kid flags, the verb-needle semantics of routes/feed.py:109-115 /
web format.ts verbNeedle, now_score ordering), and assert it matches
GET /feed across a filter grid.

Plus the safety/robustness contracts: sensitive places and unpublished
claims structurally absent, quote_internal absent from every artifact byte,
manifest hashes verify, hash-identical republish (determinism), the docs/04
§4 rules encoded in the conditions pack, correct serving headers, and the
sweep's zero-risk publish phase (failure logs + health, never aborts).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import itertools
import json
import math
import uuid
from pathlib import Path
from typing import Any

import brotli
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, insert, select, text

from place import scoring
from place.config import Settings
from place.evaluator import publish
from place.evaluator.run import sweep
from place.models import (
    activities,
    affordances,
    claims,
    condition_states,
    condition_windows,
    feed_health,
    feeds,
    good_now,
    users,
    verifications,
)

# Two clusters ~88 km apart so a 40 km radius never crosses clusters and no
# fixture place sits near a radius boundary (haversine vs the spheroid
# ST_DWithin uses must agree on membership).
O1 = (45.52, -122.68)  # Portland
O2 = (45.40, -121.57)  # Mt Hood

FLOW = "usgs_nwis:14211010:00060"  # 15-min cadence -> 30-min staleness cutoff
PRECIP = "nws:45.40,-121.57:precip_in"  # 1-h cadence -> 2-h cutoff
ASTRO = "astro:45.40,-121.57:sun_elev_deg"

SECRET_PUBLISHED = "SECRET-PUBLISHED-QUOTE-NEVER-SERVED"
SECRET_REVIEW = "SECRET-REVIEW-QUOTE-NEVER-SERVED"
SENSITIVE_NAME = "Secret Springs (synthetic)"


@pytest.fixture()
def packs_dir(tmp_path, monkeypatch) -> Path:
    """Point both the publisher and the app's /packs mount at a temp dir."""
    d = tmp_path / "packs"
    monkeypatch.setenv("PACKS_DIR", str(d))
    return d


@pytest.fixture()
def client(packs_dir, app):
    # packs_dir must resolve before `app` so create_app mounts the temp dir
    with TestClient(app) as c:
        yield c


def _place(conn, name: str, kind: str, lat: float, lng: float, sensitive: bool = False):
    pid = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO places (id, name, kind, geom, sensitive) VALUES "
            "(:id, :name, :kind, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326), :sensitive)"
        ),
        {"id": pid, "name": name, "kind": kind, "lng": lng, "lat": lat,
         "sensitive": sensitive},
    )
    return pid


def seed_graph(engine: Engine, now: dt.datetime) -> dict[str, Any]:
    """Representative fixture: hazard + non-hazard, sensitive place,
    published + unpublished affordances/claims, mixed window states."""
    ids: dict[str, Any] = {}
    with engine.begin() as conn:
        for fid, provider, param, unit, value, observed in [
            (FLOW, "usgs_nwis", "00060", "cfs", 900.0, now - dt.timedelta(minutes=10)),
            (PRECIP, "nws", "precip_in", "in", 1.6, now - dt.timedelta(hours=1)),
            (ASTRO, "astro", "sun_elev_deg", "deg", None, None),
        ]:
            conn.execute(insert(feeds).values(
                id=fid, provider=provider, parameter=param, unit=unit,
                last_value=value, last_observed_at=observed))

        for aid, name, hazard in [
            ("trail_run", "Trail run", False),
            ("wild_swim", "Wild swim", True),
            ("waterfall_view", "Waterfall view", False),
        ]:
            conn.execute(insert(activities).values(
                id=aid, display_name=name, hazard_class=hazard))

        # cluster A (Portland)
        ids["p_park"] = _place(conn, "Forest Park (synthetic)", "trailhead", 45.57, -122.75)
        ids["p_swim"] = _place(conn, "High Rocks (synthetic)", "swim_hole", 45.46, -122.66)
        ids["p_secret"] = _place(conn, SENSITIVE_NAME, "spring", 45.50, -122.70,
                                 sensitive=True)
        # cluster B (Hood)
        ids["p_falls"] = _place(conn, "Tamanawas Falls (synthetic)", "waterfall",
                                45.40, -121.57)
        ids["p_spur"] = _place(conn, "Cooper Spur (synthetic)", "trailhead", 45.47, -121.52)
        ids["p_draft"] = _place(conn, "Draft Gulch (synthetic)", "creek", 45.42, -121.60)

        def aff(key: str, place_key: str, activity: str, *, base: float,
                dog: bool | None, kid: bool | None) -> uuid.UUID:
            aid = uuid.uuid4()
            ids[key] = aid
            conn.execute(insert(affordances).values(
                id=aid, place_id=ids[place_key], activity_id=activity,
                base_quality=base, dog_ok=dog, kid_ok=kid, difficulty=2,
                typical_duration=dt.timedelta(hours=2), status="draft"))
            return aid

        aff("a_park", "p_park", "trail_run", base=0.7, dog=True, kid=False)
        aff("a_swim", "p_swim", "wild_swim", base=0.8, dog=False, kid=False)
        aff("a_secret", "p_secret", "waterfall_view", base=0.9, dog=True, kid=True)
        aff("a_falls", "p_falls", "waterfall_view", base=0.7, dog=True, kid=True)
        aff("a_spur", "p_spur", "trail_run", base=0.5, dog=False, kid=True)
        aff("a_draft", "p_draft", "waterfall_view", base=0.5, dog=None, kid=None)

        def claim(key: str, aff_key: str, *, cclass: str, stype: str, domain: str,
                  log_odds: float, age_days: int, status: str = "published",
                  quote: str | None = None, url: str | None = None) -> uuid.UUID:
            cid = uuid.uuid4()
            ids[key] = cid
            conn.execute(insert(claims).values(
                id=cid, affordance_id=ids[aff_key], cclass=cclass, stype=stype,
                source_domain=domain, source_url=url, quote_internal=quote,
                observed_date=(now - dt.timedelta(days=age_days)).date(),
                log_odds=log_odds, status=status,
                last_evidence_at=now - dt.timedelta(days=age_days)))
            return cid

        claim("c_park_a", "a_park", cclass="access", stype="llm_extracted",
              domain="oregonhikers.org", log_odds=1.2, age_days=10,
              url="https://oregonhikers.org/forest-park")
        claim("c_park_b", "a_park", cclass="access", stype="llm_extracted",
              domain="reddit.com", log_odds=0.5, age_days=20)
        claim("c_swim", "a_swim", cclass="hazard_calibration", stype="founder_verified",
              domain="place.founder", log_odds=2.94, age_days=5)
        claim("c_secret", "a_secret", cclass="geomorphic", stype="founder_verified",
              domain="place.founder", log_odds=2.94, age_days=3)
        claim("c_falls_a", "a_falls", cclass="seasonal_bio", stype="founder_verified",
              domain="place.founder", log_odds=2.94, age_days=1)
        claim("c_falls_b", "a_falls", cclass="access", stype="llm_extracted",
              domain="oregonhikers.org", log_odds=0.38, age_days=15,
              quote=SECRET_PUBLISHED)
        claim("c_falls_review", "a_falls", cclass="access", stype="llm_extracted",
              domain="reddit.com", log_odds=-0.62, age_days=2, status="review",
              quote=SECRET_REVIEW)
        claim("c_spur", "a_spur", cclass="access", stype="founder_verified",
              domain="place.founder", log_odds=2.94, age_days=7)
        claim("c_draft", "a_draft", cclass="access", stype="llm_extracted",
              domain="reddit.com", log_odds=-0.62, age_days=4, status="review")

        # publish everything except the draft affordance (the DB publication
        # gate is satisfied: founder claim or two independent domains)
        for key in ("a_park", "a_swim", "a_secret", "a_falls", "a_spur"):
            conn.execute(affordances.update()
                         .where(affordances.c.id == ids[key]).values(status="published"))

        def window(key: str, aff_key: str, wtype: str, predicate: dict, *,
                   multiplier: float, is_gate: bool = False,
                   state: bool | None = True,
                   inputs: dict | None = None) -> uuid.UUID:
            wid = uuid.uuid4()
            ids[key] = wid
            conn.execute(insert(condition_windows).values(
                id=wid, affordance_id=ids[aff_key], wtype=wtype, predicate=predicate,
                multiplier=multiplier, is_gate=is_gate, state=state,
                state_since=now - dt.timedelta(days=1), last_eval=now))
            if state is not None and inputs is not None:
                conn.execute(insert(condition_states).values(
                    window_id=wid, satisfied=state, evaluated_at=now, inputs=inputs))
            return wid

        window("w_park_season", "a_park", "seasonal", {"month": [1, 12]},
               multiplier=1.3, inputs={"month": now.month})
        window("w_park_rain", "a_park", "weather_triggered",
               {"feed": PRECIP, "agg": "sum", "window_h": 72, "op": ">=", "value": 1.0},
               multiplier=1.5,
               inputs={PRECIP: {"value": 1.6,
                                "observed_at": (now - dt.timedelta(hours=1)).isoformat()}})
        window("w_swim_gate", "a_swim", "hydrological",
               {"feed": FLOW, "op": "<", "value": 1050, "exit_value": 1200},
               multiplier=2.0, is_gate=True,
               inputs={FLOW: {"value": 900.0,
                              "observed_at": (now - dt.timedelta(minutes=10)).isoformat()}})
        window("w_swim_season", "a_swim", "seasonal", {"month": [6, 9]},
               multiplier=1.2, inputs={"month": now.month})
        window("w_falls_rain", "a_falls", "weather_triggered",
               {"feed": PRECIP, "agg": "sum", "window_h": 72, "op": ">=", "value": 1.0},
               multiplier=1.8,
               inputs={PRECIP: {"value": 1.6,
                                "observed_at": (now - dt.timedelta(hours=1)).isoformat()}})
        # a live window in state=unknown (feed down): must publish as null
        window("w_falls_astro", "a_falls", "astronomical",
               {"feed": ASTRO, "op": ">", "value": 0}, multiplier=1.1, state=None)
        window("w_spur_season", "a_spur", "seasonal", {"month": [5, 10]},
               multiplier=1.2, inputs={"month": now.month})

        founder = uuid.uuid4()
        regular = uuid.uuid4()
        conn.execute(insert(users).values(
            id=founder, email="founder@place.test", display_name="Parthiv",
            power_verifier=True))
        conn.execute(insert(users).values(
            id=regular, email="casey@place.test", display_name="Casey"))
        # power confirm on the hazard claim (run.py kill switch 2 prong)
        conn.execute(insert(verifications).values(
            claim_id=ids["c_swim"], user_id=founder, verdict="confirm",
            conditions_snapshot={FLOW: 900}, verified_at=now - dt.timedelta(days=5)))
        # regular confirm on the waterfall (last_confirm credit only)
        conn.execute(insert(verifications).values(
            claim_id=ids["c_falls_a"], user_id=regular, verdict="confirm",
            conditions_snapshot={PRECIP: 1.6}, verified_at=now - dt.timedelta(days=2)))

        # good_now rows with distinct scores (feed order must be well-defined);
        # the sensitive-place row proves both read paths exclude it.
        for aff_key, score, reasons in [
            ("a_swim", 2.2, [{"window_id": str(ids["w_swim_gate"]), "wtype": "hydrological"},
                             {"window_id": str(ids["w_swim_season"]), "wtype": "seasonal"}]),
            ("a_falls", 1.9, [{"window_id": str(ids["w_falls_rain"]),
                               "wtype": "weather_triggered"}]),
            ("a_park", 1.4, [{"window_id": str(ids["w_park_rain"]),
                              "wtype": "weather_triggered"},
                             {"window_id": str(ids["w_park_season"]), "wtype": "seasonal"}]),
            ("a_spur", 1.1, [{"window_id": str(ids["w_spur_season"]), "wtype": "seasonal"}]),
            ("a_secret", 3.0, []),
        ]:
            conn.execute(insert(good_now).values(
                affordance_id=ids[aff_key], now_score=score, reasons=reasons,
                computed_at=now))
    return ids


# ---------------------------------------------------------------------------
# the pure-Python pack client (the contract this PR establishes)
# ---------------------------------------------------------------------------


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(a))


def _verb_needle(verb: str) -> str | None:
    # routes/feed.py:109-115 / web format.ts verbNeedle: substring + plural fold
    v = verb.strip().lower()
    if not v:
        return None
    return v[:-1] if len(v) > 2 and v.endswith("s") else v


def pack_feed(
    packs: dict[str, Any], lat: float, lng: float, radius_km: float,
    verb: str | None = None, dog_ok: bool | None = None, kid_ok: bool | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    graph, conditions = packs["graph"], packs["conditions"]
    places_by_id = {p["id"]: p for p in graph["places"]}
    affs_by_id = {a["id"]: a for a in graph["affordances"]}
    acts_by_id = {a["id"]: a for a in graph["activities"]}
    needle = _verb_needle(verb) if verb is not None else None
    cards: list[dict[str, Any]] = []
    for row in conditions["good_now"]:
        aff = affs_by_id.get(row["affordance_id"])
        if aff is None:  # not in the graph pack -> not servable, whatever good_now says
            continue
        place = places_by_id[aff["place_id"]]
        act = acts_by_id[aff["activity_id"]]
        distance_km = _haversine_km(lat, lng, place["lat"], place["lng"])
        if distance_km > radius_km:
            continue
        if needle is not None and (
            needle not in act["id"].lower() and needle not in act["display_name"].lower()
        ):
            continue
        if dog_ok and not aff["dog_ok"]:
            continue
        if kid_ok and not aff["kid_ok"]:
            continue
        cards.append({
            "affordance_id": row["affordance_id"],
            "now_score": row["now_score"],
            "distance_km": distance_km,
            "reasons": row["reasons"],
        })
    cards.sort(key=lambda c: -c["now_score"])
    return cards[:limit]


def load_packs(packs_dir: Path, region: str = "pdx") -> tuple[dict, dict[str, Any]]:
    """Read manifest + artifacts the way a client would, verifying hashes."""
    region_dir = packs_dir / region
    manifest = json.loads((region_dir / "manifest.json").read_text())
    packs: dict[str, Any] = {}
    for kind, entry in manifest["artifacts"].items():
        data = (region_dir / entry["url"].rsplit("/", 1)[-1]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        assert len(data) == entry["bytes"]
        packs[kind] = json.loads(brotli.decompress(data))
    return manifest, packs


def _publish(engine: Engine, now: dt.datetime) -> publish.PublishResult:
    return publish.publish_packs(engine, settings=Settings(), now=now)


# ---------------------------------------------------------------------------
# the golden test
# ---------------------------------------------------------------------------


def test_golden_pack_feed_matches_api_feed(client, db, packs_dir):
    now = dt.datetime.now(dt.UTC)
    ids = seed_graph(db, now)
    _publish(db, now)
    _, packs = load_packs(packs_dir)

    grid = list(itertools.product(
        [O1, O2], [10, 40], [None, "runs", "swim"], [None, True], [None, True],
    ))
    compared = 0
    for (lat, lng), radius_km, verb, dog, kid in grid:
        params: dict[str, Any] = {"lat": lat, "lng": lng, "radius_km": radius_km}
        if verb is not None:
            params["activity"] = verb
        if dog:
            params["dog_ok"] = True
        if kid:
            params["kid_ok"] = True
        resp = client.get("/feed", params=params)
        assert resp.status_code == 200, resp.text
        api_cards = resp.json()["cards"]
        pack_cards = pack_feed(packs, lat, lng, radius_km, verb, dog, kid)

        label = f"origin=({lat},{lng}) r={radius_km} verb={verb} dog={dog} kid={kid}"
        assert [c["affordance_id"] for c in api_cards] == [
            c["affordance_id"] for c in pack_cards
        ], label
        for api_card, pack_card in zip(api_cards, pack_cards, strict=True):
            assert api_card["now_score"] == pytest.approx(pack_card["now_score"], rel=1e-9)
            assert abs(api_card["distance_km"] - pack_card["distance_km"]) <= 0.1, label
            assert [r["wtype"] for r in api_card["reasons"]] == [
                r["wtype"] for r in pack_card["reasons"]
            ], label
        compared += len(api_cards)
    assert compared > 0  # the grid actually exercised non-empty feeds

    # spot-pin two cells so a trivially-empty implementation can't pass
    cluster_a = pack_feed(packs, *O1, 10)
    assert [c["affordance_id"] for c in cluster_a] == [str(ids["a_swim"]), str(ids["a_park"])]
    cluster_b = pack_feed(packs, *O2, 10)
    assert [c["affordance_id"] for c in cluster_b] == [str(ids["a_falls"]), str(ids["a_spur"])]


def test_pack_and_api_claims_projections_are_field_identical(client, db, packs_dir):
    """One SQL gate guards both paths; pin that their shared fields agree."""
    now = dt.datetime.now(dt.UTC)
    ids = seed_graph(db, now)
    _publish(db, now)
    _, packs = load_packs(packs_dir)

    api_claims = client.get(f"/affordances/{ids['a_falls']}/claims").json()
    pack_claims = [
        c for c in packs["claims"]["claims"] if c["affordance_id"] == str(ids["a_falls"])
    ]
    assert {c["id"] for c in api_claims} == {c["id"] for c in pack_claims}
    api_by_id = {c["id"]: c for c in api_claims}
    for c in pack_claims:
        a = api_by_id[c["id"]]
        for field in ("cclass", "source_type", "source_domain", "source_url"):
            assert c[field] == a[field]
        assert c["observed_date"] == a["observed_date"]
        # API timestamps serialize without forcing an offset suffix; compare parsed
        assert dt.datetime.fromisoformat(c["last_evidence_at"]) == dt.datetime.fromisoformat(
            a["last_evidence_at"]
        )
        # confidence is derivable client-side from what the pack carries
        derived = scoring.sigmoid(c["log_odds"] + c["corroboration_nats"]) * (
            scoring.decay_factor(
                c["cclass"], now - dt.datetime.fromisoformat(c["last_evidence_at"])
            )
        )
        assert a["confidence"] == pytest.approx(derived, abs=5e-4)


def test_sensitive_unpublished_and_internal_never_reach_artifacts(db, packs_dir):
    now = dt.datetime.now(dt.UTC)
    ids = seed_graph(db, now)
    _publish(db, now)
    manifest, packs = load_packs(packs_dir)

    graph = packs["graph"]
    assert str(ids["p_secret"]) not in {p["id"] for p in graph["places"]}
    assert str(ids["a_secret"]) not in {a["id"] for a in graph["affordances"]}
    assert str(ids["a_draft"]) not in {a["id"] for a in graph["affordances"]}

    # the sensitive good_now row must not leak even a bare affordance id
    served = {row["affordance_id"] for row in packs["conditions"]["good_now"]}
    assert str(ids["a_secret"]) not in served
    assert served == {str(ids[k]) for k in ("a_swim", "a_falls", "a_park", "a_spur")}

    claim_ids = {c["id"] for c in packs["claims"]["claims"]}
    assert str(ids["c_falls_review"]) not in claim_ids  # unpublished
    assert str(ids["c_secret"]) not in claim_ids  # sensitive place
    assert str(ids["c_draft"]) not in claim_ids  # unpublished affordance
    assert str(ids["c_falls_b"]) in claim_ids  # published claim itself serves...

    # ...but quote_internal is structurally absent from every artifact byte
    region_dir = packs_dir / "pdx"
    for entry in manifest["artifacts"].values():
        raw = brotli.decompress((region_dir / entry["url"].rsplit("/", 1)[-1]).read_bytes())
        for needle in (b"quote_internal", SECRET_PUBLISHED.encode(),
                       SECRET_REVIEW.encode(), SENSITIVE_NAME.encode()):
            assert needle not in raw, entry["url"]


def test_conditions_pack_encodes_degradation_rules(db, packs_dir):
    now = dt.datetime.now(dt.UTC)
    ids = seed_graph(db, now)
    _publish(db, now)
    manifest, packs = load_packs(packs_dir)
    conditions = packs["conditions"]

    # rule 1: expires_at = generated_at + 2 x sweep cadence, and the manifest
    # repeats it so clients can check freshness before downloading anything
    assert conditions["generated_at"] == now.isoformat()
    assert conditions["expires_at"] == (now + dt.timedelta(hours=1)).isoformat()
    assert manifest["conditions"]["expires_at"] == conditions["expires_at"]
    assert manifest["conditions"]["sweep_cadence_s"] == 1800

    # version-skew pin: the conditions pack names the graph build it used
    assert conditions["graph_build"] == manifest["artifacts"]["graph"]["sha256"]

    # rule 3: hazard wall = min(power confirm + 60 d, gate reading + cutoff);
    # here the 30-min usgs cutoff on a 10-min-old reading wins -> now + 20 min
    wall = dt.datetime.fromisoformat(conditions["hazard_serve_until"][str(ids["a_swim"])])
    assert wall == now + dt.timedelta(minutes=20)
    assert set(conditions["hazard_serve_until"]) == {str(ids["a_swim"])}

    # rule 2: seasonal fallback for the plain card, hard zero for the hazard
    park_claims = [
        (1.2, 10, "access"), (0.5, 20, "access"),  # both boosted +0.5 (2 domains)
    ]
    park_conf = max(
        scoring.sigmoid(lo + 0.5) * scoring.decay_factor(cc, dt.timedelta(days=age))
        for lo, age, cc in park_claims
    )
    assert conditions["seasonal_prior_score"][str(ids["a_park"])] == pytest.approx(
        0.7 * 1.3 * park_conf, abs=1e-6
    )
    assert conditions["seasonal_prior_score"][str(ids["a_swim"])] == 0.0

    # unknown window state publishes as null, never as a guess (rule 1)
    astro_window = conditions["windows"][str(ids["w_falls_astro"])]
    assert astro_window["state"] is None
    gate_window = conditions["windows"][str(ids["w_swim_gate"])]
    assert gate_window["state"] is True
    assert gate_window["inputs"][FLOW]["value"] == 900.0
    assert gate_window["staleness_cutoff_s"] == 1800  # 2 x 15-min usgs cadence

    # per-feed last observations ride along for "as of <t>" rendering
    assert conditions["feeds"][FLOW]["last_value"] == 900.0

    # constants block: client math pinned to scoring.py, not re-typed
    constants = packs["graph"]["constants"]
    assert constants["half_life_days"] == scoring.HALF_LIFE_DAYS
    assert constants["serving_confidence_bar"] == scoring.SERVING_CONFIDENCE_BAR
    assert constants["corroboration_nats"] == scoring.CORROBORATION_NATS


def test_republish_is_deterministic_and_prunes(db, packs_dir):
    now = dt.datetime.now(dt.UTC)
    seed_graph(db, now)
    first = _publish(db, now)
    again = _publish(db, now)  # unchanged data, same sweep instant
    assert {a.kind: a.sha256 for a in first.artifacts} == {
        a.kind: a.sha256 for a in again.artifacts
    }

    # a later sweep with unchanged data: only the conditions artifact moves
    shas = {a.kind: a.sha256 for a in first.artifacts}
    for step in range(1, 5):
        result = _publish(db, now + step * dt.timedelta(minutes=30))
    final = {a.kind: a.sha256 for a in result.artifacts}
    assert final["graph"] == shas["graph"]
    assert final["claims"] == shas["claims"]
    assert final["conditions"] != shas["conditions"]

    # pruning keeps the last 3 conditions generations; graph/claims dedupe to 1
    region_dir = packs_dir / "pdx"
    assert len(list(region_dir.glob("conditions-*.json.br"))) == publish.KEEP_GENERATIONS
    assert len(list(region_dir.glob("graph-*.json.br"))) == 1
    assert len(list(region_dir.glob("claims-*.json.br"))) == 1


def test_packs_are_served_with_correct_headers(client, db, packs_dir):
    now = dt.datetime.now(dt.UTC)
    seed_graph(db, now)
    _publish(db, now)

    resp = client.get("/packs/pdx/manifest.json")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "public, max-age=60, stale-while-revalidate=1800"
    manifest = resp.json()

    artifact = client.get(manifest["artifacts"]["graph"]["url"])
    assert artifact.status_code == 200
    assert artifact.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert artifact.headers["content-encoding"] == "br"
    assert artifact.headers["content-type"] == "application/json"
    # httpx decodes Content-Encoding: br exactly like a browser fetch would
    payload = artifact.json()
    assert payload["region"] == "pdx"
    assert {p["name"] for p in payload["places"]} >= {"Forest Park (synthetic)"}


def test_sweep_publishes_packs_and_records_health(db, packs_dir, monkeypatch):
    now = dt.datetime.now(dt.UTC)
    seed_graph(db, now)
    settings = Settings()

    stats = sweep(db, settings=settings, now=now, adapters=[])
    assert stats.packs_published is True
    assert (packs_dir / "pdx" / "manifest.json").exists()
    publisher = publish.publisher_feed_id("pdx")
    with db.connect() as conn:
        ok = conn.execute(
            select(feed_health.c.ok).where(feed_health.c.feed_id == publisher)
            .order_by(feed_health.c.checked_at.desc(), feed_health.c.id.desc())
        ).scalars().first()
    assert ok is True

    # zero-risk contract: a publish crash logs + records health, the sweep
    # still completes (good_now materialized, no exception)
    def boom(*args, **kwargs):
        raise RuntimeError("synthetic publish crash")

    monkeypatch.setattr(publish, "publish_packs", boom)
    stats2 = sweep(db, settings=settings, now=now + dt.timedelta(minutes=30), adapters=[])
    assert stats2.packs_published is False
    assert stats2.windows_evaluated > 0  # the sweep ran to completion
    with db.connect() as conn:
        row = conn.execute(
            select(feed_health.c.ok, feed_health.c.error)
            .where(feed_health.c.feed_id == publisher)
            .order_by(feed_health.c.checked_at.desc(), feed_health.c.id.desc())
        ).first()
    assert row.ok is False
    assert "synthetic publish crash" in row.error
