# 功能規格：地圖模擬器（Map Simulator, Map Sim）

**Feature Branch**: `002-map-sim`
**Created**: 2026-04-25
**Status**: Draft
**Input**: 為反無人機 TAK 戰術感知 PoC 建立感測層的**物件狀態中央登錄表（Central Object Registry）**：接收 Unified Drone Simulator（UDS, 001-uds）對每架活躍無人機每秒推送的 `POST /objects/update`，並以 `GET /objects?lat=&lon=&radius_m=` 提供 EchoShield Simulator（radius 4800 m）與 Sentrycs Simulator（radius 8000 m）地理範圍查詢；以 TTL 機制自動清理停止更新的物件，讓感測器模擬器無需自行維護位置狀態。

---

## 1. 背景與目的

在反無人機 TAK PoC 的三層架構（感測層 → 指管層 → 呈現層）中，感測層由 UDS（無人機真實位置）、EchoShield Simulator（雷達偵測）、Sentrycs Simulator（RF 偵測）三個本機模擬器組成。若讓 EchoShield / Sentrycs 各自向 UDS 查詢位置，會造成：

1. **狀態重複維護**：每個感測器模擬器都必須自行保存所有無人機最新位置、自行實作 TTL、自行處理 UDS 推送節奏。
2. **感測器耦合無人機真實位置來源**：未來若要新增感測器（如 ADS-B、光電），必須各自再接一次 UDS。
3. **查詢邏輯重複**：「圓形範圍內有哪些物件」這個共通需求被每個感測器重寫一次。

**Map Simulator（Map Sim）** 作為感測層的中央物件登錄表解決上述問題：

- **接收端**：UDS 每個主迴圈週期對每架 `flight_state ≠ IDLE` 的無人機各推送一筆 `POST /objects/update`（per-drone 粒度，依 `08-api-icd.md` §3.1 與 `dev-docs/001-uds.md` §七 已落地的 8 欄位 payload）。
- **查詢端**：EchoShield / Sentrycs Simulator 各自以 `GET /objects?lat=&lon=&radius_m=` 取得感測器位置周圍範圍內的所有活躍物件，附帶 `distance_m` 與 `last_seen_s`。
- **TTL 管理**：Map Sim 為每個 `drone_id` 維護 `last_seen_at`；超過 `ttl_warn_s`（預設 5 s）未更新的物件在預設查詢中視為 `lost`；超過 `ttl_remove_s`（預設 10 s）未更新則從登錄表移除。感測器模擬器不再需要實作 TTL。

**架構定位（對齊 `01-system-architecture.md` 與 `03-map-simulator-spec.md` §1.2）**：

```
UDS（:18080）
  │ POST /objects/update（per-drone, ~10 Hz）
  ▼
Map Simulator（:18090, 本 feature）
  ▲                       ▲
  │ GET /objects?radius=  │ GET /objects?radius=
  │    4800（radar）      │    8000（RF）
EchoShield Sim         Sentrycs Sim
```

> **介面契約基準（必讀）**：
> - `POST /objects/update` request body 以 **UDS 已實作的 8 欄位** 為準：`drone_id / lat / lon / alt_m / speed_ms / heading_deg / status / timestamp`（見 `dev-docs/001-uds.md` §七、`specs/001-uds/contracts/rest-api.md` §3.2）。Map Sim **不得**強制要求 `model` / `operator_lat` / `operator_lon` 等 Sentrycs 專屬欄位；這些欄位屬於 Sentrycs Simulator 的內部擴充（`08-api-icd.md` §3.2 的 Sentrycs schema），不是 UDS → Map Sim 的契約。
> - `status` 值域為 UDS FlightState 字串 `{FLYING_NORMAL, MITIGATING_TAKEOVER, LANDING, LANDED}`；`IDLE` 永不出現（UDS 側已過濾，見 `specs/001-uds/contracts/rest-api.md` §3.2）。
> - UDS 進入 `LANDED` 的那一個 tick 會推送**恰一筆**最後狀態後停推（`specs/001-uds/contracts/rest-api.md` §3.4）；Map Sim 的 TTL 清理必須能讓下游查詢在合理時間內看不到這個 `drone_id`。

---

## Clarifications

