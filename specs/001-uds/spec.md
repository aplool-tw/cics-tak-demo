# 功能規格：統一無人機模擬器（Unified Drone Simulator, UDS）

**Feature Branch**: `001-uds`
**Created**: 2026-04-24
**Status**: Draft
**Input**: 為反無人機 TAK 戰術感知 PoC 建立一個統一的無人機飛行狀態模擬器（UDS），作為 PoC 中「無人機真實位置」的 Single Source of Truth，並提供接管閉環能力，讓指揮官可在 ATAK 上完整演練偵測 → 反制 → 降落的作戰流程。

---

## 1. 背景與目的

在反無人機 TAK PoC 中，真實硬體（EchoShield 4D 雷達、Sentrycs C-UAS）皆由軟體模擬器取代。若各感測器模擬器各自維護無人機位置，會導致：

1. **狀態不一致**：雷達模擬器與 RF 模擬器對同一架無人機回報位置不同步。
2. **接管閉環無法驗證**：Sentrycs 下令接管後，EchoShield 無法自動反映航線改變。

**統一無人機模擬器（UDS）** 作為感測層中「無人機真實位置」的唯一來源：

- 由 YAML 場景檔載入無人機與飛行任務。
- 在單一 asyncio 主迴圈中計算所有無人機的飛行軌跡。
- 每個主迴圈週期針對每架活躍無人機各呼叫一次 `POST /objects/update`（per-drone 粒度，依 `08-api-icd.md` §3.1 ICD）主動推送至 Map Simulator（`:8090`），供 EchoShield Simulator 與 Sentrycs Simulator 透過 Map Simulator 查詢取得。
- 提供 `:8080` HTTP REST API 供 Sentrycs Simulator 查詢狀態、發送接管指令；接管指令會即時改變 UDS 內的航線計算，促成偵測 → 反制 → 降落的完整閉環。

> **架構澄清（依 `docs/system-docs/CHANGELOG.md` v0.3 與 `01-system-architecture.md` v0.7 為準）**：
> - UDS **僅** 暴露兩個輸出介面：`HTTP :8080`（Command & Query API）與 `HTTP POST :8090/objects/update`（主動推送至 Map Simulator）。
> - UDS **不再** 自行開啟 TCP `:9000`；EchoShield JSON Feed（`:9000`）已由獨立的 EchoShield Simulator 負責。
> - `02-unified-drone-simulator-spec.md` §1.2 與第 5 節關於「EchoShield TCP Feed（:9000）」的敘述屬於舊版 v0.1 內容，尚未同步更新；本規格以 CHANGELOG v0.3 的修訂為準。

---

## Clarifications

### Session 2026-04-24

