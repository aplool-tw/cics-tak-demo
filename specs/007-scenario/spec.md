# 功能規格：端對端模擬驗證劇本（E2E Scenario Validation）

**Feature Branch**: `007-e2e-scenarios`
**Feature ID**: `007`
**Created**: 2026-05-03
**Status**: Draft

---

## Clarifications

無需 clarify — 規格已由背景說明、座標清單、YAML 格式範例及里程碑表完整定義，無模糊需澄清的決策點。

---

## 1. 背景與目的

本系統為台灣反無人機 TAK 戰術感知 PoC，由 6 個 Python 微服務組成：`uds`、`map-sim`、`echoshield-sim`、`sentrycs-sim`、`cot-gateway`、`tak-client-sim`。
目前各服務的單元功能已分別由 spec 001–006 定義；然而缺乏一組**端對端情境劇本**，導致：

1. **無法驗證跨服務整合路徑**：接管閉環（Detect → Track → Fuse → Takeover → Hold）是否在真實座標下正確觸發，無明確驗收標準。
2. **Demo 場景不具可重複性**：目前以台北市區座標演示，與作戰任務無關；每次 Demo 前需人工調整參數。
3. **CI 無法自動驗收**：缺少可在 CI pipeline 中斷言的端對端驗證腳本。

**本功能（007-scenario）目標**：

- 設計兩個以**戰略地理座標**為基礎的劇本 YAML：劇本一（單機滲透攔截）、劇本二（三機多方向同時滲透）。
- 定義每個劇本的里程碑觸發條件與預期行為，作為整合測試的驗收基準。
- 提供可透過 `scripts/dev-launcher.sh` 一鍵啟動的執行方式，以及可在 CI 中使用的自動驗證腳本。

### 戰略地理座標

| 地點 | 說明 | 緯度 | 經度 |
|------|------|------|------|
| SP（Strategic Point） | 受保護目標 | 24.725806 | 121.033750 |
| HP（Holding Point） | 接管後管制停留地點，SP 正東方 ~3.86 km | 24.725806 | 121.071889 |

---

## 2. User Scenarios & Testing *(mandatory)*

### User Story 1 — 操作員演練劇本一：單機滲透攔截全程（Priority: P1）

作戰演練操作員以 `scripts/dev-launcher.sh` 啟動劇本一，親眼觀察一架無人機從正北方 5km 處向戰略要點逼近、被 EchoShield 雷達偵測（灰色圖標）、被 Sentrycs RF 融合標注（紅色圖標），最後在 1km 處被接管、改飛至正東方管制停留地點的完整作戰流程。整個流程在 `tak-client-sim` console 可觀察到每個狀態轉換訊息，作為 TAK Server 顯示的代理驗證。

**Why this priority**：這是 PoC 對外展示的主要路徑，也是所有跨服務整合的基本可用性驗收場景。若此故事不成立，下游所有驗證都失去意義。

**Independent Test**：啟動全棧後，執行 `scripts/dev-launcher.sh --uds-scenario services/uds/scenarios/e2e_single_drone.yaml --sentrycs-scenario services/sentrycs-sim/config/e2e_single_drone.yaml`；不需額外手動操作，靜觀 `tak-client-sim` console 輸出，在 10 分鐘內應依序出現 M1 → M4 里程碑對應的 CoT 事件。

**Acceptance Scenarios**:

1. **Given** 全棧以劇本一 YAML 啟動，**When** 場景計時器達到 `at_s=0`（M1），**Then** UDS 建立無人機 `TRK-E01`，並於下一個主迴圈週期對 map-sim 推送第一筆 `flight_state=FLYING_NORMAL` 的位置更新；map-sim `GET /objects` 可查到該 drone。
2. **Given** 無人機飛行至距 SP 約 3km（M2），**When** echoshield-sim 在感測範圍內偵測到該 drone，**Then** echoshield-sim 發送 NDJSON 航跡至 cot-gateway；cot-gateway 於 1.5s 內輸出 `uid=ECHO-TRK-E01`、`type=a-u-A-M-F-Q-r` 的 CoT XML；tak-client-sim console 印出灰色未識別目標。
3. **Given** 無人機到達距 SP 約 2km（M3），**When** sentrycs-sim 將該 drone 標注為 `DETECTED`，**Then** cot-gateway 在 1.5s 內對舊 uid `ECHO-TRK-E01` 推送 `stale=now` 的清場 CoT，並發出新的 `uid=FUSED-TRK-E01`、`type=a-h-A-M-F-Q-r` 融合 CoT；tak-client-sim console 可觀察到 uid 切換與顏色升級。
4. **Given** 無人機到達距 SP 約 1km（M4），**When** sentrycs-sim 發送 `POST /command/takeover` 至 uds，目標座標為 HP（24.725806, 121.071889），**Then** uds 在下一個主迴圈週期將 `flight_state` 切換為 `MITIGATING_TAKEOVER`、重新計算往 HP 的航線；此後 tak-client-sim 持續收到 `FUSED-TRK-E01` 的位置更新，直到無人機降落於 HP 附近。

---

### User Story 2 — 操作員演練劇本二：三機多方向同時滲透（Priority: P1）

作戰演練操作員以 `scripts/dev-launcher.sh` 啟動劇本二，驗證系統能同時追蹤三架從不同方向逼近戰略要點的無人機，且相互間 CoT uid 不會混淆。三架無人機的接管指令各自獨立觸發，最終均降落於管制停留地點附近。

