/* ══════════════════════════════════════════════
   CONSTANTS
══════════════════════════════════════════════ */
const RANK_COLOR = { high: "#C0392B", medium: "#D98324", low: "#1F7A5C" };
const RANK_BG    = { high: "#FBEAEA", medium: "#FCF1E3", low: "#E9F4EE" };

const REGION_INFO = {
  majuli: {
    subtitle: "Pilot area: Majuli, Assam — Brahmaputra floodplain",
    bannerText: "Hazard polygon is hand-digitised (Majuli). Population figures are Census estimates. Do not use for real emergency decisions.",
    footnote: "Density thresholds sourced from URDPFI 2014/2015 guidelines (small-town, plain-area norm: 75–125 persons/hectare). Hazard zone is a demo polygon for Majuli, Assam.",
    resetLabel: "Reset to Majuli Pilot",
    mapCenter: [26.99, 94.19],
    mapZoom: 11,
    geocodeSuffix: ", Assam, India",
  },
  national: {
    subtitle: "All-India: 53,223 real villages across 15 states, flagged by ≥5 documented historical flood events (India Flood Inventory V3, 1960s–2020) — population is REAL Census 2011 data",
    bannerText: "REAL data throughout: flood-history hazard flagging (India Flood Inventory V3) AND real Census 2011 population/household counts, joined by official PC11 village code (97.9% match rate; unmatched villages excluded rather than estimated). Still a decision-support prototype, not certified for real emergency decisions.",
    footnote: "Hazard flagging is based on real historical flood event records (≥5 distinct events per village, 1960s–2020, 15 states). Population and households are real Census 2011 Primary Census Abstract figures, joined by exact PC11 code — not estimated.",
    resetLabel: "Reset to National Dataset",
    mapCenter: [22.9, 79.4],
    mapZoom: 5,
    geocodeSuffix: ", India",
  },
};

const TAB_DESCRIPTIONS = {
  map: "See every settlement on the map. Red shaded areas are real flood-hazard zones — click any marker for its priority score.",
  assessment: "A ranked list of settlements, highest priority first. Priority combines real hazard exposure with overcrowding (population vs. land area).",
  add: "Manually add any village — real or hypothetical — and see how it scores against the same hazard zones as everything else in this dataset.",
};

let CURRENT_REGION = (() => {
  const params = new URLSearchParams(window.location.search);
  return params.get("region") === "national" ? "national" : "majuli";
})();

function regionParam() {
  return `region=${encodeURIComponent(CURRENT_REGION)}`;
}

function applyRegionChrome() {
  const info = REGION_INFO[CURRENT_REGION];
  const subtitleEl = document.getElementById("page-subtitle");
  if (subtitleEl) subtitleEl.textContent = info.subtitle;
  const bannerTextEl = document.getElementById("demo-banner-text");
  if (bannerTextEl) bannerTextEl.textContent = info.bannerText;
  const footnoteEl = document.getElementById("assessment-footnote");
  if (footnoteEl) footnoteEl.textContent = info.footnote;
  const resetBtn = document.getElementById("reset-btn");
  if (resetBtn) resetBtn.innerHTML = `<span class="material-symbols-outlined btn-icon">restart_alt</span> ${info.resetLabel}`;
  const banner = document.getElementById("demo-banner");
  if (banner) banner.style.display = "flex"; // re-show if user dismissed it before switching
}

let map, markerLayer, hazardLayer;

/* ══════════════════════════════════════════════
   TAB SYSTEM
══════════════════════════════════════════════ */
function switchTab(tabName) {
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
  const panel = document.getElementById(`panel-${tabName}`);
  if (panel) panel.classList.add("active");

  document.querySelectorAll(".tab").forEach(t =>
    t.classList.toggle("active", t.dataset.tab === tabName));

  document.querySelectorAll(".nav-item[data-tab]").forEach(a => {
    a.classList.toggle("active", a.dataset.tab === tabName);
    const icon = a.querySelector(".material-symbols-outlined");
    if (icon) icon.style.fontVariationSettings =
      a.dataset.tab === tabName ? "'FILL' 1" : "'FILL' 0";
  });

  document.querySelectorAll(".bottom-nav-item").forEach(a =>
    a.classList.toggle("active", a.dataset.tab === tabName));

  const descEl = document.getElementById("tab-desc");
  if (descEl && TAB_DESCRIPTIONS[tabName]) descEl.textContent = TAB_DESCRIPTIONS[tabName];

  if (tabName === "map" && map) setTimeout(() => map.invalidateSize(), 60);
}

