"""aiohttp web server — serves CoT map viewer and JSON events API."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog
from aiohttp import web

from tak_client_sim.cot_store import CotStore
from tak_client_sim.models import CotEvent

_log = structlog.get_logger(__name__)

# ── HTML template (placeholders replaced at startup) ──────────────────────
_MAP_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>TAK Client Sim — CoT Map</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <style>
    *{margin:0;padding:0;box-sizing:border-box}
    body{font-family:monospace;background:#1a1a2e;color:#e0e0e0;height:100vh;display:flex;flex-direction:column;overflow:hidden}

    /* ── header ─────────────────────────────────────────── */
    #header{padding:6px 12px;background:#0f3460;display:flex;align-items:center;justify-content:space-between;flex-shrink:0;gap:10px}
    #header h1{font-size:13px;letter-spacing:1px;color:#00d4ff;white-space:nowrap}
    .hdr-group{display:flex;align-items:center;gap:8px}
    #status{font-size:11px;display:flex;align-items:center;gap:5px}
    .dot{width:8px;height:8px;border-radius:50%;background:#888;flex-shrink:0}
    #status.ok .dot{background:#00ff88}
    #status.err .dot{background:#ff4444}
    .btn{font-family:monospace;font-size:11px;padding:3px 9px;border:1px solid #4a8abf;border-radius:3px;background:transparent;color:#90caf9;cursor:pointer;white-space:nowrap;transition:background 0.15s}
    .btn:hover{background:rgba(74,138,191,0.3)}
    .btn.active{background:rgba(33,150,243,0.4);border-color:#2196F3;color:#fff}

    /* ── layout ──────────────────────────────────────────── */
    #body{display:flex;flex:1;overflow:hidden}
    #map{flex:1}

    /* ── panel ───────────────────────────────────────────── */
    #panel{width:290px;flex-shrink:0;background:#0d1b2a;border-left:1px solid #1e3a5f;display:flex;flex-direction:column;overflow:hidden;transition:width 0.2s}
    #panel.collapsed{width:0;border:none}
    #panel-title{padding:7px 10px;background:#0f3460;font-size:12px;font-weight:bold;color:#00d4ff;flex-shrink:0}
    #panel-body{flex:1;overflow-y:auto;padding:6px}
    #panel-body::-webkit-scrollbar{width:4px}
    #panel-body::-webkit-scrollbar-track{background:#0d1b2a}
    #panel-body::-webkit-scrollbar-thumb{background:#1e3a5f;border-radius:2px}

    /* ── event cards ─────────────────────────────────────── */
    .event-card{border:1px solid #1e3a5f;border-radius:4px;margin-bottom:6px;overflow:hidden;cursor:pointer;transition:border-color 0.15s}
    .event-card:hover{border-color:#2196F3}
    .event-card.selected{border-color:#00d4ff;background:rgba(0,212,255,0.05)}
    .event-card.stale{opacity:0.55}
    .event-card-head{padding:5px 8px;display:flex;align-items:center;justify-content:space-between;background:rgba(15,52,96,0.8)}
    .event-uid{font-size:11px;font-weight:bold;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .source-badge{font-size:9px;padding:1px 5px;border-radius:10px;flex-shrink:0;margin-left:4px}
    .badge-ECHO{background:rgba(33,150,243,0.25);color:#64b5f6}
    .badge-SENTRYCS{background:rgba(255,193,7,0.25);color:#ffd54f}
    .badge-FUSED{background:rgba(244,67,54,0.25);color:#ef9a9a}
    .badge-UNKNOWN{background:rgba(144,164,174,0.25);color:#b0bec5}
    .stale-tag{font-size:9px;color:#FF9800;flex-shrink:0}
    .event-fields{padding:4px 8px 5px 8px;font-size:10px;line-height:1.7;color:#b0bec5}
    .field-row{display:flex;justify-content:space-between}
    .field-val{color:#e0e0e0}

    /* ── Leaflet overrides ───────────────────────────────── */
    .leaflet-tooltip-cot{background:rgba(15,52,96,0.85);border:1px solid #2196F3;color:#90caf9;font-family:monospace;font-size:10px;font-weight:bold;padding:1px 5px;border-radius:3px;white-space:nowrap;box-shadow:none}
    .leaflet-tooltip-cot.red-label{border-color:#ef5350;color:#ef9a9a}
    .leaflet-tooltip-cot.stale-label{border-color:#78909c;color:#78909c}
    .leaflet-tooltip-sp{background:rgba(0,30,15,0.9);border:1px solid #00e676;color:#00e676;font-family:monospace;font-size:11px;font-weight:bold;padding:2px 7px;border-radius:3px;white-space:nowrap;box-shadow:none}
    .leaflet-tooltip-hp{background:rgba(0,15,35,0.9);border:1px solid #2196F3;color:#64b5f6;font-family:monospace;font-size:11px;font-weight:bold;padding:2px 7px;border-radius:3px;white-space:nowrap;box-shadow:none}
    .leaflet-popup-content-wrapper{background:#0d1b2a;border:1px solid #2196F3;border-radius:5px;color:#e0e0e0;font-family:monospace;font-size:12px}
    .leaflet-popup-tip{background:#0d1b2a}
    .popup-title{font-size:14px;font-weight:bold;color:#00d4ff;margin-bottom:8px;border-bottom:1px solid #1e3a5f;padding-bottom:5px}
    .popup-row{display:flex;justify-content:space-between;gap:12px;line-height:1.8}
    .popup-key{color:#78909c}
    .popup-val{color:#e0e0e0;font-weight:bold;text-align:right}
    .popup-stale{color:#FF9800;font-weight:bold}

    /* ── legend ──────────────────────────────────────────── */
    .legend{background:rgba(13,27,42,0.92);padding:7px 11px;border-radius:4px;font-size:11px;line-height:2;color:#b0bec5;border:1px solid #1e3a5f}
    .legend b{display:block;color:#90caf9;margin-bottom:2px}
    .legend-item{display:flex;align-items:center;gap:7px;line-height:1.6}
    .legend-dot{width:11px;height:11px;border-radius:50%;flex-shrink:0}
    .legend-ring{width:11px;height:11px;border-radius:50%;border:2px solid;background:transparent;flex-shrink:0}
    .legend-sep{border-top:1px solid #1e3a5f;margin:4px 0}
  </style>
</head>
<body>
  <div id="header">
    <h1>&#128225; TAK CLIENT SIM &mdash; COT VIEWER</h1>
    <div class="hdr-group">
      <button id="btn-labels" class="btn active" title="切換 UID 標籤">&#128204; 標籤</button>
      <button id="btn-center" class="btn" title="置中至戰略要點 SP">&#8982; SP</button>
      <button id="btn-panel"  class="btn active" title="切換資訊面板">&#9776; 資訊</button>
    </div>
    <div id="status">
      <span class="dot"></span>
      <span id="status-text">連線中...</span>
    </div>
  </div>

  <div id="body">
    <div id="map"></div>
    <div id="panel">
      <div id="panel-title">&#128225; CoT 事件列表</div>
      <div id="panel-body">
        <div id="panel-empty" style="color:#546e7a;font-size:11px;padding:8px">尚無 CoT 資料</div>
      </div>
    </div>
  </div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    /* ── scenario coordinates (injected from server config) ── */
    const SP = { lat: __SP_LAT__, lon: __SP_LON__ };
    const HP = { lat: __HP_LAT__, lon: __HP_LON__ };
    const REFRESH_MS = 2000;

    /* ── map ────────────────────────────────────────────────── */
    const map = L.map('map').setView([SP.lat, SP.lon], 13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors', maxZoom: 19
    }).addTo(map);

    /* ── range rings around SP ──────────────────────────────── */
    const RINGS = [
      { r: 1000, color: '#00e676', label: '1 km' },
      { r: 2000, color: '#ffca28', label: '2 km' },
      { r: 3000, color: '#ef5350', label: '3 km' },
    ];
    RINGS.forEach(ring => {
      L.circle([SP.lat, SP.lon], {
        radius: ring.r, color: ring.color, weight: 1.5, opacity: 0.55,
        fillOpacity: 0.025, dashArray: '6 5'
      }).bindTooltip(ring.label, { direction: 'right', className: 'leaflet-tooltip-sp' })
        .addTo(map);
    });

    /* ── SP marker (Strategic Point / radar systems) ─────────── */
    const spIcon = L.divIcon({
      className: '',
      html: `<svg viewBox="-16 -16 32 32" width="34" height="34">
        <circle r="14" fill="rgba(0,200,100,0.12)" stroke="#00e676" stroke-width="2"/>
        <line x1="-14" y1="0" x2="14" y2="0" stroke="#00e676" stroke-width="1.5"/>
        <line x1="0" y1="-14" x2="0" y2="14" stroke="#00e676" stroke-width="1.5"/>
        <circle r="8" fill="none" stroke="#00e676" stroke-width="1" opacity="0.5"/>
        <circle r="3" fill="#00e676"/>
      </svg>`,
      iconSize: [34, 34], iconAnchor: [17, 17], popupAnchor: [0, -20]
    });
    L.marker([SP.lat, SP.lon], { icon: spIcon })
      .bindTooltip('SP 戰略要點 (雷達陣地)', {
        permanent: true, direction: 'right', offset: [12, 0],
        className: 'leaflet-tooltip-sp'
      })
      .bindPopup(
        '<div class="popup-title">&#127961; SP 戰略要點</div>' +
        prow('說明', 'EchoShield + Sentrycs 雷達陣地') +
        prow('座標', SP.lat.toFixed(6) + ', ' + SP.lon.toFixed(6)) +
        prow('範圍圈', '1 km / 2 km / 3 km'),
        { maxWidth: 280 }
      )
      .addTo(map);

    /* ── HP marker (Holding / Landing Point) ──────────────────── */
    const hpIcon = L.divIcon({
      className: '',
      html: `<svg viewBox="-15 -15 30 30" width="30" height="30">
        <circle r="13" fill="rgba(33,150,243,0.15)" stroke="#2196F3" stroke-width="2"/>
        <text x="0" y="5" text-anchor="middle" dominant-baseline="middle"
              font-size="13" font-weight="bold" fill="#2196F3" font-family="monospace">H</text>
      </svg>`,
      iconSize: [30, 30], iconAnchor: [15, 15], popupAnchor: [0, -18]
    });
    L.marker([HP.lat, HP.lon], { icon: hpIcon })
      .bindTooltip('HP 指定停機點', {
        permanent: true, direction: 'right', offset: [12, 0],
        className: 'leaflet-tooltip-hp'
      })
      .bindPopup(
        '<div class="popup-title">&#128641; HP 指定停機點</div>' +
        prow('說明', '無人機接管後降落目標') +
        prow('座標', HP.lat.toFixed(6) + ', ' + HP.lon.toFixed(6)) +
        prow('與 SP 距離', dist(SP.lat, SP.lon, HP.lat, HP.lon).toFixed(0) + ' m'),
        { maxWidth: 260 }
      )
      .addTo(map);

    /* ── legend ─────────────────────────────────────────────── */
    const legend = L.control({ position: 'bottomleft' });
    legend.onAdd = () => {
      const d = L.DomUtil.create('div', 'legend');
      d.innerHTML =
        '<b>圖例 Legend</b>' +
        '<div class="legend-item"><span class="legend-ring" style="border-color:#00e676"></span>1 km 範圍</div>' +
        '<div class="legend-item"><span class="legend-ring" style="border-color:#ffca28"></span>2 km 範圍</div>' +
        '<div class="legend-item"><span class="legend-ring" style="border-color:#ef5350"></span>3 km 範圍</div>' +
        '<div class="legend-sep"></div>' +
        '<div class="legend-item"><svg viewBox="-12 -12 24 24" width="16" height="16"><circle r="10" fill="#90a4ae" stroke="#546e7a" stroke-width="2"/><line x1="-5" y1="-5" x2="5" y2="5" stroke="#546e7a" stroke-width="1.5" stroke-linecap="round"/><line x1="5" y1="-5" x2="-5" y2="5" stroke="#546e7a" stroke-width="1.5" stroke-linecap="round"/></svg>\u00a0未知目標 Unknown (a-u-*)</div>' +
        '<div class="legend-item"><svg viewBox="-12 -12 24 24" width="16" height="16"><rect x="-8" y="-8" width="16" height="16" fill="#ef5350" stroke="#b71c1c" stroke-width="2" transform="rotate(45)"/></svg>\u00a0敵對目標 Hostile (a-h-*)</div>' +
        '<div class="legend-item" style="opacity:0.45"><svg viewBox="-12 -12 24 24" width="16" height="16"><circle r="10" fill="#546e7a" stroke="#37474f" stroke-width="2"/><line x1="-5" y1="-5" x2="5" y2="5" stroke="#37474f" stroke-width="1.5" stroke-linecap="round"/><line x1="5" y1="-5" x2="-5" y2="5" stroke="#37474f" stroke-width="1.5" stroke-linecap="round"/></svg>\u00a0過期 Stale</div>';
      return d;
    };
    legend.addTo(map);

    /* ── state ─────────────────────────────────────────────── */
    const markers   = {};   // uid -> L.Marker
    let showLabels  = true;
    let selectedUid = null;
    let firstFit    = true;

    /* ── helpers ─────────────────────────────────────────────── */
    function prow(k, v) {
      return '<div class="popup-row"><span class="popup-key">' + k +
             '</span><span class="popup-val">' + v + '</span></div>';
    }

    function dist(la1, lo1, la2, lo2) {
      const R = 6371000;
      const dLat = (la2 - la1) * Math.PI / 180;
      const dLon = (lo2 - lo1) * Math.PI / 180;
      const a = Math.sin(dLat/2)**2 + Math.cos(la1*Math.PI/180)*Math.cos(la2*Math.PI/180)*Math.sin(dLon/2)**2;
      return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    }

    function makeIconHtml(cotType, isStale, speed, course) {
      const staleStyle = isStale ? 'opacity:0.45' : '';
      const arrow = (speed > 0.3)
        ? `<g transform="rotate(${course})"><polygon points="0,-7 -3,-1 3,-1" fill="white" opacity="0.85"/></g>`
        : '';

      if (cotType.startsWith('a-h')) {
        const fill = isStale ? '#546e7a' : '#ef5350';
        const stroke = isStale ? '#37474f' : '#b71c1c';
        return `<svg viewBox="-12 -12 24 24" width="24" height="24" style="${staleStyle}">
          <rect x="-8" y="-8" width="16" height="16" fill="${fill}" stroke="${stroke}" stroke-width="2" transform="rotate(45)"/>
          ${arrow}
        </svg>`;
      } else {
        const fill = isStale ? '#546e7a' : '#90a4ae';
        const stroke = isStale ? '#37474f' : '#546e7a';
        return `<svg viewBox="-12 -12 24 24" width="24" height="24" style="${staleStyle}">
          <circle r="10" fill="${fill}" stroke="${stroke}" stroke-width="2"/>
          <line x1="-5" y1="-5" x2="5" y2="5" stroke="${stroke}" stroke-width="1.5" stroke-linecap="round"/>
          <line x1="5" y1="-5" x2="-5" y2="5" stroke="${stroke}" stroke-width="1.5" stroke-linecap="round"/>
          ${arrow}
        </svg>`;
      }
    }

    function makeDroneIcon(evt) {
      const html = makeIconHtml(evt.cot_type, evt.is_stale, evt.speed, evt.course);
      return L.divIcon({
        className: '',
        html: html,
        iconSize: [24, 24], iconAnchor: [12, 12], popupAnchor: [0, -16]
      });
    }

    function cotColor(cotType, isStale) {
      if (isStale) return '#b0bec5';
      if (cotType.startsWith('a-h')) return '#ef5350';
      if (cotType.startsWith('a-u')) return '#90a4ae';
      return '#b0bec5';
    }

    function tooltipClass(evt) {
      if (evt.is_stale) return 'leaflet-tooltip-cot stale-label';
      if (evt.cot_type && evt.cot_type.startsWith('a-h')) return 'leaflet-tooltip-cot red-label';
      return 'leaflet-tooltip-cot';
    }

    function popupHtml(evt) {
      const staleTag = evt.is_stale
        ? '<span class="popup-stale"> ⚠ STALE</span>' : '';
      const timeStr = evt.time.replace('T', ' ').replace('.000Z', '').replace('Z', '');
      return '<div class="popup-title">&#128225; ' + evt.uid + staleTag + '</div>' +
        prow('來源 Source',   evt.source + ' [' + evt.color + ']') +
        prow('CoT Type',      evt.cot_type) +
        prow('緯度 Lat',      evt.lat.toFixed(6) + '°') +
        prow('經度 Lon',      evt.lon.toFixed(6) + '°') +
        prow('高度 HAE',      evt.hae.toFixed(1) + ' m') +
        prow('速度 Speed',    evt.speed.toFixed(1) + ' m/s') +
        prow('航向 Course',   evt.course.toFixed(1) + '°') +
        (evt.remarks ? prow('備註', evt.remarks) : '') +
        prow('時間', timeStr) +
        prow('Stale in',      evt.stale_in_s + ' s') +
        prow('與 SP 距離',    dist(SP.lat, SP.lon, evt.lat, evt.lon).toFixed(0) + ' m');
    }

    function cardHtml(evt) {
      const badgeClass = 'source-badge badge-' + evt.source;
      const staleTag   = evt.is_stale ? '<span class="stale-tag">⚠ STALE</span>' : '';
      const colorDot   = cotColor(evt.cot_type, evt.is_stale);
      const timeStr    = evt.time.replace('T', ' ').substr(0, 19).replace('T', ' ').substr(11, 8);
      const distM      = dist(SP.lat, SP.lon, evt.lat, evt.lon).toFixed(0);
      return '<div class="event-card' + (evt.is_stale ? ' stale' : '') +
             (evt.uid === selectedUid ? ' selected' : '') +
             '" id="card-' + evt.uid + '" data-uid="' + evt.uid + '">' +
        '<div class="event-card-head">' +
          '<span class="event-uid" style="color:' + colorDot + '">&#9632; ' + evt.uid + '</span>' +
          '<span class="' + badgeClass + '">' + evt.source + '</span>' +
          staleTag +
        '</div>' +
        '<div class="event-fields">' +
          frow('位置', evt.lat.toFixed(5) + ', ' + evt.lon.toFixed(5)) +
          frow('高度/速度', evt.hae.toFixed(0) + ' m  /  ' + evt.speed.toFixed(1) + ' m/s') +
          frow('航向', evt.course.toFixed(0) + '°') +
          frow('距 SP', distM + ' m') +
          (evt.remarks ? frow('備註', evt.remarks) : '') +
          frow('時間', evt.time.substr(11, 8)) +
        '</div>' +
      '</div>';
    }

    function frow(k, v) {
      return '<div class="field-row"><span>' + k + '</span>' +
             '<span class="field-val">' + v + '</span></div>';
    }

    /* ── select a CoT event ─────────────────────────────────── */
    function selectEvent(uid) {
      selectedUid = uid;
      document.querySelectorAll('.event-card').forEach(el => {
        el.classList.toggle('selected', el.dataset.uid === uid);
      });
      const m = markers[uid];
      if (m) { map.panTo(m.getLatLng()); m.openPopup(); }
    }

    /* ── label visibility ────────────────────────────────────── */
    function applyLabelVisibility() {
      Object.keys(markers).forEach(uid => {
        const tt = markers[uid].getTooltip();
        if (!tt) return;
        if (showLabels) markers[uid].openTooltip();
        else markers[uid].closeTooltip();
      });
    }

    /* ── main refresh ────────────────────────────────────────── */
    async function refresh() {
      const statusEl   = document.getElementById('status');
      const statusText = document.getElementById('status-text');
      try {
        const res = await fetch('/events', {cache: 'no-store'});
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();

        statusEl.className = 'ok';
        statusText.textContent =
          data.count + ' CoT 目標  |  ' + new Date().toLocaleTimeString('zh-TW');

        const seen      = new Set();
        const positions = [];
        let   panelHtml = '';

        for (const evt of data.events) {
          seen.add(evt.uid);
          positions.push([evt.lat, evt.lon]);
          panelHtml += cardHtml(evt);

          if (markers[evt.uid]) {
            markers[evt.uid].setLatLng([evt.lat, evt.lon]);
            markers[evt.uid].setIcon(makeDroneIcon(evt));
            markers[evt.uid].setPopupContent(popupHtml(evt));
            const tt = markers[evt.uid].getTooltip();
            if (tt) {
              const el = tt.getElement();
              if (el) el.className = tooltipClass(evt);
            }
          } else {
            const m = L.marker([evt.lat, evt.lon], { icon: makeDroneIcon(evt) })
              .bindPopup(popupHtml(evt), { maxWidth: 280, minWidth: 220 })
              .bindTooltip(evt.uid, {
                permanent: true, direction: 'right', offset: [10, 0],
                className: tooltipClass(evt)
              })
              .addTo(map);
            m.on('click', () => { selectedUid = evt.uid; refreshCards(); });
            markers[evt.uid] = m;
            if (!showLabels) m.closeTooltip();
          }
        }

        // remove disappeared markers
        for (const uid of Object.keys(markers)) {
          if (!seen.has(uid)) {
            map.removeLayer(markers[uid]);
            delete markers[uid];
          }
        }

        // update panel
        const panelBody = document.getElementById('panel-body');
        if (data.events.length === 0) {
          panelBody.innerHTML =
            '<div id="panel-empty" style="color:#546e7a;font-size:11px;padding:8px">尚無 CoT 資料</div>';
        } else {
          panelBody.innerHTML = panelHtml;
          panelBody.querySelectorAll('.event-card').forEach(card => {
            card.addEventListener('click', () => selectEvent(card.dataset.uid));
          });
        }

        // auto-fit first load
        if (firstFit && positions.length > 0) {
          firstFit = false;
          if (positions.length === 1) map.setView(positions[0], 14);
          else map.fitBounds(L.latLngBounds(positions).pad(0.3));
        }
      } catch (e) {
        statusEl.className = 'err';
        statusText.textContent = '錯誤: ' + e.message;
      }
    }

    function refreshCards() {
      document.querySelectorAll('.event-card').forEach(el => {
        el.classList.toggle('selected', el.dataset.uid === selectedUid);
      });
    }

    /* ── toolbar ─────────────────────────────────────────────── */
    document.getElementById('btn-labels').addEventListener('click', function () {
      showLabels = !showLabels;
      this.classList.toggle('active', showLabels);
      applyLabelVisibility();
    });

    document.getElementById('btn-center').addEventListener('click', function () {
      map.setView([SP.lat, SP.lon], 13);
    });

    document.getElementById('btn-panel').addEventListener('click', function () {
      const panel = document.getElementById('panel');
      panel.classList.toggle('collapsed');
      this.classList.toggle('active', !panel.classList.contains('collapsed'));
      setTimeout(() => map.invalidateSize(), 210);
    });

    /* ── start ───────────────────────────────────────────────── */
    refresh();
    setInterval(refresh, REFRESH_MS);
  </script>
</body>
</html>
"""


