# Feature Specification: Sentrycs Simulator

**Feature Branch**: `004-sentrycs-sim`
**Created**: 2026-04-23
**Status**: Draft
**Input**: User description: "Sentrycs C-UAS（被動 RF 偵測）模擬器，以 HTTP JSON Status API（:17070）輸出偵測資料給 CoT Gateway SentrycsAdapter，向 Map Simulator 查詢無人機位置，在 MITIGATING 狀態時呼叫 UDS `/command/takeover` 觸發接管，並模擬操控者 RF 定向位置。"

---

## Clarifications

### Session 2026-04-24

- Q: `FR-SC-016` 要求輸出 `model` 欄位，但 Map Simulator `GET /objects` 契約並未回傳無人機型號；Sentrycs 應從何處取得 `model`？ → A: 場景 YAML 每架無人機必填 `model` 字串欄位，由 `uid` 對應；Sentrycs 啟動時載入場景，於執行期以 Map Sim 查到的 `uid` 回本地 scenario 表查 `model` 後一併輸出。

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 完整偵測-接管-制壓流程對外提供狀態查詢 (Priority: P1)

場景操作員啟動 Sentrycs 模擬器與 CoT Gateway，場景開始後在預定時序（`detected_at_s`）偵測到入侵無人機，依序轉為 `DETECTED → MITIGATING → NEUTRALIZED`。CoT Gateway 的 SentrycsAdapter 以 1 Hz 輪詢 `GET /detections`，取得含無人機位置、型號、狀態、操控者位置的 JSON，並融合到 TAK Server。這是本模擬器最核心的任務流，沒有它整個 C-UAS Demo 劇情無法呈現。

**Why this priority**: 核心 MVP——Demo 的主劇情（偵測→干擾→制壓）完全仰賴此故事；缺少它其他故事都無意義。

**Independent Test**: 僅啟動 Sentrycs Simulator（搭配 Mock Map Simulator 與 Mock UDS），以 HTTP Client 每秒輪詢 `GET /detections`，可完整觀察到 IDLE（空列表）→ DETECTED → MITIGATING → NEUTRALIZED 的狀態序列與對應 JSON 欄位；並驗證 `POST /command/takeover` 在 MITIGATING 觸發時被呼叫一次。

**Acceptance Scenarios**:

1. **Given** 場景設定 `detected_at_s=5, mitigating_at_s=20, neutralized_at_s=35`，Map Simulator 在感測器中心 8km 內回傳對應無人機物件，**When** 模擬器啟動並執行 35+ 秒，**Then** `GET /detections` 依序回傳 `DETECTED`、`MITIGATING`、`NEUTRALIZED` 狀態，且在 MITIGATING 轉換那一刻對 UDS `/command/takeover` 發送恰好一次含 `drone_id/target_lat/target_lon/target_alt_m` 的請求。
2. **Given** 無人機處於 `MITIGATING`，**When** UDS 將無人機移動至目標點並由 Map Simulator 將其 `status` 更新為 `LANDED`（或 `is_lost=false` 且 status 變為 LANDED），**Then** Sentrycs 在下一次輪詢內將偵測狀態轉為 `NEUTRALIZED`，並維持 30 秒後自 `/detections` 移除。
3. **Given** Sentrycs 處於 `IDLE`（尚未到達 `detected_at_s`），**When** 外部呼叫 `GET /detections`，**Then** 回傳 HTTP 200 與空陣列 `[]`，且不會對 UDS 發出任何接管請求。

---

### User Story 2 - 操控者 RF 定向位置模擬 (Priority: P1)

為了在 TAK 上呈現 Sentrycs 最具代表性的功能（以 RF 定向反推操控者位置），Sentrycs 模擬器必須依每架無人機的設定（`operator_bearing_deg`、`operator_distance_m`，200–500m）計算出固定的操控者地面位置，於每筆偵測 JSON 中一併輸出 `operator_lat / operator_lon / operator_distance_m / operator_bearing_deg`，使 Gateway 能在 TAK 同步繪製操控者敵方圖示。

**Why this priority**: 與 P1 共同構成 Demo 故事的「可看性」；沒有操控者位置就失去 Sentrycs 在 Demo 中的差異化賣點，但狀態機輸出本身仍可運作，因此與 Story 1 並列為 P1。

**Independent Test**: 給定無人機位置 `(25.0330, 121.5654)`，設定 `operator_bearing_deg=225, operator_distance_m=300`，檢視 `GET /detections` 的 `operator_lat/operator_lon`，以 WGS84 大地距離公式反算，誤差小於 1m；且在整個場景中此值保持固定不隨無人機移動而改變。