**Why this priority**：多機同時滲透是 PoC 的壓力驗收場景，驗證 TrackCorrelator 的跨機區分能力與 UDS 並行狀態管理正確性，同等重要。

**Independent Test**：啟動全棧後，執行劇本二多機 YAML；在 15 分鐘內觀察 tak-client-sim console，確認出現三個不同 uid 系列（`ECHO-TRK-E0A`/`B`/`C`、`FUSED-TRK-E0A`/`B`/`C`）的完整狀態序列，且每個 uid 的狀態轉換彼此獨立不交叉。

**Acceptance Scenarios**:

1. **Given** 全棧以劇本二 YAML 啟動，**When** 場景依 Drone A（at_s=0）、Drone B（at_s=30）、Drone C（at_s=60）錯開起飛，**Then** map-sim `GET /objects` 在 t=60s 後可同時查到三架 drone 的位置，各自的 `lat`/`lon` 符合各自航向的預期位置。
2. **Given** 三架 drone 各自到達其 3km 里程碑時，**When** echoshield-sim 偵測，**Then** 分別產生 `ECHO-TRK-E0A`、`ECHO-TRK-E0B`、`ECHO-TRK-E0C` 三個不同 uid 的 CoT，tak-client-sim console 不出現跨 drone uid 混用。
3. **Given** 三架 drone 各自到達其 2km 里程碑，**When** sentrycs-sim 分別標注 DETECTED，**Then** cot-gateway 分別對三個 uid 升級為 `FUSED-TRK-E0A`/`E0B`/`E0C`（各自的清場 + 首筆融合），三次切換彼此獨立。
4. **Given** 三架 drone 分別到達其 1km 里程碑，**When** sentrycs-sim 對每架 drone 各發送一次 `POST /command/takeover`，**Then** uds 為三架 drone 各自切換 `MITIGATING_TAKEOVER`；三筆接管互不干擾；最終三架 drone 均降落於 HP 附近（座標誤差 ≤ 50m）。
5. **Given** 三架 drone 同時在飛行中（無人機 B 剛起飛），**When** 查詢任一 `FUSED-TRK-E0X` 的最新 CoT，**Then** 其 `<point>` 座標對應該 drone 的實際位置，不會出現另一架 drone 的座標。

---

### User Story 3 — CI 腳本自動驗證劇本完整性（Priority: P2）

CI pipeline（或本地開發者）透過 `specs/007-scenario/scripts/validate_scenario.py` 對執行中的全棧發起黑箱驗證：抓取 tak-client-sim 的 console 輸出或直接解析 CoT XML 事件流，逐一核對里程碑觸發順序、uid 一致性、CoT type、stale 時間計算，最後輸出 PASS/FAIL 報告。

**Why this priority**：Demo 前可作為冒煙測試；CI pipeline 可在每次 PR merge 後自動跑，防止回歸。P2 是因快樂路徑（Story 1/2）可先人工驗收，但自動化驗收是交付品質的護欄。

**Independent Test**：在全棧正常運行劇本一期間，於另一個 terminal 執行 `python specs/007-scenario/scripts/validate_scenario.py --scenario single`；腳本在場景結束後輸出 PASS + 各里程碑的通過/失敗細節，exit code 0。

**Acceptance Scenarios**:

1. **Given** 劇本一正在執行，**When** `validate_scenario.py --scenario single` 在場景完成後執行（或以 `--wait` 等待完成），**Then** 腳本輸出涵蓋 M1~M4 四個里程碑的 PASS/FAIL 行，每行格式為 `[PASS|FAIL] M{n}: {description}`，整體 exit code 反映最終結果（0=全通過，1=有失敗）。
2. **Given** 某里程碑（例如 FUSED CoT）在預期時間窗口（+30s 緩衝）內未出現，**When** 驗證腳本逾時，**Then** 輸出 `[FAIL] M3: FUSED CoT not observed within timeout`，exit code=1。
3. **Given** 劇本二（三機）執行完成，**When** `validate_scenario.py --scenario multi` 執行，**Then** 針對三架 drone 各自輸出四個里程碑的驗證結果（共 12 行 M 指標），且跨 drone uid 混淆計數輸出為 0。

---

### User Story 4 — 操作員確認 CoT 合規性（Priority: P2）

安全技術操作員在 Demo 前透過 `specs/007-scenario/scripts/validate_cot.py` 對 cot-gateway 的輸出串流進行靜態合規驗證：確認 CoT type 字串、stale 計算、uid 前綴格式、source 切換時的雙訊息機制均符合 `005-cot-gateway` spec 所定義的凍結契約。

**Why this priority**：CoT 合規是 ATAK 顯示正確的前提，若 type 或 stale 不符則 ATAK 顏色或存留時間錯誤，影響 Demo 質量。

**Independent Test**：執行劇本一，同時以 `validate_cot.py --tap-host 127.0.0.1 --tap-port 8089` 抓取 cot-gateway 輸出；場景結束後驗證腳本輸出合規報告，無 `[FAIL]` 項目。

**Acceptance Scenarios**:

