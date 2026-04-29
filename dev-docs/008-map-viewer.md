# 008-map-viewer — Leaflet.js Browser Map Viewer for Map Sim

## 概述

為 Map Simulator 新增 `GET /map` 端點，提供瀏覽器可直接開啟的 Leaflet.js 即時地圖。地圖每 3 秒輪詢 `/objects/all`，自動顯示所有無人機位置、狀態、完整資訊，並附示範啟動腳本。

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
# 啟動 demo
bash scripts/demo-map-viewer.sh

# 停止 demo
bash scripts/demo-map-viewer.sh --stop

# 直接開發測試（需先啟動 map-sim）
open http://127.0.0.1:8090/map
```
