# Feature Specification: EchoShield Simulator

**Feature Branch**: `003-echoshield-sim`
**Created**: 2026-04-23
**Status**: Draft
**Input**: 感測層雷達模擬器；以 10 Hz 從 Map Sim `GET /objects` 取得範圍內物件，加入雷達誤差後以 TCP JSON Feed（:9000）供 CoT Gateway EchodyneAdapter 使用。

---

## 概述

EchoShield Simulator 是 PoC 感測層的**雷達模擬器**，取代真實 EchoShield® 4D Radar 硬體，使 CoT Gateway
的 EchodyneAdapter 在無硬體環境下能以相同 wire protocol 運作。

它的唯一資料源是 Map Simulator（`GET /objects`），作為「在特定地理位置上以一支雷達觀察世界」的角色：
以固定 10 Hz 對雷達安裝點（`sensor_lat/lon`）與最大偵測距離（預設 4800m）查詢範圍內無人機，加入雷達特性
模擬（位置噪點、速度噪點、方位角 / 仰角幾何），再以 asyncio TCP Server（:9000）將每筆航跡以換行分隔
JSON 廣播給所有已連線的 Client（EchodyneAdapter）。

本模組**不負責**物件追蹤狀態管理的下游語義（如 CoT type、融合）——這些由 CoT Gateway 處理。本模組
**只**負責「雷達看到什麼 → 輸出雷達級的 track」。

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - CoT Gateway 透過 TCP 接收 10 Hz 雷達航跡 (Priority: P1)

CoT Gateway 的 EchodyneAdapter 啟動後連接至 EchoShield Simulator 的 `TCP :9000`，持續收到每 100ms 一批
的 EchoShield JSON 航跡（換行分隔）。對 Adapter 而言，Simulator 與真實硬體在 wire protocol 層完全一致：
同樣的 port、同樣的 JSON schema、同樣的推送節奏。

**Why this priority**: 這是 Simulator 存在的根本目的——讓 Gateway 在沒有硬體的情況下仍能跑完整個資料鏈
（Sensor → Gateway → TAK）。沒有這項，整個 PoC 無法 demo。

**Independent Test**: 使用 `nc localhost 9000`（或一個測試用的 TCP Client）連線，驗證 ≥10 秒內以 10 Hz
收到合法 JSON 行、每行符合 EchoShield schema，即完成本故事的驗證，不需要真的啟動 Gateway。

**Acceptance Scenarios**:

1. **Given** Simulator 已啟動且 Map Sim 內有 1 架無人機位於雷達範圍內，**When** 測試 Client 連線至
   `:9000`，**Then** Client 在 1.0s 內至少收到 8 筆 JSON 行（10 Hz × 1s，容忍初期抖動），每行以 `\n` 結尾，
   且為合法 UTF-8 JSON 物件。
2. **Given** 同上，**When** Client 連線並讀取 5 秒，**Then** 所有訊息皆帶有 `track_id` / `latitude` /
   `longitude` / `altitude_m` / `velocity_ms` / `azimuth_deg` / `elevation_deg` / `timestamp` /
   `track_status` / `classification` 欄位，且型別符合 §Key Entities。
3. **Given** 一個已連線的 Client，**When** 該 Client 主動關閉 TCP 連線，**Then** Simulator 將該 writer
   從廣播名單移除且不影響其他 Client，且後續對該 socket 的寫入不會造成 Simulator 進程崩潰。

---

### User Story 2 - 雷達範圍內物件查詢（過濾 is_lost，不覆寫 status）(Priority: P1)

Simulator 以固定頻率（預設 10 Hz）向 Map Sim 發送 `GET /objects?lat={sensor_lat}&lon={sensor_lon}&
radius_m={max_range_m}`，取得「雷達視野內」的無人機集合，並作為當輪廣播的輸入。Map Sim 契約
（`specs/002-map-sim/contracts/rest-api.md` §3.2）保證：

- `include_lost` 未帶時預設 `false` → 已逾 `ttl_warn` 的 `is_lost=true` 物件**不**出現在回應中。
- `objects[].status` 為 UDS 原始字串（`FLYING_NORMAL` / `LANDING` / `LANDED` / …），**絕不**被 Map Sim
  改寫為 `"lost"`；`is_lost` 是獨立布林欄位。