1. **Given** cot-gateway 正在輸出 CoT XML 事件，**When** `validate_cot.py` 解析每筆事件，**Then** 所有 `ECHO-` 或 `SENTRYCS-` uid 的 `type` 屬性均為 `a-u-A-M-F-Q-r`；所有 `FUSED-` uid 的 `type` 均為 `a-h-A-M-F-Q-r`；任何違規輸出 `[FAIL] COT-TYPE: uid={uid} expected={expected} got={actual}`。
2. **Given** CoT 事件的 `detection_status` 為 `DETECTED` 或 `MITIGATING`，**When** 驗證 stale 欄位，**Then** `stale` = `time + 11s`（允許 ±1s 計算誤差）；NEUTRALIZED 為 `time + 30s`；Lost/清場事件為 `time`。
3. **Given** source 從 `ECHO-TRK-E01` 升級為 `FUSED-TRK-E01`，**When** 驗證事件序列，**Then** 在新 uid 首次出現之前，舊 uid 必須有一筆 `stale ≤ time` 的清場事件（雙訊息機制），若缺少清場事件輸出 `[FAIL] COT-STALE-CLEAR: missing stale-now for {old_uid}`。

---

### User Story 5 — 操作員使用 dev-launcher.sh 整合啟動劇本（Priority: P2）

操作員或開發者透過單一 `dev-launcher.sh` 指令並附帶 `--uds-scenario` 與 `--sentrycs-scenario` 參數，一鍵選擇要執行的劇本 YAML，不需修改任何服務程式碼或手動設定環境變數。

**Why this priority**：降低執行門檻，確保 Demo 可重複，並為 CI pipeline 提供一致的啟動介面。

**Independent Test**：於全乾淨狀態下執行 `scripts/dev-launcher.sh --uds-scenario services/uds/scenarios/e2e_single_drone.yaml --sentrycs-scenario services/sentrycs-sim/config/e2e_single_drone.yaml`；6 個服務在 30s 內全部啟動並顯示 `[OK]` 狀態；無需任何額外配置。

**Acceptance Scenarios**:

1. **Given** `dev-launcher.sh` 已支援 `--uds-scenario` 與 `--sentrycs-scenario` 參數，**When** 傳入本功能新增的劇本 YAML 路徑，**Then** UDS 載入指定 YAML、sentrycs-sim 載入指定 config，其餘服務 URL 由 `dev-launcher.sh` 自動推導，無需額外 `--*-url` 參數。
2. **Given** `dev-launcher.sh --status` 執行中，**When** 所有服務正常運行，**Then** 輸出欄位包含各服務 PID 與 port，可確認劇本 YAML 是否已正確傳入（logs/<service>.log 首行記錄 YAML 路徑）。

---

### Edge Cases

- **時間錯開超時**：劇本二中若 Drone B/C 因計時問題未能在預期時間起飛，驗證腳本應以 `[FAIL] M1-B: start_flying timeout` 而非靜默通過。
- **Network partition**：cot-gateway 與 TAK Server 間的 TCP 中斷期間，CoT 事件應由 gateway 快取並在重連後補送；驗證腳本需允許最多 30s 的延遲窗口後再判定里程碑超時。
- **Takeover 位置偏差**：由於 UDS 以離散主迴圈（10 Hz）更新位置，接管後無人機最終降落點與 HP 座標理論上存在 ≤ 5m 偏差（飛越判斷點）；驗收標準設定為 ≤ 50m，給予充足容差。
- **CoT 事件丟失**：tak-client-sim 若以 console 輸出解析為驗證方式，需考慮日誌截斷；驗證腳本應優先從 cot-gateway 直接抓取事件，而非依賴 tak-client-sim 的 stdout。
- **同架 drone 重複接管**：在 M4 觸發後、drone 抵達 HP 前，若 sentrycs-sim 因競態再次發送 takeover，UDS 應接受並以最新目標覆寫（依 `001-uds` spec）；驗證腳本應確認最終降落點為最後一次 takeover 的目標，而非第一次。

---

## 3. Requirements *(mandatory)*

### FR-SCN-001 ～ FR-SCN-010：劇本一 — 單機滲透攔截 YAML 設計

**FR-SCN-001**：系統 MUST 提供 UDS 劇本一 YAML 檔案 `services/uds/scenarios/e2e_single_drone.yaml`，其內容包含以下欄位，且所有座標使用戰略地理座標：

| 欄位 | 值 |
|------|----|
| `scenario.name` | `"e2e_single_drone_invasion"` |
| `drones[0].drone_id` | `"TRK-E01"` |
| `drones[0].model` | `"DJI Mavic 3"` |
| `drones[0].start_lat` | `24.806556` |
| `drones[0].start_lon` | `121.033750` |
| `drones[0].start_alt_m` | `150.0` |
| `drones[0].speed_ms` | `15.0` |
| `drones[0].heading_deg` | `180.0` |
| `drones[0].waypoints[0]` | `{ lat: 24.725806, lon: 121.033750, alt_m: 150.0 }` |
| `drones[0].landing_point` | `{ lat: 24.725806, lon: 121.071889, alt_m: 0.0, descent_speed_ms: 3.0 }` |

**FR-SCN-002**：UDS 劇本一 timeline MUST 包含恰一個 `start_flying` 事件，`at_s: 0`，`drone_id: "TRK-E01"`，以符合 `001-uds` spec 的封閉白名單約束。

