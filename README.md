# SIH26191 — Hazard Red Zones, Carrying Capacity & Relocation

Intelligent Identification of Hazard-Based Red Zones, Carrying Capacity
Assessment, and Immediate Relocation Needs for Vulnerable Habitations.
Ministry of Home Affairs · Disaster Management · Software.

## What it does

1. **Hazard mapping** — loads a flood hazard zone (demo polygon, Majuli, Assam)
2. **Exposure check** — point-in-polygon test: is a settlement inside the hazard zone?
3. **Carrying capacity** — classifies settlement density against URDPFI 2014/2015
   residential planning norms (75–125 persons/hectare, small town, plain terrain)
4. **Relocation priority** — rule-based score combining hazard severity + overcrowding
5. **Dashboard** — map + ranked assessment view

## Stack

- Backend: Flask (Python), Shapely for geometry
- Frontend: plain HTML/CSS/JS, Leaflet for the map — no framework
- Data: Census 2011 village data (Mohkhuti No.2, Mohkhuti No.3, Majuli district)

## Run it

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python backend/server.py
```

Open http://localhost:5000

Or use `./start.sh` once the venv is set up.

## Structure

```
backend/server.py       Flask API + serves frontend
frontend/                index.html, style.css, app.js
app/hazard/               GeoJSON load, point-in-polygon
app/capacity/              URDPFI density classification
app/relocation/             priority scoring engine
data/                    demo hazard zone + real village data
research/pdf_scraper.py  standalone tool to fetch NDMA/MoHUA guideline PDFs
```

## Known limitations (documented, not hidden)

- Hazard zone is a hand-digitized demo polygon, not live NDMA/NRSC data
  (NDMA flood atlases are published as PDFs, not machine-readable GeoJSON)
- Settlement area is estimated, not drone/satellite-measured
- Priority formula validated on 2 villages only — expand before treating as final