document.querySelectorAll("[data-tab]").forEach(el => {
  el.addEventListener("click", e => { e.preventDefault(); switchTab(el.dataset.tab); });
});

switchTab("map");

/* ══════════════════════════════════════════════
   MAP
══════════════════════════════════════════════ */
let map, markerLayer, hazardLayer;
let markersById = {};
let currentAssessments = [];

function initMap() {
  const info = REGION_INFO[CURRENT_REGION];
  map = L.map("map", { zoomControl: true }).setView(info.mapCenter, info.mapZoom);
  L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", {
    attribution: "Map data: OpenStreetMap contributors, SRTM | Style: OpenTopoMap",
    maxZoom: 17,
  }).addTo(map);

  // Clustered with chunkedLoading so large datasets (53k+ villages)
  // process asynchronously without freezing the browser's UI thread.
  markerLayer = L.markerClusterGroup({
    maxClusterRadius: 45,
    spiderfyOnMaxZoom: true,
    disableClusteringAtZoom: 14,
    chunkedLoading: true,
    chunkInterval: 100,
    chunkDelay: 20,
    removeOutsideVisibleBounds: true,
  });
  map.addLayer(markerLayer);
}

async function loadHazardZone() {
  try {
    if (hazardLayer) { map.removeLayer(hazardLayer); hazardLayer = null; }
    const res = await fetch(`/api/hazard?${regionParam()}`);
    if (!res.ok) return;
    const geojson = await res.json();
    hazardLayer = L.geoJSON(geojson, {
      style: { fillColor: "#C0392B", color: "#C0392B", fillOpacity: 0.22, weight: 2, dashArray: "6 4" },
      onEachFeature: (feat, layer) => {
        const p = feat.properties || {};
        const label = p.hazard_type || p.MainCause || "Hazard Zone";
        const sev = p.severity || p.State || "—";
        layer.bindTooltip(`<strong>${label}</strong><br>${sev}`);
      },
    }).addTo(map);
  } catch (e) { console.warn("Hazard zone unavailable:", e); }
}

function buildPopupHtml(a) {
  const color = RANK_COLOR[a.priority_rank] || "#888";
  return `
    <div style="font-family:'IBM Plex Sans',sans-serif;min-width:180px;">
      <div style="font-family:'IBM Plex Serif',serif;font-size:1rem;font-weight:600;color:#0F1B2D;margin-bottom:4px;">${a.settlement_id}</div>
      <div style="font-size:0.75rem;color:#5B6472;font-family:'IBM Plex Mono',monospace;margin-bottom:8px;">
        ${Number(a.population).toLocaleString()} people · ${a.area_hectares} ha · ${a.terrain}
      </div>
      <div style="display:flex;gap:12px;margin-bottom:10px;">
        <div><div style="font-family:'IBM Plex Mono',monospace;font-size:1.4rem;font-weight:700;color:#0F1B2D;">${a.priority_score}</div><div style="font-size:0.6rem;color:#5B6472;text-transform:uppercase;letter-spacing:.08em;">Score</div></div>
        <div><div style="font-family:'IBM Plex Mono',monospace;font-size:1.4rem;font-weight:700;color:#0F1B2D;">${a.persons_per_hectare}</div><div style="font-size:0.6rem;color:#5B6472;text-transform:uppercase;letter-spacing:.08em;">pph</div></div>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <span style="padding:3px 10px;border-radius:99px;font-size:0.65rem;font-family:'IBM Plex Mono',monospace;font-weight:700;text-transform:uppercase;background:${RANK_BG[a.priority_rank]};color:${color};">${a.priority_rank} priority</span>
        <a href="/settlement/${encodeURIComponent(a.settlement_id)}?${regionParam()}" style="font-size:0.72rem;color:#0F1B2D;font-family:'IBM Plex Mono',monospace;text-decoration:none;">Details →</a>
      </div>
    </div>
  `;
}

