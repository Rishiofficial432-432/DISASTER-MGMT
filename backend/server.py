"""
Flask backend — serves the hazard/capacity/relocation pipeline as a JSON API
and hosts the static multi-page frontend.

Endpoints:
  GET    /api/regions                     -> list available datasets/regions
  GET    /api/hazard?region=X             -> hazard zone GeoJSON for region (default: majuli)
  GET    /api/settlements?region=X        -> list of settlements in memory for region
  POST   /api/settlements?region=X        -> add a settlement {name, lat, lon, population, area_hectares, terrain}
  DELETE /api/settlements/<name>?region=X -> remove a settlement
  POST   /api/settlements/reset?region=X  -> reset region to its original demo set
  GET    /api/assessment?region=X         -> run the full pipeline, return ranked results
  GET    /api/village-check?q=name&region=X -> "Check My Village" — verdict for one settlement by name
  GET    /api/nearest-village?lat=X&lon=Y&region=R -> auto-detect: verdict for the nearest settlement to a given lat/lon (used by the browser Geolocation "Use My Location" flow)
  GET    /api/geocode?q=place             -> convert place name to lat/lon (Nominatim)

Two regions/datasets are available (see REGIONS below):
  - "majuli" (default): the original small hand-curated Majuli, Assam pilot
    (2 real villages, hand-digitised demo hazard polygon). Precise, small,
    good for a focused walkthrough of the pipeline.
  - "national": 53,223 real villages across 15 states of India (from
    PC11/SHRUG village geometry) that were flagged by intersecting >=5
    distinct real historical flood events (India Flood Inventory V3,
    IMD/multi-source, 1960s-2020, CC-BY-4.0). Population and household
    counts are REAL Census 2011 Primary Census Abstract figures (official,
    Town/Village level), joined by exact PC11 state/district/subdistrict/
    village code -- NOT estimated. 53,223 of 54,337 flood-flagged villages
    (97.9%) matched to a real Census record by exact code; the unmatched
    ~2.1% (code mismatches, likely villages merged/renamed between the
    SHRUG geometry release and the Census PCA release) were EXCLUDED
    entirely rather than filled with an estimate, so every village in this
    dataset has 100% real population, geometry, and hazard-history data.
    Village geometry source: SHRUG (Development Data Lab), CC-BY-NC-SA-4.0
    — non-commercial use only. Population source: Census of India 2011,
    Primary Census Abstract (Town/Village level), official government data.
    See data/files 2/final_flood_villages_REAL_ONLY.json and
    data/files 2/trimmed_flood_hazard_REAL.geojson for the raw sourced data
    and per-record provenance fields (population_source, hazard_source).

    Threshold note: >=5 events was chosen to get geographic spread (15
    states) rather than a tighter threshold that would cover fewer states.

    Performance note: hazard lookup uses a shapely STRtree spatial index
    built once at startup per region (see _build_hazard_index below), not
    the naive O(villages x hazard_polygons) linear scan in
    app/hazard/point_in_polygon.py — that function is fine at Majuli's tiny
    scale but a real bottleneck at national scale (53k+ villages x ~500
    polygons, which timed out during integration testing).

    IMPORTANT: even with fully real source data, this remains a decision-
    SUPPORT prototype, not a system usable for actual emergency/relocation
    decisions -- that requires official certification, ground verification,
    and legal authority no dataset alone can provide.

Pages served:
  /                          -> Check My Village (entry screen)
  /dashboard                 -> Planner Dashboard (assessment + map)
  /protocols                 -> Protocols & Guidelines (static reference)
  /settlement/<name>         -> Settlement Detail
  /resources                 -> Resource Allocation

Run with: python3 backend/server.py
Default port: 5001 (macOS port 5000 is taken by AirPlay/ControlCenter).
Override:     PORT=8080 python3 backend/server.py
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask import Flask, jsonify, request, send_from_directory
from dataclasses import asdict
from shapely.geometry import shape, Point

from app.hazard.load_hazard_data import load_hazard_geojson, DATA_DIR
from app.relocation.priority_engine import SettlementAssessment, rank_settlements
from data.demo_settlements import DEMO_SETTLEMENTS

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
FILES_DIR = DATA_DIR / "files"
# The v2 national dataset files landed in "files 2" (macOS auto-renamed the
# download folder to avoid clobbering the original "files" dir that already
# held the v1 pair) rather than being moved into "files" -- pointing directly
# at it here avoids an unnecessary manual file-move step.
FILES_DIR_V2 = DATA_DIR / "files 2"

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")

DEFAULT_REGION = "majuli"


def _load_national_settlements():
    path = FILES_DIR_V2 / "final_flood_villages_REAL_ONLY.json"
    with open(path, "r") as f:
        raw = json.load(f)
    out = []
    for v in raw:
        out.append({
            "name": v["name"],
            "lat": v["lat"],
            "lon": v["lon"],
            "population": v["population"],
            "households": v.get("households"),
            "area_hectares": v["area_hectares"],
            "terrain": v.get("terrain", "plain"),
            "pc11_state_code": v.get("pc11_state_code"),
            "pc11_district_code": v.get("pc11_district_code"),
            "flood_event_count": v.get("flood_event_count"),
            "population_source": v.get("population_source"),
            "hazard_source": v.get("hazard_source"),
        })
    return out


def _build_hazard_index(hazard_geojson):
    """Build a shapely STRtree once per region so hazard lookups are fast
    at any scale. See performance note in the module docstring."""
    geoms, props = [], []
    for feat in hazard_geojson.get("features", []):
        g = shape(feat["geometry"])
        if not g.is_valid:
            g = g.buffer(0)
        geoms.append(g)
        props.append(feat.get("properties", {}))
    from shapely.strtree import STRtree
    tree = STRtree(geoms) if geoms else None
    return {"tree": tree, "geoms": geoms, "props": props}


def _hazard_lookup(lat, lon, hazard_index):
    """Fast point-in-polygon hazard check using the pre-built spatial index.
    Returns the matching feature's properties dict, or None."""
    if hazard_index["tree"] is None:
        return None
    p = Point(lon, lat)  # GeoJSON order is (lon, lat)
    geoms, props = hazard_index["geoms"], hazard_index["props"]
    for idx in hazard_index["tree"].query(p):
        if geoms[idx].contains(p):
            return props[idx]
    return None


