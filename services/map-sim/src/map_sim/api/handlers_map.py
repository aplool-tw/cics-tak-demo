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
    }
    #header {
      padding: 8px 14px;
      background: #0f3460;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-shrink: 0;
    }
    #header h1 { font-size: 14px; letter-spacing: 1px; color: #00d4ff; }
    #status { font-size: 11px; display: flex; align-items: center; gap: 5px; }
    .dot {
      width: 9px; height: 9px;
      border-radius: 50%;
      background: #888;
      flex-shrink: 0;
    }
    #status.ok  .dot { background: #00ff88; }
    #status.err .dot { background: #ff4444; }
    #map { flex: 1; }
    .legend {
      background: rgba(15, 52, 96, 0.92);
      padding: 8px 12px;
      border-radius: 4px;
      font-size: 11px;
      line-height: 2;
      color: #e0e0e0;
    }
    .legend b { display: block; margin-bottom: 2px; }
    .legend-item { display: flex; align-items: center; gap: 7px; }
    .legend-dot { width: 11px; height: 11px; border-radius: 50%; flex-shrink: 0; }
  </style>
</head>
<body>
  <div id="header">
    <h1>&#128225; MAP SIM — DRONE TRACKER</h1>
    <div id="status">
      <span class="dot"></span>
      <span id="status-text">連線中...</span>
    </div>
  </div>
  <div id="map"></div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const REFRESH_MS  = 3000;
    const TAIWAN_INIT = [24.0, 121.0];

    const map = L.map('map').setView(TAIWAN_INIT, 8);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 19
    }).addTo(map);

    /* ── legend ─────────────────────────────────────────────── */
    const legend = L.control({ position: 'bottomright' });
    legend.onAdd = () => {
      const div = L.DomUtil.create('div', 'legend');
      div.innerHTML = [
        '<b>圖例 Legend</b>',
        '<div class="legend-item">',
        '  <span class="legend-dot" style="background:#2196F3;border:2px solid #0D47A1"></span>',
        '  活躍 Active',
        '</div>',
        '<div class="legend-item">',
        '  <span class="legend-dot" style="background:#FF9800;border:2px solid #E65100"></span>',
        '  失聯 Lost',
        '</div>'
      ].join('');
      return div;
    };
    legend.addTo(map);

    /* ── marker helpers ──────────────────────────────────────── */
    function makeIcon(isLost) {
      const bg     = isLost ? '#FF9800' : '#2196F3';
      const border = isLost ? '#E65100' : '#0D47A1';
      return L.divIcon({
        className: '',
        html: '<div style="width:14px;height:14px;border-radius:50%;' +
              'background:' + bg + ';border:2px solid ' + border + ';' +
              'box-shadow:0 0 6px ' + bg + '"></div>',
        iconSize:    [14, 14],
        iconAnchor:  [7, 7],
        popupAnchor: [0, -12]
      });
    }

    function popupHtml(o) {
      return '<b>' + o.drone_id + '</b><br>' +
        '狀態: <b>' + o.status + '</b>' + (o.is_lost ? ' &#9888; Lost' : '') + '<br>' +
        '座標: ' + o.lat.toFixed(6) + ', ' + o.lon.toFixed(6) + '<br>' +
        '高度: ' + o.alt_m + ' m<br>' +
        '速度: ' + o.speed_ms + ' m/s<br>' +
        '航向: ' + o.heading_deg + '&deg;<br>' +
        '上次更新: ' + o.last_seen_s + 's 前';
    }

    /* ── state ───────────────────────────────────────────────── */
    const markers  = {};
    let   firstFit = true;

    /* ── main refresh loop ───────────────────────────────────── */
    async function refresh() {
      const statusEl   = document.getElementById('status');
      const statusText = document.getElementById('status-text');
      try {
        const res = await fetch('/objects/all');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();

        statusEl.className   = 'ok';
        statusText.textContent =
          data.active + ' 活躍  ' + data.lost + ' 失聯' +
          '  |  ' + new Date().toLocaleTimeString('zh-TW');

        const seen = new Set();
        const positions = [];

        for (const obj of data.objects) {
          seen.add(obj.drone_id);
          positions.push([obj.lat, obj.lon]);
          if (markers[obj.drone_id]) {
            markers[obj.drone_id].setLatLng([obj.lat, obj.lon]);
            markers[obj.drone_id].setIcon(makeIcon(obj.is_lost));
            markers[obj.drone_id].setPopupContent(popupHtml(obj));
          } else {
            markers[obj.drone_id] = L.marker([obj.lat, obj.lon], { icon: makeIcon(obj.is_lost) })
              .bindPopup(popupHtml(obj))
              .addTo(map);
          }
        }

        /* remove markers for drones no longer in registry */
        for (const id of Object.keys(markers)) {
          if (!seen.has(id)) {
            map.removeLayer(markers[id]);
            delete markers[id];
          }
        }

        /* auto-fit on first load that has objects */
        if (firstFit && positions.length > 0) {
          firstFit = false;
          if (positions.length === 1) {
            map.setView(positions[0], 14);
          } else {
            map.fitBounds(L.latLngBounds(positions).pad(0.25));
          }
        }
      } catch (e) {
        statusEl.className   = 'err';
        statusText.textContent = '錯誤: ' + e.message;
      }
    }

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