- 回應物件**已**按 `distance_m` 升冪排序、且已由 Map Sim 以 haversine 過濾至 `radius_m` 內。

Simulator **不**加 `include_lost=true`，因此它看到的就是「雷達目前能偵測到的」物件。Simulator
**不得**自行重新過濾距離（避免與 Map Sim 的 haversine 結果產生偏差），但 **MAY** 基於 `status` 或
`is_lost` 做額外降級處理（見 FR-ES-012）。

**Why this priority**: 這是「雷達看到的世界」的唯一來源；若取不到或取錯，下游所有輸出都是錯的。必須與
Story 1 並列 P1，否則 Gateway 雖然能連線但永遠看不到目標。

**Independent Test**: 可獨立測試——以假的 Map Sim stub server 回傳已知 `objects[]`，驗證 Simulator
以正確 URL / query 參數查詢、並在下一次廣播中含有對應筆數。

**Acceptance Scenarios**:

1. **Given** Map Sim 回傳 `{"count": 2, "objects": [A, B]}`，**When** Simulator 完成一輪處理，**Then**
   該輪廣播至所有 Client 的 JSON 行恰為 2 筆（Active），分別對應 A、B（以 drone_id → track_id 穩定映射）。
2. **Given** Map Sim 回傳 `{"count": 0, "objects": []}`，**When** 輪到下一次廣播，**Then** Simulator
   **不**送出任何 JSON 行（「安靜模式」），且 TCP 連線保持健康。
3. **Given** 某 `drone_id` 上一輪存在、這一輪已從 Map Sim 回應中消失（例如離開範圍或被 Map Sim TTL
   過濾），**When** 當輪廣播，**Then** Simulator 為該 drone_id 額外發出**一筆** `track_status: "Lost"`
   的 JSON 行，之後不再為該 drone_id 廣播，且下次若該 drone_id 重新出現，Simulator 分配**新**的 `track_id`。

---

### User Story 3 - 雷達誤差模擬與幾何計算 (Priority: P2)

Simulator 將 Map Sim 的精確真實位置，轉換為「雷達量測值」：

- **位置噪點**：`(lat, lon)` 疊加 σ=5m 的二維 Gaussian 誤差；`alt_m` 疊加 σ=2m。
- **速度噪點**：`speed_ms` 疊加 σ=0.5 m/s 的 Gaussian 誤差，並 clamp 至 `>= 0`。
- **方位角**：以雷達安裝位置為原點，計算至目標的大圓 bearing（正北 0°，順時針，範圍 `[0, 360)`）。
- **仰角**：以 `atan2(alt_diff, horiz_dist)`（horiz_dist = haversine），範圍 `[-90, 90]`；水平距離 < 1m
  時退化為 ±90°。

**Why this priority**: 這是「為什麼需要 Simulator 而不是直接轉發 Map Sim」的核心——下游融合演算法
（TrackCorrelator）需要看到帶誤差的雷達資料，才能驗證與 RF 資料（Sentrycs）的關聯閾值（50m）。但相較
於 Story 1/2，此故事可以用固定噪點（甚至暫時關閉噪點）先出第一版，對端對端 demo 影響較小。

**Independent Test**: 可獨立用單元測試驗證——固定 `random.seed`，以已知雷達位置與已知目標位置呼叫
RadarProcessor，驗證 azimuth / elevation 在理論值的 ±0.1° 內、位置偏移符合 Gaussian 分布。

**Acceptance Scenarios**:

1. **Given** 雷達位於 `(24.0, 121.0, 10m)`，目標位於**正北**方向 1 km、同高度 10m，**When** 呼叫
   RadarProcessor 關閉噪點，**Then** `azimuth_deg` ≈ 0.0°（±0.1°）、`elevation_deg` ≈ 0.0°（±0.1°）。
2. **Given** 雷達位於地表、目標在正上方 100m（水平距離 < 1m），**When** 處理，**Then** `elevation_deg`
   = 90.0°（不得出現 NaN 或除以零例外）。
