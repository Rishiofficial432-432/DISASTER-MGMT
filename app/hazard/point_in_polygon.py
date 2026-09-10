"""
Step 2: Point-in-polygon check — is a settlement location inside a hazard zone?

Uses shapely. Input: settlement lat/lon (or polygon boundary from drone_autocontour),
hazard zone GeoJSON (from load_hazard_data.py).
"""

from shapely.geometry import shape, Point, Polygon
from typing import Optional


def point_in_hazard_zone(lat: float, lon: float, hazard_geojson: dict) -> Optional[dict]:
    """
    Check if a point falls inside any hazard zone polygon.
    Returns the matching feature's properties (hazard_type, severity) or None.
    """
    point = Point(lon, lat)  # GeoJSON is (lon, lat)
    for feature in hazard_geojson.get("features", []):
        polygon = shape(feature["geometry"])
        if polygon.contains(point):
            return feature.get("properties", {})
    return None


def settlement_polygon_overlap(settlement_polygon: Polygon, hazard_geojson: dict) -> list[dict]:
    """
    For a settlement boundary (e.g. output of drone_autocontour), check overlap
    with each hazard zone. Returns list of {hazard_type, severity, overlap_fraction}.
    """
    results = []
    settlement_area = settlement_polygon.area
    if settlement_area == 0:
        return results

    for feature in hazard_geojson.get("features", []):
        hazard_poly = shape(feature["geometry"])
        if settlement_polygon.intersects(hazard_poly):
            overlap_area = settlement_polygon.intersection(hazard_poly).area
            overlap_fraction = overlap_area / settlement_area
            props = feature.get("properties", {})
            results.append({
                "hazard_type": props.get("hazard_type"),
                "severity": props.get("severity"),
                "overlap_fraction": round(overlap_fraction, 3),
            })
    return results
