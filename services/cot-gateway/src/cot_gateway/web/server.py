"""CoT Gateway aiohttp web server: /map, /sites, /tracks, /health."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
from aiohttp import web

from cot_gateway.logging import get_logger
from cot_gateway.web.sites import SitesConfig
from cot_gateway.web.track_store import TrackStore

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>CoT Gateway — TAK Tactical Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0a0e14; color: #c9d1d9; font-family: 'Courier New', monospace; height: 100vh; display: flex; flex-direction: column; }
  #header { background: #0d1117; border-bottom: 1px solid #21262d; padding: 8px 16px; display: flex; align-items: center; gap: 16px; flex-shrink: 0; }
  #header h1 { font-size: 14px; color: #58a6ff; letter-spacing: 2px; text-transform: uppercase; }
  #status-bar { font-size: 11px; color: #8b949e; margin-left: auto; display: flex; gap: 16px; }
  .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 4px; }
  .dot-echo { background: #00BFFF; } .dot-sntr { background: #FFD700; } .dot-fused { background: #FF4444; }
  #map { flex: 1; }
  #sidebar { position: absolute; top: 60px; right: 10px; z-index: 1000; background: rgba(13,17,23,0.92); border: 1px solid #21262d; border-radius: 6px; padding: 10px; min-width: 200px; max-width: 240px; font-size: 11px; }
  #sidebar h3 { color: #58a6ff; font-size: 12px; margin-bottom: 8px; letter-spacing: 1px; border-bottom: 1px solid #21262d; padding-bottom: 4px; }
  .legend-item { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; color: #8b949e; }
  .leg-swatch { width: 14px; height: 14px; border-radius: 50%; flex-shrink: 0; }
  .leg-line { width: 20px; height: 2px; flex-shrink: 0; }
  .leg-dashed { border-top: 2px dashed; flex-shrink: 0; width: 20px; }
  #track-list { margin-top: 8px; max-height: 280px; overflow-y: auto; }
  .track-row { padding: 3px 0; border-bottom: 1px solid #161b22; }
  .track-row .tid { font-weight: bold; }
  .src-echo { color: #00BFFF; } .src-sntr { color: #FFD700; } .src-fused { color: #FF4444; }
  .track-row .coords { color: #6e7681; font-size: 10px; }
  #sensor-status { margin-top: 8px; }
</style>
</head>
<body>
<div id="header">
  <h1>&#9733; CoT Gateway — TAK Tactical Map</h1>
  <div id="status-bar">
    <span><span class="dot dot-echo"></span>EchoShield</span>
    <span><span class="dot dot-sntr"></span>Sentrycs</span>
    <span><span class="dot dot-fused"></span>Fused</span>
    <span id="track-count">tracks: 0</span>
    <span id="last-update"></span>
  </div>
</div>
<div id="map"></div>
<div id="sidebar">
  <h3>Legend</h3>
  <div class="legend-item"><div class="leg-swatch" style="background:#00BFFF;border:2px solid #0090CC;"></div><span>EchoShield Track</span></div>
  <div class="legend-item"><div class="leg-swatch" style="background:#FFD700;border:2px solid #CC9000;"></div><span>Sentrycs Track</span></div>
  <div class="legend-item"><div class="leg-swatch" style="background:#FF4444;border:2px solid #CC0000;"></div><span>Fused (Hostile)</span></div>
  <div class="legend-item"><div class="leg-swatch" style="background:none;border:2px solid #00FF88;border-radius:0;transform:rotate(45deg);"></div><span>Strategic Point</span></div>
  <div class="legend-item"><div class="leg-swatch" style="background:none;border:2px solid #FFFFFF;border-radius:2px;"></div><span>Holding Point</span></div>
  <div class="legend-item"><div class="leg-dashed" style="border-color:#00BFFF;"></div><span>Radar Range</span></div>
  <div class="legend-item"><div class="leg-dashed" style="border-color:#FFD700;"></div><span>RF Range</span></div>
  <div id="sensor-status"></div>
  <h3 style="margin-top:10px;">Live Tracks</h3>
  <div id="track-list"><em style="color:#6e7681;">waiting for data…</em></div>
</div>

<script>
const SP_LAT = __SP_LAT__, SP_LON = __SP_LON__;
const API_BASE = '';
const SOURCE_COLORS = { ECHOSHIELD: '#00BFFF', SENTRYCS: '#FFD700', FUSED: '#FF4444' };
const SOURCE_BORDER = { ECHOSHIELD: '#0090CC', SENTRYCS: '#CC9000', FUSED: '#CC0000' };

const map = L.map('map', { preferCanvas: true, zoomControl: true }).setView([SP_LAT, SP_LON], 13);
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap contributors &copy; CARTO'
}).addTo(map);

// ── helpers ────────────────────────────────────────────────────────────────
function makeCircle(lat, lon, r, color, dash) {
  return L.circle([lat, lon], { radius: r, color, weight: 1.5,
    dashArray: dash || null, fill: false, opacity: 0.7 });
}

function makeArrow(lat, lon, deg, color) {
  const rad = (deg - 90) * Math.PI / 180;
  const len = 0.0006;
  const tip = [lat + Math.cos(deg * Math.PI / 180) * len,
               lon + Math.sin(deg * Math.PI / 180) * len / Math.cos(lat * Math.PI / 180)];
  return L.polyline([[lat, lon], tip], { color, weight: 2, opacity: 0.8 });
}

function crosshairIcon(color) {
  return L.divIcon({
    className: '',
    html: `<svg width="24" height="24" viewBox="-12 -12 24 24" xmlns="http://www.w3.org/2000/svg">
      <circle cx="0" cy="0" r="5" fill="none" stroke="${color}" stroke-width="2"/>
      <line x1="-12" y1="0" x2="-6" y2="0" stroke="${color}" stroke-width="2"/>
      <line x1="6" y1="0" x2="12" y2="0" stroke="${color}" stroke-width="2"/>
      <line x1="0" y1="-12" x2="0" y2="-6" stroke="${color}" stroke-width="2"/>
      <line x1="0" y1="6" x2="0" y2="12" stroke="${color}" stroke-width="2"/>
    </svg>`,
    iconSize: [24, 24], iconAnchor: [12, 12]
  });
}

function hIcon() {
  return L.divIcon({
    className: '',
    html: `<div style="width:26px;height:26px;border:2px solid #fff;border-radius:4px;background:rgba(255,255,255,0.15);display:flex;align-items:center;justify-content:center;color:#fff;font-weight:bold;font-size:13px;font-family:monospace;">H</div>`,
    iconSize: [26, 26], iconAnchor: [13, 13]
  });
}

function radarIcon(color) {
  return L.divIcon({
    className: '',
    html: `<svg width="22" height="22" viewBox="0 0 22 22" xmlns="http://www.w3.org/2000/svg">
      <circle cx="11" cy="11" r="10" fill="none" stroke="${color}" stroke-width="1.5" opacity="0.6"/>
      <circle cx="11" cy="11" r="4" fill="none" stroke="${color}" stroke-width="1.5"/>
      <line x1="11" y1="11" x2="11" y2="1" stroke="${color}" stroke-width="2"/>
      <line x1="11" y1="11" x2="19" y2="6" stroke="${color}" stroke-width="1.5" opacity="0.5"/>
    </svg>`,
    iconSize: [22, 22], iconAnchor: [11, 11]
  });
}

function rfIcon(color) {
  return L.divIcon({
    className: '',
    html: `<svg width="22" height="22" viewBox="0 0 22 22" xmlns="http://www.w3.org/2000/svg">
      <path d="M11 11 L11 3" stroke="${color}" stroke-width="2.5"/>
      <path d="M7 7 Q11 3 15 7" fill="none" stroke="${color}" stroke-width="1.5"/>
      <path d="M4 10 Q11 2 18 10" fill="none" stroke="${color}" stroke-width="1" opacity="0.5"/>
      <circle cx="11" cy="14" r="3" fill="${color}" opacity="0.4"/>
    </svg>`,
    iconSize: [22, 22], iconAnchor: [11, 14]
  });
}

function droneIcon(source, lost) {
  const c = lost ? '#555' : (SOURCE_COLORS[source] || '#888');
  const b = lost ? '#333' : (SOURCE_BORDER[source] || '#555');
  const sym = source === 'FUSED' ? '✈' : (source === 'ECHOSHIELD' ? '◆' : '⬡');
  return L.divIcon({
    className: '',
    html: `<div style="width:20px;height:20px;border-radius:50%;border:2px solid ${b};background:${c};opacity:${lost?0.4:0.9};display:flex;align-items:center;justify-content:center;color:#000;font-size:10px;">${sym}</div>`,
    iconSize: [20, 20], iconAnchor: [10, 10]
  });
}

// ── static site layers ──────────────────────────────────────────────────────
const siteLayer = L.layerGroup().addTo(map);
const sensorLayer = L.layerGroup().addTo(map);
const trackLayer = L.layerGroup().addTo(map);

async function refreshSites() {
  try {
    const r = await fetch(API_BASE + '/sites');
    if (!r.ok) return;
    const data = await r.json();
    siteLayer.clearLayers();
    sensorLayer.clearLayers();

    // Strategic / holding sites
    for (const site of (data.strategic || [])) {
      if (site.type === 'strategic_point') {
        L.marker([site.lat, site.lon], { icon: crosshairIcon('#00FF88'), zIndexOffset: 1000 })
          .bindTooltip(`<b>${site.name}</b><br>${site.lat.toFixed(6)}, ${site.lon.toFixed(6)}`, { permanent: false })
          .addTo(siteLayer);
        if (site.ranges_m) {
          const colors = ['#00FF00', '#FFFF00', '#FF4444'];
          site.ranges_m.forEach((r, i) => {
            makeCircle(site.lat, site.lon, r, colors[i] || '#FF4444', '4 4').addTo(siteLayer);
            L.marker([site.lat, site.lon - 0.00001], {
              icon: L.divIcon({ className:'', html:`<span style="font-size:10px;color:${colors[i] || '#FF4444'};white-space:nowrap;">${r >= 1000 ? (r/1000)+'km' : r+'m'}</span>`, iconAnchor:[-4, 6] })
            }).addTo(siteLayer);
          });
        }
      } else if (site.type === 'holding_point') {
        L.marker([site.lat, site.lon], { icon: hIcon(), zIndexOffset: 1000 })
          .bindTooltip(`<b>${site.name}</b><br>${site.lat.toFixed(6)}, ${site.lon.toFixed(6)}`, { permanent: false })
          .addTo(siteLayer);
      }
    }

    // Sensor overlays
    const sensorStatusEl = document.getElementById('sensor-status');
    let statusHtml = '<div style="border-top:1px solid #21262d;margin-top:6px;padding-top:6px;">';
    for (const s of (data.sensors || [])) {
      if (s.status === 'unreachable') {
        statusHtml += `<div style="color:#6e7681;font-size:10px;">${s.type} ⚠ unreachable</div>`;
        continue;
      }
      const lat = s.sensor_lat, lon = s.sensor_lon;
      if (s.type === 'echoshield') {
        L.marker([lat, lon], { icon: radarIcon('#00BFFF'), zIndexOffset: 900 })
          .bindTooltip(`<b>EchoShield</b><br>${lat.toFixed(6)}, ${lon.toFixed(6)}<br>Range: ${s.max_range_m}m`, { permanent: false })
          .addTo(sensorLayer);
        if (s.max_range_m) makeCircle(lat, lon, s.max_range_m, '#00BFFF', '6 4').addTo(sensorLayer);
        statusHtml += `<div style="color:#00BFFF;font-size:10px;">&#9679; EchoShield ${lat.toFixed(4)},${lon.toFixed(4)}</div>`;
      } else if (s.type === 'sentrycs') {
        L.marker([lat, lon], { icon: rfIcon('#FFD700'), zIndexOffset: 900 })
          .bindTooltip(`<b>Sentrycs</b><br>${lat.toFixed(6)}, ${lon.toFixed(6)}<br>Range: ${s.detection_radius_m}m`, { permanent: false })
          .addTo(sensorLayer);
        if (s.detection_radius_m) makeCircle(lat, lon, s.detection_radius_m, '#FFD700', '6 4').addTo(sensorLayer);
        statusHtml += `<div style="color:#FFD700;font-size:10px;">&#9679; Sentrycs ${lat.toFixed(4)},${lon.toFixed(4)}</div>`;
      }
    }
    statusHtml += '</div>';
    sensorStatusEl.innerHTML = statusHtml;
  } catch (e) {
    console.warn('sites fetch failed', e);
  }
}

// ── live tracks ────────────────────────────────────────────────────────────
const trackMarkers = {};

async function refreshTracks() {
  try {
    const r = await fetch(API_BASE + '/tracks');
    if (!r.ok) return;
    const tracks = await r.json();

    trackLayer.clearLayers();
    Object.keys(trackMarkers).forEach(k => delete trackMarkers[k]);

    const listEl = document.getElementById('track-list');
    document.getElementById('track-count').textContent = 'tracks: ' + tracks.length;
    document.getElementById('last-update').textContent = new Date().toLocaleTimeString();

    if (!tracks.length) {
      listEl.innerHTML = '<em style="color:#6e7681;">no active tracks</em>';
      return;
    }

    let listHtml = '';
    for (const t of tracks) {
      const lost = t.track_status === 'Lost';
      const ic = droneIcon(t.source, lost);
      const m = L.marker([t.lat, t.lon], { icon: ic, zIndexOffset: 500 });
      const ds = t.detection_status ? ` [${t.detection_status}]` : '';
      const vel = t.velocity_ms ? ` ${t.velocity_ms.toFixed(1)}m/s` : '';
      const alt = ` ${t.alt_m.toFixed(0)}m`;
      m.bindTooltip(
        `<b>${t.track_id}</b> (${t.source}${ds})<br>${t.lat.toFixed(6)}, ${t.lon.toFixed(6)}<br>Alt:${alt} Spd:${vel} Hdg: ${t.azimuth_deg.toFixed(0)}°`,
        { permanent: false }
      );
      m.addTo(trackLayer);
      if (!lost && t.azimuth_deg !== undefined) {
        makeArrow(t.lat, t.lon, t.azimuth_deg, SOURCE_COLORS[t.source] || '#888').addTo(trackLayer);
      }

      const srcClass = 'src-' + t.source.toLowerCase().replace('echoshield','echo').replace('sentrycs','sntr').replace('fused','fused');
      listHtml += `<div class="track-row"><span class="tid ${srcClass}">${t.track_id}</span> <span class="coords">${t.lat.toFixed(4)},${t.lon.toFixed(4)} ${alt}${vel}</span></div>`;
    }
    listEl.innerHTML = listHtml;
  } catch (e) {
    console.warn('tracks fetch failed', e);
  }
}

refreshSites();
refreshTracks();
setInterval(refreshSites, 30000);
setInterval(refreshTracks, 2000);
</script>
</body>
</html>
"""