- Q: UDS → Map Simulator `POST /objects/update` 的請求粒度應如何定義（每個主迴圈週期是呼叫一次含所有無人機，還是每架一次）？ → A: **Per-drone**：依 `03-map-simulator-spec.md` 與 `08-api-icd.md` §3.1 現有 ICD，request body 為單一無人機 JSON；UDS 每個主迴圈週期對每架 `flight_state ≠ IDLE` 的無人機各呼叫一次 `POST /objects/update`（10 架 × 10 Hz ⇒ 100 req/s）。
- Q: 當無人機進入 `LANDED` 時，UDS 對 Map Simulator 的「收尾推送」語意應如何明確定義？ → A: **同週期收尾推送 + 之後停止**：UDS 在狀態切換到 `LANDED` 的「同一個主迴圈週期」必須對該 `drone_id` 推送恰一筆 `POST /objects/update`，其 request body 中 `flight_state = "LANDED"`（明確旗標）；自下一個主迴圈週期起，不再推送該 `drone_id` 的任何更新（直到場景重置 / `LANDED → IDLE`）。不採用「只靠下一週期起停推、不發最後一筆」的替代方案。
- Q: UDS `:8080` REST API 的契約範圍應如何劃分（`POST /command/takeover` 與 `GET /status/{drone_id}` / `GET /drones` 是否皆為正式契約）？ → A: **只有 takeover 為正式契約**：`POST /command/takeover` 是 UDS 對 Sentrycs Simulator 的正式 API 契約，必須納入契約測試並維持向後相容；`GET /status/{drone_id}` 與 `GET /drones` 降級為「除錯端點」，僅在啟動時帶 `--debug` 旗標才會註冊路由（預設關閉），回應 schema 不納入契約測試，且不保證跨版本穩定。Sentrycs Simulator 正式運行路徑**不得**依賴這兩個端點；位置查詢一律透過 Map Simulator。
- Q: Scenario YAML `timeline[].action` 的合法值域應如何約束？ → A: **封閉白名單 { `start_flying` }**：PoC 階段 `timeline[].action` 僅允許 `start_flying` 一種值；載入 YAML 時若遇到其他值（含拼寫錯誤、未知 action、空字串），`ScenarioLoader` 必須以 `unknown action: <value>` 之類的明確訊息 fail-fast（拋錯 + 非零 exit code），不得靜默忽略，也不得執行任何後續的主迴圈初始化。未來若需擴充（如 `set_waypoint`、`hold`），須透過版本化 schema 另行引入。
- Q: `POST /command/takeover` 的 `target_lat/target_lon/target_alt_m` 欄位語意與無人機當前狀態前置條件應如何明確化？ → A: **全部必填 + 座標/高度值域校驗 + 以 409 區分「未起飛」**：
  - `target_lat` 與 `target_lon` 皆為必填；載入時必須校驗 `target_lat ∈ [-90, 90]`、`target_lon ∈ [-180, 180]`，任一越界 → 回傳 **HTTP 400 `invalid coordinates`**。
  - `target_alt_m` 為必填，單位為公尺（HAE），允許 `≥ 0`；若 `< 0` → 回傳 **HTTP 400 `invalid altitude`**。`target_alt_m` 無預設值，呼叫端必須顯式傳入（不得省略、不得由 UDS 推論）。
  - 目標無人機若處於 `IDLE`（尚未起飛）時收到接管指令 → 回傳 **HTTP 409 Conflict `drone not airborne`**；此情況**不得**與「已 `LANDED`」共用 400，兩者語意必須區分（`IDLE` 為 409、`LANDED` 為 400 `already landed`）。
  - 對同一 `drone_id` 在尚未 `LANDED` 前連續接管：回傳 **HTTP 200 `accepted`**，以最新一筆 `takeover_cmd` 覆寫舊目標（新的 `target_lat/target_lon/target_alt_m` 取代舊值），`flight_state` 維持 `MITIGATING_TAKEOVER`，不加額外旗標或計數欄位。

---

## 2. User Scenarios & Testing *(mandatory)*

### User Story 1 — 指揮官演練接管閉環（Priority: P1）

指揮官（ATAK 操作人員）希望在 PoC 展示場景中，完整演練「偵測敵機 → 下令反制 → 敵機被接管降落 → 圖標變藍」的作戰流程，以驗證系統所有子元件（感測層、指管層、TAK、ATAK）在真實情境下的協同運作。

**Why this priority**：此 User Story 是整個 PoC 的主要驗收情境，也是 UDS 存在的核心理由；若不成立，則多感測器融合、TAK 顯示等其他功能都失去驗證場景。

**Independent Test**：以 `single_drone_invasion` 場景啟動 UDS 與所有相依元件，由 Sentrycs Simulator 在腳本指定時間呼叫 `POST /command/takeover`，觀察 ATAK 上無人機圖標是否在接管後依序轉為「橘色閃爍（Mitigating）→ 藍色（Neutralized）→ 消失（Lost）」，以及 UDS 回報的 `flight_state` 是否依序經過 `MITIGATING_TAKEOVER → LANDING → LANDED`。

**Acceptance Scenarios**:

1. **Given** UDS 以 `single_drone_invasion` 場景啟動，且無人機處於 `FLYING_NORMAL`，**When** Sentrycs Simulator 呼叫 `POST /command/takeover` 並指定降落點，**Then** UDS 必須在下一個主迴圈週期內將該無人機切換為 `MITIGATING_TAKEOVER`、重新計算往降落點的航線，且 API 回傳 `status: accepted`、`new_state: MITIGATING_TAKEOVER`。
2. **Given** 無人機處於 `MITIGATING_TAKEOVER` 或 `LANDING` 狀態，**When** 無人機高度降至 ≤ 2 m 且速度 ≤ 0.5 m/s，**Then** UDS 必須自動切換為 `LANDED`、推送最後一筆狀態至 Map Simulator 並停止後續推送。
3. **Given** 場景載入完成，**When** 由 `POST /command/takeover` 發出到 UDS 切換狀態並於 Map Simulator 反映新位置，**Then** 此端到端閉環的任一環節延遲都必須可測量且符合 SC-002。

---

### User Story 2 — Sentrycs Simulator 接管指令（Priority: P1）

