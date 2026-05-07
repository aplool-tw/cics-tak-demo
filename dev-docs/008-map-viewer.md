# 008-map-viewer — Leaflet.js Browser Map Viewers (Map Sim + CoT Gateway)

## 概述

本 feature 分兩階段：
1. **Map Sim** — 為 Map Simulator 新增 `GET /map` 端點，顯示即時無人機位置。
2. **CoT Gateway** — 為 CoT Gateway 新增 web module，顯示 EchoShield + Sentrycs 融合後的 TAK 軌跡、感測器位置、戰略目標（SP/HP）及 1/2/3km 範圍圈。

## 功能清單

| 功能 | 說明 |
|------|------|
| 即時地圖 | Leaflet.js CDN，每 3 秒 poll `/objects/all` |
| 自動縮放 | 首次載入有物件時自動 fitBounds |
| 顏色標記 | Active=藍色圓形，Lost=橘色圓形 |
| 永久標籤 | 顯示 drone_id，可用「標籤」按鈕切換 |
| 點擊 Popup | 顯示 8 欄位：status/lat/lon/alt/speed/heading/timestamp/last_seen |
| 右側資訊欄 | 所有無人機卡片清單，Active=藍色 badge，Lost=橘色 badge |
| 點擊卡片 | 地圖 panTo + 開啟 popup + 卡片高亮 |
| 連線狀態列 | 顯示「連線中…」→「已連線（N 架）」 |
| 示範腳本 | `scripts/demo-map-viewer.sh`：啟動 map-sim(8090) + uds(18080) + 3-drone 情境 |

## 新增 / 修改檔案

```
services/map-sim/src/map_sim/api/
  handlers_map.py          NEW  GET /map handler；內嵌完整 HTML/CSS/JS
  server.py                MOD  新增 GET /map 路由

services/map-sim/tests/contract/
  test_map_contract.py     NEW  5 個 contract 測試（200、content-type、leaflet、/objects/all、setInterval）

scripts/
  demo-map-viewer.sh       NEW  demo 啟動腳本（--stop 模式可停止服務）

services/uds/scenarios/
  e2e_multi_drone.yaml     MOD  TRK-E0C model 由 "Skydio 2+" 改為 "DJI Matrice 30T"（UDS Literal 約束）
```

## 技術決策

### 1. 內嵌 HTML 而非獨立靜態檔案

考慮點：map-sim 為 PoC 單服務，不引入靜態目錄路由複雜度；單一 Python 字串方便單元測試斷言內容。  
缺點：HTML 超過 400 行嵌在 Python 字串中，維護時需留意逸脫規則。

### 2. Python 三重引號字串的逸脫陷阱

`"""..."""` 內的 `\'` 被 Python 解析為 `'`（反斜線被消耗），因此不能用 `onclick="selectDrone(\'' + id + '\')"` 產生合法 JS。

**解法**：改用 `data-id` attribute + 事件委派（delegated listener），完全避開逸脫問題：

```python
# cardHtml() 中
"<div class='drone-card' data-id='" + o.drone_id + "'>"

# refresh() 中，panelBody.innerHTML 設置完後
panelBody.querySelectorAll('.drone-card').forEach(card => {
  card.addEventListener('click', () => selectDrone(card.dataset.id));
});
```

### 3. demo-map-viewer.sh 直接啟動服務

`dev-launcher.sh` 有 `trap cleanup EXIT`，以背景執行會在子 shell 退出時 SIGTERM 所有子程序。改為直接 `exec python3 -m map_sim` 以 subprocess 方式啟動，避免 trap 問題。

### 4. UDS 無 /health 端點

UDS 只提供 `POST /command/takeover`。健康檢查改用 TCP port 探測：

```bash
bash -c "echo > /dev/tcp/127.0.0.1/${PORT}" 2>/dev/null
```

### 5. Port 8080 衝突

環境中 8080 被 `security-drone-system` 佔用。Demo 腳本將 UDS 改為 18080，僅影響示範情境（正式整合仍用 8080）。

## Leaflet.js 選型理由

- 純前端 CDN，無需 build tool
- 輕量（46 KB gz），適合 PoC 內嵌 HTML
- 原生 `bindTooltip / bindPopup / fitBounds` API 滿足所有功能需求
- 符合 G7（Minimal Dependencies）：JS 端只需 Leaflet；Python 端無新依賴

## 已知限制

- Leaflet CDN 需要外部網路（`unpkg.com`）；離線環境需自行 host 或 vendor
- HTML 嵌在 Python 字串中，drone_id 若含特殊字元（`<`, `>`, `"`, `&`）目前未做 HTML escape（PoC 情境 ID 均為英數，故不構成問題）
- 同時顯示物件數無上限設計，大量無人機（>100）可能造成 DOM 效能問題

## 測試

```
107 passed in 2.86s
ruff: clean
black: clean
```