def _build_map_html(sp_lat: float, sp_lon: float, hp_lat: float, hp_lon: float) -> str:
    return (
        _MAP_HTML_TEMPLATE.replace("__SP_LAT__", str(sp_lat))
        .replace("__SP_LON__", str(sp_lon))
        .replace("__HP_LAT__", str(hp_lat))
        .replace("__HP_LON__", str(hp_lon))
    )


_NO_CACHE: dict[str, str] = {"Cache-Control": "no-store, no-cache", "Pragma": "no-cache"}


# ── DTO serialisation ─────────────────────────────────────────────────────


def _fmt_dt(dt: datetime) -> str:
    ms = dt.microsecond // 1000
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms:03d}Z"


def _event_to_dict(evt: CotEvent, now: datetime) -> dict[str, Any]:
    stale_in_s = round((evt.stale - now).total_seconds())
    is_stale = stale_in_s < 0
    return {
        "uid": evt.uid,
        "source": evt.source,
        "color": evt.color,
        "cot_type": evt.cot_type,
        "lat": evt.lat,
        "lon": evt.lon,
        "hae": evt.hae,
        "speed": evt.speed,
        "course": evt.course,
        "remarks": evt.remarks,
        "time": _fmt_dt(evt.time),
        "stale": _fmt_dt(evt.stale),
        "delta_s": evt.delta_s,
        "is_stale": is_stale,
        "stale_in_s": stale_in_s,
    }