3. **Given** 相同輸入重複執行 10,000 次（噪點開啟），**When** 統計輸出 `latitude` 偏移值，**Then** 樣本
   標準差在 `[4.0m, 6.0m]` 區間內（σ=5m 的合理容忍）。

---

### Edge Cases

- **Map Sim 暫時不可用**（連線被拒 / 5xx / timeout > 1s）：Simulator **MUST** 在該輪靜默跳過廣播，
  記錄一筆 WARNING log，並於下一個 100ms tick 重試。**不得**因此退出進程、也**不得**關閉現有 TCP Client
  連線。連續失敗時 log 應節流（例如每秒最多一行），避免洗版。
- **Map Sim 回應延遲超過 100ms tick**：當輪超時則放棄該筆結果；下一 tick 正常發起新查詢。**不得**累積
  併發查詢（每輪最多一個 in-flight 請求）。
- **Map Sim 回 `is_lost=true` 的物件**：在預設 `include_lost=false` 下不會出現；若未來呼叫方自行帶
  `include_lost=true` 造成回應含 `is_lost=true`，Simulator **MUST**（為與預設行為一致）將其視為「不可見」
  並觸發該 drone_id 的 Lost 事件（見 FR-ES-012）。
- **TCP Client 斷線**：writer 從廣播名單移除，其他 Client 不受影響。當新 Client 連線時立即納入下一輪
  廣播，**不**回放歷史資料（每位 Client 從當下時刻開始）。
- **多個 TCP Client 同時連線**：所有 Client 收到**相同的** JSON 行內容（broadcast fan-out）；每輪僅產生
  一組航跡（同一組噪點 / 時間戳），廣播時複製 bytes 給每個 writer。
- **物件剛 LANDED**（UDS 推送 `status: "LANDED"`）：Map Sim 仍回傳該物件（只要尚未逾 `ttl_warn`），
  Simulator 會把它當作一般 Active 目標輸出；其 `track_status` 仍為 `"Active"`（雷達看不見 `status` 字串
  語義，它只看是否仍在回應中）。當 UDS 停止推送而 Map Sim 因 TTL 過濾掉後，Simulator 即按 Story 2 AC 3
  發送一筆 `track_status: "Lost"` 並釋放 `track_id`。
- **目標在同一 tick 內短暫消失又出現**（例如 Map Sim 一次 5xx）：被視為同一 drone_id 的 Lost → Active
  序列，Simulator 在 Lost 後會為下次出現重新分配 `track_id`（與 4.1.1 下游對 Lost 的處理一致）。
- **雷達範圍內同時 > 20 個目標**：PoC 不保證正確性（見 Assumptions），但 Simulator **不得**崩潰；
  超量時仍應持續輸出（例如按 Map Sim 距離排序前 N 筆，或全部輸出，由實作選擇）。

---

## Requirements *(mandatory)*

### Functional Requirements

#### 查詢與主迴圈

- **FR-ES-001**：Simulator **MUST** 以 `update_rate_hz`（預設 10 Hz）為週期驅動主迴圈；每次 tick 觸發一次
  Map Sim 查詢 + 一次廣播。
- **FR-ES-002**：每次 tick **MUST** 對 Map Sim 發送 `GET {map_sim_url}/objects?lat={sensor_lat}&
  lon={sensor_lon}&radius_m={max_range_m}`；**MUST NOT** 帶 `include_lost` 參數（使用 Map Sim 預設 false）。
- **FR-ES-003**：Map Sim 查詢 timeout **MUST** ≤ 1.0s；timeout / 連線失敗 / 非 2xx 回應時，當輪視為
  「查詢失敗」並跳過處理，但主迴圈 **MUST** 繼續下一 tick（不退出、不關閉 TCP Server）。
- **FR-ES-004**：同時最多只有一個 in-flight Map Sim 請求；若前一個請求尚未完成而下一 tick 到期，當輪
  **MUST** 直接跳過（不累積併發）。

#### 輸出格式

- **FR-ES-005**：每筆航跡 **MUST** 輸出為單行 JSON + `\n`（UTF-8），欄位同 §Key Entities `RadarTrack`。
  `track_id` 格式為 `echo-{8-hex}`（由 uuid4 前 8 位產生）。