function focusSettlementOnMap(lat, lon, name) {
  switchTab("map");
  // Close mobile drawer if open
  const sidenav = document.getElementById("sidenav");
  const backdrop = document.getElementById("sidenav-backdrop");
  if (sidenav && sidenav.classList.contains("open")) {
    sidenav.classList.remove("open");
    if (backdrop) backdrop.classList.remove("active");
  }
  if (!map) return;
  map.setView([lat, lon], 14, { animate: true });
  const marker = markersById[name];
  if (marker && markerLayer) {
    markerLayer.zoomToShowLayer(marker, () => {
      marker.openPopup();
    });
  }
}

function renderMarkers(assessment) {
  markerLayer.clearLayers();
  markersById = {};
  const markers = [];

  assessment.forEach(a => {
    const color = RANK_COLOR[a.priority_rank] || "#888";
    const marker = L.circleMarker([a.lat, a.lon], {
      radius: 10,
      color,
      fillColor: color,
      fillOpacity: 0.85,
      weight: 2,
    });

    // Lazy popup evaluation: only generate HTML when clicked
    marker.bindPopup(() => buildPopupHtml(a), { maxWidth: 240 });

    if (assessment.length <= 100) {
      marker.bindTooltip(a.settlement_id, { direction: "top", offset: [0, -8] });
    }

    markersById[a.settlement_id] = marker;
    markers.push(marker);
  });

  markerLayer.addLayers(markers);
}

/* ══════════════════════════════════════════════
   SIDENAV SETTLEMENT LIST (Fast, Searchable)
══════════════════════════════════════════════ */
let sidenavFilterQuery = "";

function renderSidenavSettlements(assessment) {
  const el = document.getElementById("sidenav-settlements");
  if (!el) return;
  el.innerHTML = "";

  if (!assessment || !assessment.length) {
    el.innerHTML = `<div style="padding:8px 16px;font-size:0.75rem;color:#5B6472;">No settlements yet.</div>`;
    return;
  }

  // Filter box for large datasets
  if (assessment.length > 50) {
    const searchBox = document.createElement("div");
    searchBox.className = "sidenav-search-box";
    searchBox.innerHTML = `
      <input type="text" class="sidenav-search-input" id="sidenav-search-input"
             placeholder="Search ${assessment.length.toLocaleString()} villages…"
             value="${sidenavFilterQuery.replace(/"/g, '&quot;')}" autocomplete="off">
      <div class="sidenav-meta-count" id="sidenav-count-text"></div>
    `;
    el.appendChild(searchBox);

    const input = searchBox.querySelector("#sidenav-search-input");
    input.addEventListener("input", (e) => {
      sidenavFilterQuery = e.target.value.trim().toLowerCase();
      updateSidenavList(assessment);
    });
  }

  const container = document.createElement("div");
  container.id = "sidenav-rows-container";
  container.style.display = "flex";
  container.style.flexDirection = "column";
  container.style.gap = "2px";
  el.appendChild(container);

  updateSidenavList(assessment);
}

function updateSidenavList(assessment) {
  const container = document.getElementById("sidenav-rows-container");
  const countText = document.getElementById("sidenav-count-text");
  if (!container) return;
  container.innerHTML = "";

  let filtered = assessment;
  if (sidenavFilterQuery) {
    filtered = assessment.filter(a => a.settlement_id.toLowerCase().includes(sidenavFilterQuery));
  }

  const maxToShow = 50;
  const toRender = filtered.slice(0, maxToShow);

  if (countText) {
    if (sidenavFilterQuery) {
      countText.textContent = `Found ${filtered.length.toLocaleString()} (showing ${toRender.length})`;
    } else {
      countText.textContent = `Top ${toRender.length} of ${assessment.length.toLocaleString()} priority villages`;
    }
  }

  if (!toRender.length) {
    container.innerHTML = `<div style="padding:8px 12px;font-size:0.74rem;color:#5B6472;">No matches found.</div>`;
    return;
  }

  toRender.forEach(a => {
    const row = document.createElement("div");
    row.className = `sidenav-s-row rank-${a.priority_rank}`;
    row.title = `${a.settlement_id} (${a.priority_rank} priority, score ${a.priority_score})`;
    row.innerHTML = `
      <span class="s-name">${a.settlement_id}</span>
      <button class="s-del" title="Remove settlement" data-name="${a.settlement_id}">✕</button>
    `;
    row.querySelector(".s-del").addEventListener("click", async e => {
      e.stopPropagation();
      try {
        await fetch(`/api/settlements/${encodeURIComponent(e.currentTarget.dataset.name)}?${regionParam()}`, { method: "DELETE" });
        await refreshAll();
      } catch (err) {
        alert("Could not delete settlement. Server might be busy.");
      }
    });
    row.addEventListener("click", (e) => {
      if (e.target.classList.contains("s-del")) return;
      focusSettlementOnMap(a.lat, a.lon, a.settlement_id);
    });
    container.appendChild(row);
  });
}