**Acceptance Scenarios**:

1. **Given** `operator_bearing_deg=225, operator_distance_m=300` 與無人機初始位置，**When** 呼叫 `GET /detections`，**Then** 回傳的 `operator_lat/operator_lon` 位於無人機西南方約 300m（誤差 < 1m），且 `operator_distance_m=300, operator_bearing_deg=225`。
2. **Given** 場景運行中無人機位置隨 Map Simulator 更新而改變，**When** 多次輪詢 `/detections`，**Then** 同一偵測目標的 `operator_lat/operator_lon` 在整個場景期間保持不變（操控者靜止）。

---

### User Story 3 - 多無人機並行偵測與個別接管 (Priority: P2)

單一場景 YAML 可列出多架無人機（不同型號、不同 `detected_at_s`）。Sentrycs 模擬器需同時追蹤所有目標，各自獨立推進狀態機與接管請求，`GET /detections` 回傳當前所有非 IDLE 目標清單，每筆皆有獨立 `uid` 與狀態；一架的失敗不影響其他架。

**Why this priority**: Demo 的擴展場景（如多機圍攻）需要此能力，但主劇情 P1 先完成單機版即可發布。

**Independent Test**: 載入含 2 架以上無人機（不同 `detected_at_s`）的場景檔，在 Mock Map Simulator 中同時提供兩筆物件，輪詢 `/detections` 可同時觀察到各自的狀態進程；對 Mock UDS 觀察到兩次獨立的 `takeover` 呼叫，各自帶不同 `drone_id`。

**Acceptance Scenarios**:

1. **Given** 場景定義 2 架無人機 A（`detected_at_s=5`）與 B（`detected_at_s=30`），**When** 模擬器執行至 35s，**Then** `GET /detections` 同時包含 A（可能已 MITIGATING）與 B（DETECTED），兩者 `uid` 不同且狀態獨立推進。
2. **Given** 其中一架的 `takeover` 呼叫因 UDS 回傳 `409 Conflict`（已接管）而失敗，**When** 下一次輪詢，**Then** 另一架無人機狀態機仍持續推進，未受影響，且故障無人機會記錄錯誤並維持於 `MITIGATING` 直到落地條件達成或場景結束。

---

### Edge Cases

- **Map Simulator 下線或連線失敗**：Sentrycs 必須以退避策略持續重試，不可崩潰；在成功恢復查詢前，已進入非 IDLE 狀態的偵測目標保持上一次已知位置並在 `/detections` 中持續回傳（狀態不回退），重試恢復後以最新位置覆蓋。
- **UDS `/command/takeover` 回傳 409 Conflict（已被其他 sensor 接管）**：視為「接管已生效」等同成功，立即轉入 `MITIGATING`，不重試。
- **UDS 回傳 404（drone_id 不存在）或 400（參數錯誤）**：記錄錯誤並維持 `DETECTED`，不進入 `MITIGATING`；下一個 `mitigating_at_s` 週期不重送，以避免與真實場景差異擴大。
- **MITIGATING 期間目標自 Map Simulator 消失**（例如離開 8km 範圍或被其他系統移除）：在設定的寬限時間（例如 10 秒）內持續以上一位置輸出；逾時後視為 `NEUTRALIZED`（制壓成功假設）並開始 30 秒保持倒數。
- **Map Simulator 回傳 `is_lost=true` 的物件**：Sentrycs 必須忽略（不加入偵測清單、不觸發狀態轉移），因 RF 被動偵測本質上無法定位「已失聯」目標。
- **操控者位置抖動**：因操控者為固定估計位置，輸出 `operator_lat/lon` 在場景期間必須完全一致（不可每秒重算導致毫秒級抖動）。
- **多無人機並行且時序重疊**：每架無人機以獨立 async task 推進，狀態轉換與接管呼叫互不阻塞；單一目標處理逾時不得拖慢其他目標的 1 Hz 輸出。
- **場景中 `detected_at_s > mitigating_at_s`（設定錯誤）**：載入場景時即 fail fast，回報明確錯誤訊息並拒絕啟動。
- **CoT Gateway 同時開啟多個輪詢連線**：HTTP API 必須支援並發請求，各請求取得一致快照。
- **目標在 DETECTED 階段就從 Map Simulator 移除**：視為誤報，回到 `IDLE`，不觸發 `/command/takeover`。
- **Map Simulator 回傳的 `uid` 不在場景 YAML 內**（場景未登記的外來無人機）：Sentrycs MUST 記錄 error log（含該 `uid`），仍將該目標納入狀態機與 `/detections` 輸出，但 `model` 欄位固定填 `"Unknown"`，以避免因資料缺漏阻塞 Demo 流程；場景設計者應回頭補齊 YAML。

