"""GET /map handler — serves the browser-based Leaflet.js drone map viewer."""

from __future__ import annotations

from aiohttp import web

_MAP_HTML = """\
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Map Sim — Drone Tracker</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }

    body {
      font-family: monospace;
      background: #1a1a2e;
      color: #e0e0e0;
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

    /* ── header ─────────────────────────────────── */
    #header {
      padding: 6px 12px;
      background: #0f3460;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-shrink: 0;
      gap: 10px;
    }
    #header h1 { font-size: 13px; letter-spacing: 1px; color: #00d4ff; white-space: nowrap; }

    .hdr-group { display: flex; align-items: center; gap: 8px; }

    #status { font-size: 11px; display: flex; align-items: center; gap: 5px; }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: #888; flex-shrink: 0; }
    #status.ok  .dot { background: #00ff88; }
    #status.err .dot { background: #ff4444; }

    /* toolbar buttons */
    .btn {
      font-family: monospace;
      font-size: 11px;
      padding: 3px 9px;
      border: 1px solid #4a8abf;
      border-radius: 3px;
      background: transparent;
      color: #90caf9;
      cursor: pointer;
      white-space: nowrap;
      transition: background 0.15s;
    }
    .btn:hover { background: rgba(74,138,191,0.3); }
    .btn.active { background: rgba(33,150,243,0.4); border-color: #2196F3; color: #fff; }

    /* ── body layout ─────────────────────────────── */
    #body { display: flex; flex: 1; overflow: hidden; }
    #map  { flex: 1; }

    /* ── info panel ──────────────────────────────── */
    #panel {
      width: 280px;
      flex-shrink: 0;
      background: #0d1b2a;
      border-left: 1px solid #1e3a5f;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      transition: width 0.2s;
    }
    #panel.collapsed { width: 0; border: none; }

    #panel-title {
      padding: 7px 10px;
      background: #0f3460;
      font-size: 12px;
      font-weight: bold;
      color: #00d4ff;
      flex-shrink: 0;
    }

    #panel-body {
      flex: 1;
      overflow-y: auto;
      padding: 6px;
    }

    /* drone cards */
    .drone-card {
      border: 1px solid #1e3a5f;
      border-radius: 4px;
      margin-bottom: 6px;
      overflow: hidden;
      cursor: pointer;
      transition: border-color 0.15s;
    }
    .drone-card:hover { border-color: #2196F3; }
    .drone-card.selected { border-color: #00d4ff; background: rgba(0,212,255,0.05); }

    .drone-card-head {
      padding: 5px 8px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: rgba(15,52,96,0.8);
    }
    .drone-id { font-size: 12px; font-weight: bold; color: #90caf9; }
    .drone-status {
      font-size: 10px;
      padding: 1px 6px;
      border-radius: 10px;
      background: rgba(33,150,243,0.2);
      color: #64b5f6;
    }
    .drone-status.lost { background: rgba(255,152,0,0.2); color: #ffb74d; }

    .drone-fields {
      padding: 5px 8px 6px 8px;
      font-size: 10px;
      line-height: 1.7;
      color: #b0bec5;
    }
    .drone-fields .field-row { display: flex; justify-content: space-between; }
    .drone-fields .field-val { color: #e0e0e0; }

    /* ── Leaflet overrides ───────────────────────── */
    .leaflet-tooltip-perm {
      background: rgba(15,52,96,0.85);
      border: 1px solid #2196F3;
      color: #90caf9;
      font-family: monospace;
      font-size: 11px;
      font-weight: bold;
      padding: 1px 5px;
      border-radius: 3px;
      white-space: nowrap;
      box-shadow: none;
    }
    .leaflet-tooltip-perm.lost-label {
      border-color: #FF9800;
      color: #ffb74d;
    }

    /* custom popup */
    .leaflet-popup-content-wrapper {
      background: #0d1b2a;
      border: 1px solid #2196F3;
      border-radius: 5px;
      color: #e0e0e0;
      font-family: monospace;
      font-size: 12px;
    }
    .leaflet-popup-tip { background: #0d1b2a; }

    .popup-title {
      font-size: 14px;
      font-weight: bold;
      color: #00d4ff;
      margin-bottom: 8px;
      border-bottom: 1px solid #1e3a5f;
      padding-bottom: 5px;
    }
    .popup-row { display: flex; justify-content: space-between; gap: 12px; line-height: 1.8; }
    .popup-key { color: #78909c; }
    .popup-val { color: #e0e0e0; font-weight: bold; text-align: right; }
    .popup-lost { color: #FF9800; font-weight: bold; }

    /* legend */
    .legend {
      background: rgba(13,27,42,0.92);
      padding: 7px 11px;
      border-radius: 4px;
      font-size: 11px;
      line-height: 2;
      color: #b0bec5;
      border: 1px solid #1e3a5f;
    }
    .legend b { display: block; color: #90caf9; margin-bottom: 2px; }
    .legend-item { display: flex; align-items: center; gap: 7px; }
    .legend-dot { width: 11px; height: 11px; border-radius: 50%; flex-shrink: 0; }

    /* scrollbar */
    #panel-body::-webkit-scrollbar { width: 4px; }
    #panel-body::-webkit-scrollbar-track { background: #0d1b2a; }
    #panel-body::-webkit-scrollbar-thumb { background: #1e3a5f; border-radius: 2px; }
  </style>
</head>
<body>
  <div id="header">
    <h1>&#128225; MAP SIM &mdash; DRONE TRACKER</h1>
    <div class="hdr-group">
      <button id="btn-labels" class="btn active" title="切換物件名稱顯示">&#128204; 標籤</button>
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
      <div id="panel-title">&#9992; 無人機資訊列表</div>
      <div id="panel-body">
        <div id="panel-empty" style="color:#546e7a;font-size:11px;padding:8px">
          尚無物件資料
        </div>
      </div>
    </div>
  </div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    /* ── constants ──────────────────────────────────────────── */
    const REFRESH_MS  = 3000;
    const TAIWAN_INIT = [24.0, 121.0];

    /* ── map init ───────────────────────────────────────────── */
    const map = L.map('map').setView(TAIWAN_INIT, 8);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 19
    }).addTo(map);

    /* ── legend ─────────────────────────────────────────────── */
    const legend = L.control({ position: 'bottomleft' });
    legend.onAdd = () => {
      const div = L.DomUtil.create('div', 'legend');
      div.innerHTML =
        '<b>圖例 Legend</b>' +
        '<div class="legend-item"><span class="legend-dot" style="background:#2196F3;border:2px solid #0D47A1"></span>活躍 Active</div>' +
        '<div class="legend-item"><span class="legend-dot" style="background:#FF9800;border:2px solid #E65100"></span>失聯 Lost</div>';
      return div;
    };
    legend.addTo(map);

    /* ── state ───────────────────────────────────────────────── */
    const markers     = {};   // drone_id -> L.Marker
    const tooltipObjs = {};   // drone_id -> drone data (for re-render)
    let   firstFit    = true;
    let   showLabels  = true;
    let   selectedId  = null;

    /* ── colour helpers ─────────────────────────────────────── */
    function colors(isLost) {
      return isLost
        ? { bg: '#FF9800', border: '#E65100' }
        : { bg: '#2196F3', border: '#0D47A1' };
    }

    function makeIcon(isLost) {
      const c = colors(isLost);
      return L.divIcon({
        className: '',
        html: '<div style="width:14px;height:14px;border-radius:50%;' +
              'background:' + c.bg + ';border:2.5px solid ' + c.border + ';' +
              'box-shadow:0 0 7px ' + c.bg + '"></div>',
        iconSize: [14, 14], iconAnchor: [7, 7], popupAnchor: [0, -12]
      });
    }

    /* ── popup HTML ─────────────────────────────────────────── */
    function popupHtml(o) {
      const lostBadge = o.is_lost
        ? '<span class="popup-lost"> &#9888; LOST</span>' : '';
      return '<div class="popup-title">&#128225; ' + o.drone_id + lostBadge + '</div>' +
        row('狀態 Status',  o.status) +
        row('緯度 Lat',     o.lat.toFixed(6) + '°') +
        row('經度 Lon',     o.lon.toFixed(6) + '°') +
        row('高度 Alt',     o.alt_m + ' m') +
        row('速度 Speed',   o.speed_ms + ' m/s') +
        row('航向 Heading', o.heading_deg.toFixed(1) + '°') +
        row('時間戳 Time',  o.timestamp.replace('T',' ').replace('Z','')) +
        row('上次更新',     o.last_seen_s + 's 前');
    }

    function row(k, v) {
      return '<div class="popup-row"><span class="popup-key">' + k +
             '</span><span class="popup-val">' + v + '</span></div>';
    }

    /* ── panel card HTML ────────────────────────────────────── */
    function cardHtml(o) {
      const lostClass  = o.is_lost ? ' lost' : '';
      const lostText   = o.is_lost ? ' ⚠ LOST' : '';
      return '<div class="drone-card' + (o.drone_id === selectedId ? ' selected' : '') +
             '" id="card-' + o.drone_id + '" data-id="' + o.drone_id + '">' +
        '<div class="drone-card-head">' +
          '<span class="drone-id">' + o.drone_id + '</span>' +
          '<span class="drone-status' + lostClass + '">' + o.status + lostText + '</span>' +
        '</div>' +
        '<div class="drone-fields">' +
          cardRow('Lat / Lon', o.lat.toFixed(5) + ', ' + o.lon.toFixed(5)) +
          cardRow('Alt / Speed', o.alt_m + ' m  /  ' + o.speed_ms + ' m/s') +
          cardRow('Heading', o.heading_deg.toFixed(1) + '°') +
          cardRow('Last seen', o.last_seen_s + 's 前') +
          cardRow('Timestamp', o.timestamp.replace('T',' ').replace('Z','')) +
        '</div>' +
      '</div>';
    }

    function cardRow(k, v) {
      return '<div class="field-row"><span>' + k + '</span><span class="field-val">' + v + '</span></div>';
    }

    /* ── select a drone (centre map + open popup) ────────────── */
    function selectDrone(id) {
      selectedId = id;
      // refresh card highlights
      document.querySelectorAll('.drone-card').forEach(el => {
        el.classList.toggle('selected', el.id === 'card-' + id);
      });
      const m = markers[id];
      if (m) {
        map.panTo(m.getLatLng());
        m.openPopup();
      }
    }

    /* ── label visibility ────────────────────────────────────── */
    function applyLabelVisibility() {
      for (const id of Object.keys(markers)) {
        const tt = markers[id].getTooltip();
        if (!tt) continue;
        if (showLabels) markers[id].openTooltip();
        else markers[id].closeTooltip();
      }
    }

    /* ── main refresh ────────────────────────────────────────── */
    async function refresh() {
      const statusEl   = document.getElementById('status');
      const statusText = document.getElementById('status-text');
      try {
        const res = await fetch('/objects/all');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();

        statusEl.className = 'ok';
        statusText.textContent =
          data.active + ' 活躍  ' + data.lost + ' 失聯  |  ' +
          new Date().toLocaleTimeString('zh-TW');

        const seen      = new Set();
        const positions = [];
        let   panelHtml = '';

        for (const obj of data.objects) {
          seen.add(obj.drone_id);
          positions.push([obj.lat, obj.lon]);
          panelHtml += cardHtml(obj);

          if (markers[obj.drone_id]) {
            // update existing marker
            markers[obj.drone_id].setLatLng([obj.lat, obj.lon]);
            markers[obj.drone_id].setIcon(makeIcon(obj.is_lost));
            markers[obj.drone_id].setPopupContent(popupHtml(obj));
            // update tooltip class
            const tt = markers[obj.drone_id].getTooltip();
            if (tt) {
              tt.setContent(obj.drone_id);
              const el = tt.getElement();
              if (el) {
                el.classList.toggle('lost-label', obj.is_lost);
              }
            }
          } else {
            // create new marker
            const m = L.marker([obj.lat, obj.lon], { icon: makeIcon(obj.is_lost) })
              .bindPopup(popupHtml(obj), { maxWidth: 260, minWidth: 200 })
              .bindTooltip(obj.drone_id, {
                permanent: true,
                direction: 'right',
                offset: [10, 0],
                className: 'leaflet-tooltip-perm' + (obj.is_lost ? ' lost-label' : '')
              })
              .addTo(map);

            m.on('click', () => { selectedId = obj.drone_id; refreshCards(); });
            markers[obj.drone_id] = m;

            if (!showLabels) m.closeTooltip();
          }
        }

        // remove stale markers
        for (const id of Object.keys(markers)) {
          if (!seen.has(id)) {
            map.removeLayer(markers[id]);
            delete markers[id];
          }
        }

        // update panel
        const panelBody  = document.getElementById('panel-body');
        const panelEmpty = document.getElementById('panel-empty');
        if (data.objects.length === 0) {
          panelBody.innerHTML = '<div id="panel-empty" style="color:#546e7a;font-size:11px;padding:8px">尚無物件資料</div>';
        } else {
          panelBody.innerHTML = panelHtml;
          // attach click via delegation (avoids inline onclick + escaping issues)
          panelBody.querySelectorAll('.drone-card').forEach(card => {
            card.addEventListener('click', () => selectDrone(card.dataset.id));
          });
        }

        // auto-fit on first load with objects
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
      document.querySelectorAll('.drone-card').forEach(el => {
        const id = el.id.replace('card-', '');
        el.classList.toggle('selected', id === selectedId);
      });
    }

    /* ── toolbar buttons ─────────────────────────────────────── */
    document.getElementById('btn-labels').addEventListener('click', function () {
      showLabels = !showLabels;
      this.classList.toggle('active', showLabels);
      applyLabelVisibility();
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


async def map_view(request: web.Request) -> web.Response:
    return web.Response(
        content_type="text/html",
        charset="utf-8",
        text=_MAP_HTML,
    )