**FR-SCN-003**：系統 MUST 提供 sentrycs-sim 劇本一設定檔 `services/sentrycs-sim/config/e2e_single_drone.yaml`，其 `sensor_lat` / `sensor_lon` 設定為 SP 座標（`24.725806`, `121.033750`）。

**FR-SCN-004**：sentrycs-sim 劇本一設定檔 MUST 包含 `drones` 陣列，恰好含一個 drone 條目，`uid: TRK-E01`、`model: "DJI Mavic 3"`，且三個時間戳欄位（`detected_at_s`、`mitigating_at_s`、`neutralized_at_s`）須與下表里程碑計算一致（允許 ±30s 調校）：

| 里程碑 | 距 SP 距離 | 約略飛行時間（15 m/s）| sentrycs YAML 欄位 | 建議值 |
|--------|-----------|----------------------|-------------------|--------|
| M3 DETECTED | 2 km | ≈ 470 s | `detected_at_s` | 460 |
| M4 MITIGATING（發送 takeover） | 1 km | ≈ 535 s | `mitigating_at_s` | 525 |
| NEUTRALIZED（接管完成） | HP 附近 | ≈ 575 s | `neutralized_at_s` | 565 |

> 建議值以起點距 SP 約 8.99 km、速度 15 m/s 計算；實際調校以驗證腳本 M4 通過為準。

**FR-SCN-005**：UDS 劇本一的 `operator_bearing_deg` 及 `operator_distance_m` 欄位 MUST 填入合理的操作員位置估算值，使 Sentrycs `GET /detections` 回應中的操作員座標有意義（建議 `bearing=225`、`distance=300`）。

**FR-SCN-006**：劇本一所有新增檔案不得修改現有服務程式碼（`services/` 下的 `.py` 檔案），僅新增或修改 YAML 設定檔與 `specs/007-scenario/` 下的腳本檔。

**FR-SCN-007**：劇本一 YAML 所定義的 M2 里程碑（3km）觸發條件為「EchoShield 感測範圍涵蓋 drone 當前位置」，由 echoshield-sim 的感測範圍設定控制；本規格 MUST 確認 echoshield-sim 的感測半徑設定覆蓋至少 3km，否則需在劇本說明文件中指出需調整的設定欄位。

**FR-SCN-008**：劇本一 YAML 設計 MUST 在 `specs/007-scenario/` 下附帶一份 `scenario1-milestones.md`，列出四個里程碑的觸發條件、預期座標範圍、對應 CoT 事件（uid、type、stale 規則），作為人工驗收的參考清單。

**FR-SCN-009**：劇本一的 sentrycs takeover 指令 MUST 以 HP 作為目標座標（`target_lat: 24.725806`、`target_lon: 121.071889`、`target_alt_m: 0.0`）。若 sentrycs-sim 以 YAML 中的 `landing_point` 欄位自動繼承 UDS 的 `landing_point`，則 sentrycs YAML 可省略此欄位，但 spec 需明確記錄此繼承行為。

**FR-SCN-010**：劇本一完整執行時間 MUST ≤ 12 分鐘（從 at_s=0 到 drone LANDED），以確保 Demo 節奏可控。

---

### FR-SCN-011 ～ FR-SCN-020：劇本二 — 三機多方向同時滲透 YAML 設計

**FR-SCN-011**：系統 MUST 提供 UDS 劇本二 YAML 檔案 `services/uds/scenarios/e2e_multi_drone.yaml`，包含三架 drone，座標及航向如下：

| Drone ID | 起點緯度 | 起點經度 | 高度 AGL | 速度 | heading_deg |
|----------|---------|---------|---------|------|-------------|
| `TRK-E0A` | 24.806556 | 121.033750 | 120.0 m | 12 m/s | 180.0 |
| `TRK-E0B` | 24.725806 | 120.962306 | 130.0 m | 12 m/s | 90.0 |
| `TRK-E0C` | 24.784500 | 121.087278 | 140.0 m | 12 m/s | 225.0 |

**FR-SCN-012**：劇本二三架 drone 的 `waypoints` 及 `landing_point` MUST 均指向 HP（`lat: 24.725806`, `lon: 121.071889`）作為接管後降落目標；初始 `waypoints` 可填入 SP 作為原始侵入終點（takeover 前的航線）。

**FR-SCN-013**：劇本二 UDS timeline MUST 包含三個 `start_flying` 事件，錯開時間如下：

```
- { at_s: 0,  action: start_flying, drone_id: "TRK-E0A" }
- { at_s: 30, action: start_flying, drone_id: "TRK-E0B" }
- { at_s: 60, action: start_flying, drone_id: "TRK-E0C" }
```

**FR-SCN-014**：系統 MUST 提供 sentrycs-sim 劇本二設定檔 `services/sentrycs-sim/config/e2e_multi_drone.yaml`，包含對應三架 drone 的 uid 條目（`TRK-E0A`、`TRK-E0B`、`TRK-E0C`），各自的 `detected_at_s` / `mitigating_at_s` / `neutralized_at_s` 依各 drone 各方向的飛行時間計算（見下表）：