/* ══════════════════════════════════════════════
   ASSESSMENT CARDS
══════════════════════════════════════════════ */
const MAX_CARDS_RENDERED = 150;

function renderAssessmentCards(assessment) {
  const el = document.getElementById("assessment-cards");
  if (!el) return;
  el.innerHTML = "";

  if (!assessment.length) {
    el.innerHTML = `
      <div class="empty-state">
        <span class="material-symbols-outlined">location_off</span>
        <p>No settlements yet.<br>Add one using the <strong>Add Settlement</strong> tab.</p>
      </div>`;
    return;
  }

  const truncated = assessment.length > MAX_CARDS_RENDERED;
  const toRender = truncated ? assessment.slice(0, MAX_CARDS_RENDERED) : assessment;

  if (truncated) {
    const notice = document.createElement("p");
    notice.className = "footnote";
    notice.style.marginBottom = "12px";
    notice.textContent = `Showing top ${MAX_CARDS_RENDERED} of ${assessment.length.toLocaleString()} settlements, ranked by priority score. Use the map view to see all of them (clustered).`;
    el.appendChild(notice);
  }

  toRender.forEach(a => {
    const chipClass = `chip-${a.priority_rank}`;
    const hazardHtml = a.hazard_type
      ? `<div class="hazard-line hazard-in">
           <span class="material-symbols-outlined" style="font-variation-settings:'FILL' 1">warning</span>
           Inside a <strong>${a.hazard_type}</strong> hazard zone — severity <strong>${a.hazard_severity}</strong>
         </div>`
      : `<div class="hazard-line hazard-out">
           <span class="material-symbols-outlined" style="font-variation-settings:'FILL' 1">check_circle</span>
           Not inside a mapped hazard zone
         </div>`;

    const card = document.createElement("div");
    card.className = `rz-card rank-${a.priority_rank}`;
    card.innerHTML = `
      <div class="rz-card-header">
        <div>
          <div class="settlement-name">${a.settlement_id}</div>
          <div class="settlement-meta">${Number(a.population).toLocaleString()} people · ${a.area_hectares} ha · ${a.terrain} terrain</div>
        </div>
        <span class="rz-chip ${chipClass}">${a.priority_rank} priority</span>
      </div>
      <div class="rz-card-body">
        <div class="readouts">
          <div><div class="readout-val">${a.priority_score}</div><div class="readout-label">Priority Score</div></div>
          <div><div class="readout-val">${a.persons_per_hectare}</div><div class="readout-label">Persons / ha</div></div>
          <div><div class="readout-val" style="text-transform:capitalize">${a.density_tier}</div><div class="readout-label">Density Tier</div></div>
        </div>
        ${hazardHtml}
        <div style="margin-top:12px;display:flex;gap:16px;align-items:center;">
          <a href="/settlement/${encodeURIComponent(a.settlement_id)}?${regionParam()}"
             style="font-family:'IBM Plex Mono',monospace;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.06em;color:#0F1B2D;text-decoration:none;">
            View full details →
          </a>
          <button type="button" class="view-on-map-link"
                  data-lat="${a.lat}" data-lon="${a.lon}" data-name="${a.settlement_id}"
                  style="background:none;border:none;cursor:pointer;font-family:'IBM Plex Mono',monospace;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.06em;color:#1F7A5C;">
            Locate on map ⌖
          </button>
        </div>
      </div>
    `;
    card.querySelector(".view-on-map-link").addEventListener("click", (e) => {
      const btn = e.currentTarget;
      focusSettlementOnMap(parseFloat(btn.dataset.lat), parseFloat(btn.dataset.lon), btn.dataset.name);
    });
    el.appendChild(card);
  });
}