### Session 2026-04-24

- Q: `GET /objects` 回應中，物件在進入 `[ttl_warn_s, ttl_remove_s)` lost 區間時，`status` 欄位應如何呈現？ → A: 保留原始 FlightState 值（如 `LANDED`、`FLYING_NORMAL`）不被覆寫；另以獨立布林欄位 `is_lost` 表達 TTL 狀態：當 `last_seen_s ≥ ttl_warn_s` 時為 `true`，否則 `false` 或省略。

---

## 2. User Scenarios & Testing *(mandatory)*

### User Story 1 — UDS 推送無人機狀態（Priority: P1）

UDS 作為無人機真實位置的 Single Source of Truth，每個主迴圈週期對每架活躍無人機呼叫一次 `POST /objects/update`，將最新位置與飛行狀態寫入 Map Sim 的物件登錄表。

**Why this priority**：整個 PoC 的資料流起點。若 Map Sim 無法穩定接收 UDS 推送，後續所有感測器、融合、TAK 呈現均無資料可用。

**Independent Test**：啟動 Map Sim（`:18090`），以 `curl` 或簡易腳本重現 UDS 的 8 欄位 payload，反覆呼叫 `POST /objects/update` 後以 `GET /objects/all` 驗證登錄表內容；不需啟動 UDS / EchoShield / Sentrycs。

**Acceptance Scenarios**:

1. **Given** Map Sim 剛啟動、登錄表為空，**When** 以合法 8 欄位 body（`drone_id=TRK-001`、`status=FLYING_NORMAL` 等）呼叫 `POST /objects/update`，**Then** 回傳 **200 OK**，body 包含 `status: "updated"`、`drone_id: "TRK-001"`、`registered_at`（ISO 8601 UTC）；隨後 `GET /objects/all` 必須能看到該物件且 `last_seen_s < 1.0`。
2. **Given** `TRK-001` 已在登錄表（`status=FLYING_NORMAL`），**When** 對同一 `drone_id` 再送一筆 `status=MITIGATING_TAKEOVER`、座標不同的 update，**Then** 回傳 **200 OK**；登錄表中 `TRK-001` 的 `lat/lon/status/timestamp` 全部被最新一筆覆寫（不累積歷史）。
3. **Given** Map Sim 已啟動，**When** request body 缺少必填欄位（如缺 `drone_id`、缺 `speed_ms`），**Then** 回傳 **400 Bad Request**，body 含 `status: "error"`、`reason: "missing required field: <field>"`；登錄表不得有任何變更。
4. **Given** Map Sim 已啟動，**When** request body 包含 UDS 契約以外的欄位（如 `model`, `operator_lat`, `operator_lon`），**Then** Map Sim **必須**仍接受此請求並成功寫入 8 個契約欄位；額外欄位可靜默忽略，不得因此回 400。
5. **Given** UDS 對某 `drone_id` 推送 `status="LANDED"` 後停推（`specs/001-uds/contracts/rest-api.md` §3.4），**When** Map Sim 收到該筆 LANDED 更新，**Then** 登錄表仍保留該物件且 `status=LANDED`，但 `last_seen_at` 會隨時間推移、經 TTL 處理後最終自動消失（見 User Story 3）。

---

### User Story 2 — 感測器模擬器地理範圍查詢（Priority: P1）

EchoShield Simulator（雷達，半徑 4800 m）與 Sentrycs Simulator（RF，半徑 8000 m）以各自的感測器位置為圓心、向 Map Sim 查詢範圍內的活躍無人機，取得統一、一致的位置狀態，作為自身偵測邏輯的輸入。

**Why this priority**：兩個下游感測器模擬器的正式資料來源；若查詢 API 不穩定，EchoShield / Sentrycs 就無法產生正確的偵測資料流給 CoT Gateway。

**Independent Test**：在 Map Sim 已有多架無人機狀態的情境下，以不同 `(lat, lon, radius_m)` 參數呼叫 `GET /objects`，驗證回傳物件集合、`distance_m` 排序、`count` 欄位符合 Haversine 幾何；不需啟動 EchoShield / Sentrycs。

**Acceptance Scenarios**:

