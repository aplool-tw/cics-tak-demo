"""CoT Gateway aiohttp web server: /map, /sites, /tracks, /health."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
from aiohttp import web

from cot_gateway.logging import get_logger
from cot_gateway.web.sites import SitesConfig
from cot_gateway.web.track_store import TrackStore

_NO_CACHE = {"Cache-Control": "no-store, no-cache", "Pragma": "no-cache"}

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>CoT Gateway — TAK Tactical Map</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <style>
    *{margin:0;padding:0;box-sizing:border-box}
    body{font-family:monospace;background:#1a1a2e;color:#e0e0e0;height:100vh;display:flex;flex-direction:column;overflow:hidden}
    #header{padding:6px 14px;background:#0f3460;display:flex;align-items:center;justify-content:space-between;flex-shrink:0;gap:10px}
    #header h1{font-size:13px;letter-spacing:1px;color:#00d4ff;white-space:nowrap}
    .hdr-right{display:flex;align-items:center;gap:12px;font-size:11px;color:#90caf9}
    .dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:3px;vertical-align:middle}
    .dot-echo{background:#00BFFF} .dot-sntr{background:#FFD700} .dot-fused{background:#FF4444}
    #map{flex:1;min-height:0}
    /* floating panel */
    #panel{position:absolute;top:46px;right:10px;z-index:1000;width:230px;background:rgba(13,27,42,0.93);border:1px solid #1e3a5f;border-radius:5px;overflow:hidden;font-size:11px}
    #panel-head{padding:6px 10px;background:#0f3460;color:#00d4ff;font-size:12px;font-weight:bold}
    #panel-body{padding:8px 10px;max-height:calc(100vh - 150px);overflow-y:auto}
    #panel-body::-webkit-scrollbar{width:4px}
    #panel-body::-webkit-scrollbar-thumb{background:#1e3a5f;border-radius:2px}
    .leg-row{display:flex;align-items:center;gap:7px;margin-bottom:4px;color:#b0bec5}
    .leg-dot{width:12px;height:12px;border-radius:50%;flex-shrink:0;border:2px solid}
    .leg-line{width:18px;height:0;flex-shrink:0;border-top:2px dashed}
    .leg-sep{border-top:1px solid #1e3a5f;margin:6px 0}
    #sensor-info{margin-bottom:4px}
    #track-list-head{color:#64b5f6;font-weight:bold;margin:6px 0 4px}
    .t-row{padding:2px 0;border-bottom:1px solid #0d1b2a;line-height:1.5}
    .t-id{font-weight:bold} .t-echo{color:#00BFFF} .t-sntr{color:#FFD700} .t-fused{color:#FF4444}
    .t-coord{color:#6e7681;font-size:10px}
    /* map display control */
    #map-ctrl{position:absolute;bottom:34px;left:10px;z-index:1000;width:170px;background:rgba(13,27,42,0.92);border:1px solid #1e3a5f;border-radius:5px;padding:8px 11px;font-size:11px;font-family:monospace;color:#90caf9}
    #map-ctrl-head{font-size:10px;color:#64b5f6;margin-bottom:6px;letter-spacing:.5px}
    .ctrl-row{display:flex;align-items:center;justify-content:space-between;margin-bottom:5px}
    .ctrl-lbl{flex-shrink:0;width:68px}
    .ctrl-val{width:32px;text-align:right;color:#00d4ff;flex-shrink:0}
    .ctrl-row input[type=range]{flex:1;margin:0 5px;accent-color:#00d4ff;height:4px;cursor:pointer}
    .leaflet-tooltip-gw{background:rgba(13,27,42,0.9);border:1px solid #2196F3;color:#90caf9;font-family:monospace;font-size:10px;padding:2px 6px;border-radius:3px;white-space:nowrap;box-shadow:none}
    .leaflet-popup-content-wrapper{background:#0d1b2a;border:1px solid #2196F3;border-radius:5px;color:#e0e0e0;font-family:monospace;font-size:12px}
    .leaflet-popup-tip{background:#0d1b2a}
  </style>
</head>
<body>
<div id="header">
  <h1>&#9733; CoT Gateway — TAK Tactical Map</h1>
  <div class="hdr-right">
    <span><span class="dot dot-echo"></span>EchoShield</span>
    <span><span class="dot dot-sntr"></span>Sentrycs</span>
    <span><span class="dot dot-fused"></span>Fused</span>
    <span id="track-count" style="color:#e0e0e0">tracks: –</span>
    <span id="last-upd" style="color:#546e7a"></span>
  </div>
</div>
<div id="map"></div>
<div id="map-ctrl">
  <div id="map-ctrl-head">&#9788; Map Display</div>
  <div class="ctrl-row">
    <span class="ctrl-lbl">Brightness</span>
    <input id="bri" type="range" min="20" max="150" step="5" value="40">
    <span class="ctrl-val" id="bri-val">40%</span>
  </div>
  <div class="ctrl-row">
    <span class="ctrl-lbl">Opacity</span>
    <input id="opa" type="range" min="20" max="100" step="5" value="100">
    <span class="ctrl-val" id="opa-val">100%</span>
  </div>
</div>
<div id="panel">
  <div id="panel-head">&#128225; Legend &amp; Live Tracks</div>
  <div id="panel-body">
    <!-- Legend -->
    <div class="leg-row"><span class="leg-dot" style="background:#00BFFF;border-color:#0090CC"></span>EchoShield track</div>
    <div class="leg-row"><span class="leg-dot" style="background:#FFD700;border-color:#CC9000"></span>Sentrycs track</div>
    <div class="leg-row"><span class="leg-dot" style="background:#FF4444;border-color:#CC0000"></span>Fused (hostile)</div>
    <div class="leg-row"><span class="leg-dot" style="background:rgba(0,255,136,0.2);border-color:#00FF88;border-radius:0;transform:rotate(45deg)"></span>Strategic point</div>
    <div class="leg-row"><span class="leg-dot" style="background:rgba(33,150,243,0.15);border-color:#2196F3;border-radius:3px"></span>Holding point</div>
    <div class="leg-row"><span class="leg-line" style="border-color:#00BFFF"></span>Radar range</div>
    <div class="leg-row"><span class="leg-line" style="border-color:#FFD700"></span>RF range</div>
    <div class="leg-row"><span class="leg-line" style="border-color:#80deea"></span>1 km defense ring</div>
    <div class="leg-row"><span class="leg-line" style="border-color:#ffcc80"></span>2 km defense ring</div>
    <div class="leg-row"><span class="leg-line" style="border-color:#ef9a9a"></span>3 km defense ring</div>
    <div class="leg-sep"></div>
    <!-- Sensor live status -->
    <div id="sensor-info"><em style="color:#546e7a">loading sensors…</em></div>
    <div class="leg-sep"></div>
    <!-- Live track list -->
    <div id="track-list-head">&#9998; Live Tracks</div>
    <div id="track-list"><em style="color:#546e7a">waiting for tracks…</em></div>
  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const SP_LAT = __SP_LAT__, SP_LON = __SP_LON__;
const SRC_COLOR = { ECHOSHIELD:'#00BFFF', SENTRYCS:'#FFD700', FUSED:'#FF4444' };
const SRC_BORDER = { ECHOSHIELD:'#0090CC', SENTRYCS:'#CC9000', FUSED:'#CC0000' };

// ── map (OpenStreetMap tiles — reliable, no dark CDN dependency) ────────────
const map = L.map('map').setView([SP_LAT, SP_LON], 14);
const tileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19
}).addTo(map);

// ── map display controls (brightness / opacity) ──────────────────────────────
function applyTileStyle() {
  const bri = parseInt(document.getElementById('bri').value, 10);
  const opa = parseInt(document.getElementById('opa').value, 10);
  document.getElementById('bri-val').textContent = bri + '%';
  document.getElementById('opa-val').textContent = opa + '%';
  const c = tileLayer.getContainer();
  if (c) {
    c.style.filter  = `brightness(${bri / 100})`;
    c.style.opacity = String(opa / 100);
  }
}
document.getElementById('bri').addEventListener('input', applyTileStyle);
document.getElementById('opa').addEventListener('input', applyTileStyle);

// ── layer groups ────────────────────────────────────────────────────────────
const siteLayer   = L.layerGroup().addTo(map);
const sensorLayer = L.layerGroup().addTo(map);
const trackLayer  = L.layerGroup().addTo(map);
const arrowLayer  = L.layerGroup().addTo(map);
const droneMarkers = {};

// ── helpers ─────────────────────────────────────────────────────────────────
function circle(lat, lon, r, color, dash) {
  return L.circle([lat, lon], { radius:r, color, weight:1.5, dashArray:dash||null, fill:false, opacity:0.75 });
}

function arrowLine(lat, lon, deg, color) {
  const len = 0.0007;
  const tip = [lat + Math.cos(deg*Math.PI/180)*len,
               lon + Math.sin(deg*Math.PI/180)*len/Math.cos(lat*Math.PI/180)];
  return L.polyline([[lat,lon],tip], { color, weight:2, opacity:0.85 });
}

function spIcon() {
  return L.divIcon({ className:'',
    html:`<svg viewBox="-16 -16 32 32" width="34" height="34">
      <circle r="14" fill="rgba(0,255,136,0.12)" stroke="#00FF88" stroke-width="2"/>
      <line x1="-14" y1="0" x2="14" y2="0" stroke="#00FF88" stroke-width="1.5"/>
      <line x1="0" y1="-14" x2="0" y2="14" stroke="#00FF88" stroke-width="1.5"/>
      <circle r="3" fill="#00FF88"/>
    </svg>`, iconSize:[34,34], iconAnchor:[17,17] });
}

function hpIcon() {
  return L.divIcon({ className:'',
    html:`<svg viewBox="-15 -15 30 30" width="30" height="30">
      <circle r="13" fill="rgba(33,150,243,0.15)" stroke="#2196F3" stroke-width="2"/>
      <text x="0" y="5" text-anchor="middle" dominant-baseline="middle"
            font-size="13" font-weight="bold" fill="#2196F3" font-family="monospace">H</text>
    </svg>`, iconSize:[30,30], iconAnchor:[15,15] });
}

function radarIcon(c) {
  return L.divIcon({ className:'',
    html:`<svg width="24" height="24" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="11" fill="none" stroke="${c}" stroke-width="1.5" opacity="0.6"/>
      <circle cx="12" cy="12" r="4" fill="none" stroke="${c}" stroke-width="1.5"/>
      <line x1="12" y1="12" x2="12" y2="1" stroke="${c}" stroke-width="2"/>
      <line x1="12" y1="12" x2="20" y2="7" stroke="${c}" stroke-width="1.5" opacity="0.5"/>
    </svg>`, iconSize:[24,24], iconAnchor:[12,12] });
}

function rfIcon(c) {
  return L.divIcon({ className:'',
    html:`<svg width="24" height="24" viewBox="0 0 24 24">
      <path d="M12 14 L12 4" stroke="${c}" stroke-width="2.5"/>
      <path d="M8 9 Q12 4 16 9" fill="none" stroke="${c}" stroke-width="1.5"/>
      <path d="M5 13 Q12 3 19 13" fill="none" stroke="${c}" stroke-width="1" opacity="0.5"/>
      <circle cx="12" cy="17" r="3" fill="${c}" opacity="0.5"/>
    </svg>`, iconSize:[24,24], iconAnchor:[12,17] });
}

// TEST: droneIcon – visual state matrix
// | t.takeover_issued | lost | source   | fill        | border    |
// |-------------------|------|----------|-------------|-----------|
// | true              | any  | any      | #FF9800     | #CC6600   |
// | false             | true | any      | #777        | #444      |
// | false             | false| FUSED    | #FF4444     | #CC0000   |
// | false             | false| SENTRYCS | #FFD700     | #CC9000   |
// | false             | false| ECHO     | #00BFFF     | #0090CC   |
function droneIcon(t, lost) {
  const c = t.takeover_issued ? '#FF9800' : (lost ? '#777' : (SRC_COLOR[t.source]||'#888'));
  const b = t.takeover_issued ? '#CC6600' : (lost ? '#444' : (SRC_BORDER[t.source]||'#555'));
  const sym = t.source==='FUSED'?'✈':(t.source==='ECHOSHIELD'?'◆':'⬡');
  const op = lost ? 0.4 : 0.9;
  return L.divIcon({ className:'',
    html:`<div style="width:22px;height:22px;border-radius:50%;border:2px solid ${b};background:${c};opacity:${op};display:flex;align-items:center;justify-content:center;color:#000;font-size:11px;font-weight:bold">${sym}</div>`,
    iconSize:[22,22], iconAnchor:[11,11] });
}

// ── sites (strategic + holding points) ─────────────────────────────────────
async function refreshSites() {
  try {
    const r = await fetch('/sites', {cache: 'no-store'});
    if (!r.ok) return;
    const data = await r.json();

    siteLayer.clearLayers();
    sensorLayer.clearLayers();

    const RING_COLORS = ['#80deea','#ffcc80','#ef9a9a'];
    const RING_LABELS = ['1 km defense ring','2 km defense ring','3 km defense ring'];

    for (const s of (data.strategic||[])) {
      if (s.type==='strategic_point') {
        L.marker([s.lat,s.lon],{icon:spIcon(),zIndexOffset:1000})
          .bindTooltip(`<b>${s.name}</b><br>${s.lat.toFixed(6)}, ${s.lon.toFixed(6)}`,{className:'leaflet-tooltip-gw'})
          .addTo(siteLayer);
        (s.ranges_m||[]).forEach((rm,i)=>{
          circle(s.lat,s.lon,rm,RING_COLORS[i]||'#ef9a9a','6 5').bindTooltip(RING_LABELS[i],{className:'leaflet-tooltip-gw',permanent:false}).addTo(siteLayer);
        });
      } else if (s.type==='holding_point') {
        L.marker([s.lat,s.lon],{icon:hpIcon(),zIndexOffset:1000})
          .bindTooltip(`<b>${s.name}</b><br>${s.lat.toFixed(6)}, ${s.lon.toFixed(6)}`,{className:'leaflet-tooltip-gw'})
          .addTo(siteLayer);
      }
    }

    // Sensor overlays
    let infoHtml='';
    for (const s of (data.sensors||[])) {
      if (s.status==='unreachable') {
        infoHtml+=`<div style="color:#546e7a">&#9888; ${s.type} unreachable</div>`;
        continue;
      }
      if (s.type==='echoshield') {
        L.marker([s.sensor_lat,s.sensor_lon],{icon:radarIcon('#00BFFF'),zIndexOffset:900})
          .bindTooltip(`EchoShield ${s.sensor_lat.toFixed(4)},${s.sensor_lon.toFixed(4)} range:${s.max_range_m}m`,{className:'leaflet-tooltip-gw'})
          .addTo(sensorLayer);
        circle(s.sensor_lat,s.sensor_lon,s.max_range_m,'#00BFFF','8 5').addTo(sensorLayer);
        infoHtml+=`<div style="color:#00BFFF">&#9679; EchoShield &nbsp;${s.sensor_lat.toFixed(4)},${s.sensor_lon.toFixed(4)}</div>`;
      } else if (s.type==='sentrycs') {
        L.marker([s.sensor_lat,s.sensor_lon],{icon:rfIcon('#FFD700'),zIndexOffset:900})
          .bindTooltip(`Sentrycs ${s.sensor_lat.toFixed(4)},${s.sensor_lon.toFixed(4)} range:${s.detection_radius_m}m`,{className:'leaflet-tooltip-gw'})
          .addTo(sensorLayer);
        circle(s.sensor_lat,s.sensor_lon,s.detection_radius_m,'#FFD700','8 5').addTo(sensorLayer);
        infoHtml+=`<div style="color:#FFD700">&#9679; Sentrycs &nbsp;&nbsp;${s.sensor_lat.toFixed(4)},${s.sensor_lon.toFixed(4)}</div>`;
      }
    }
    document.getElementById('sensor-info').innerHTML=infoHtml||'<em style="color:#546e7a">no sensors</em>';
  } catch(e){ console.warn('sites fetch err',e); }
}

// ── live tracks ─────────────────────────────────────────────────────────────
async function refreshTracks() {
  try {
    const r = await fetch('/tracks', {cache: 'no-store'});
    if (!r.ok) return;
    const tracks = await r.json();

    document.getElementById('track-count').textContent='tracks: '+tracks.length;
    document.getElementById('last-upd').textContent=new Date().toLocaleTimeString();

    const listEl=document.getElementById('track-list');
    if (!tracks.length){ listEl.innerHTML='<em style="color:#546e7a">no active tracks</em>'; return; }

    let html='';
    for (const t of tracks) {
      const lost=t.track_status==='Lost';
      const icon=droneIcon(t,lost);
      const ds=t.detection_status?` [${t.detection_status}]`:'';
      const vel=t.velocity_ms?` ${t.velocity_ms.toFixed(1)}m/s`:'';
      const tooltip=`<b>${t.track_id}</b> (${t.source}${ds})<br>`+
        `${t.lat.toFixed(6)}, ${t.lon.toFixed(6)}<br>`+
        `Alt: ${t.alt_m.toFixed(0)}m  Hdg: ${t.azimuth_deg.toFixed(0)}°${vel}`;
      if (droneMarkers[t.uid]) {
        droneMarkers[t.uid].setLatLng([t.lat, t.lon]);
        droneMarkers[t.uid].setIcon(icon);
        droneMarkers[t.uid].bindTooltip(tooltip, {className:'leaflet-tooltip-gw'});
      } else {
        const m=L.marker([t.lat,t.lon],{icon,zIndexOffset:500});
        m.bindTooltip(tooltip,{className:'leaflet-tooltip-gw'}).addTo(trackLayer);
        droneMarkers[t.uid]=m;
      }
      const cls='t-'+t.source.toLowerCase().replace('echoshield','echo').replace('sentrycs','sntr');
      html+=`<div class="t-row"><span class="t-id ${cls}">${t.track_id}</span>${ds}${t.takeover_issued ? ' <b style="color:#FF9800">[TAKEOVER]</b>' : ''}`+
            `<span class="t-coord"> ${t.lat.toFixed(4)},${t.lon.toFixed(4)} ${t.alt_m.toFixed(0)}m${vel}</span></div>`;
    }

    // Remove stale markers by uid
    const currentUids = new Set(tracks.map(t => t.uid));
    for (const uid of Object.keys(droneMarkers)) {
      if (!currentUids.has(uid)) {
        trackLayer.removeLayer(droneMarkers[uid]);
        delete droneMarkers[uid];
      }
    }

    // Redraw arrows each cycle on dedicated layer (prevents accumulation)
    arrowLayer.clearLayers();
    for (const t of tracks) {
      if (t.track_status!=='Lost' && t.velocity_ms>0.5) {
        arrowLine(t.lat,t.lon,t.azimuth_deg,SRC_COLOR[t.source]||'#888').addTo(arrowLayer);
      }
    }

    listEl.innerHTML=html;
  } catch(e){ console.warn('tracks fetch err',e); }
}

applyTileStyle();
refreshSites();
refreshTracks();
setInterval(refreshSites, 30000);
setInterval(refreshTracks, 1000);
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
        return web.json_response(payload, headers=_NO_CACHE)

    async def _tracks(request: web.Request) -> web.Response:
        return web.json_response(await track_store.get_all(), headers=_NO_CACHE)

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