Sentrycs Simulator 作為 RF 偵測模擬器，在內部狀態機進入「下令接管」時，直接呼叫 UDS 發出接管指令；位置資訊一律透過 Map Simulator 取得，不依賴 UDS 查詢端點。

**Why this priority**：沒有這條路徑，接管閉環無法觸發。`POST /command/takeover` 是 UDS `:8080` REST API 對外的**唯一正式契約**。

**Independent Test**：以 `curl` 或 Sentrycs Simulator 的單元測試，針對一個已知的 `drone_id` 呼叫 `POST /command/takeover`，驗證回應格式、HTTP 狀態碼與錯誤處理符合契約；契約測試僅涵蓋此端點。

**Acceptance Scenarios**:

1. **Given** UDS 已載入場景且 `TRK-001` 存在且處於 `FLYING_NORMAL`，**When** 以合法 body（含必填 `drone_id`、`target_lat ∈ [-90, 90]`、`target_lon ∈ [-180, 180]`、`target_alt_m ≥ 0`）呼叫 `POST /command/takeover`，**Then** 回傳 **200 OK** 且 JSON 包含 `status: accepted`、`previous_state`、`new_state: MITIGATING_TAKEOVER`。
2. **Given** 要求接管的 `drone_id` 不存在於當前場景，**When** 呼叫 `POST /command/takeover`，**Then** 回傳 **400** 並包含 `drone_id not found`。
3. **Given** 目標無人機已處於 `LANDED`，**When** 呼叫 `POST /command/takeover`，**Then** 回傳 **400** `already landed`。
4. **Given** 目標無人機仍處於 `IDLE`（尚未透過 `timeline.start_flying` 起飛），**When** 呼叫 `POST /command/takeover`，**Then** 回傳 **409 Conflict** `drone not airborne`（與 `already landed` 之 400 明確區分）。
5. **Given** request body 缺少必填欄位，或 `target_lat ∉ [-90, 90]` / `target_lon ∉ [-180, 180]`，**When** 呼叫 `POST /command/takeover`，**Then** 回傳 **400** `invalid coordinates`（缺欄位時可搭配欄位名稱的錯誤訊息）。
6. **Given** request body 中 `target_alt_m < 0` 或缺 `target_alt_m`，**When** 呼叫 `POST /command/takeover`，**Then** 回傳 **400** `invalid altitude`；`target_alt_m` 無預設值，必須由呼叫端顯式傳入。
7. **Given** 同一 `drone_id` 已處於 `MITIGATING_TAKEOVER` 或 `LANDING` 而尚未 `LANDED`，**When** 以新的合法目標再次呼叫 `POST /command/takeover`，**Then** 回傳 **200 OK** `accepted`，UDS 以最新一筆 `takeover_cmd` 覆寫舊目標（`target_lat/target_lon/target_alt_m` 取代舊值），`flight_state` 維持 `MITIGATING_TAKEOVER`，回應中不另加旗標或覆寫計數。
8. **Given** UDS 以預設模式啟動（未帶 `--debug`），**When** 呼叫 `GET /status/{drone_id}` 或 `GET /drones`，**Then** 回傳 404（路由未註冊）；僅於 `--debug` 模式才可用，且其回應 schema 不納入契約測試。

---

### User Story 3 — 感測器模擬器取得無人機位置（Priority: P1）

EchoShield Simulator（雷達）與 Sentrycs Simulator（RF）作為下游消費者，需要定期取得所有無人機的最新位置與狀態，以便套用感測器特性（雷達誤差、偵測距離、RF 狀態機）後，輸出各自的感測資料流。

**Why this priority**：UDS → Map Simulator → 感測器模擬器是 PoC 的主要資料流；若 UDS 不推送或推送內容不足，下游都無法產生有效偵測資料。

**Independent Test**：啟動 UDS 與 Map Simulator（其他元件可關閉），在 Map Simulator `:8090` 端輪詢 `GET /objects`，驗證每個主迴圈週期都會更新，且欄位完整可讓 EchoShield/Sentrycs Simulator 完成自身計算。

**Acceptance Scenarios**:

1. **Given** UDS 與 Map Simulator 都已啟動且場景含 N 架活躍無人機，**When** UDS 完成一次主迴圈更新，**Then** UDS 必須針對每架 `flight_state ≠ IDLE` 的無人機各呼叫一次 `POST http://<map-sim>:8090/objects/update`（共 N 筆請求），每筆 request body 為單一無人機 JSON（依 `08-api-icd.md` §3.1）。
2. **Given** UDS 的主迴圈頻率設為 10 Hz 且場景含 N 架活躍無人機，**When** 持續執行 10 秒，**Then** 期間 `POST /objects/update` 的實際呼叫次數必須落在 N × (95 ~ 105) 之間（每架 10±0.5 Hz，允許 ±5% 抖動）。
3. **Given** 無人機進入 `LANDED`，**When** UDS 處理切換到 `LANDED` 的那個主迴圈週期，**Then** UDS 必須對該 `drone_id` 推送恰一筆 `POST /objects/update`，其 `flight_state` 欄位明確為 `"LANDED"`；自下一個主迴圈週期起，該 `drone_id` 不再出現在任何 `POST /objects/update` 請求中。

---

### Edge Cases

- **無效 `track_id` / `drone_id` 接管**：`POST /command/takeover` 指向不存在的 `drone_id` → 400 `drone_id not found`；對已 `LANDED` 的無人機再發接管 → 400 `already landed`；對仍處於 `IDLE`（尚未起飛）的無人機發接管 → **409 Conflict `drone not airborne`**（409 與 400 明確區分，不得混用）。
- **LANDED 後再接管**：系統必須拒絕且不改變狀態（避免降落中的殭屍無人機重新起飛）；回應碼固定為 400 `already landed`。
- **無效欄位值（座標/高度越界）**：`target_lat ∉ [-90, 90]` 或 `target_lon ∉ [-180, 180]` → 400 `invalid coordinates`；`target_alt_m < 0` → 400 `invalid altitude`；`target_alt_m` 為必填且無預設值，若請求省略 `target_alt_m` → 400 `invalid altitude`（欄位缺失與負值共用同一錯誤碼，但訊息可附欄位資訊）。
- **多架同時接管**：在同一迴圈週期內收到多筆不同 `drone_id` 的接管指令時，必須各自套用而互不干擾，每筆均獨立進入 `MITIGATING_TAKEOVER`。
- **對同一 `drone_id` 連續接管（未 LANDED 前）**：尚未 `LANDED` 前對同一 `drone_id` 重複呼叫 → 回傳 **200 `accepted`**，UDS 以最新一筆 `takeover_cmd` 覆寫舊目標（新的 `target_lat/target_lon/target_alt_m` 取代舊值），`flight_state` 維持 `MITIGATING_TAKEOVER`；回應 body **不**新增任何「覆寫旗標」或「覆寫次數」欄位。
- **Map Simulator 暫時不可用**：`POST /objects/update` 逾時或回傳 5xx 時，UDS 必須記錄錯誤但**不中斷**主迴圈，下個週期繼續推送最新狀態；連線恢復後自然重新同步。
- **場景 YAML 錯誤**：缺少必要欄位（`drone_id`、`start_lat`、`landing_point`）→ 啟動時即失敗並以非零 exit code 結束。
- **場景 YAML `timeline[].action` 為未知值**：若 `timeline` 項目含非白名單（非 `start_flying`）的 `action`，`ScenarioLoader` 必須在載入階段立即拋出 `unknown action: <value>` 並以非零 exit code 結束；主迴圈、HTTP server 都不得啟動，亦不得跳過該事件繼續執行。
- **降落點距當前位置過遠**：UDS 仍執行接管，只是到達 `LANDED` 的時間較長；但必須持續推送狀態，不能無限拖延（最壞情況受 `velocity_ms`、`descent_speed_ms` 及場景地理範圍限制）。
- **時鐘跳變 / 系統休眠**：主迴圈以 wall-clock 時間計算 `dt`；若 `dt` 異常大（> 1 s），UDS 應以固定上限（如 1 s）進行單步積分，避免一次跳躍過頭。

---

## 3. Requirements *(mandatory)*

### Functional Requirements

以下需求依 `docs/system-docs/02-unified-drone-simulator-spec.md` §2 為基礎，並依 CHANGELOG v0.3 澄清移除 TCP `:9000` 相關職責，改以 `POST /objects/update` 推送為主。