1. **Given** 登錄表中有 3 架活躍無人機（距查詢中心分別 1 km / 3 km / 6 km）、`last_seen_s < ttl_warn_s`，**When** 以 `GET /objects?lat=<c_lat>&lon=<c_lon>&radius_m=4800` 查詢，**Then** 回傳 **200 OK**，`count=2`，`objects[]` 依 `distance_m` 由近到遠排序，每筆包含完整 8 欄位加 `distance_m` 與 `last_seen_s`；6 km 外那架不出現。
2. **Given** 登錄表中同一組物件，**When** 以 `radius_m=8000` 查詢（Sentrycs 視角），**Then** 三架全部出現；結果仍按 `distance_m` 由近到遠排序。
3. **Given** 登錄表中沒有任何 `drone_id` 落在查詢圓內（例如查詢中心在地球另一側），**When** 呼叫 `GET /objects?lat=&lon=&radius_m=4800`，**Then** 回傳 **200 OK**、`count=0`、`objects=[]`（**不是 404**）。
4. **Given** 登錄表中某物件的 `last_seen_s > ttl_warn_s` 但 `< ttl_remove_s`（在 lost 區間），**When** 以 `GET /objects?...`（未帶 `include_lost` 或 `include_lost=false`）查詢，**Then** 該物件不出現；**When** 改以 `include_lost=true` 查詢，**Then** 該物件出現，`status` 欄位**保留原始 FlightState 值**（如 `FLYING_NORMAL`、`LANDED`，不被覆寫），並附獨立布林欄位 `is_lost: true` 表達 TTL 狀態。
5. **Given** Map Sim 已啟動，**When** 呼叫 `GET /objects` 但缺 `lat` / `lon` / `radius_m` 任一必填參數，或參數型別無法轉為 float，**Then** 回傳 **400 Bad Request**，`reason` 明確指出缺少/錯誤的參數。
6. **Given** Map Sim 已啟動，**When** `GET /objects?...&radius_m=0` 或 `radius_m=-1`，**Then** 回傳 **400 Bad Request**，`reason` 明確指出 `radius_m must be > 0`（`0` 與負值均視為非法）。

---

### User Story 3 — TTL 自動過期清理（Priority: P1）

當上游（UDS 或其他來源）停止推送某個 `drone_id`（例如該無人機已 `LANDED` 並完成收尾、或 UDS 停機、或物件離開模擬場景）時，Map Sim 自動讓該物件在合理時間後從查詢結果消失，保持登錄表與下游感測器視角的「活著物件」集合清潔。

**Why this priority**：沒有 TTL，下游感測器會看到陳舊的鬼影物件、造成錯誤偵測與錯誤 CoT；且登錄表會持續成長無法回收。

**Independent Test**：對 Map Sim 推送一筆 `drone_id=TRK-099`（任意合法 status）後停止推送；以短 TTL 設定（如 `--ttl-warn-s 1 --ttl-remove-s 2`）執行，並在時間軸上反覆 `GET /objects` 與 `GET /objects/all`，驗證物件依序轉為 lost、最終從登錄表消失。

**Acceptance Scenarios**:

1. **Given** Map Sim 以 `ttl_warn_s=5.0, ttl_remove_s=10.0` 啟動、`TRK-001` 剛以 `FLYING_NORMAL` 寫入，**When** 等待 6 秒且期間沒有新的 update，**Then** `GET /objects?...` 預設（`include_lost=false`）不回傳 `TRK-001`；`GET /objects?...&include_lost=true` 與 `GET /objects/all` 仍可見 `TRK-001`，其 `status` 維持原始值 `FLYING_NORMAL`（**不被覆寫**），並附 `is_lost: true`，且 `last_seen_s ≥ 5.0`。
2. **Given** 同上情境，**When** 再繼續等待直到總計超過 10 秒，**Then** `TRK-001` 必須從登錄表完全消失；`GET /objects/all` 回傳的 `total` 不再包含 `TRK-001`，且無論 `include_lost` 為何，`GET /objects` 都不會回傳。
3. **Given** UDS 對 `TRK-001` 推送最後一筆 `status="LANDED"` 後停推（見 User Story 1 §5），**When** 經過 `ttl_warn_s` 秒，**Then** `TRK-001` 在預設查詢中不再出現；經過 `ttl_remove_s` 秒後從登錄表移除；整段過程不得要求 UDS 主動呼叫 `DELETE /objects/{drone_id}`（DELETE 為選填除錯端點，不是正式清理路徑）。
4. **Given** Map Sim 正在執行背景 TTL 清理，**When** 清理任務移除 N 個過期物件，**Then** 清理動作不得影響同時間進行中的 `POST /objects/update` / `GET /objects` 請求正確性（互斥存取由 `asyncio.Lock` 或等效機制保證，見 FR-MS-007）。

