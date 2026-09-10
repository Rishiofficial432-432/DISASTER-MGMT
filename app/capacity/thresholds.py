"""
Step 3: Residential capacity thresholds — NOT event-crowd density numbers.

SOURCED from URDPFI Guidelines 2014/2015 (Ministry of Housing & Urban Affairs,
Govt of India) — gross developed-area density norms, persons per hectare (pph),
by settlement type and terrain. This is the official Indian planning standard,
distinct from event-crowd-crush thresholds (e.g. Fruin's Level of Service).

Table (URDPFI 2014/2015, Vol I):
  Settlement type    | Plain areas (pph) | Hill areas (pph)
  -------------------|--------------------|-------------------
  Small town         | 75–125             | 45–75
  Medium town        | 100–150            | 60–90
  Large city         | 100–150            | 60–90
  Metro city         | 125–175            | —

Note: URDPFI norms target statutory towns, not unplanned rural villages —
but MoHUA guidance explicitly says the concepts extend to all human
settlements. For a rural pilot village with no formal density classification,
treat it as "small town, plain" (75–125 pph) unless it's in hilly terrain
(45–75 pph), and flag this assumption in the demo/pitch narrative.

What drives relocation priority is NOT raw density alone — it's density
relative to safe capacity GIVEN hazard exposure (evacuation route capacity
degrades in flood/landslide conditions). This module gives the density tier;
priority_engine.py combines it with hazard severity.
"""

from dataclasses import dataclass


@dataclass
class DensityBand:
    min_pph: float
    max_pph: float
    label: str


# Plain-area small-town band, per URDPFI 2014/2015 — default for rural pilot villages
PLAIN_SMALL_TOWN = DensityBand(75, 125, "URDPFI small town, plain")
# Hill-area small-town band — use if pilot village is in hilly/hazard-prone hill terrain
HILL_SMALL_TOWN = DensityBand(45, 75, "URDPFI small town, hill")

CAPACITY_TIERS = {
    "low": {"max_density": PLAIN_SMALL_TOWN.min_pph, "label": "Within safe capacity"},
    "moderate": {"max_density": PLAIN_SMALL_TOWN.max_pph, "label": "Approaching capacity"},
    "high": {"max_density": float("inf"), "label": "Overcrowded (exceeds URDPFI small-town norm)"},
}


def classify_density(persons_per_hectare: float, terrain: str = "plain") -> str:
    """
    Classify a density value into a capacity tier using URDPFI small-town norms.
    terrain: "plain" or "hill" — picks the appropriate band.
    Returns one of: "low", "moderate", "high".
    """
    band = HILL_SMALL_TOWN if terrain == "hill" else PLAIN_SMALL_TOWN
    if persons_per_hectare <= band.min_pph:
        return "low"
    elif persons_per_hectare <= band.max_pph:
        return "moderate"
    else:
        return "high"


def hectare_capacity(area_hectares: float, terrain: str = "plain") -> tuple[float, float]:
    """Return (min_safe_population, max_safe_population) for a given area."""
    band = HILL_SMALL_TOWN if terrain == "hill" else PLAIN_SMALL_TOWN
    return (area_hectares * band.min_pph, area_hectares * band.max_pph)
