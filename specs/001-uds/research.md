# Phase 0 — Research: UDS 技術選型摘要

> 目的：解決 `plan.md` Technical Context 中的決策，記錄「選什麼／為何選／放棄了什麼」。本 PoC 的
> spec 已完整 clarify（見 `spec.md` §Clarifications），故沒有殘留 `NEEDS CLARIFICATION`；本檔案補充
> **技術選型面** 的決策。

---

## 1. 語言與執行環境

- **Decision**：Python **3.11+**。
- **Rationale**：
  - 需要 `asyncio.TaskGroup`、`asyncio.timeout()` 來安全地管理主迴圈、aiohttp server、per-drone push workers
    的生命週期（Python 3.11 內建）。
  - 與 `docs/system-docs/02-unified-drone-simulator-spec.md` §9 的程式碼例示保持同一語言。
  - 型別註記 + `dataclass(slots=True)` 有助於降低每週期 100 次物件存取的開銷。
- **Alternatives considered**：
  - Go 1.22：效能更佳，但與 PoC 其他 Python 服務語言不一致，提高維運成本。
  - Python 3.10：缺 `TaskGroup` / `asyncio.timeout()` 會使錯誤傳播更囉嗦。

## 2. 並行模型

- **Decision**：**單行程 + 單 asyncio 事件迴圈**。主迴圈、HTTP server、HTTP client push 全部 co-routine。
- **Rationale**：
  - 100 req/s（10 架 × 10 Hz）屬 I/O-bound，在單核 asyncio 下綽綽有餘。
  - 狀態機共用記憶體：避免跨執行緒 / 跨行程的同步原語（spec 要求「下一個主迴圈週期前切換狀態」，單迴圈最易達成）。
- **Alternatives considered**：
  - 多 thread（`concurrent.futures.ThreadPoolExecutor`）：引入 GIL 與 aiohttp loop-per-thread 問題，收益低。
  - 多進程（每架一個 worker）：狀態同步成本過高、違反「single source of truth」設計初衷。

## 3. HTTP 疊：Server + Client 共用 `aiohttp`

- **Decision**：`aiohttp` ≥ 3.9。Server 用 `aiohttp.web`；Client 用單一 `aiohttp.ClientSession` 全程共用。
- **Rationale**：
  - `ClientSession` 內建連線池 + HTTP keep-alive；10 架 × 10 Hz 可重用同一條 TCP 連線至 Map Simulator。
  - Server 端可直接與 asyncio 迴圈整合（`asyncio.run_app` 或以 `AppRunner` 手動掛載至主迴圈），
    不需再引入 `uvicorn` + `FastAPI` 的 ASGI 層。
  - `aiohttp.test_utils` 提供 `TestServer` / `TestClient`，契約測試直接跑 in-process。
- **Alternatives considered**：
  - FastAPI + uvicorn + httpx：疊三個框架只為一個 POST 端點，複雜度明顯高於 aiohttp。
  - `httpx.AsyncClient`（僅 client）+ aiohttp server：客戶端多一個依賴、好處不明顯。

### 3.1 背壓策略（per-drone push）

- **Decision**：每架無人機一個 `asyncio.Queue(maxsize=2)`；主迴圈只 `put_nowait(payload)`，
  `QueueFull` 時丟棄「最舊」一筆並記 `push.backpressure` warning。
- **Rationale**：
  - 滿足 Clarification「per-drone、100 req/s、有連線池 + 背壓」；丟舊不丟新符合即時模擬語意
    （最新位置比舊位置有價值）。
  - `LANDED` 的收尾訊息以「同 queue 最後一筆 + 設 sentinel（停推 flag）」實現，不另開額外 queue。
- **Alternatives considered**：
  - Batch push：被 spec Clarification 明確否決。
  - 單一全域 queue + round-robin worker：LANDED 收尾需跨 drone 辨識，複雜度上升。

## 4. 場景 YAML 驗證

- **Decision**：`PyYAML`（載入）+ `pydantic v2`（schema 驗證）。
  - `timeline[].action: Literal["start_flying"]` 實現封閉白名單。
  - `ScenarioLoader` 在 `ValidationError` 時列印人類可讀錯誤、`sys.exit(2)`，主迴圈與 HTTP server 皆不啟動。
- **Rationale**：
  - Clarification 明確要求 fail-fast；`Literal` + pydantic 能自然產生 `unknown action: <value>` 等訊息。
  - pydantic 同時驗證 `update_hz ∈ [1, 20]`、`start_lat ∈ [-90, 90]` 等值域，與 `POST /command/takeover`
    的 request 驗證共用同一套工具鏈。
- **Alternatives considered**：
  - `jsonschema`：沒有 Python native object 輸出，需再手動 dataclass 轉換。
  - 自刻 validator：維護成本高、錯誤訊息不統一。

