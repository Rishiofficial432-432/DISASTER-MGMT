"""
Step 6: Demo settlement data for the Majuli, Assam pilot.

SOURCED (not synthetic): coordinates and populations below are from Wikipedia
(sourced to Census of India 2011) for two real villages in Majuli district:
  - Mohkhuti No.3: https://en.wikipedia.org/wiki/Mohkhuti_No.3
  - Mohkhuti No.2: https://en.wikipedia.org/wiki/Mohkhuti_No.2

Area (hectares) is NOT from Census data (Census publishes population, not
built-up area) — it's an estimate based on typical Majuli village footprint,
flagged clearly below. Refine with actual satellite/drone-measured area
(via drone_analyze, reused from the anomaly-detection codebase) before
the final demo — that's the intended real data source for this field.
"""

DEMO_SETTLEMENTS = [
    {
        "name": "Mohkhuti No.3",
        "lat": 26.983,
        "lon": 94.188,
        "population": 1025,          # Census 2011, via Wikipedia
        "area_hectares": 8.0,        # ESTIMATED — replace with drone_analyze measurement
        "terrain": "plain",
        "source": "https://en.wikipedia.org/wiki/Mohkhuti_No.3",
    },
    {
        "name": "Mohkhuti No.2",
        "lat": 26.954,
        "lon": 94.189,
        "population": 1485,          # Census 2011, via Wikipedia
        "area_hectares": 14.0,       # ESTIMATED — replace with drone_analyze measurement
        "terrain": "plain",
        "source": "https://en.wikipedia.org/wiki/Mohkhuti_No.2",
    },
]
