/**
 * app.js – Chase Wildcard Route Optimizer
 *
 * Responsibilities:
 *  - Load pre-generated routes.json and elevation.json from the build step.
 *  - Render start point, radius circle, and selected route on a Leaflet map
 *    backed by CARTO dark tiles.
 *  - Render the elevation profile of the selected route with Chart.js.
 *  - Provide a browser-side GPX download for the selected route.
 */

"use strict";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const ROUTES_URL = "../build/routes.json";
const ELEVATION_URL = "../build/elevation.json";

const CARTO_DARK_TILES =
  "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
const CARTO_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> ' +
  'contributors &copy; <a href="https://carto.com/">CARTO</a>';

const ROUTE_COLOR = "#e94560";
const ROUTE_WEIGHT = 3;
const ROUTE_HOVER_WEIGHT = 5;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let map;
let elevationChart = null;
let circleLayer = null;
let startMarker = null;
let routeLayer = null;
let routesData = null;      // parsed routes.json
let elevationData = null;   // parsed elevation.json
let activeRank = null;      // currently displayed route rank (string)

// ---------------------------------------------------------------------------
// Map initialisation
// ---------------------------------------------------------------------------
function initMap() {
  map = L.map("map", {
    center: [51.5, 7.0],
    zoom: 9,
    zoomControl: true,
  });

  L.tileLayer(CARTO_DARK_TILES, {
    attribution: CARTO_ATTRIBUTION,
    subdomains: "abcd",
    maxZoom: 19,
  }).addTo(map);
}

// ---------------------------------------------------------------------------
// Helpers – map layers
// ---------------------------------------------------------------------------
function clearMapOverlays() {
  if (circleLayer) { map.removeLayer(circleLayer); circleLayer = null; }
  if (startMarker) { map.removeLayer(startMarker); startMarker = null; }
  if (routeLayer)  { map.removeLayer(routeLayer);  routeLayer  = null; }
}

function drawCentre(lat, lon, radiusKm) {
  const startIcon = L.divIcon({
    html: '<div style="width:14px;height:14px;background:#e94560;border:3px solid #fff;border-radius:50%;box-shadow:0 0 8px #e94560"></div>',
    iconAnchor: [7, 7],
    className: "",
  });

  startMarker = L.marker([lat, lon], { icon: startIcon })
    .bindPopup(`<strong>Start</strong><br>${lat.toFixed(4)}, ${lon.toFixed(4)}`)
    .addTo(map);

  circleLayer = L.circle([lat, lon], {
    radius: radiusKm * 1000,
    color: "#e94560",
    weight: 1.5,
    opacity: 0.6,
    fill: true,
    fillColor: "#e94560",
    fillOpacity: 0.05,
  }).addTo(map);
}

function drawRoute(rank) {
  if (routeLayer) { map.removeLayer(routeLayer); routeLayer = null; }

  const rankStr = String(rank);
  const routeEle = elevationData && elevationData[rankStr];
  if (!routeEle) return;

  // ORS returns [lon, lat, ele] – Leaflet needs [lat, lon]
  const latlngs = (routeEle.coordinates || []).map(c => [c[1], c[0]]);
  if (!latlngs.length) return;

  routeLayer = L.polyline(latlngs, {
    color: ROUTE_COLOR,
    weight: ROUTE_WEIGHT,
    opacity: 0.9,
    lineJoin: "round",
  }).addTo(map);

  routeLayer.on("mouseover", () => routeLayer.setStyle({ weight: ROUTE_HOVER_WEIGHT }));
  routeLayer.on("mouseout",  () => routeLayer.setStyle({ weight: ROUTE_WEIGHT }));

  map.fitBounds(routeLayer.getBounds(), { padding: [40, 40] });
}

// ---------------------------------------------------------------------------
// Route list UI
// ---------------------------------------------------------------------------
function renderRouteList(routes) {
  const section = document.getElementById("route-list-section");
  const list    = document.getElementById("route-list");
  list.innerHTML = "";

  routes.forEach(route => {
    const li = document.createElement("li");
    li.className = "route-item";
    li.dataset.rank = route.rank;
    li.innerHTML = `
      <div class="route-rank">Rank #${route.rank}</div>
      <div class="route-name">Peak ${route.peak_elevation_m} m</div>
      <div class="route-stats">
        <div class="stat">Dist <span>${route.distance_km} km</span></div>
        <div class="stat">↑ <span>${route.total_ascent_m} m</span></div>
        <div class="stat">FIETS <span>${route.fiets_score}</span></div>
      </div>
    `;
    li.addEventListener("click", () => selectRoute(route.rank));
    list.appendChild(li);
  });

  section.hidden = false;
}

function setActiveListItem(rank) {
  document.querySelectorAll(".route-item").forEach(el => {
    el.classList.toggle("active", Number(el.dataset.rank) === Number(rank));
  });
}