---

## Requirements *(mandatory)*

### Functional Requirements

#### 狀態機與核心流程

- **FR-SC-001**: System MUST 實作 `IDLE → DETECTED → MITIGATING → NEUTRALIZED → IDLE` 狀態機，每架無人機獨立維護。
- **FR-SC-002**: System MUST 依場景 YAML 的 `detected_at_s` 觸發 `IDLE → DETECTED` 轉移，前提是該無人機於 Map Simulator 的感測器半徑內可被查詢到。
- **FR-SC-003**: System MUST 在 `mitigating_at_s` 呼叫 UDS `POST /command/takeover`，請求體為 `{drone_id, target_lat, target_lon, target_alt_m}`；請求成功（HTTP 200）或 `409 Conflict` 後立即轉入 `MITIGATING`。
- **FR-SC-004**: System MUST 在 `MITIGATING` 期間持續輪詢 Map Simulator，當目標 `status=LANDED` 時轉入 `NEUTRALIZED`。
- **FR-SC-005**: System MUST 在 `NEUTRALIZED` 狀態保持 30 秒後，將該偵測目標自 `GET /detections` 輸出中移除（回到 IDLE/結束）。

#### 上游查詢（Map Simulator）

- **FR-SC-006**: System MUST 每 0.5 秒以場景設定之 `sensor_lat, sensor_lon` 為中心，呼叫 `GET /objects?lat=&lon=&radius_m=8000` 向 Map Simulator 查詢偵測範圍內物件。
- **FR-SC-007**: System MUST 忽略 Map Simulator 回傳中 `is_lost=true` 的物件，不納入偵測、不觸發狀態轉移。
- **FR-SC-008**: System MUST 以 Map Simulator 回傳物件的 `status` 欄位判斷落地（`LANDED`），取代任何其他落地旗標。
- **FR-SC-009**: System MUST 在 Map Simulator 連線失敗時以指數退避（如 1s → 2s → 4s，最大 10s）重試，並保留既有狀態不回退。

#### 下游指令（UDS）

- **FR-SC-010**: System MUST 僅在由 `DETECTED → MITIGATING` 這一次狀態轉移時對 UDS 發送 `/command/takeover`；同一目標不可重送。
- **FR-SC-011**: System MUST 將 UDS `/command/takeover` 回傳之 `409 Conflict` 視為「已接管」成功，照常進入 `MITIGATING`；`400/404` 視為失敗並保留於 `DETECTED`。
- **FR-SC-012**: System MUST 使用可設定之 UDS host/port（預設 `localhost:18080`）與超時（建議 3 秒）。

#### 對外介面（HTTP JSON Status API :17070）

- **FR-SC-013**: System MUST 提供 HTTP JSON 狀態 API，預設監聽 `0.0.0.0:17070`，Port 可由 CLI `--api-port` 與場景檔覆寫。
- **FR-SC-014**: System MUST 提供 `GET /detections` 端點，回傳所有非 IDLE 偵測目標的陣列；IDLE 目標不包含在回傳中。
- **FR-SC-015**: System MUST 提供 `GET /detection/{uid}` 端點，對存在且非 IDLE 的目標回傳單一 JSON（HTTP 200），否則回傳 HTTP 404（body `{"status":"error","reason":"not_found"}`）。
- **FR-SC-015b**: System MUST 提供 `GET /health` 端點，回傳 HTTP 200 與 JSON `{status, uptime_s, tracked_drones, map_sim_reachable}`，供 smoke test 與就緒探測使用；該端點不得觸發任何狀態機副作用或寫入 registry。啟動後就緒時間 < 2 秒（SC-SC-011 以 `/health` 200 為就緒信號的等價條件）。
- **FR-SC-016**: System MUST 在每筆偵測 JSON 中包含 `uid, model, detection_status, lat, lon, alt_m, velocity_ms, azimuth_deg, operator_lat, operator_lon, operator_distance_m, operator_bearing_deg, timestamp, is_landed` 全部欄位。其中 `model` 來源為場景 YAML 中該 `uid` 對應的 `model` 設定（Map Simulator `/objects` 契約不提供型號，由 Sentrycs 以本地 scenario 表補上）；若收到的 `uid` 不在場景 YAML 內，MUST 輸出 `model: "Unknown"` 並記錄 error log，不得中斷狀態機或 API 輸出。
- **FR-SC-017**: System MUST 以 ISO 8601 UTC（結尾 `Z`）格式輸出 `timestamp`，反映該筆狀態的最新更新時間。
- **FR-SC-018**: System MUST 支援多個 HTTP Client 同時輪詢（至少 5 個並發連線），各請求取得一致的偵測快照。