| Drone | 起點距 SP | M3 DETECTED（≈） | M4 MITIGATING（≈） | NEUTRALIZED（≈） |
|-------|---------|---------------|-----------------|----------------|
| TRK-E0A（北→南，12 m/s） | ≈ 8.99 km | detected_at_s: 580 | mitigating_at_s: 666 | neutralized_at_s: 706 |
| TRK-E0B（西→東，12 m/s） | ≈ 7.22 km | detected_at_s: 406 | mitigating_at_s: 489 | neutralized_at_s: 519 |
| TRK-E0C（東北→西南，12 m/s） | ≈ 8.48 km | detected_at_s: 600 | mitigating_at_s: 684 | neutralized_at_s: 716 |

> 所有值為絕對場景時間（秒），含起飛時間偏移；調校容許 ±30s。

**FR-SCN-015**：劇本二三架 drone 的 `operator_bearing_deg` 及 `operator_distance_m` MUST 各自反映不同操作員位置：A → `bearing=180, distance=300`；B → `bearing=270, distance=350`；C → `bearing=45, distance=280`。

**FR-SCN-016**：劇本二 YAML 設計 MUST 在 `specs/007-scenario/` 下附帶 `scenario2-milestones.md`，為三架 drone 各自列出 M1～M4 里程碑，格式與劇本一一致。

**FR-SCN-017**：劇本二設計 MUST 確保三架 drone 的里程碑不會在同一秒觸發超過兩個（避免 cot-gateway 瞬間事件洪流導致 CoT queue 堆積）；若計算顯示衝突，YAML 中的時間偏移需調整使相鄰里程碑間隔 ≥ 10s。

**FR-SCN-018**：劇本二的 sentrycs-sim YAML 中，每架 drone 的 `neutralized_at_s` 對應的 takeover 指令目標 MUST 均為 HP 座標，不得使用各架 drone 的不同降落點。

**FR-SCN-019**：劇本二設計 MUST 驗證三個 `TRK-E0X` uid 間，在任意時刻 cot-gateway 的 TrackCorrelator 不會因距離閾值（50m）跨機誤關聯；三架 drone 在飛行路徑上的最短距離 MUST > 300m（可由幾何計算確認）。

**FR-SCN-020**：劇本二完整執行時間 MUST ≤ 18 分鐘（從 at_s=0 到最後一架 drone LANDED）。

---

### FR-SCN-021 ～ FR-SCN-030：整合驗證 — CoT 合規與 tak-client-sim 觀察

**FR-SCN-021**：`tak-client-sim` MUST 在 console 輸出中可觀察到以下事件序列（劇本一）：

```
[t≈0]    M1: TRK-E01 FLYING_NORMAL - map-sim updated
[t≈400]  M2: ECHO-TRK-E01 type=a-u-A-M-F-Q-r (gray) → TAK
[t≈470]  M3: FUSED-TRK-E01 type=a-h-A-M-F-Q-r (red) → TAK [STALE-CLEAR ECHO-TRK-E01]
[t≈535]  M4: takeover accepted → TRK-E01 MITIGATING_TAKEOVER heading HP
[t≈600]  TRK-E01 LANDED at HP ±50m
```

**FR-SCN-022**：CoT XML 的 `type` 屬性 MUST 嚴格遵守以下規則（凍結契約，不得因 `detection_status` 切換而改變）：
- `ECHO-*` uid → `a-u-A-M-F-Q-r`
- `SENTRYCS-*` uid → `a-u-A-M-F-Q-r`
- `FUSED-*` uid → `a-h-A-M-F-Q-r`

**FR-SCN-023**：CoT XML 的 `stale` 屬性 MUST 遵守以下計算規則：

| 狀態 | stale 計算 |
|------|-----------|
| Lost / 清場（source 切換舊 uid） | `stale = time`（立即過期） |
| NEUTRALIZED | `stale = time + 30s` |
| 其他（Active / DETECTED / MITIGATING） | `stale = time + 11s` |

**FR-SCN-024**：Source 切換事件（ECHO → FUSED）MUST 依照雙訊息機制：cot-gateway 先推送舊 uid（`ECHO-TRK-E01`）的 `stale=time` CoT（清場），再推送新 uid（`FUSED-TRK-E01`）的首筆 CoT；兩筆訊息 MUST 在同一個處理週期（≤ 500ms）內先後發出。

**FR-SCN-025**：uid 前綴格式 MUST 嚴格為：
- EchoShield 單源：`ECHO-{track_id}`（例 `ECHO-TRK-E01`）
- Sentrycs 單源：`SENTRYCS-{rf_id}`（例 `SENTRYCS-TRK-E01`）
- 融合：`FUSED-{rf_id}`（例 `FUSED-TRK-E01`）

**FR-SCN-026**：在劇本二中，三架 drone 的 uid 串列 MUST 各自獨立，驗證期間 FUSED-TRK-E0A 的 CoT 事件中不得出現 TRK-E0B 或 TRK-E0C 的座標。

**FR-SCN-027**：tak-client-sim 的 console 輸出格式 MUST 包含至少以下欄位，供驗證腳本解析：
```
[ISO8601_TIMESTAMP] uid=<uid> type=<cot_type> lat=<lat> lon=<lon> stale=<stale> status=<status>
```

**FR-SCN-028**：在劇本一中，接管後無人機（`TRK-E01`）的最終 LANDED 座標 MUST 與 HP（24.725806, 121.071889）的 Haversine 距離 ≤ 50m；此值需由驗證腳本計算並記錄。