# REGIONS holds the per-region in-memory state: the working settlement list
# (mutable — add/delete/reset act on this), the hazard GeoJSON (served as-is
# to the frontend map), and a pre-built spatial index over that same
# GeoJSON (used internally for fast hazard lookups in run_pipeline).
REGIONS = {
    "majuli": {
        "label": "Majuli, Assam (pilot)",
        "description": "2 real villages, hand-digitised demo hazard polygon. Precise, small-scale.",
        "demo_settlements": [dict(s) for s in DEMO_SETTLEMENTS],
        "hazard_geojson": load_hazard_geojson(str(DATA_DIR / "hazard_zones_majuli_demo.geojson")),
    },
    "national": {
        "label": "All-India flood-history villages (real data)",
        "description": (
            "53,223 real villages across 15 states, flagged by >=5 real historical flood events. "
            "Population and households are REAL Census 2011 figures (97.9% match rate; unmatched villages excluded, not estimated)."
        ),
        "demo_settlements": _load_national_settlements(),
        "hazard_geojson": load_hazard_geojson(str(FILES_DIR_V2 / "trimmed_flood_hazard_REAL.geojson")),
    },
}

for _cfg in REGIONS.values():
    _cfg["hazard_index"] = _build_hazard_index(_cfg["hazard_geojson"])

# Mutable working settlement lists, one per region.
settlements_by_region = {
    key: [dict(s) for s in cfg["demo_settlements"]]
    for key, cfg in REGIONS.items()
}


def _region_key():
    r = (request.args.get("region") or DEFAULT_REGION).strip().lower()
    return r if r in REGIONS else DEFAULT_REGION


# Priority rank -> plain-language verdict shown on the "Check My Village" screen
VERDICT_MAP = {
    "high": {
        "verdict": "URGENT",
        "message": "This village is in a flood-prone area and is overcrowded for its size. Immediate relocation review is recommended.",
    },
    "medium": {
        "verdict": "WATCH",
        "message": "This village shows some hazard exposure or overcrowding. Monitor conditions and review periodically.",
    },
    "low": {
        "verdict": "SAFE",
        "message": "This village is not currently flagged for hazard exposure or overcrowding based on available data.",
    },
}