- **FR-ES-006**：每筆 `timestamp` **MUST** 為當次處理時間（以 Simulator 主機 UTC 時鐘為準），格式
  `YYYY-MM-DDTHH:MM:SS.sssZ`（毫秒精度、`Z` 後綴）。**不得**回傳 Map Sim 的原始 timestamp。
- **FR-ES-007**：`classification` **MUST** 為固定字串 `"UAV"`（EchoShield 硬體無型號識別能力）。
- **FR-ES-008**：`track_status` 僅取 `"Active"` 或 `"Lost"` 二者（首字大寫）。本規格與 doc 08 ICD-001
  的 `NEW/UPDATED/LOST` 不一致，以本規格為準（見 Assumptions）。

#### Track 生命週期

- **FR-ES-009**：對每個 `drone_id`，首次出現在 Map Sim 回應時 Simulator **MUST** 分配一個新的 `track_id`
  並於該 drone_id 仍在回應中期間**保持不變**。
- **FR-ES-010**：當某 drone_id 從「上一輪在回應中」變為「這一輪不在回應中」時，Simulator **MUST** 於
  當輪**額外**輸出一筆 `track_status: "Lost"` 的 JSON（可沿用最後一次已知位置，但 `timestamp` 為當下），
  之後釋放該 drone_id 的 `track_id` 映射；若之後該 drone_id 再次出現，Simulator **MUST** 分配新的
  `track_id`（不復用）。
- **FR-ES-011**：當本輪 Map Sim 回應中無任何物件且上一輪亦無 → 安靜模式：**MUST NOT** 送出任何 bytes。
  若上一輪有物件、本輪無 → 僅送出該輪的 Lost 行。

#### `is_lost` / `status` 語義（與 Map Sim §3.2 一致）

- **FR-ES-012**：Simulator **MUST NOT** 使用 Map Sim 回應的 `objects[].status` 字串來影響輸出（不對
  `"LANDED"` 等做特殊處理——雷達只知道「看到 / 沒看到」）。若某回應中出現 `is_lost=true`（僅在呼叫方
  自行改為 `include_lost=true` 時可能發生，本規格預設不帶），Simulator **MUST** 把該物件視為「不在
  回應中」（即等同 FR-ES-010 的消失情境）。

#### TCP Feed Server

- **FR-ES-013**：Simulator **MUST** 於 `feed_host:feed_port`（預設 `0.0.0.0:9000`）啟動 asyncio TCP
  Server；**MUST** 支援 ≥ 2 個 Client 同時連線；所有 Client 收到相同的每輪 JSON 行內容。
- **FR-ES-014**：Client 斷線（EOF / write error / reset）**MUST**：(a) 被 Simulator 偵測並從廣播名單
  移除；(b) 不影響其他 Client；(c) 不使主迴圈中斷。
- **FR-ES-015**：新 Client 連線 **MUST** 立即加入廣播名單，從下一輪開始接收；Simulator **MUST NOT**
  回放任何歷史資料。
- **FR-ES-016**：當無任何 Client 連線時，主迴圈 **MUST** 仍然執行（繼續查詢 Map Sim、產生航跡），但
  **MAY** 跳過實際 socket 寫入（等價於沒有接收端）。

#### 雷達特性模擬

- **FR-ES-017**：位置噪點 **MUST** 為獨立 Gaussian，`sigma_lat_lon = position_noise_m`（預設 5m，
  以 `111320` m/deg 換算至經緯度）、`sigma_alt = 2m`。
- **FR-ES-018**：速度噪點 **MUST** 為 Gaussian σ = `velocity_noise_ms`（預設 0.5 m/s），輸出 **MUST**
  clamp 至 ≥ 0。
- **FR-ES-019**：方位角與仰角計算 **MUST** 使用加過噪點的目標位置為輸入（與「雷達量測值」一致）；
  方位角範圍 `[0, 360)`，仰角範圍 `[-90, 90]`。
- **FR-ES-020**：水平距離 < 1m 時 `elevation_deg` **MUST** 為 `+90.0`（目標在雷達上方）或 `-90.0`
  （下方），不得拋出例外。

