"""
Geocode a village/place name to lat/lon using Nominatim (OpenStreetMap) —
free, no API key required.

This is NOT a scraper — it's a documented public API. Nominatim's usage
policy requires: max 1 request/second, and a real User-Agent identifying
your app (not a browser-spoofed one). Both are respected below.

Usage:
    python geocode_village.py "Majuli, Assam, India"
    python geocode_village.py --batch villages.txt --out geocoded.json

villages.txt format: one place name per line.

Output JSON matches the schema used by data/demo_settlements.py:
    {"name": ..., "lat": ..., "lon": ..., "population": null, "area_hectares": null, "terrain": "plain"}
(population/area are left null — Nominatim doesn't provide these; fill them
in from Census/data.gov.in data separately.)
"""

import sys
import json
import time
import argparse
import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {
    # Nominatim's usage policy requires a real identifying User-Agent
    "User-Agent": "SIH26191-RedZoneAssessment/1.0 (research/prototype use)"
}
RATE_LIMIT_SEC = 1.1  # Nominatim policy: max 1 req/sec, add a small buffer


def geocode(place_name: str) -> dict | None:
    params = {
        "q": place_name,
        "format": "json",
        "limit": 1,
        "addressdetails": 0,
    }
    r = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=15)
    r.raise_for_status()
    results = r.json()
    if not results:
        return None
    top = results[0]
    return {
        "name": place_name,
        "lat": float(top["lat"]),
        "lon": float(top["lon"]),
        "population": None,       # not provided by Nominatim — fill from Census/data.gov.in
        "area_hectares": None,    # not provided by Nominatim — fill from Census/data.gov.in
        "terrain": "plain",       # default assumption — adjust manually if hilly
        "display_name": top.get("display_name"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("place", nargs="?", help="Single place name to geocode")
    parser.add_argument("--batch", help="Path to a text file, one place name per line")
    parser.add_argument("--out", default="geocoded_settlements.json", help="Output JSON file")
    args = parser.parse_args()

    if not args.place and not args.batch:
        parser.error("Provide a place name or --batch file")

    places = [args.place] if args.place else []
    if args.batch:
        with open(args.batch) as f:
            places.extend(line.strip() for line in f if line.strip())

    results = []
    for i, place in enumerate(places):
        print(f"Geocoding: {place}")
        try:
            result = geocode(place)
            if result:
                results.append(result)
                print(f"  -> {result['lat']}, {result['lon']}")
            else:
                print(f"  -> not found")
        except Exception as e:
            print(f"  -> error: {e}")
        if i < len(places) - 1:
            time.sleep(RATE_LIMIT_SEC)

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote {len(results)} result(s) to {args.out}")


if __name__ == "__main__":
    main()