---

### Edge Cases

- **缺必填欄位的 POST**：回 400 `missing required field: <name>`，不寫入登錄表，不觸發 TTL 更新。
- **未知 `drone_id` 的查詢**：`GET /objects?...` 回 200、`count=0`、`objects=[]`；**不得**回 404。Map Sim 不對「查得到/查不到」做語意區分。
- **`radius_m = 0` 或負值**：回 400；不得回 200 且 `count=0`（避免掩蓋呼叫端 bug）。
- **`radius_m` 極大值（如繞地球一圈）**：仍接受，回傳登錄表中所有活躍物件並按距離排序；不得當成錯誤。
- **UDS 重複 `drone_id` 更新**：最新一筆完全覆寫舊值（無合併、無歷史、無版本計數），`last_seen_at` 重設為當下。
- **高頻並發 POST + GET**：在 UDS 推送（10 架 × 10 Hz ≈ 100 req/s）與兩個感測器各自輪詢 `GET /objects`（合計 ~20 req/s）的併發下，讀寫不得互相污染（髒讀、部分更新）。以 `asyncio.Lock` 序列化登錄表存取即足夠（PoC 量級，不需 lock-free）。
- **LANDED 後停推，但 TTL 未到**：該 `drone_id` 仍出現在預設查詢中，`status="LANDED"`、`last_seen_s` 逐步上升；TTL 到期後依 User Story 3 清理。這是期望行為，讓下游感測器有短暫時間觀察到「已降落」事件。
- **`include_lost=true` 的行為**：在 `[ttl_warn_s, ttl_remove_s)` 區間的物件會隨回應出現，`status` 欄位**保留原始 FlightState 值**（如 `FLYING_NORMAL`、`LANDED`，不被覆寫），並以獨立布林欄位 `is_lost=true` 標示 TTL 狀態；超過 `ttl_remove_s` 的物件已從登錄表移除，**無法**再被 `include_lost=true` 救回。
- **非法 `timestamp` 格式**：回 400；Map Sim 以 ISO 8601 UTC（可含 `Z` 或 `+00:00`）為準。解析失敗視為型別錯誤。
- **Map Sim 啟動時登錄表為空**：所有 `GET /objects` 回 200、`count=0`；`GET /health` 回 `registered_objects: 0`。

---

## 3. Requirements *(mandatory)*

### Functional Requirements

（編號與 `03-map-simulator-spec.md` §2 對齊，並擴充本 feature 新增的細節。）