## 使用方式

```bash
# Map Sim Demo
bash scripts/demo-map-viewer.sh

# 停止
bash scripts/demo-map-viewer.sh --stop

# 直接開發測試
open http://127.0.0.1:18090/map
```

---

## Part 2 — CoT Gateway Leaflet Map

### 概述

CoT Gateway 新增 `web/` module，整合即時 TAK 軌跡（EchoShield + Sentrycs/融合）、感測器位置、戰略目標（SP = 雷達站位、HP = 停機點）及範圍圈顯示。

### 功能清單

| 功能 | 說明 |
|------|------|
| 即時軌跡 | 每 3 秒 poll `/tracks`，依來源著色：ECHOSHIELD=藍、SENTRYCS=紫、FUSED=紅 |
| 感測器位置 | GET /info (EchoShield :19001) + GET /sensor-info (Sentrycs :17070) 顯示感測器 marker |
| SP（雷達站） | 綠色 marker，附 1km/2km/3km 範圍圈 |
| HP（停機點） | 橘色 H 標記 marker |
| 軌跡卡片 | 右側面板顯示所有 active 軌跡，含 UID/座標/狀態 |
| 右鍵 popup | 顯示軌跡詳情 |

### 新增 / 修改檔案

```
services/cot-gateway/
  src/cot_gateway/web/__init__.py      NEW  module init
  src/cot_gateway/web/track_store.py  NEW  asyncio-safe UID→UnifiedTrack store
  src/cot_gateway/web/sites.py        NEW  SiteEntry+SitesConfig pydantic models
  src/cot_gateway/web/server.py       NEW  aiohttp: GET /map, /tracks, /sites, /health
  config/sites.yaml                   NEW  SP(24.725806,121.033750) + HP(24.725806,121.071889)
  config/demo.yaml                    NEW  web enabled, use_ssl=false, max_retries=9999
  src/cot_gateway/config.py           MOD  WebConfig + GatewayConfig.web 欄位
  src/cot_gateway/loop.py             MOD  track_store param; upsert/remove; web server task
  src/cot_gateway/cli.py              MOD  --web/--no-web/--web-host/--web-port/--sites-file

services/echoshield-sim/
  src/echoshield_sim/config.py        MOD  info_host, info_port: 9001
  src/echoshield_sim/loop.py          MOD  aiohttp GET /info + /health HTTP server
  config/demo.yaml                    NEW  local dev config

services/sentrycs-sim/
  src/sentrycs_sim/config.py          MOD  sensor_alt_m: float = 0.0
  src/sentrycs_sim/api/server.py      MOD  build_app() sensor params; GET /sensor-info
  src/sentrycs_sim/loop.py            MOD  passes sensor coords to build_app()
  config/demo.yaml                    NEW  local dev config

services/uds/
  scenarios/demo_single_drone.yaml    NEW  3.5km start (24.757306N), 20m/s

scripts/
  demo-cot-gateway-map.sh             NEW  5 服務 demo 啟動腳本（含健康檢查、--stop）
```

### 關鍵 Bug 修正：EchoShield wire field names

**問題**：`echoshield/adapter.py` 的 `REQUIRED_FIELDS` 使用 `"lat"`/`"lon"`，但 `RadarTrack.model_dump()` 輸出 `"latitude"`/`"longitude"`（符合 AGENTS.md wire 契約）。每筆 EchoShield 軌跡皆以 `invalid_wire_fields` 錯誤被靜默丟棄，地圖完全無軌跡。

**修正**：
- `adapter.py` 改讀 `msg["latitude"]` / `msg["longitude"]`
- 7 個測試檔案的 echo mock 資料同步更新（sentrycs RF mock 保留 `lat`/`lon`）

### 技術決策

1. **aiohttp AppRunner + TCPSite**：CoT Gateway 在 asyncio 內啟動 web server 必須用此模式，不可用 `web.run_app()`（會佔用 event loop）。
2. **`stop` Event 協調**：`GatewayMain._stop` asyncio.Event 傳入 web server，實現乾淨關閉。
3. **TrackStore 由 CoT UID 索引**（如 `ECHO-TRK-E01`），TTL 移除軌跡時同步從 store 刪除。
4. **OSM tiles**：改用 OpenStreetMap tile server，不依賴 CartoDB dark CDN（PoC 環境網路不穩定）。
5. **sites.yaml 相對路徑**：demo 腳本在 `services/cot-gateway/` 目錄執行，`config/sites.yaml` 正確解析。

### 測試

```
94 passed in 15.51s  (cot-gateway)
ruff: clean
black: clean
```

### 使用方式

```bash
# CoT Gateway + EchoShield + Sentrycs + UDS demo
bash scripts/demo-cot-gateway-map.sh

# 停止
bash scripts/demo-cot-gateway-map.sh --stop

# 開啟地圖
open http://127.0.0.1:18091/map
```