/* ══════════════════════════════════════════════
   ORCHESTRATION
══════════════════════════════════════════════ */
async function refreshAll() {
  try {
    const r = await fetch(`/api/assessment?${regionParam()}`);
    if (r.ok) {
      currentAssessments = await r.json();
      renderSidenavSettlements(currentAssessments);
      renderMarkers(currentAssessments);
      renderAssessmentCards(currentAssessments);
    }
  } catch (err) {
    console.warn("Could not fetch assessments:", err);
  }
}

/* ══════════════════════════════════════════════
   ADD SETTLEMENT FORM
══════════════════════════════════════════════ */
/* ══════════════════════════════════════════════
   GEOCODE LOOKUP ("Look up coordinates" button)
══════════════════════════════════════════════ */
const geocodeBtn = document.getElementById("f-geocode-btn");
if (geocodeBtn) {
  geocodeBtn.addEventListener("click", async () => {
    const name = document.getElementById("f-name").value.trim();
    if (!name) { showFormError("Enter a settlement name first to look up its coordinates."); return; }

    geocodeBtn.disabled = true;
    geocodeBtn.innerHTML = `<span class="material-symbols-outlined btn-icon" style="font-size:15px">hourglass_top</span> Looking up…`;
    clearFormError();

    try {
      const res = await fetch(`/api/geocode?q=${encodeURIComponent(name + REGION_INFO[CURRENT_REGION].geocodeSuffix)}`);
      const data = await res.json();
      if (data.found) {
        document.getElementById("f-lat").value = data.lat.toFixed(4);
        document.getElementById("f-lon").value = data.lon.toFixed(4);
        showFormSuccess(`Coordinates found: ${data.lat.toFixed(4)}, ${data.lon.toFixed(4)}`);
      } else {
        showFormError(`"${name}" not found on OpenStreetMap. Enter coordinates manually.`);
      }
    } catch {
      showFormError("Geocoding service unavailable. Enter coordinates manually.");
    }

    geocodeBtn.disabled = false;
    geocodeBtn.innerHTML = `<span class="material-symbols-outlined btn-icon" style="font-size:15px">my_location</span> Look up coords`;
  });
}

function showFormError(msg) {
  let el = document.getElementById("form-feedback");
  if (!el) return;
  el.textContent = msg;
  el.className = "form-feedback form-feedback--error";
  el.style.display = "block";
}
function showFormSuccess(msg) {
  let el = document.getElementById("form-feedback");
  if (!el) return;
  el.textContent = msg;
  el.className = "form-feedback form-feedback--success";
  el.style.display = "block";
}
function clearFormError() {
  let el = document.getElementById("form-feedback");
  if (el) el.style.display = "none";
}

