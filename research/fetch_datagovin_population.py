"""
Fetch village population data from data.gov.in's Open Government Data (OGD)
Platform API — free, but requires a free API key (not scraping; this is a
documented REST API, more reliable than scraping).

HOW TO GET A FREE API KEY (2 minutes):
  1. Go to https://data.gov.in
  2. Click "Register" (top right) — free, just email + basic details
  3. After login, go to your profile -> "My Account" -> copy your API Key
  4. Set it as an environment variable before running this script:
       export DATA_GOV_IN_API_KEY="your-key-here"
     or pass --key on the command line

FINDING A DATASET RESOURCE ID:
  data.gov.in doesn't have one single "all villages" dataset — data is split
  by state/district/theme. To find one:
  1. Go to https://data.gov.in/catalogs and search e.g. "village population Assam"
  2. Open a matching dataset, click "API" tab — it shows the resource_id and
     a sample API URL you can copy directly
  3. Pass that resource_id to this script with --resource-id

Usage:
    export DATA_GOV_IN_API_KEY="your-key"
    python fetch_datagovin_population.py --resource-id <RESOURCE_ID> --out villages.json

Output JSON is raw records from the dataset — inspect the field names (they
vary per dataset) and map them into data/demo_settlements.py's schema
(name, lat, lon, population, area_hectares, terrain) manually, since data.gov.in
datasets don't follow one consistent column naming convention.
"""

import os
import sys
import json
import argparse
import requests

BASE_URL = "https://api.data.gov.in/resource"


def fetch_resource(resource_id: str, api_key: str, limit: int = 1000, offset: int = 0) -> dict:
    url = f"{BASE_URL}/{resource_id}"
    params = {
        "api-key": api_key,
        "format": "json",
        "limit": limit,
        "offset": offset,
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_all(resource_id: str, api_key: str, page_size: int = 1000) -> list[dict]:
    all_records = []
    offset = 0
    while True:
        print(f"Fetching offset {offset}...")
        data = fetch_resource(resource_id, api_key, limit=page_size, offset=offset)
        records = data.get("records", [])
        if not records:
            break
        all_records.extend(records)
        total = int(data.get("total", 0))
        offset += page_size
        if offset >= total:
            break
    return all_records


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--resource-id", required=True, help="Dataset resource ID from data.gov.in")
    parser.add_argument("--key", default=os.environ.get("DATA_GOV_IN_API_KEY"), help="API key (or set DATA_GOV_IN_API_KEY env var)")
    parser.add_argument("--out", default="datagovin_records.json", help="Output JSON file")
    args = parser.parse_args()

    if not args.key:
        print("ERROR: No API key. Set DATA_GOV_IN_API_KEY env var or pass --key.")
        print("Get a free key at https://data.gov.in (see docstring for steps).")
        sys.exit(1)

    records = fetch_all(args.resource_id, args.key)
    print(f"\nFetched {len(records)} record(s).")
    if records:
        print("Sample record (inspect field names to map into your app's schema):")
        print(json.dumps(records[0], indent=2))

    with open(args.out, "w") as f:
        json.dump(records, f, indent=2)
    print(f"\nWrote all records to {args.out}")


if __name__ == "__main__":
    main()