**FR-SCN-029**：所有劇本中，EchoShield 的 NDJSON 資料流 MUST 以 `track_id` 與 UDS `drone_id` 一一對應（即 `ECHO-TRK-E01` ← UDS `TRK-E01`），不得出現 track_id 與 drone_id 不對應的事件。

**FR-SCN-030**：驗證清單 `specs/007-scenario/checklists/requirements.md` MUST 包含覆蓋 FR-SCN-001～FR-SCN-050 的核查項目，並在每次劇本執行後可手動或自動更新勾選狀態。

---

### FR-SCN-031 ～ FR-SCN-040：自動驗證腳本

**FR-SCN-031**：系統 MUST 提供 Python 驗證腳本 `specs/007-scenario/scripts/validate_scenario.py`，支援 `--scenario {single|multi}` 參數，可獨立執行不依賴 pytest 或外部框架（標準函式庫 + `requests`）。

**FR-SCN-032**：`validate_scenario.py` MUST 透過輪詢 map-sim `GET /objects` 驗證 M1 里程碑（UDS 啟動後 drone 出現於 map-sim 物件列表），每 2s 輪詢一次，超時 60s 則輸出 FAIL。

**FR-SCN-033**：`validate_scenario.py` MUST 透過解析 tak-client-sim 的日誌檔（預設路徑：`logs/tak-client-sim.log`）或直接監聽 cot-gateway 的 CoT XML 輸出，驗證 M2～M4 里程碑；腳本 MUST 支援 `--cot-log <path>` 參數覆蓋預設路徑。

**FR-SCN-034**：`validate_scenario.py` MUST 在每個里程碑驗證中檢查以下條件：

| 里程碑 | 驗證項目 |
|--------|---------|
| M2 | `uid=ECHO-TRK-E0X`、`type=a-u-A-M-F-Q-r` 出現於日誌 |
| M3 | 先有 `uid=ECHO-TRK-E0X stale≤now`（清場），後有 `uid=FUSED-TRK-E0X type=a-h-A-M-F-Q-r` |
| M4 | `uid=FUSED-TRK-E0X status=MITIGATING_TAKEOVER` 出現，且隨後 lat/lon 接近 HP |
| LANDED | 最後一筆 `TRK-E0X` 事件的 lat/lon 與 HP 距離 ≤ 50m |

**FR-SCN-035**：`validate_scenario.py` 的輸出 MUST 符合以下格式，以便 CI 解析：

```
[PASS] M1: TRK-E01 appears in map-sim within 10s
[PASS] M2: ECHO-TRK-E01 CoT (gray) observed at t=401s
[PASS] M3: FUSED-TRK-E01 CoT (red) observed, stale-clear for ECHO-TRK-E01 present
[PASS] M4: MITIGATING_TAKEOVER received, drone heading HP
[PASS] LANDED: TRK-E01 at (24.725801, 121.071842), dist=6.2m ≤ 50m

RESULT: PASS (5/5 milestones validated)
```

**FR-SCN-036**：`validate_scenario.py` 的 exit code MUST 為 0（全部 PASS）或 1（任何 FAIL），以供 CI pipeline（如 GitHub Actions）判斷。

**FR-SCN-037**：系統 MUST 提供 CoT 合規驗證腳本 `specs/007-scenario/scripts/validate_cot.py`，接受 `--cot-log <path>` 並輸出 CoT type、stale、uid 前綴的逐筆合規報告；違規條目輸出 `[FAIL]`，合規條目輸出 `[PASS]`。

**FR-SCN-038**：`validate_cot.py` MUST 統計以下指標並在報告末行輸出：
- 總事件數
- 違規 CoT type 數
- 違規 stale 計算數（允許 ±1s 誤差）
- 缺少清場事件（source 切換雙訊息）的次數
- 跨 drone uid 混淆次數（三機劇本）

**FR-SCN-039**：兩個驗證腳本 MUST 可在不啟動任何服務的情況下，對歷史日誌檔執行離線驗證（`--offline` 模式，僅解析日誌，不輪詢 map-sim）。

**FR-SCN-040**：`specs/007-scenario/scripts/` 下 MUST 提供 `README.md`，說明腳本的執行前提（已安裝 Python 3.9+、`requests` 函式庫）、參數說明、典型使用範例（含 CI pipeline YAML 片段）。

---

### FR-SCN-041 ～ FR-SCN-050：dev-launcher.sh 整合啟動

**FR-SCN-041**：`scripts/dev-launcher.sh` MUST 已支援（或需擴充支援）`--uds-scenario <path>` 參數，該參數值直接傳遞給 UDS 的 `--scenario` CLI 旗標。若 dev-launcher.sh 目前已支援此參數（依現有程式碼確認），本 spec 僅需驗證新劇本 YAML 路徑可正確傳入；若不支援，需在 `scripts/dev-launcher.sh` 新增此參數（不屬於服務程式碼修改限制範圍）。

**FR-SCN-042**：`scripts/dev-launcher.sh` MUST 已支援（或需擴充支援）`--sentrycs-scenario <path>` 參數，傳遞給 sentrycs-sim 的 config 路徑。

**FR-SCN-043**：以下兩個啟動命令 MUST 可正常執行劇本一與劇本二：