/* ══════════════════════════════════════════════
   ADD SETTLEMENT FORM — with client-side validation
══════════════════════════════════════════════ */
document.getElementById("add-form").addEventListener("submit", async e => {
  e.preventDefault();
  clearFormError();

  // ── Client-side validation ──
  const name     = document.getElementById("f-name").value.trim();
  const lat      = parseFloat(document.getElementById("f-lat").value);
  const lon      = parseFloat(document.getElementById("f-lon").value);
  const pop      = parseInt(document.getElementById("f-pop").value, 10);
  const area     = parseFloat(document.getElementById("f-area").value);
  const terrain  = document.getElementById("f-terrain").value;

  if (!name) { showFormError("Settlement name is required."); return; }
  if (isNaN(lat) || lat < -90  || lat > 90)  { showFormError("Latitude must be between –90 and 90."); return; }
  if (isNaN(lon) || lon < -180 || lon > 180) { showFormError("Longitude must be between –180 and 180."); return; }
  if (isNaN(pop) || pop < 1)   { showFormError("Population must be a positive whole number."); return; }
  if (isNaN(area) || area <= 0) { showFormError("Area must be greater than 0 hectares."); return; }

  const btn = e.target.querySelector("button[type=submit]");
  btn.disabled = true;
  btn.innerHTML = `<span class="material-symbols-outlined btn-icon">hourglass_top</span> Adding…`;

  const body = { name, lat, lon, population: pop, area_hectares: area, terrain };

  try {
    const res = await fetch(`/api/settlements?${regionParam()}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (res.ok) {
      e.target.reset();
      document.getElementById("f-lat").value  = "26.99";
      document.getElementById("f-lon").value  = "94.19";
      document.getElementById("f-pop").value  = "1000";
      document.getElementById("f-area").value = "10";
      clearFormError();
      await refreshAll();
      switchTab("assessment");
    } else {
      const err = await res.json().catch(() => ({}));
      showFormError(err.error || "Could not add settlement.");
    }
  } catch { showFormError("Network error — is the server running?"); }

  btn.disabled = false;
  btn.innerHTML = `<span class="material-symbols-outlined btn-icon">add_location_alt</span> Add Settlement`;
});

/* ══════════════════════════════════════════════
   RESET BUTTON
══════════════════════════════════════════════ */
document.getElementById("reset-btn").addEventListener("click", async () => {
  const btn = document.getElementById("reset-btn");
  btn.disabled = true; btn.textContent = "Resetting…";
  try {
    await fetch(`/api/settlements/reset?${regionParam()}`, { method: "POST" });
    await refreshAll();
  } catch { alert("Network error — is the server running?"); }
  btn.disabled = false;
  btn.innerHTML = `<span class="material-symbols-outlined btn-icon">restart_alt</span> ${REGION_INFO[CURRENT_REGION].resetLabel}`;
});

/* ══════════════════════════════════════════════
   REGION SWITCHER
══════════════════════════════════════════════ */
const regionSelect = document.getElementById("region-select");
if (regionSelect) {
  regionSelect.value = CURRENT_REGION;
  regionSelect.addEventListener("change", async () => {
    CURRENT_REGION = regionSelect.value;
    applyRegionChrome();
    const info = REGION_INFO[CURRENT_REGION];
    map.setView(info.mapCenter, info.mapZoom);
    await loadHazardZone();
    await refreshAll();
  });
}

/* ══════════════════════════════════════════════
   INIT
══════════════════════════════════════════════ */
const howtoPanel  = document.getElementById("howto-panel");
const howtoReopen = document.getElementById("howto-reopen");
if (howtoPanel && howtoReopen) {
  if (localStorage.getItem("sih26191_howto_dismissed") === "1") {
    howtoPanel.style.display = "none";
    howtoReopen.style.display = "flex";
  }
  document.getElementById("howto-close").addEventListener("click", () => {
    howtoPanel.style.display = "none";
    howtoReopen.style.display = "flex";
    localStorage.setItem("sih26191_howto_dismissed", "1");
  });
  howtoReopen.addEventListener("click", () => {
    howtoPanel.style.display = "block";
    howtoReopen.style.display = "none";
    localStorage.removeItem("sih26191_howto_dismissed");
  });
/* ══════════════════════════════════════════════
   MOBILE DRAWER & TOPBAR ACTIONS
══════════════════════════════════════════════ */
const menuToggle = document.getElementById("menu-toggle");
const sidenav = document.getElementById("sidenav");
const backdrop = document.getElementById("sidenav-backdrop");

if (menuToggle && sidenav && backdrop) {
  menuToggle.addEventListener("click", () => {
    sidenav.classList.toggle("open");
    backdrop.classList.toggle("active");
  });

  backdrop.addEventListener("click", () => {
    sidenav.classList.remove("open");
    backdrop.classList.remove("active");
  });

  // Close drawer when clicking any nav item
  sidenav.querySelectorAll(".nav-item").forEach(item => {
    item.addEventListener("click", () => {
      if (window.innerWidth < 900) {
        sidenav.classList.remove("open");
        backdrop.classList.remove("active");
      }
    });
  });
}

const notifBtn = document.getElementById("topbar-notif-btn");
if (notifBtn) {
  notifBtn.addEventListener("click", () => {
    alert("Field Ops Notification:\nAll spatial hazard datasets active.\nPriority classification pipeline running.");
  });
}

(async function start() {
  applyRegionChrome();
  initMap();
  await loadHazardZone();
  await refreshAll();
})();