- **FR-UDS-001**：UDS 必須為每架無人機維護飛行狀態物件（位置、速度、方向、高度、狀態機），並在每個主迴圈週期依 `dt` 更新該物件。
- **FR-UDS-002**：UDS 必須在每個主迴圈週期對每架 `flight_state ≠ IDLE` 的無人機各發送一次 `POST http://<map-sim-host>:8090/objects/update`（per-drone 粒度），每筆 request body 為單一無人機 JSON，欄位依 `docs/system-docs/03-map-simulator-spec.md` §3.1 與 `contracts/rest-api.md` §3.2 所定義的 8 個欄位：`drone_id`、`lat`、`lon`、`alt_m`、`speed_ms`（由 `DroneState.velocity_ms` 換算）、`heading_deg`、`status`（由 `flight_state.value` 換算）、`timestamp`。**UDS 推送不包含** `model` 或 `operator_lat/operator_lon`（這些欄位由 Sentrycs Simulator 於其 `:7070` JSON 輸出中提供，不屬於 UDS→Map Simulator 的推送契約）。
- **FR-UDS-003**：UDS 必須以 HTTP REST Server 於 `:8080` 提供**正式契約端點**：
  - `POST /command/takeover` — 接收接管指令（**唯一正式契約**，必須納入契約測試並維持向後相容）。
- **FR-UDS-003a**（除錯端點）：UDS 可選擇性提供下列除錯端點，**僅在啟動時帶 `--debug` 旗標才註冊**（預設關閉，未帶旗標時路由不存在，回應 404）：
  - `GET /status/{drone_id}` — 回傳指定無人機當前狀態。
  - `GET /drones` — 回傳所有活躍無人機的摘要清單。
  這些端點**不**納入契約測試，回應 schema 不保證跨版本穩定；Sentrycs Simulator 的正式運行路徑不得依賴，位置查詢一律透過 Map Simulator。
- **FR-UDS-004**：`POST /command/takeover` 收到有效請求後，UDS 必須在下一個主迴圈週期前將目標無人機的 `flight_state` 切換為 `MITIGATING_TAKEOVER`，並以請求中的 `target_lat`、`target_lon`、`target_alt_m` 作為新航線終點；回應必須包含 `status: accepted`、`previous_state`、`new_state` 與估計降落時間。
  - `target_lat`、`target_lon`、`target_alt_m` **皆為必填**，無預設值（呼叫端必須顯式傳入），UDS 不得自動以 `0.0` 或當前位置/高度推論。
  - 合法值域：`target_lat ∈ [-90, 90]`、`target_lon ∈ [-180, 180]`、`target_alt_m ≥ 0`（公尺，HAE）。
  - 對同一 `drone_id` 在尚未 `LANDED` 前重複呼叫（目標無人機處於 `MITIGATING_TAKEOVER` 或 `LANDING`）：回傳 **200 `accepted`**，並以本次的 `target_lat/target_lon/target_alt_m` 覆寫既有 `takeover_cmd`，`flight_state` 維持 `MITIGATING_TAKEOVER`，回應中不新增任何額外旗標或覆寫計數欄位。
- **FR-UDS-005**：UDS 必須實作飛行狀態機，狀態集合為 `{ IDLE, FLYING_NORMAL, MITIGATING_TAKEOVER, LANDING, LANDED }`，並僅允許下列轉移：
  - `IDLE → FLYING_NORMAL`（場景觸發 `start_flying`）
  - `FLYING_NORMAL → MITIGATING_TAKEOVER`（收到合法 takeover）
  - `MITIGATING_TAKEOVER → LANDING`（距降落點 ≤ 100 m 時自動進入）
  - `LANDING → LANDED`（高度 ≤ 2 m 且速度 ≤ 0.5 m/s 時自動進入）
  - `LANDED → IDLE`（預留，用於重置場景；PoC 可不實作）