```bash
# 劇本一
scripts/dev-launcher.sh \
  --uds-scenario services/uds/scenarios/e2e_single_drone.yaml \
  --sentrycs-scenario services/sentrycs-sim/config/e2e_single_drone.yaml

# 劇本二
scripts/dev-launcher.sh \
  --uds-scenario services/uds/scenarios/e2e_multi_drone.yaml \
  --sentrycs-scenario services/sentrycs-sim/config/e2e_multi_drone.yaml
```

**FR-SCN-044**：`dev-launcher.sh` 啟動後，所有 6 個服務 MUST 在 30s 內進入健康狀態（可透過 `--status` 確認）；若任一服務啟動失敗，launcher 應輸出錯誤並停止啟動剩餘服務。

**FR-SCN-045**：`dev-launcher.sh --stop` 執行後，MUST 確保所有服務 process 終止，`logs/` 下各 `.pid` 檔案清除，以確保下次啟動不會因殘留 pid 衝突而失敗。

**FR-SCN-046**：`specs/007-scenario/` MUST 提供 `README.md`，包含：
1. 快速啟動劇本一的 one-liner
2. 快速啟動劇本二的 one-liner
3. 執行驗證腳本的 one-liner
4. 里程碑預期輸出的範例
5. 常見問題排查（port 衝突、UDS YAML 路徑錯誤等）

**FR-SCN-047**：本功能新增的所有 YAML 及腳本檔案 MUST 透過執行劇本一端對端流程驗證（手動或 CI）後才標記為 `Status: Approved`；spec.md 的狀態欄位應從 `Draft` 更新為 `Approved`。

**FR-SCN-048**：新劇本 YAML 的所有座標精度 MUST 保留至小數點後 6 位（例 `24.725806`，對應地面精度約 ±0.11m）。

**FR-SCN-049**：`specs/007-scenario/` 目錄結構 MUST 符合以下佈局：

```
specs/007-scenario/
├── spec.md                           # 本規格文件
├── README.md                         # 快速啟動說明
├── scenario1-milestones.md           # 劇本一里程碑清單
├── scenario2-milestones.md           # 劇本二里程碑清單
├── checklists/
│   └── requirements.md              # 規格品質驗收清單
└── scripts/
    ├── README.md                     # 腳本說明
    ├── validate_scenario.py          # 劇本里程碑驗證
    └── validate_cot.py               # CoT 合規驗證
```

**FR-SCN-050**：當劇本一或劇本二的任何 YAML 設定值需調整時，MUST 在 `scenario1-milestones.md` 或 `scenario2-milestones.md` 中同步更新對應的時間估算，以確保文件與實際行為一致。

---

## 4. Success Criteria *(mandatory)*

### SC-SCN-001 — 劇本一端對端可觀察性

劇本一從啟動到 drone LANDED，在 12 分鐘內，`tak-client-sim` console 必須依序輸出所有四個里程碑（M1～M4）對應的事件，且每個里程碑事件之間的出現順序正確，不得出現倒序或缺漏。

**量化基準**：4 個里程碑事件均在 720s 內按序出現；M2 相對 M1 延遲 ≤ 450s；M3 相對 M2 延遲 ≤ 120s；M4 相對 M3 延遲 ≤ 120s。

### SC-SCN-002 — 接管位置精度

劇本一及劇本二中，每架 drone 在收到 takeover 指令後，最終 LANDED 座標與 HP（24.725806, 121.071889）的 Haversine 距離 MUST ≤ 50m（由驗證腳本計算並記錄）。

**量化基準**：95% 的 takeover 測試運行中，最終降落座標誤差 ≤ 50m；單次最大誤差不超過 100m。

### SC-SCN-003 — CoT 事件序列完整性（劇本一）

劇本一 CoT 事件流必須包含：
1. 至少 1 筆 `ECHO-TRK-E01` 的 `type=a-u-A-M-F-Q-r` 事件
2. 恰好 1 筆 `ECHO-TRK-E01` 的 `stale=time`（清場）事件
3. 至少 1 筆 `FUSED-TRK-E01` 的 `type=a-h-A-M-F-Q-r` 事件
4. 清場事件 MUST 先於 FUSED 首筆事件（時序驗證）

**量化基準**：連續執行 5 次劇本一，以上 4 個條件均通過。

### SC-SCN-004 — 三機獨立性（劇本二）

劇本二中，三架 drone 的 CoT uid 系列（`FUSED-TRK-E0A`/`B`/`C`）MUST 互不干擾：

- 跨 drone uid 混淆次數 = 0（即 `FUSED-TRK-E0A` 的 `<point>` 座標永遠對應 Drone A 的位置，與 B/C 無關）
- 三筆 takeover 指令各自獨立到達 uds，無丟失

**量化基準**：`validate_cot.py` 輸出的跨 drone uid 混淆次數 = 0；三架 drone 的 M4 里程碑均在各自 timeout 窗口內通過。

### SC-SCN-005 — CoT type 合規率

全劇本（一 + 二）執行中，所有 CoT 事件的 `type` 屬性合規率 MUST = 100%（0 違規）；stale 計算合規率 MUST ≥ 99%（允許 ±1s 計算誤差，在 stale 判斷時使用）。

**量化基準**：`validate_cot.py` 輸出的違規 CoT type 數 = 0；違規 stale 計算數 / 總事件數 < 1%。

### SC-SCN-006 — 驗證腳本可靠性