def _build_html(sp_lat: float, sp_lon: float) -> str:
    return _HTML_TEMPLATE.replace("__SP_LAT__", str(sp_lat)).replace("__SP_LON__", str(sp_lon))


async def _fetch_sensor(
    session: aiohttp.ClientSession, url: str, sensor_type: str
) -> dict[str, Any]:
    """Query a sensor info endpoint; return error dict on failure."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=2.0)) as resp:
            if resp.status == 200:
                data = await resp.json()
                data["status"] = "ok"
                return data
            return {"type": sensor_type, "status": "unreachable"}
    except Exception:
        return {"type": sensor_type, "status": "unreachable"}


def build_web_app(
    *,
    sites_config: SitesConfig,
    track_store: TrackStore,
    echoshield_info_url: str,
    sentrycs_sensor_url: str,
    sp_lat: float,
    sp_lon: float,
) -> web.Application:
    log = get_logger("cot_gateway.web")
    html = _build_html(sp_lat, sp_lon)

    async def _map(request: web.Request) -> web.Response:
        return web.Response(text=html, content_type="text/html")

    async def _sites(request: web.Request) -> web.Response:
        strategic = [s.model_dump() for s in sites_config.sites]
        async with aiohttp.ClientSession() as session:
            echo_info, sntr_info = await asyncio.gather(
                _fetch_sensor(session, echoshield_info_url, "echoshield"),
                _fetch_sensor(session, sentrycs_sensor_url, "sentrycs"),
            )
        payload = {"strategic": strategic, "sensors": [echo_info, sntr_info]}
        return web.json_response(payload)

    async def _tracks(request: web.Request) -> web.Response:
        return web.json_response(await track_store.get_all())

    async def _health(request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "service": "cot-gateway-web"})

    app = web.Application()
    app.router.add_get("/map", _map)
    app.router.add_get("/sites", _sites)
    app.router.add_get("/tracks", _tracks)
    app.router.add_get("/health", _health)
    log.info(
        "web_app_built",
        echoshield_info_url=echoshield_info_url,
        sentrycs_sensor_url=sentrycs_sensor_url,
    )
    return app


async def run_web_server(
    host: str,
    port: int,
    sites_config: SitesConfig,
    track_store: TrackStore,
    echoshield_info_url: str,
    sentrycs_sensor_url: str,
    sp_lat: float,
    sp_lon: float,
    stop: asyncio.Event,
) -> None:
    log = get_logger("cot_gateway.web")
    app = build_web_app(
        sites_config=sites_config,
        track_store=track_store,
        echoshield_info_url=echoshield_info_url,
        sentrycs_sensor_url=sentrycs_sensor_url,
        sp_lat=sp_lat,
        sp_lon=sp_lon,
    )
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    log.info("web_server_started", host=host, port=port)
    try:
        await stop.wait()
    finally:
        await runner.cleanup()
        log.info("web_server_stopped")