- **FR-UDS-006**：UDS 必須在高度 ≤ 2 m 且速度 ≤ 0.5 m/s 時自動將無人機切換為 `LANDED`，並於該切換所在的主迴圈週期對 Map Simulator 推送恰一筆 `POST /objects/update`（request body `flight_state = "LANDED"`，作為明確的收尾旗標）；自下一個主迴圈週期起，UDS 不得再對該 `drone_id` 發送任何 `POST /objects/update`（直到場景重置）。
- **FR-UDS-007**：UDS 必須從 YAML 場景檔載入無人機清單、初始位置 / 高度 / 速度 / 航向、操控者位置、航點（waypoints）、降落點（`landing_point`）、`update_hz` 與時間軸事件（`timeline`）。`timeline[].action` 欄位採封閉白名單，PoC 階段僅允許單一值 `start_flying`；載入時遇到白名單以外的值（含拼寫錯誤、未知 action、空字串），`ScenarioLoader` 必須立即 fail-fast（拋出 `unknown action: <value>` 並以非零 exit code 結束），不得靜默忽略或跳過該事件。
- **FR-UDS-008**：UDS 必須支援直線飛行、轉向飛行與降落軌跡插值，使用 WGS84 Haversine 距離、Bearing 計算與座標偏移公式。
- **FR-UDS-009**：UDS 主迴圈頻率必須可透過 CLI 旗標 / 場景檔設定，預設 10 Hz、合法範圍 1–20 Hz。設定優先序：**CLI `--hz` > 場景檔 `scenario.update_hz` > 預設 10**（任一來源越界皆 fail-fast）。相同優先序規則套用於 `--api-port` 與 `scenario.servers.command_api_port`（CLI 覆寫 YAML 覆寫預設 8080）。
- **FR-UDS-010**：UDS 必須在單一行程內支援同時模擬至少 10 架無人機（PoC 規模上限）。
- **FR-UDS-011**：UDS CLI 必須至少提供 `--scenario`（YAML 路徑）、`--api-port`（預設 8080）、`--map-sim-url`（預設 `http://127.0.0.1:8090`）、`--hz`、`--verbose`、`--debug`（布林旗標；預設 false；啟用後才註冊 FR-UDS-003a 的除錯端點）。
- **FR-UDS-012**：UDS 必須使用 WGS84 座標系（Haversine 距離、Bearing、座標偏移皆以地球半徑 6,371,000 m 計算）。
- **FR-UDS-013**：UDS 必須對轉向實施平滑限制，每個主迴圈週期最多轉向 30°，避免方位瞬間跳變造成下游感測器模擬異常。
- **FR-UDS-014**：UDS 推送至 Map Simulator 的請求若失敗（連線拒絕、逾時、5xx），必須記錄結構化錯誤日誌且**不中止**主迴圈；下一週期依舊嘗試推送。
- **FR-UDS-015**：UDS 必須依下列規則拒絕無效的接管指令，並回傳對應 HTTP 狀態碼與錯誤訊息：
  - `drone_id` 不存在於當前場景 → **400** `drone_id not found`。
  - 目標無人機已處於 `LANDED` → **400** `already landed`。
  - 目標無人機仍處於 `IDLE`（尚未透過 `timeline.start_flying` 起飛）→ **409 Conflict** `drone not airborne`（與 `already landed` 之 400 區分，不得混用）。
  - Request body 缺少 `drone_id` / `target_lat` / `target_lon` 或欄位型別錯誤 → **400**（訊息應指出缺欄位或型別錯誤）。
  - `target_lat ∉ [-90, 90]` 或 `target_lon ∉ [-180, 180]` → **400** `invalid coordinates`。
  - `target_alt_m` 缺失或 `< 0` → **400** `invalid altitude`（`target_alt_m` 為必填、無預設值）。
  - 上述所有錯誤回應皆不得變更目標無人機的 `flight_state`，也不得產生任何 `POST /objects/update` 的副作用。

> **對 `02-spec` §2 的修正說明**：
> - 原 FR-UDS-002「TCP Server Port 9000，以 10 Hz 輸出 EchoShield JSON 格式」已改為 FR-UDS-002「每週期 `POST /objects/update`」；`:9000` 由 EchoShield Simulator 負責，不再是 UDS 的職責。
> - 原 FR-UDS-014「LANDED 後自動停止 EchoShield TCP 廣播（最後一筆 track_status: LOST）」的「廣播 / track_status」語意已改為 FR-UDS-006 的「收尾推送 / LANDED 旗標」語意：UDS 在進入 `LANDED` 的同一週期對 Map Simulator 推送恰一筆 `flight_state = "LANDED"` 的 `POST /objects/update`，之後不再推送該 `drone_id`；`track_status` 由 EchoShield Simulator 產生，非 UDS。現行 FR-UDS-014 專責「推送失敗的容錯策略」，與 LANDED 收尾語意不再共用同一條需求。
> - 原 FR-UDS-012「錯誤模擬」為選配功能，PoC 不列入必要範圍，故本規格不複述。

### Key Entities