#### 設定與 CLI

- **FR-ES-021**：所有可調參數（`sensor_lat/lon/alt_m`、`max_range_m`、`update_rate_hz`、
  `position_noise_m`、`velocity_noise_ms`、`map_sim_url`、`feed_host`、`feed_port`）**MUST** 可由 YAML
  設定檔配置。
- **FR-ES-022**：CLI **MUST** 支援 `--config <path>`（必要）與 `--verbose`（選填，啟用 DEBUG 日誌）。

### Key Entities

- **RadarConfig**：雷達的「安裝參數 + 模擬參數」。
  - 安裝：`sensor_lat`（WGS84 緯度）、`sensor_lon`（WGS84 經度）、`sensor_alt_m`（安裝高度，公尺 HAE）。
  - 偵測：`max_range_m`（最大偵測距離，公尺；預設 4800，對應 Group 1；支援 6400 / 11400 等任意值）、
    `update_rate_hz`（預設 10）。
  - 噪點：`position_noise_m`（σ，預設 5.0）、`velocity_noise_ms`（σ，預設 0.5）。
  - 上下游：`map_sim_url`（預設 `http://localhost:8090`）、`feed_host` / `feed_port`（預設 `0.0.0.0:9000`）。

- **RadarTrack**（EchoShield JSON 輸出的單筆航跡）。
  - `track_id`：string，格式 `echo-{8-hex}`，於單次 Active 生命週期內穩定。
  - `latitude` / `longitude`：number，WGS84 度，含噪點，分別 7 位小數。
  - `altitude_m`：number，公尺 HAE，含噪點，1 位小數。
  - `velocity_ms`：number，地速 m/s，含噪點 + `max(0, …)` clamp，2 位小數。
  - `azimuth_deg`：number，`[0, 360)`，2 位小數。
  - `elevation_deg`：number，`[-90, 90]`，2 位小數。
  - `timestamp`：string，ISO 8601 UTC 毫秒（`Z` 後綴）。
  - `track_status`：string，`"Active"` | `"Lost"`。
  - `classification`：string，固定 `"UAV"`。

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-ES-001（輸出頻率）**：當 Map Sim 內有 ≥ 1 個範圍內物件且主迴圈穩定後，連續觀察 10 秒內每個活躍
  `track_id` 收到的 JSON 行數 **MUST** 落在 `[90, 110]` 區間（10 Hz × 10s，±10% 容忍）。
- **SC-ES-002（端對端延遲）**：從 Map Sim 返回 `objects` 到對應 JSON bytes 寫入所有 Client socket 的
  時間差（不含網路傳輸）**MUST** 在 95 百分位下 ≤ 10ms。
- **SC-ES-003（範圍過濾精度）**：給定 10 個分布於雷達 0.1–10 km 的合成目標，當 `max_range_m = 4800`
  時輸出的 `track_id` 集合 **MUST** 恰為 Map Sim 以相同 `radius_m=4800` 查詢所回的 `drone_id` 集合
  （Simulator **不**自行重新以距離過濾）。
- **SC-ES-004（位置噪點幅度）**：關閉速度 / 角度驗證、對同一靜止目標連續取樣 10,000 次，輸出 `latitude`
  與 `longitude` 各自轉為公尺的樣本標準差 **MUST** 落在 `[4.0, 6.0]` m（σ=5m 的合理實測區間）。
- **SC-ES-005（方位角精度）**：雷達位於 `(24.0, 121.0, 10m)`、目標於正北 / 正東 / 正南 / 正西各 1 km，
  關閉噪點時 `azimuth_deg` **MUST** 與理論值（0° / 90° / 180° / 270°）誤差 < 0.1°。
- **SC-ES-006（仰角精度）**：雷達於地表、目標於同經緯度上空 100m，關閉噪點時 `elevation_deg`
  **MUST** = 90.0°（±0.01°）。
- **SC-ES-007（TCP 並行）**：同時 3 個 Client 連線並讀取 5 秒，**MUST** 每個 Client 收到相同內容且
  行數差距 ≤ 1（允許最後一行 buffering 差）。
