"""
Step 1: Load flood/landslide hazard zone GeoJSON for the pilot area.

NDMA's flood hazard atlases are published as PDFs, not downloadable GeoJSON,
so there's no public one-click source for most districts. This prototype
loads a pre-built hazard polygon (data/hazard_zones_majuli_demo.geojson,
Majuli, Assam) from disk. Production version would query NDEM/Bhuvan's
Flood Hazard Zonation WMS service instead of a static file.
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_hazard_geojson(path: str) -> dict:
    """Load a local hazard GeoJSON file into memory."""
    with open(path, "r") as f:
        return json.load(f)