## 5. 地理計算（WGS84 球面）

- **Decision**：自實作 `haversine_m(a, b)`、`bearing_deg(a, b)`、`offset_wgs84(a, bearing_deg, distance_m)`；
  地球半徑 `R = 6_371_000.0 m`（與 spec FR-UDS-012 對齊）。`geopy.distance.distance` 僅用於**單元測試交叉驗證**。
- **Rationale**：
  - 確保 SC-008 重現性（純公式、無隨機性、無外部資料庫依賴）。
  - 公式量少且標準，避免引入對 `geopy` 內部版本的耦合；測試階段比對 `geopy` 可抓實作錯誤。
- **公式**：
  - **Haversine 距離**（公尺）：
    ```text
    Δφ = φ₂ − φ₁
    Δλ = λ₂ − λ₁
    a  = sin²(Δφ/2) + cos φ₁ · cos φ₂ · sin²(Δλ/2)
    c  = 2 · atan2(√a, √(1−a))
    d  = R · c
    ```
  - **Initial bearing（forward azimuth，正北順時針 0–360°）**：
    ```text
    y = sin Δλ · cos φ₂
    x = cos φ₁ · sin φ₂ − sin φ₁ · cos φ₂ · cos Δλ
    θ = atan2(y, x)         # 弧度
    bearing = (deg(θ) + 360) mod 360
    ```
  - **Destination point（給 bearing + 距離算目標座標）**：
    ```text
    δ = d / R
    φ₂ = asin( sin φ₁ · cos δ + cos φ₁ · sin δ · cos θ )
    λ₂ = λ₁ + atan2( sin θ · sin δ · cos φ₁,
                     cos δ − sin φ₁ · sin φ₂ )
    ```
  - 所有 φ / λ / θ 計算前轉弧度、回傳前轉度；`λ` 結果以 `((λ + 540) mod 360) − 180` 規整到 `[-180, 180]`。
- **平滑轉向（FR-UDS-013）**：每週期 heading 變化量 clamp 在 ±30°；差值以 `((diff + 540) mod 360) − 180`
  回到 `[-180, 180]` 後 clamp。
- **Alternatives considered**：
  - 直接用 `geopy.distance.geodesic`（橢球體，Vincenty）：比 Haversine 精準 0.5%，但 Spec §5 Assumptions
    已選用球面近似，且 Vincenty 在極端緯度有收斂問題。
  - `pyproj`：大依賴、需要 C 擴充，對 PoC 過重。

## 6. 可觀測性（Logging）

- **Decision**：`structlog` ≥ 24.1，JSON renderer、stdlib logging bridge；`--verbose` 切 DEBUG。
- **Rationale**：per-drone push 成功/失敗、狀態轉移、takeover 接收皆需結構化欄位（`drone_id`、
  `flight_state`、`http_status`、`latency_ms`）以便 PoC 展示時即席查錯。
- **Alternatives considered**：
  - `logging` 原生 + 自刻 formatter：欄位容易遺漏、PR review 成本高。
  - `loguru`：stdlib 整合較麻煩，aiohttp access log 不易接。

## 7. 測試框架

- **Decision**：`pytest` ≥ 8.0、`pytest-asyncio` ≥ 0.23（`asyncio_mode = "auto"`）、
  `aiohttp.test_utils.TestServer`（fake Map Simulator）、`freezegun`（積分重現性）。
- **Rationale**：
  - 契約測試可直接 in-process，不需要跑真實 :8080。
  - `TestServer` 在同 loop 內啟動，fake Map Simulator 回 200/500/timeout 可覆蓋 FR-UDS-014 容錯路徑。
  - `freezegun` 搭配注入 `clock()` 函數可重現 SC-008（同場景兩次執行、位置差 ≤ 1 m）。
- **Alternatives considered**：
  - `unittest`：async 支援弱、fixture 體系不便。
  - `hypothesis`：對 geo 公式很適合，可在 unit test 選擇性加入；非必要。

## 8. 依賴版本彙整

| 用途 | 套件 | 最低版本 |
|------|------|---------|
| Async runtime | （stdlib） | Python 3.11 |
| HTTP server + client | `aiohttp` | 3.9 |
| YAML 載入 | `PyYAML` | 6.0 |
| Schema 驗證 | `pydantic` | 2.6 |
| 地理計算交叉驗證（測試） | `geopy` | 2.4 |
| 結構化日誌 | `structlog` | 24.1 |
| 測試 | `pytest`, `pytest-asyncio`, `freezegun` | 8.0 / 0.23 / 1.4 |

---

**Outcome**：所有技術決策鎖定，無殘留 `NEEDS CLARIFICATION`；可進入 Phase 1 設計。