- **FR-MS-001**（接收端）：Map Sim MUST 以 `POST /objects/update` 接收 UDS 推送的無人機狀態，request body 的**契約欄位**為 `drone_id / lat / lon / alt_m / speed_ms / heading_deg / status / timestamp` 等 8 個必填欄位，與 `specs/001-uds/contracts/rest-api.md` §3.2 完全對齊。
- **FR-MS-002**（schema 寬鬆度）：Map Sim MUST NOT 因 request body 包含 8 欄位以外的欄位（如 `model`、`operator_lat`、`operator_lon`、未來擴充欄位）而拒絕請求；額外欄位可靜默忽略或僅記 DEBUG log，**不得**回 400。缺任一必填欄位則 MUST 回 400。
- **FR-MS-003**（地理範圍查詢）：Map Sim MUST 提供 `GET /objects?lat=&lon=&radius_m=&include_lost=` 端點，以 Haversine 距離計算圓形範圍，回傳範圍內符合條件的物件集合；回應 MUST 依 `distance_m` 由近到遠排序、包含 `count` 欄位與每筆物件的 `distance_m`、`last_seen_s`。
- **FR-MS-004**（未命中查詢語意）：當查詢範圍內無任何活躍物件時，Map Sim MUST 回 200、`count=0`、`objects=[]`；**不得**回 404。呼叫端（EchoShield / Sentrycs）以「空陣列」作為正常狀態處理。
- **FR-MS-005**（查詢參數校驗）：`lat` / `lon` / `radius_m` 任一缺漏或無法轉為 float、或 `radius_m ≤ 0` → MUST 回 400 並在 `reason` 欄位明確指出錯誤參數名。
- **FR-MS-006**（TTL 機制）：Map Sim MUST 為每個 `drone_id` 維護 `last_seen_at`；物件 `age_s >= ttl_warn_s` 時，預設查詢（`include_lost=false`）MUST 不回傳該物件；當以 `include_lost=true` 或 `GET /objects/all` 取得該物件時，回應中該物件的 `status` 欄位 MUST **保留原始 FlightState 值**（如 `FLYING_NORMAL`、`MITIGATING_TAKEOVER`、`LANDING`、`LANDED`），**不得**被覆寫為 `"lost"`；TTL 狀態 MUST 以獨立布林欄位 `is_lost` 表達：當 `last_seen_s ≥ ttl_warn_s` 時 `is_lost=true`，否則 `is_lost=false`（可省略欄位或明確為 `false`，擇一實作並於 contracts 固定）。`age_s >= ttl_remove_s` 時，Map Sim MUST 從登錄表移除該物件，之後無論 `include_lost` 為何皆不可見。預設 `ttl_warn_s=5.0`、`ttl_remove_s=10.0`。
- **FR-MS-007**（並發安全）：`POST /objects/update` / `GET /objects` / `GET /objects/all` / 背景 TTL 清理 之間對登錄表的讀寫 MUST 以互斥機制（`asyncio.Lock` 或等效）保護，保證不出現髒讀、部分更新、或清理過程中讀到被刪除物件的不一致狀態。
- **FR-MS-008**（除錯查詢）：Map Sim MUST 提供 `GET /objects/all`，回傳登錄表中所有物件（含 lost），並附 `total` / `active` / `lost` 計數；此端點用於除錯、不納入正式契約測試的性能 SC。
- **FR-MS-009**（手動移除）：Map Sim MUST 提供 `DELETE /objects/{drone_id}` 端點供測試/除錯手動移除特定物件；此端點為選填路徑，正式資料流仍以 TTL 為清理機制。
- **FR-MS-010**（健康檢查）：Map Sim MUST 提供 `GET /health`，回傳 `status: "ok"`、`registered_objects`、`uptime_s`。
- **FR-MS-011**（容量）：Map Sim MUST 同時維護至少 20 個 `drone_id`（PoC 場景最多 5 個）的狀態而不退化。
- **FR-MS-012**（CLI）：Map Sim MUST 提供 CLI，支援 `--port`（預設 8090）、`--ttl-warn-s`（預設 5.0）、`--ttl-remove-s`（預設 10.0）、`--verbose`（詳細日誌）。
- **FR-MS-013**（本機部署）：Map Sim MUST 以 asyncio aiohttp（或等效 async HTTP server）本機執行，Port 預設 `8090`；預設綁定 `127.0.0.1`（PoC 場景同主機部署）。
- **FR-MS-014**（LANDED 收尾可見性）：對於 UDS 推送的最後一筆 `status="LANDED"` 後停推的 `drone_id`，Map Sim MUST 在 `[0, ttl_warn_s)` 期間於預設查詢中仍回傳該物件（`status="LANDED"`），在 `[ttl_warn_s, ttl_remove_s)` 期間標為 lost，之後完全移除。**不得**在收到 `LANDED` 的瞬間立刻將該物件從登錄表刪除。
- **FR-MS-015**（副作用隔離）：`400` / `5xx` 回應 MUST NOT 變更登錄表狀態、MUST NOT 更新任何 `last_seen_at`、MUST NOT 觸發 TTL 清理。

### Key Entities *(include if feature involves data)*