- **DroneState**：單一無人機的完整狀態物件。
  - 識別：`drone_id`（對應 ICD `track_id`，如 `TRK-001`）、`model`（如 `DJI Mavic 3`）。
  - 位置：`lat`、`lon`（WGS84 十進位度）、`alt_m`（HAE 公尺）。
  - 運動學：`velocity_ms`、`heading_deg`（正北順時針）、目前 waypoint 指標。
  - 狀態：`flight_state`（FlightState 列舉）、`takeover_cmd`（Optional，儲存最近一筆接管指令）。
  - 操控者：`operator_lat`、`operator_lon`（供 Sentrycs 模擬器使用）。
  - 感測輔助欄位：`snr_db`、`rcs_dbsm`（提供給 EchoShield Simulator 當成固定或基礎值，非 UDS 本身的感測邏輯）。

- **FlightState（列舉）**：
  - `IDLE`：尚未起飛或重置後；UDS 不將其包含在 `POST /objects/update`。
  - `FLYING_NORMAL`：按場景航線飛行。
  - `MITIGATING_TAKEOVER`：已收到 takeover，正改變航線；高度開始遞減。
  - `LANDING`：距降落點 ≤ 100 m，高度持續降低、速度逐漸減小。
  - `LANDED`：完成降落；推送最後一筆後停止該 `drone_id` 的後續推送。

- **TakeoverCommand**：`drone_id`、`target_lat`（必填，`∈ [-90, 90]`）、`target_lon`（必填，`∈ [-180, 180]`）、`target_alt_m`（必填，公尺 HAE，`≥ 0`，**無預設值**）、`descent_speed_ms`（選填，預設 3.0 m/s）。來源為 `POST /command/takeover` 的 request body。對同一 `drone_id` 在 `LANDED` 前重複接收時，最新一筆 `TakeoverCommand` **完全覆寫**舊值，不保留歷史。

- **Scenario YAML Schema**（由 `ScenarioLoader` 讀取）：
  - `scenario.name`、`scenario.description`：識別與描述。
  - `scenario.update_hz`：主迴圈頻率（1–20）。
  - `scenario.servers.command_api_port`：UDS REST API 埠號（預設 8080）。
  - `scenario.drones[]`：每架無人機含
    - `drone_id`、`model`
    - `start_lat`、`start_lon`、`start_alt_m`
    - `speed_ms`、`heading_deg`
    - `operator_bearing_deg`、`operator_distance_m`（相對起點換算操控者位置）
    - `waypoints[]`（每個含 `lat`、`lon`、`alt_m`）
    - `landing_point`（含 `lat`、`lon`、`alt_m`、`descent_speed_ms`）
  - `scenario.timeline[]`：事件清單，每個含 `at_s`、`action`、`drone_id`。`action` 為封閉列舉，PoC 階段唯一合法值為 `start_flying`；其他值（含未知字串、空值）由 `ScenarioLoader` 在載入階段 fail-fast 拒絕。

---

## 4. Success Criteria *(mandatory)*

所有指標皆以 PoC 驗收情境為準，與技術實作無關，只描述系統外部可觀察之行為。

- **SC-001（飛行更新頻率）**：當 `update_hz` 設為 10 時，UDS 在穩態下對 Map Simulator 的 `POST /objects/update` 呼叫頻率必須達 **每架 10 ± 0.5 Hz**（以 10 秒窗口量測）；對 N 架活躍無人機而言，總請求速率即為 N × (10 ± 0.5) req/s（10 架時 ≈ 95 ~ 105 req/s）。
- **SC-002（接管閉環端到端時間）**：自 Sentrycs Simulator 呼叫 `POST /command/takeover` 成功回應起算，至該無人機在 UDS 狀態進入 `LANDED`，在預設場景（降落距離 ≤ 1 km、`descent_speed_ms = 3 m/s`）下必須 ≤ 90 秒，且在任一時刻 Map Simulator 上該無人機的位置變化必須與 UDS 的內部狀態一致。
- **SC-003（接管指令即時性）**：`POST /command/takeover` 的 HTTP 回應時間必須 ≤ 200 ms（本機），且該指令必須在 ≤ 1 個主迴圈週期內（預設 ≤ 100 ms）於 Map Simulator 推送中反映為 `MITIGATING_TAKEOVER`。
- **SC-004（多架無人機）**：UDS 必須可同時模擬至少 10 架無人機且維持 SC-001 的每架更新頻率；10 秒內推送總請求數（N × update_hz × 10 秒）偏差不超過 5%（10 架 @ 10 Hz 應為 950 ~ 1050 筆）。
- **SC-005（LANDED 偵測準確性）**：針對降落中的無人機，UDS 必須在高度首次 ≤ 2 m 且速度 ≤ 0.5 m/s 的下一個主迴圈週期內（≤ 100 ms @ 10 Hz）切換為 `LANDED`，不得有「持續抖動於 LANDING / LANDED 之間」的行為。
- **SC-006（除錯端點資料新鮮度，僅 `--debug` 模式）**：當 `--debug` 啟用時，`GET /status/{drone_id}` 回傳的 `lat/lon/alt_m/velocity_ms/flight_state` 必須來自最近一個已完成的主迴圈週期，時間誤差 ≤ 1 × 主迴圈週期；此 SC 屬觀測性輔助指標，不納入正式契約測試。
- **SC-007（Map Simulator 故障韌性）**：若 Map Simulator 連續 30 秒不可用，UDS 必須持續執行主迴圈不崩潰、並在 Map Simulator 恢復後的第一個主迴圈週期內重新成功推送。
- **SC-008（場景重現性）**：同一份 YAML 場景在相同硬體上兩次執行，在沒有外部接管指令的情況下，任一時間點同一無人機的位置差 ≤ 1 公尺（允許浮點誤差）。