#### 操控者位置模擬

- **FR-SC-019**: System MUST 依場景設定之 `operator_bearing_deg` 與 `operator_distance_m`（200–500m）在無人機初始位置上以 WGS84 大地距離計算操控者地面位置，並於偵測目標整個生命週期內維持不變。
- **FR-SC-020**: System MUST 在偵測 JSON 中一併輸出 `operator_lat, operator_lon, operator_distance_m, operator_bearing_deg` 四欄位。

#### 場景、CLI、可觀測性

- **FR-SC-021**: System MUST 支援以 YAML 場景檔（`--scenario`）載入感測器座標、Map Simulator/UDS 連線、API Port、多架無人機時序與操控者設定；載入失敗（檔案不存在、欄位缺失、時序矛盾）MUST fail fast 並回報具名錯誤。場景 YAML 的無人機清單中，每架無人機 MUST 具備以下必填欄位：`uid`（字串，對應 Map Simulator 物件 uid）、`model`（字串，例如 "DJI Mavic 3"，用於 `FR-SC-016` 偵測 JSON 的 `model` 輸出）、`detected_at_s`、`mitigating_at_s`、`neutralized_at_s`、`operator_bearing_deg`、`operator_distance_m`；缺少任一欄位視為欄位缺失並 fail fast。
- **FR-SC-022**: System MUST 提供 CLI 介面，至少支援 `--scenario`、`--api-port`、`--verbose` 參數。
- **FR-SC-023**: System MUST 支援多架無人機並行追蹤，每架以獨立 async task 推進，互不阻塞。
- **FR-SC-024**: System MUST 於 `--verbose` 開啟時，為每次狀態轉移、每次 Map Simulator 查詢結果摘要（物件數）、每次 UDS `/command/takeover` 請求與回應輸出結構化日誌。
- **FR-SC-025**: System MUST 在收到 `SIGINT/SIGTERM` 時優雅關閉：停止接受新 HTTP 請求、取消未完成的輪詢任務、關閉 UDS client session，3 秒內結束行程。

### Key Entities