- **DroneObject**：登錄表中的單架無人機狀態。屬性包含 UDS 推送的 8 個契約欄位（`drone_id`、`lat`、`lon`、`alt_m`、`speed_ms`、`heading_deg`、`status`、`timestamp`）、以及 Map Sim 自行維護的 `last_seen_at`（Map Sim 收到該筆 update 的 wall-clock 時間）。具備以下衍生行為：
  - `age_s()`：從 `last_seen_at` 到現在的秒數，用於 TTL 判斷與 `last_seen_s` 輸出。
  - `is_active(ttl_warn_s)`：回傳是否仍在 warn TTL 內；供查詢過濾用。
- **ObjectRegistry**：以 `drone_id` 為鍵的 DroneObject 字典，附 `asyncio.Lock`。對外提供 `update / query_radius / get_all / remove / cleanup_expired` 五種操作；所有操作 MUST 取得鎖。`cleanup_expired` 由背景任務週期呼叫（建議 2 s 一次）。
- **Query Response**：`GET /objects` 的回應物件，包含 `query`（echo 查詢參數 + 回應產生時間戳）、`count`（過濾後物件數）、`objects[]`（DroneObject 序列化 + `distance_m` + `last_seen_s` + `is_lost: bool`，依距離升冪排序）。`objects[].status` 永遠是原始 UDS FlightState 值，不被 TTL 狀態覆寫；`is_lost` 為獨立布林欄位，`true` 表示 `last_seen_s ≥ ttl_warn_s`（僅在 `include_lost=true` 時可能出現 `true`），`false` 或省略表示仍在 warn TTL 內。`GET /objects/all` 另有 `total / active / lost` 三個計數欄位，其中 `lost` 以 `is_lost=true` 為判準計數。
- **Haversine Distance**：以 WGS84 球面近似計算（R = 6371000 m）。Map Sim 不引入橢球（Vincenty）計算；PoC 容差上，100 km 內 < 0.5% 誤差可接受。

---

## 4. Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-MS-001**（接收吞吐）：在 UDS 每秒推送 **100 筆**（10 架 × 10 Hz）的穩態負載下，Map Sim 持續 10 秒內 `POST /objects/update` 的成功率 ≥ 99.5%，無任何 5xx；平均處理延遲 < 5 ms。
- **SC-MS-002**（查詢延遲）：當登錄表內同時有 20 個 `drone_id`、兩個感測器客戶端各自以 1 Hz 查詢時，`GET /objects` 從 client 送出到收到回應的端到端 p95 延遲 < 20 ms（本機迴圈、含 Haversine 排序）。
- **SC-MS-003**（TTL warn 精度）：從某 `drone_id` 最後一筆 update 到該物件首次在預設查詢中不再出現之延遲，MUST 落在 `[ttl_warn_s, ttl_warn_s + 2.0 s]` 區間（2 秒為背景清理週期的最大誤差）。
- **SC-MS-004**（TTL remove 精度）：從某 `drone_id` 最後一筆 update 到該物件從登錄表完全消失的延遲，MUST 落在 `[ttl_remove_s, ttl_remove_s + 2.0 s]` 區間。
- **SC-MS-005**（查詢正確性）：對固定登錄表快照，以不同 `(lat, lon, radius_m)` 查詢 100 次的回傳物件集合與 Haversine 距離 ground truth 相比，誤判（應入未入 / 不應入但入）率為 0；排序與 `distance_m` 值與 ground truth 的差 < 0.5%。
- **SC-MS-006**（並發安全）：在 100 req/s 的 POST 與 20 req/s 的 GET 併發下持續 30 秒，`GET /objects/all` 的 `total` 計數絕不出現負值、不超過曾 update 過的唯一 `drone_id` 數；不出現 DroneObject 欄位部分新、部分舊的混合狀態。
- **SC-MS-007**（容量）：登錄表同時維護 20 個 `drone_id` 時，記憶體使用量 < 50 MB；CPU 使用率（single core）< 15%。
- **SC-MS-008**（健康檢查可用性）：在 SC-MS-001 的負載下，`GET /health` 回應時間 < 50 ms 且始終回 200。
- **SC-MS-009**（LANDED 可見性窗口）：UDS 推送最後一筆 `status="LANDED"` 後，下游以預設查詢仍可觀察到該 `drone_id`（`status="LANDED"`）至少 `ttl_warn_s - 1.0` 秒；之後依 FR-MS-014 轉 lost 再消失。

---