---

## 5. Assumptions

- **單機部署**：UDS 與 Map Simulator、Sentrycs Simulator、EchoShield Simulator 皆運行於同一台展示主機（`127.0.0.1`）；本機通訊不需要 TLS。
- **Map Simulator 的 `POST /objects/update` 介面**以 `docs/system-docs/08-api-icd.md` 與 `03-map-simulator-spec.md` 為準；UDS 僅為 HTTP Client，介面若有調整以 Map Simulator 規格為主。
- **Sentrycs 位置查詢由 Map Simulator 承接**：Sentrycs Simulator 不透過 UDS 查詢位置；UDS 的 `GET /status/{drone_id}` 與 `GET /drones` 已降級為 `--debug` 旗標下的除錯端點（見 FR-UDS-003a），預設關閉且不納入契約測試。
- **場景規模**：最多 10 架無人機（對齊 `01-system-architecture.md` §1.2 的 PoC 範圍）。
- **地球模型**：假設 WGS84 球面模型足夠（地球半徑 6,371,000 m 常數），不做橢球體修正。
- **飛行動力學簡化**：不模擬風、不模擬慣性、不模擬馬達延遲；僅以線性插值 + 平滑轉向限制（≤ 30°/週期）近似實際飛行。
- **Clock 來源**：以行程本地 wall-clock 為唯一時間源；UDS 不負責與外部 NTP 同步。
- **永續化不在範圍內**：UDS 不寫入任何資料庫 / 檔案狀態；每次啟動從 YAML 重新初始化。
- **接管指令來源單一**：PoC 中僅 Sentrycs Simulator 會呼叫 `POST /command/takeover`，不處理多來源競爭（仍以最後一筆為準）。

---

## 6. Out of Scope

以下項目明確不屬於本功能範圍（將在未來版本或獨立功能中評估）：

- **真實硬體整合**：真實 EchoShield 4D 雷達、真實 Sentrycs C-UAS、真實無人機 / 遙控器。
- **> 10 架大規模場景**：高密度無人機群、蜂群戰術（swarm）、動態生成無人機。
- **持久化與回放**：飛行紀錄持久化、錄影 / 重播、歷史查詢 API。
- **作戰級安全**：UDS REST API 目前為明文 HTTP（本機通訊），不處理 mTLS、API Token、RBAC。
- **高可用 / 災難回復**：不支援多副本、狀態遷移、跨主機容錯。
- **真實飛行動力學**：風場、慣性、馬達響應延遲、電量 / 失速模型。
- **接管以外的指令**：如「返航」、「更改任務點」、「啟動干擾」等；本 PoC 僅需 `POST /command/takeover`。
- **UI / 控制台**：UDS 為 CLI + HTTP 服務，本規格不涵蓋圖形介面。
- **錯誤注入 / 故障模擬**：封包遺失、延遲注入等（即 `02-spec` FR-UDS-012）列為未來選配功能。

---

## 7. 參考文件

- `docs/system-docs/00-index.md`
- `docs/system-docs/01-system-architecture.md`（§2.2, §3, §4.5）
- `docs/system-docs/02-unified-drone-simulator-spec.md`（主要來源；本 spec 針對 §1.2 / FR-UDS-002 / FR-UDS-014 依 CHANGELOG v0.3 修訂）
- `docs/system-docs/03-map-simulator-spec.md`
- `docs/system-docs/08-api-icd.md`
- `docs/system-docs/CHANGELOG.md`（v0.3：Map Simulator 新增、UDS 職責拆分）