# ── request handlers ──────────────────────────────────────────────────────


async def _handle_map(request: web.Request) -> web.Response:
    html: str = request.app["map_html"]
    return web.Response(content_type="text/html", charset="utf-8", text=html)


async def _handle_events(request: web.Request) -> web.Response:
    store: CotStore = request.app["store"]
    now = datetime.now(timezone.utc)
    events = await store.get_all()
    payload = {
        "events": [_event_to_dict(e, now) for e in events],
        "count": len(events),
        "timestamp": _fmt_dt(now),
    }
    return web.json_response(payload, headers=_NO_CACHE)


async def _handle_health(request: web.Request) -> web.Response:
    store: CotStore = request.app["store"]
    events = await store.get_all()
    return web.json_response({"status": "ok", "tracked": len(events)}, headers=_NO_CACHE)


# ── app factory + lifecycle ───────────────────────────────────────────────


def _build_app(map_html: str, store: CotStore) -> web.Application:
    app = web.Application()
    app["map_html"] = map_html
    app["store"] = store
    app.router.add_get("/map", _handle_map)
    app.router.add_get("/events", _handle_events)
    app.router.add_get("/health", _handle_health)
    return app


async def run_web_server(
    host: str,
    port: int,
    sp_lat: float,
    sp_lon: float,
    hp_lat: float,
    hp_lon: float,
    store: CotStore,
    stop: asyncio.Event,
) -> None:
    """Run the aiohttp map server until *stop* is set."""
    map_html = _build_map_html(sp_lat, sp_lon, hp_lat, hp_lon)
    app = _build_app(map_html, store)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    _log.info("web_server_started", host=host, port=port, map_url=f"http://{host}:{port}/map")
    try:
        await stop.wait()
    finally:
        await runner.cleanup()
        _log.info("web_server_stopped")