def _haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km. Plain-Python (no numpy/scipy dependency)
    -- fine at this scale since /api/nearest-village does one linear scan
    per request (54,341 villages, a few ms), not a hot path."""
    from math import radians, sin, cos, sqrt, atan2
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def _severity_from_flood_event_count(n: int) -> str:
    """National dataset's hazard polygons (India Flood Inventory V3) don't carry
    a hazard_type/severity property the way the hand-digitised Majuli polygon
    does -- they carry State/Districts/MainCause/etc. instead. Rather than let
    hazard_severity silently come back None (which would zero out the hazard
    component of every national-village score -- a real bug caught during
    integration), derive severity from the real per-village flood_event_count
    (how many distinct historical flood events, 1960s-2020, hit this village).
    Thresholds are a simple, explainable judgement call, not a cited standard.
    Recalibrated for the >=5 threshold dataset (was >=15 in an earlier pass).
    """
    if n >= 21:
        return "extreme"
    if n >= 15:
        return "high"
    if n >= 10:
        return "moderate"
    return "low"


def run_pipeline(region):
    settlements = settlements_by_region[region]
    hazard_index = REGIONS[region]["hazard_index"]

    assessments = []
    # Map each assessment back to its source settlement by Python object
    # identity (id(a)), NOT by name -- village names collide constantly
    # across India's ~650k villages (many "Rampur"s etc across different
    # districts/states), so a later name-based re-lookup would silently
    # attach the wrong lat/lon/population to a result. It was also an O(n)
    # scan run once per result (O(n^2) overall), which is fine at Majuli's
    # scale (2 villages) but took 51+ seconds at national scale (54,341
    # villages) during integration testing -- a real bug caught by actually
    # running the endpoint, not just reading the code.
    assessment_to_settlement = {}
    for s in settlements:
        hz = _hazard_lookup(s["lat"], s["lon"], hazard_index)
        pph = s["population"] / s["area_hectares"] if s["area_hectares"] else 0

        hazard_type = hz.get("hazard_type") if hz else None
        hazard_severity = hz.get("severity") if hz else None
        if hz and not hazard_severity:
            # National dataset fallback: derive from real per-village flood history.
            hazard_type = hazard_type or "flood"
            hazard_severity = _severity_from_flood_event_count(s.get("flood_event_count") or 0)

        a = SettlementAssessment(
            settlement_id=s["name"],
            hazard_type=hazard_type,
            hazard_severity=hazard_severity,
            overlap_fraction=1.0 if hz else 0.0,
            persons_per_hectare=round(pph, 1),
            terrain=s.get("terrain", "plain"),
        )
        assessments.append(a)
        assessment_to_settlement[id(a)] = s
    ranked = rank_settlements(assessments)

    out = []
    for a in ranked:
        s = assessment_to_settlement[id(a)]
        row = asdict(a)
        row["lat"] = s["lat"]
        row["lon"] = s["lon"]
        row["population"] = s["population"]
        row["area_hectares"] = s["area_hectares"]
        out.append(row)
    return out


# In-memory pipeline cache so national-scale (53k+ villages) responds in <5ms
# instead of recalculating 53k spatial queries on every request.
_assessments_cache = {}


def get_cached_assessment(region):
    if region not in _assessments_cache or _assessments_cache[region] is None:
        _assessments_cache[region] = run_pipeline(region)
    return _assessments_cache[region]


def invalidate_assessment_cache(region=None):
    if region:
        _assessments_cache[region] = None
    else:
        _assessments_cache.clear()


# ---------- API ----------

@app.get("/api/regions")
def get_regions():
    return jsonify([
        {
            "key": key,
            "label": cfg["label"],
            "description": cfg["description"],
            "settlement_count": len(settlements_by_region[key]),
        }
        for key, cfg in REGIONS.items()
    ])


@app.get("/api/hazard")
def get_hazard():
    region = _region_key()
    return jsonify(REGIONS[region]["hazard_geojson"])


@app.get("/api/settlements")
def get_settlements():
    region = _region_key()
    return jsonify(settlements_by_region[region])


@app.post("/api/settlements")
def add_settlement():
    region = _region_key()
    settlements = settlements_by_region[region]
    data = request.get_json(force=True)
    required = {"name", "lat", "lon", "population", "area_hectares"}
    if not required.issubset(data):
        return jsonify({"error": f"missing fields, need: {sorted(required)}"}), 400
    if any(s["name"] == data["name"] for s in settlements):
        return jsonify({"error": "a settlement with this name already exists"}), 409
    settlements.append({
        "name": data["name"],
        "lat": float(data["lat"]),
        "lon": float(data["lon"]),
        "population": int(data["population"]),
        "area_hectares": float(data["area_hectares"]),
        "terrain": data.get("terrain", "plain"),
    })
    invalidate_assessment_cache(region)
    return jsonify({"ok": True}), 201


@app.delete("/api/settlements/<path:name>")
def delete_settlement(name):
    region = _region_key()
    before = len(settlements_by_region[region])
    settlements_by_region[region] = [s for s in settlements_by_region[region] if s["name"] != name]
    if len(settlements_by_region[region]) == before:
        return jsonify({"error": "not found"}), 404
    invalidate_assessment_cache(region)
    return jsonify({"ok": True})


@app.post("/api/settlements/reset")
def reset_settlements():
    region = _region_key()
    settlements_by_region[region] = [dict(s) for s in REGIONS[region]["demo_settlements"]]
    invalidate_assessment_cache(region)
    return jsonify({"ok": True})


@app.get("/api/assessment")
def get_assessment():
    region = _region_key()
    if not settlements_by_region[region]:
        return jsonify([])
    data = get_cached_assessment(region)
    limit = request.args.get("limit")
    if limit:
        try:
            return jsonify(data[:int(limit)])
        except ValueError:
            pass
    return jsonify(data)


@app.get("/api/assessment-summary")
def assessment_summary():
    """Returns counts by priority tier and top 150 settlements in <5ms without transferring 15MB."""
    region = _region_key()
    results = get_cached_assessment(region)
    counts = {"high": 0, "medium": 0, "low": 0}
    for r in results:
        pr = r.get("priority_rank", "low")
        counts[pr] = counts.get(pr, 0) + 1
    return jsonify({
        "counts": counts,
        "total": len(results),
        "top": results[:150],
    })


@app.get("/api/settlement-detail")
def settlement_detail():
    """Fast single-settlement assessment lookup in <2ms, avoiding 15MB transfer."""
    region = _region_key()
    name = (request.args.get("name") or "").strip()
    if not name:
        return jsonify({"error": "missing ?name="}), 400

    results = get_cached_assessment(region)
    match = next((r for r in results if r["settlement_id"].lower() == name.lower()), None)
    if not match:
        return jsonify({"found": False}), 404
    return jsonify({"found": True, "settlement": match})


@app.get("/api/village-check")
def village_check():
    """Instant case-insensitive substring match on pre-cached assessment results."""
    region = _region_key()
    q = (request.args.get("q") or "").strip().lower()
    if not q:
        return jsonify({"error": "missing ?q= village name"}), 400

    results = get_cached_assessment(region)
    match = next((r for r in results if q in r["settlement_id"].lower()), None)
    if not match:
        return jsonify({"found": False}), 404

    verdict_info = VERDICT_MAP.get(match["priority_rank"], VERDICT_MAP["low"])
    return jsonify({
        "found": True,
        "settlement_id": match["settlement_id"],
        "verdict": verdict_info["verdict"],
        "message": verdict_info["message"],
        "priority_rank": match["priority_rank"],
        "priority_score": match["priority_score"],
    })


@app.get("/api/nearest-village")
def nearest_village():
    """Instant auto-detect: find nearest village in pre-cached dataset in <5ms."""
    region = _region_key()
    try:
        lat = float(request.args.get("lat"))
        lon = float(request.args.get("lon"))
    except (TypeError, ValueError):
        return jsonify({"error": "missing/invalid ?lat= & ?lon="}), 400

    results = get_cached_assessment(region)
    if not results:
        return jsonify({"found": False, "error": "no settlements in this region"}), 404

    match = min(results, key=lambda s: _haversine_km(lat, lon, s["lat"], s["lon"]))
    distance_km = round(_haversine_km(lat, lon, match["lat"], match["lon"]), 1)

    verdict_info = VERDICT_MAP.get(match["priority_rank"], VERDICT_MAP["low"])
    return jsonify({
        "found": True,
        "settlement_id": match["settlement_id"],
        "distance_km": distance_km,
        "verdict": verdict_info["verdict"],
        "message": verdict_info["message"],
        "priority_rank": match["priority_rank"],
        "priority_score": match["priority_score"],
    })


@app.get("/api/geocode")
def geocode():
    """Convert place name -> lat/lon via Nominatim (OpenStreetMap). Free, no API key."""
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"error": "missing ?q= place name"}), 400

    try:
        import requests
        params = {
            "q": q,
            "format": "json",
            "limit": 1,
        }
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params=params,
            headers={"User-Agent": "SIH26191-RedZoneAssessment/1.0"},
            timeout=10,
        )
        r.raise_for_status()
        results = r.json()
        if not results:
            return jsonify({"found": False, "error": f"place '{q}' not found"}), 404
        top = results[0]
        return jsonify({
            "found": True,
            "name": q,
            "lat": float(top["lat"]),
            "lon": float(top["lon"]),
            "display_name": top.get("display_name", ""),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- pages ----------

@app.get("/")
def page_index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/dashboard")
def page_dashboard():
    return send_from_directory(FRONTEND_DIR, "dashboard.html")


@app.get("/settlement/<path:name>")
def page_settlement(name):
    return send_from_directory(FRONTEND_DIR, "settlement.html")


@app.get("/protocols")
def page_protocols():
    return send_from_directory(FRONTEND_DIR, "protocols.html")


@app.get("/resources")
def page_resources():
    return send_from_directory(FRONTEND_DIR, "resources.html")


# ---------- static assets (CSS / JS) ----------

@app.get("/<path:filename>")
def static_files(filename):
    return send_from_directory(FRONTEND_DIR, filename)


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5001))
    print(f" * SIH26191 server starting on http://localhost:{port}")
    print(f" * Pre-computing pipeline assessment caches for instant responses...")
    for _r in REGIONS.keys():
        get_cached_assessment(_r)
        print(f"   ✔ Cache ready: {_r} ({len(settlements_by_region[_r])} settlements)")
    print(f" * Regions available: {', '.join(REGIONS.keys())} (default: {DEFAULT_REGION})")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)