- **SC-ES-008（Client 斷線隔離）**：3 個 Client 連線後關閉其中 1 個，其餘 2 個 **MUST** 於 1 秒內仍
  持續收到下一輪廣播，且 Simulator 進程未崩潰、主迴圈仍在 10 Hz 運行。
- **SC-ES-009（Map Sim 不可用恢復）**：阻斷 Map Sim（例如 kill 或 firewall）持續 3 秒後恢復，Simulator
  **MUST** 在恢復後的下一 tick（≤ 100ms）恢復正常廣播，且阻斷期間主迴圈未退出。
- **SC-ES-010（Lost 事件）**：某 drone_id 從 Map Sim 回應消失，Simulator **MUST** 在該事件發生的**下一
  輪廣播**中恰發出 1 筆 `track_status: "Lost"`，之後至該 drone_id 重新出現前 **MUST** 不再為其廣播任何
  JSON 行。
- **SC-ES-011（空結果靜默）**：Map Sim 連續 5 秒回 `count=0`，Simulator **MUST** 在 TCP Socket 上不送
  任何 bytes（連線保持開啟）。
- **SC-ES-012（資源）**：長時間（≥ 1 小時）在 3 個目標 + 1 個 Client 情境下運行，進程常駐記憶體
  **MUST** < 100 MB、無持續上升趨勢（無記憶體洩漏）。

---

## Assumptions

- **主要來源**：本規格以 `docs/system-docs/04-echoshield-simulator-spec.md` 為主要來源。當 04 規格與
  `docs/system-docs/08-api-icd.md`（ICD-001）衝突時（例如欄位名稱 `latitude` vs `lat`、`track_status`
  取值集合 `Active/Lost` vs `NEW/UPDATED/LOST`），**以 04 為準**；ICD-001 的差異留待後續介面對齊
  工作項處理（out of scope for 003）。
- **Map Sim 契約**：`GET /objects` 遵循 `specs/002-map-sim/contracts/rest-api.md` §3.2，特別是
  (a) `objects[].status` 永不被 Map Sim 覆寫為 `"lost"`、(b) `is_lost` 為獨立布林欄位、
  (c) 預設 `include_lost=false`、(d) 已按 `distance_m` 升冪排序。
- **時鐘**：`timestamp` 以 Simulator 主機 UTC 時鐘為準；PoC 階段不考慮多主機時鐘偏差。
- **目標數量上限**：PoC 場景同時 ≤ 5 架無人機；超過 20 時正確性不保證（但進程仍不得崩潰）。
- **網路**：Simulator 與 Map Sim、Gateway 均位於同一主機；TCP / HTTP 皆為明文、無 SSL、無認證。
- **無持久化**：Simulator 完全無狀態持久化；重啟後所有 `track_id` 映射丟失，下游（Gateway）應能容忍
  `track_id` 重新分配。
- **安靜模式**：無目標時不送任何 bytes，包含不送空行 / keepalive；依賴 TCP 連線本身維持存活（Gateway
  若需 liveness，應由 Gateway 端 timeout 機制負責）。

## Out of Scope

- 真實雷達的電磁特性模擬：RCS / SNR / 波束成形 / 副瓣 / 多徑（04 §1.2 已明列）。
- 地形遮蔽、大氣折射、氣象衰減。
- 多雷達融合 / 多感測器配置（本模組假設單一雷達安裝點）。
- Track ID 在 Simulator 重啟後的持久化與復原。
- 雷達誤差的進階統計模型（如距離相關的誤差放大、方位相關誤差）——僅使用單一 σ Gaussian。
- TCP 連線的認證 / 授權 / 加密（PoC 明文，生產由硬體提供）。
- 對 `status` 字串（`LANDING` / `LANDED` / `MITIGATING_TAKEOVER`）的差異化輸出語義——本模組忽略
  `status`，只看「是否在 Map Sim 回應中」。
- CoT type / 融合 / 關聯邏輯——屬 CoT Gateway 職責（features 004+）。
- `snr_db` / `rcs_dbsm` 等 ICD-001 選填欄位——本規格不輸出（見 Assumptions 第 1 點）。