`validate_scenario.py` 在劇本一正常執行下（無 network partition），連續 5 次執行均輸出 `RESULT: PASS`，無誤報（False Negative）；exit code 一致為 0。

**量化基準**：5 次執行成功率 = 100%；腳本執行時間（不含等待場景完成）≤ 30s。

### SC-SCN-007 — dev-launcher.sh 啟動時間

使用 `dev-launcher.sh` 啟動劇本一時，6 個服務從命令執行到全部健康（`--status` 均顯示 OK）的時間 MUST ≤ 30s（在本地開發機上，不含 Python 環境安裝時間）。

**量化基準**：在 Python 依賴已安裝的環境下，啟動時間 ≤ 30s；測量 3 次取最大值。

### SC-SCN-008 — 劇本二完整執行時間

劇本二從 at_s=0 到最後一架 drone（TRK-E0A，最長飛行路徑）LANDED，總執行時間 MUST ≤ 18 分鐘。

**量化基準**：`LANDED` 事件在 at_s=1080s（18 分鐘）之前出現於 tak-client-sim console。

---

## 5. Key Entities

**ScenarioSpec**：代表一個完整劇本的設定描述，包含所有 drone 的初始狀態（起點、速度、航向、高度）、飛行路徑（waypoints）、接管後降落點（landing_point）、時間軸事件（timeline）。對應 UDS YAML `scenario` 頂層節點。關聯 `DroneProfile`（1 對多）與 `MilestoneSet`（1 對 1）。

**DroneProfile**：代表劇本中一架無人機的全部參數，包含：`drone_id`（系統唯一識別）、`model`（型號，用於 Sentrycs 融合 remarks）、起點座標、速度、航向、操作員位置估算（bearing/distance）、waypoints 陣列、landing_point（接管目標座標）。在 sentrycs-sim YAML 中以 `uid`（對應 UDS `drone_id`）識別同一無人機，並附帶狀態切換時間戳（detected_at_s / mitigating_at_s / neutralized_at_s）。

**Milestone**：代表劇本中的一個關鍵觸發點，屬性包含：里程碑編號（M1～M4）、觸發條件（距 SP 距離閾值）、預期動作（起飛 / 雷達偵測 / RF 融合 / 接管指令）、預期 CoT 事件（uid、type、stale 規則）、預期絕對時間（估算值 + 允差）。用於驗證腳本的斷言邏輯。

**ValidationChecklist**：代表一次劇本驗收的結果記錄，包含：劇本名稱、執行時間、各 Milestone 的 PASS/FAIL 狀態、CoT 合規統計（總事件數、違規數）、takeover 位置誤差（公尺）。可由驗證腳本自動產生，也可手動填寫 `checklists/requirements.md`。

**HoldingPoint**：管制停留地點（HP）是所有劇本共用的接管目標，座標固定為（24.725806, 121.071889），是戰略要點（SP）正東方 **~3.86 km**（Haversine 距離 ≈ 3858m）的特定位置。所有 UDS `landing_point` 及 sentrycs-sim takeover 目標均應指向此點。

**StrategicPoint**：受保護目標（SP），座標固定為（24.725806, 121.033750），是劇本地圖的中心參照點，所有里程碑距離（3km / 2km / 1km）均以此為基準計算。

---

## 6. Assumptions

- **座標轉換精度**：所有座標以 WGS-84 十進位度表示，精度保留至小數點後 6 位（約 ±0.11m）；Haversine 距離計算作為里程碑觸發判斷，精度 ±5m（遠優於 50m 接管容差）。
- **服務已正常運行前提**：劇本執行前，`uds`、`map-sim`、`echoshield-sim`、`sentrycs-sim`、`cot-gateway`、`tak-client-sim` 六個服務均已依各自 spec（001–006）正確實作，且通過各自的單元測試；本規格不覆蓋服務實作本身的正確性。
- **EchoShield 感測範圍**：假設 echoshield-sim 的最大感測半徑設定 ≥ 10km，足以覆蓋劇本中所有 drone 的 3km 里程碑位置；若實際設定較小，需調整 echoshield-sim config 而非修改劇本 YAML。
- **時間精度**：sentrycs YAML 中的 `detected_at_s` / `mitigating_at_s` / `neutralized_at_s` 為絕對場景時間（秒），與 UDS 主迴圈計時器對齊；兩個服務的計時誤差假設 ≤ 1s（單機本地執行）。
- **開發環境**：劇本設計以單機本地開發環境（`dev-launcher.sh`）為主要執行目標；不考慮跨機網路延遲對里程碑觸發時間的影響。
- **不修改服務程式碼**：所有新增 artifact 均為 YAML 設定檔與 Python/bash 腳本，不修改任何 `services/*/` 下的 `.py` 原始碼；若發現 YAML 欄位尚未被服務支援，需透過另一個 spec（服務修改）解決，本規格不包含此範圍。
- **tak-client-sim 輸出格式**：假設 tak-client-sim console 輸出格式固定（依 `006-tak-client-sim` spec），驗證腳本可直接解析其日誌；若格式未定義，需先完成 006 spec 的相關 FR。
- **HP 與 SP 距離基準**：HP 座標（24.725806, 121.071889）與 SP（24.725806, 121.033750）之間的 Haversine 距離計算為 2.00km，以 `cos(24.725806°) × 111320 × 0.038139°` 估算；此座標已由任務描述明確給定，無需重新計算。