// ---------------------------------------------------------------------------
// Elevation chart
// ---------------------------------------------------------------------------
function renderElevationChart(rank) {
  const rankStr = String(rank);
  const routeEle = elevationData && elevationData[rankStr];
  const panel = document.getElementById("elevation-panel");

  if (!routeEle || !routeEle.profile || !routeEle.profile.length) {
    panel.hidden = true;
    return;
  }

  const profile = routeEle.profile;
  const labels  = profile.map(p => p.d.toFixed(1));
  const data    = profile.map(p => p.e);

  // Update title
  const route = routesData && routesData.routes && routesData.routes.find(
    r => String(r.rank) === rankStr
  );
  if (route) {
    document.getElementById("elevation-title").textContent =
      `Route #${rank} · ${route.distance_km} km · ↑${route.total_ascent_m} m · FIETS ${route.fiets_score}`;
  }

  panel.hidden = false;

  const ctx = document.getElementById("elevation-chart").getContext("2d");

  if (elevationChart) {
    elevationChart.destroy();
    elevationChart = null;
  }

  elevationChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: "Elevation (m)",
        data,
        fill: true,
        tension: 0.3,
        borderColor: "#e94560",
        borderWidth: 2,
        backgroundColor: "rgba(233, 69, 96, 0.15)",
        pointRadius: 0,
        pointHoverRadius: 4,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#16213e",
          titleColor: "#8888aa",
          bodyColor: "#e0e0f0",
          callbacks: {
            title: items => `${items[0].label} km`,
            label: item => `${item.raw} m`,
          },
        },
      },
      scales: {
        x: {
          ticks: {
            color: "#8888aa",
            maxTicksLimit: 10,
            callback: val => val + " km",
          },
          grid: { color: "rgba(255,255,255,0.05)" },
        },
        y: {
          ticks: { color: "#8888aa" },
          grid: { color: "rgba(255,255,255,0.05)" },
        },
      },
    },
  });
}

// ---------------------------------------------------------------------------
// GPX download (browser-side)
// ---------------------------------------------------------------------------
function buildGpxString(rank) {
  const rankStr = String(rank);
  const routeEle = elevationData && elevationData[rankStr];
  if (!routeEle || !routeEle.coordinates) return null;

  const route = routesData && routesData.routes &&
    routesData.routes.find(r => String(r.rank) === rankStr);

  const name = route
    ? `Chase Route #${rank} – Peak ${route.peak_elevation_m}m – ${route.distance_km}km – FIETS ${route.fiets_score}`
    : `Chase Route #${rank}`;

  const pts = routeEle.coordinates.map(c => {
    const lon = c[0], lat = c[1];
    const ele = c.length >= 3 ? `\n      <ele>${c[2]}</ele>` : "";
    return `    <trkpt lat="${lat}" lon="${lon}">${ele}\n    </trkpt>`;
  }).join("\n");

  return `<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="Chase Wildcard Route Optimizer"
     xmlns="http://www.topografix.com/GPX/1/1"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     xsi:schemaLocation="http://www.topografix.com/GPX/1/1
       http://www.topografix.com/GPX/1/1/gpx.xsd">
  <metadata>
    <name>${escapeXml(name)}</name>
    <time>${new Date().toISOString()}</time>
  </metadata>
  <trk>
    <name>${escapeXml(name)}</name>
    <type>cycling</type>
    <trkseg>
${pts}
    </trkseg>
  </trk>
</gpx>`;
}

function escapeXml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function downloadGpx(rank) {
  const gpx = buildGpxString(rank);
  if (!gpx) { alert("No route data available for GPX export."); return; }

  const blob = new Blob([gpx], { type: "application/gpx+xml" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = `chase_route_${String(rank).padStart(2, "0")}.gpx`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Route selection
// ---------------------------------------------------------------------------
function selectRoute(rank) {
  activeRank = rank;
  setActiveListItem(rank);
  drawRoute(rank);
  renderElevationChart(rank);
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------
async function loadData(lat, lon, radiusKm) {
  document.getElementById("btn-load").textContent = "Loading…";
  document.getElementById("btn-load").disabled = true;

  try {
    const [rResp, eResp] = await Promise.all([
      fetch(ROUTES_URL),
      fetch(ELEVATION_URL),
    ]);

    if (!rResp.ok) throw new Error(`routes.json: ${rResp.status} ${rResp.statusText}`);
    if (!eResp.ok) throw new Error(`elevation.json: ${eResp.status} ${eResp.statusText}`);

    routesData   = await rResp.json();
    elevationData = await eResp.json();

    const centre = routesData.centre || { lat, lon };
    const radius = routesData.radius_km || radiusKm;

    clearMapOverlays();
    drawCentre(centre.lat, centre.lon, radius);
    renderRouteList(routesData.routes || []);

    if (routesData.routes && routesData.routes.length > 0) {
      selectRoute(routesData.routes[0].rank);
    }
  } catch (err) {
    alert(`Failed to load route data:\n${err.message}\n\nRun the build scripts first.`);
    console.error(err);
  } finally {
    document.getElementById("btn-load").textContent = "Load Routes";
    document.getElementById("btn-load").disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Event wiring
// ---------------------------------------------------------------------------
document.getElementById("btn-load").addEventListener("click", () => {
  const lat    = parseFloat(document.getElementById("input-lat").value);
  const lon    = parseFloat(document.getElementById("input-lon").value);
  const radius = parseFloat(document.getElementById("input-radius").value) || 80;

  if (isNaN(lat) || isNaN(lon)) {
    alert("Please enter valid Start Latitude and Longitude.");
    return;
  }

  map.setView([lat, lon], 9);
  loadData(lat, lon, radius);
});

document.getElementById("btn-gpx").addEventListener("click", () => {
  if (activeRank === null) { alert("Select a route first."); return; }
  downloadGpx(activeRank);
});

document.getElementById("btn-close-elevation").addEventListener("click", () => {
  document.getElementById("elevation-panel").hidden = true;
  if (elevationChart) { elevationChart.destroy(); elevationChart = null; }
});

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
initMap();