## 5. Assumptions

- **單機部署**：UDS、Map Sim、EchoShield Sim、Sentrycs Sim 均部署於同一台 PoC 主機，Map Sim 綁 `127.0.0.1:18090`；不處理跨主機、跨網段、反向代理、TLS。
- **單一上游**：僅 UDS 一個來源推送 `POST /objects/update`；不考慮多個上游系統對同一 `drone_id` 競爭寫入的仲裁策略（最後到的一筆覆寫，不做 timestamp 排序合併）。
- **不持久化**：Map Sim 重啟即清空登錄表；不寫入任何檔案或資料庫；狀態僅存記憶體。UDS 重啟後會重新推送，下游感測器容忍短暫空窗。
- **不跨實例擴展**：單一 Map Sim 行程即可覆蓋 PoC 容量；不考慮橫向擴展、sharding、主從複製。
- **時鐘基準**：`last_seen_at` 以 Map Sim 本地 `datetime.now(timezone.utc)` 為準；不使用 request body 中的 `timestamp`（避免 UDS 時鐘漂移影響 TTL）。request body `timestamp` 僅原樣保存、供下游參考。
- **無身份驗證**：`POST /objects/update` / `GET /objects` / `DELETE /objects/{id}` 均不需 API key 或 Token；PoC 本機信任邊界之內。
- **無 rate limit**：Map Sim 不主動限流；若下游感測器異常高頻查詢，依 FR-MS-007 並發鎖仍保證正確性，但延遲可能下降。
- **Haversine 即足夠**：以 R=6371 km 球面近似計算距離；100 km 內誤差 < 0.5%，對 4.8 km / 8 km 的感測器半徑完全充分。不引入 Vincenty 等橢球演算法。
- **`status` 值域信任 UDS**：Map Sim 不白名單驗證 `status` 字串（接受任何非空字串），未知值原樣儲存；FlightState 值域由 UDS 契約保證（`specs/001-uds/contracts/rest-api.md` §3.2）。

### Out of Scope

- **持久化/歷史軌跡回放**：Map Sim 不寫磁碟、不儲存歷史軌跡；若未來需要重播，應由獨立記錄服務負責。
- **真實硬體整合**：Map Sim 僅服務 PoC 模擬器；實接 EchoShield / Sentrycs 硬體的 Adapter 不在本 feature 範圍。
- **跨機房/高可用**：不做主備、不做故障切換、不做 leader election。
- **認證、授權、審計**：不處理 TLS、API Key、RBAC、審計日誌。
- **非圓形查詢**：不支援多邊形、走廊、橢圓等其他幾何範圍查詢。
- **批次 POST（batch update）**：不支援 `POST /objects/update` 一次多筆；UDS 已固定採 per-drone 粒度（見 `specs/001-uds/contracts/rest-api.md` §3.1 Clarification Q1），Map Sim 不另開 batch 介面避免契約分叉。
- **Push-based 通知（WebSocket / SSE）**：下游一律以 HTTP pull 取得；未來若要改 push，屬另一 feature。
- **CoT XML 生成**：Map Sim 僅管理物件狀態，不產生 CoT；CoT XML 由 CoT Gateway 的 CotGenerator 生成（見 `08-api-icd.md` §4）。

---

## 6. 依賴與下游契約承諾

- **上游依賴**：`specs/001-uds`（UDS）已實作並穩定，Map Sim 以 UDS push payload 8 欄位為接收端契約基準。
- **下游承諾**：EchoShield Simulator 與 Sentrycs Simulator（後續 features）MAY 依賴以下行為：
  - `GET /objects?lat=&lon=&radius_m=` 預設 `include_lost=false`、回應含 `distance_m` 與 `last_seen_s`、按距離升冪排序。
  - 未命中查詢必為 200 + `count=0` + `objects=[]`。
  - TTL 預設 warn 5 s / remove 10 s；可由 CLI 覆寫但預設行為穩定。
- **版本承諾**：Map Sim v1.x MUST NOT 破壞性變更 `POST /objects/update` 的 8 個必填欄位名稱、`GET /objects` 的必填參數、回應中 `count / objects / distance_m / last_seen_s` 欄位名。新增選填欄位不視為破壞性變更。