- **SentrycsConfig**：由場景 YAML 解析而得的不可變設定物件，內含感測器安裝座標（`sensor_lat/lon`）、偵測半徑（固定 8000m）、Map Simulator 連線與 `poll_interval_s`、UDS 連線、`api_host/port`，以及一組 `DroneScenario` 清單（每架無人機的初始狀態、時序、操控者設定）。
- **DroneTrack**（對應內部 `DroneDetection`）：單一無人機偵測目標的運行時狀態，包含 `uid, model, callsign`、最近一次由 Map Simulator 同步的位置/高度/速度/方位、目前 `DetectionStatus`、`status_changed_at` 時間戳、關聯的 `OperatorEstimate`。其中 `model` 欄位**不**來自 Map Simulator 回傳，而是由 Sentrycs 啟動時從場景 YAML 的 `drones[*].model` 建立一張 `uid → model` 查找表，於每次以 `uid` 收到 Map Sim 物件時查表填入；若 `uid` 未登記於場景（例如 Map Sim 多了額外無人機），填入 `"Unknown"` 並記錄 error log。
- **OperatorEstimate**：每架無人機的操控者估計位置，在 DroneTrack 建立時依 `bearing_deg + distance_m` 計算一次並固定不變；輸出 `operator_lat/lon/distance_m/bearing_deg`。
- **StateMachine**：管理 `IDLE / DETECTED / MITIGATING / NEUTRALIZED` 四狀態之間的合法轉移、觸發條件（時序、takeover 結果、落地訊號、30s 倒數），以及每次轉移時的副作用（呼叫 UDS、更新 timestamp、記錄日誌）。
- **TakeoverRequest**：對 UDS `/command/takeover` 的請求紀錄，欄位包含 `drone_id, target_lat, target_lon, target_alt_m`、送出時間、回應狀態碼與結果解讀（`accepted / already_taken_over(409) / rejected(400|404) / failed`），用於日誌追蹤與避免重送。

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-SC-001**（流程正確性）：在標準場景下，從 `detected_at_s` 到 `GET /detections` 首次出現該目標的延遲 < 1 秒；從 `mitigating_at_s` 到 UDS 觀察到 `takeover` 請求的延遲 < 500 毫秒。
- **SC-SC-002**（落地反應速度）：Map Simulator 將目標 `status` 改為 `LANDED` 之後，`GET /detections` 於 ≤ 1 秒內顯示 `detection_status=NEUTRALIZED` 且 `is_landed=true`。
- **SC-SC-003**（查詢吞吐）：在 5 個並發 HTTP Client 以 1 Hz 輪詢情境下，API `GET /detections` 的 P95 延遲 < 100 毫秒，錯誤率 0%。
- **SC-SC-004**（位置準確性）：操控者位置以 WGS84 大地距離公式驗算，與期望位置誤差 < 1m；且在整個場景中 `operator_lat/lon` 的最大抖動 = 0。
- **SC-SC-005**（狀態穩定性）：非 IDLE 目標每秒至少更新一次 JSON 快照（`timestamp` 前進 ≥ 1 次/秒），穩定狀態下連續 60 秒無 missed tick。
- **SC-SC-006**（多機擴展）：同時載入 5 架無人機時，每架狀態轉移時序誤差 < 1 秒，CPU 使用率（單核）< 20%。
- **SC-SC-007**（容錯：Map Simulator 下線）：Map Simulator 下線 30 秒期間，Sentrycs 不崩潰、`GET /detections` 持續回應、既有非 IDLE 目標保留上一次狀態；恢復後 1 秒內追上最新位置。
- **SC-SC-008**（容錯：UDS 409）：當 UDS 回傳 409 時，目標在 ≤ 1 秒內進入 `MITIGATING` 且不重送 takeover。
- **SC-SC-009**（`is_lost` 過濾）：Map Simulator 回傳中標記 `is_lost=true` 的物件 100% 被排除於偵測清單之外。
- **SC-SC-010**（可觀測性）：`--verbose` 模式下，每次狀態轉移、每次 takeover 請求、每次 Map Simulator 錯誤皆產生 1 筆結構化日誌（含 `uid`、舊狀態、新狀態、時間戳）。
- **SC-SC-011**（啟動時間）：從 CLI 啟動到 `GET /health` 回應 HTTP 200（等價於 `GET /detections` 回應 HTTP 200，服務就緒）的時間 < 2 秒。
- **SC-SC-012**（優雅關閉）：收到 `SIGINT` 後，行程在 3 秒內結束，且未留下懸掛的 HTTP 連線或 async task。

---

## Assumptions

- 感測器安裝位置（`sensor_lat/lon`）與偵測半徑 8000m 由場景檔提供，場景執行期間不變更。
- Map Simulator 在感測器半徑內即時回傳最新無人機位置與 `status`；Sentrycs 不負責位置平滑或融合，僅做透傳與忽略 `is_lost=true`。
- 操控者在場景期間靜止不動；RF 方向定位精度以固定 `ce=50m` 呈現（由 CoT Gateway 使用，本模擬器僅輸出距離/方位）。
- UDS `/command/takeover` 是冪等的接管語意，對同一 `drone_id` 重複呼叫風險由上層避免；本模擬器保證每目標僅送一次。
- CoT XML 生成由 CoT Gateway 的 SentrycsAdapter 負責，本模擬器僅輸出 JSON；§6 的 CoT 範例僅供參考，不屬於本 feature 的驗收範圍。
- 預設 API Port `7070`、Map Simulator `localhost:18090`、UDS `localhost:18080`，均可由 YAML 覆寫。
- 依賴 Map Simulator 與 UDS 已凍結的契約：`GET /objects?lat=&lon=&radius_m=` 回傳含 `status + is_lost`；`POST /command/takeover` 接受 `{drone_id, target_lat, target_lon, target_alt_m}` 並回傳 200/400/404/409。
- Python 3.11+、`aiohttp`、`PyYAML`、`pydantic v2`、`structlog` 為可用的執行環境依賴；WGS84 大地距離/方位計算由本服務以手寫 destination formula（約 15 行）實作，**不**引入 `geopy`，以守依賴最小化原則（詳 plan.md §Dependencies、research.md R3）。
