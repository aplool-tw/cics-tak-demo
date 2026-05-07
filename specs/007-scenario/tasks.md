# Tasks: 007-e2e-scenarios（端對端模擬驗證劇本）

**Feature**: `007-e2e-scenarios`
**Feature Branch**: `feature/007-e2e-scenarios`
**Phase**: Tasks
**Created**: 2026-05-03
**Status**: Draft

**Input**: `specs/007-scenario/`（plan.md, spec.md, research.md, data-model.md, contracts/）
**Output**: 兩套劇本 YAML、驗證腳本、EchoShield 設定、dev-launcher.sh 擴充、文件

---

## 格式說明

```
T### [P] [US?] Description — file/path
```

- **[P]**：可與其他無依賴任務並行執行（不同檔案）
- **[US1]～[US4]**：對應 spec.md User Story 編號
- 每個任務包含精確的檔案路徑，可直接由 LLM 執行

---

## Phase 0：目錄與環境設定（Setup）

**目的**：建立後續所有任務所需的目錄結構，確保所有 YAML 與腳本的落點存在。

- [ ] T001 建立所有新增目錄：`specs/007-scenario/scripts/`、`services/echoshield-sim/config/`、`specs/007-scenario/checklists/`（若不存在則執行 `mkdir -p`）

---

## Phase 1：驗證腳本單元測試（G1 Test-First）

**目的**：依據 G1 準則，在實作前先撰寫並確認 FAIL 的單元測試。驗收腳本測試必須優先於實作。

**⚠️ CRITICAL**：T002、T003 必須在對應實作任務（T050、T051）之前執行，並確認測試狀態為 FAIL。

### Group 1A：validate_scenario.py 測試（US3）

- [ ] T002 [US3] 為 `validate_scenario.py` 寫失敗單元測試，新增至 `specs/007-scenario/scripts/test_validate_scenario.py`。測試項目：
  1. `haversine_m(24.725806, 121.033750, 24.725806, 121.071889)` → 預期 ≈ 3858m（誤差 < 1m）
  2. `haversine_m(24.806556, 121.033750, 24.725806, 121.033750)` → 預期 ≈ 8989m（誤差 < 10m）
  3. `destination_point(24.806556, 121.033750, 180.0, 5989.0)` → 預期 lat ≈ 24.7527（誤差 < 0.001°）
  4. `MilestoneChecker.check_m1_drone_appears(objects=[], drone_id="TRK-E01")` → 預期 `MilestoneStatus.FAIL`
  5. `MilestoneChecker.check_m2_echo_cot(log_lines=[], uid="ECHO-TRK-E01")` → 預期 `MilestoneStatus.FAIL`
  6. `MilestoneChecker.check_m3_fused_cot(log_lines=[], uid="FUSED-TRK-E01")` → 預期 `MilestoneStatus.FAIL`
  7. `MilestoneChecker.check_m4_mitigating(log_lines=[], uid="FUSED-TRK-E01")` → 預期 `MilestoneStatus.FAIL`
  8. `ValidationResult.summary_line()` for 0/4 passed → `"RESULT: FAIL (0/4 milestones validated)"`

  執行 `python -m pytest specs/007-scenario/scripts/test_validate_scenario.py -v` 確認全部 FAIL（ImportError/AttributeError 視為 FAIL，可接受）

### Group 1B：validate_cot.py 測試（US4）

- [ ] T003 [US4] 為 `validate_cot.py` 寫失敗單元測試，新增至 `specs/007-scenario/scripts/test_validate_cot.py`。測試項目：
  1. `CotEvent(uid="ECHO-TRK-E01", cot_type="a-u-A-M-F-Q-r", ...).uid_prefix` → 預期 `"ECHO"`
  2. `CotEvent(uid="FUSED-TRK-E01", cot_type="a-h-A-M-F-Q-r", ...).uid_prefix` → 預期 `"FUSED"`
  3. `CotEvent(uid="ECHO-TRK-E01", cot_type="WRONG-TYPE", ...).uid_prefix` → type 驗證 → `FAIL`
  4. `CotEvent(..., stale_delta_s=-1.0).is_stale_clear` → 預期 `True`（清場事件）
  5. `CotEvent(..., stale_delta_s=11.0).is_stale_clear` → 預期 `False`
  6. `expected_stale(time=T, status="Active")` → 預期 `T + 11s`
  7. `expected_stale(time=T, status="NEUTRALIZED")` → 預期 `T + 30s`
  8. `expected_stale(time=T, status="stale-clear")` → 預期 `T`（stale ≤ time）
  9. uid 前綴驗證：`validate_uid_prefix("BAD-TRK-E01")` → 預期 `WARN`
  10. `CotComplianceChecker.check_all(events=[])` → 預期 `total_events=0, violations=0`

  執行 `python -m pytest specs/007-scenario/scripts/test_validate_cot.py -v` 確認全部 FAIL

---

## Phase 2：UDS 劇本 YAML（US1 + US2）

**目的**：建立 UDS 服務使用的劇本 YAML，定義無人機起點、航線、時間軸。依賴：T001（目錄存在）。

### Group 2A：劇本一（US1）

- [ ] T010 [P] [US1] 建立 `services/uds/scenarios/e2e_single_drone.yaml`，內容：
  ```yaml
  scenario:
    name: "e2e_single_drone_invasion"
    description: "單架無人機從正北 8.99km 處向戰略要點 SP 逼近，EchoShield 偵測後 Sentrycs 接管，改飛至 HP"
    update_hz: 10
    servers:
      command_api_port: 8080
    drones:
      - drone_id: "TRK-E01"
        model: "DJI Mavic 3"
        start_lat: 24.806556   # 正北 ~8.99km
        start_lon: 121.033750
        start_alt_m: 150.0
        speed_ms: 15.0
        heading_deg: 180.0     # 向正南飛（往 SP 方向）
        operator_bearing_deg: 225
        operator_distance_m: 300
        waypoints:
          - lat: 24.725806     # SP
            lon: 121.033750
            alt_m: 150.0
        landing_point:
          lat: 24.725806       # HP（SP 正東方 ~3.86km）
          lon: 121.071889
          alt_m: 0.0
          descent_speed_ms: 3.0
    timeline:
      - at_s: 0
        action: start_flying
        drone_id: "TRK-E01"
  ```
  確認 schema 符合 `data-model.md §1 UDSScenarioConfig`（extra=forbid）

### Group 2B：劇本二（US2）

- [ ] T011 [P] [US2] 建立 `services/uds/scenarios/e2e_multi_drone.yaml`，內容：
  三架無人機（TRK-E0A 正北、TRK-E0B 正西、TRK-E0C 東北）同時滲透，各自 start_flying 事件偏移 0/30/60 秒：
  ```yaml
  scenario:
    name: "e2e_multi_drone_invasion"
    description: "三架無人機從不同方向同時逼近 SP，驗證多機並行追蹤與接管不干擾"
    update_hz: 10
    servers:
      command_api_port: 8080
    drones:
      - drone_id: "TRK-E0A"
        model: "DJI Mavic 3"
        start_lat: 24.806556   # 正北 ~8.99km
        start_lon: 121.033750
        start_alt_m: 120.0
        speed_ms: 12.0
        heading_deg: 180.0
        operator_bearing_deg: 180
        operator_distance_m: 300
        waypoints:
          - lat: 24.725806
            lon: 121.033750
            alt_m: 120.0
        landing_point:
          lat: 24.725806
          lon: 121.071889
          alt_m: 0.0
          descent_speed_ms: 3.0
      - drone_id: "TRK-E0B"
        model: "Autel EVO II"
        start_lat: 24.725806   # 正西 ~7.22km
        start_lon: 120.962306
        start_alt_m: 130.0
        speed_ms: 12.0
        heading_deg: 90.0      # 向正東飛（往 SP 方向）
        operator_bearing_deg: 270
        operator_distance_m: 350
        waypoints:
          - lat: 24.725806
            lon: 121.033750
            alt_m: 130.0
        landing_point:
          lat: 24.725806
          lon: 121.071889
          alt_m: 0.0
          descent_speed_ms: 3.0
      - drone_id: "TRK-E0C"
        model: "Skydio 2+"
        start_lat: 24.784500   # 東北 ~8.49km
        start_lon: 121.087278
        start_alt_m: 140.0
        speed_ms: 12.0
        heading_deg: 225.0     # 向西南飛（往 SP 方向）
        operator_bearing_deg: 45
        operator_distance_m: 280
        waypoints:
          - lat: 24.725806
            lon: 121.033750
            alt_m: 140.0
        landing_point:
          lat: 24.725806
          lon: 121.071889
          alt_m: 0.0
          descent_speed_ms: 3.0
    timeline:
      - at_s: 0
        action: start_flying
        drone_id: "TRK-E0A"
      - at_s: 30
        action: start_flying
        drone_id: "TRK-E0B"
      - at_s: 60
        action: start_flying
        drone_id: "TRK-E0C"
  ```
  確認三架 drone 的 timeline at_s 分別為 0/30/60，符合 research.md §Decision 3 計算

---

## Phase 3：Sentrycs 劇本設定 YAML（US1 + US2）

**目的**：建立 Sentrycs 服務的劇本設定，定義各 drone 的 DETECTED/MITIGATING/NEUTRALIZED 觸發時間。
依賴：T010（確認 drone_id 格式）、T011（確認多機 uid）。

### Group 3A：劇本一（US1）

- [ ] T020 [P] [US1] 建立 `services/sentrycs-sim/config/e2e_single_drone.yaml`，timing 依 research.md §Decision 3 精確計算：
  ```yaml
  sensor_lat: 24.725806   # SP — Sentrycs RF 感測器位於戰略要點
  sensor_lon: 121.033750
  poll_interval_s: 0.5
  map_sim_url: http://localhost:18090   # dev-launcher 覆寫
  uds_url: http://localhost:18080       # dev-launcher 覆寫
  api_host: 0.0.0.0
  api_port: 7070
  neutralized_hold_s: 30.0
  mitigating_disappear_grace_s: 10.0

  drones:
    - uid: TRK-E01
      model: "DJI Mavic 3"
      detected_at_s: 460      # drone 距 SP ≈2km；幾何計算 465.9s，spec 建議 460s（±30s 容差內）
      mitigating_at_s: 525    # drone 距 SP ≈1km；幾何計算 532.6s，spec 建議 525s
      neutralized_at_s: 565   # mitigating + 40s；確認接管
      operator_bearing_deg: 225
      operator_distance_m: 300
  ```
  確認 `detected_at_s < mitigating_at_s < neutralized_at_s` 約束成立

### Group 3B：劇本二（US2）

- [ ] T021 [P] [US2] 建立 `services/sentrycs-sim/config/e2e_multi_drone.yaml`，三機時序依 research.md §Decision 3 劇本二計算表及里程碑碰撞修正：
  ```yaml
  sensor_lat: 24.725806   # SP
  sensor_lon: 121.033750
  poll_interval_s: 0.5
  map_sim_url: http://localhost:18090
  uds_url: http://localhost:18080
  api_host: 0.0.0.0
  api_port: 7070
  neutralized_hold_s: 30.0
  mitigating_disappear_grace_s: 10.0

  drones:
    - uid: TRK-E0A
      model: "DJI Mavic 3"
      detected_at_s: 580      # d=8989m，v=12m/s，t_start=0 → (8989-2000)/12 = 582.4s；spec 建議 580s
      mitigating_at_s: 666    # (8989-1000)/12 = 665.7s；spec 建議 666s
      neutralized_at_s: 706   # 666 + 40s
      operator_bearing_deg: 180
      operator_distance_m: 300

    - uid: TRK-E0B
      model: "Autel EVO II"
      detected_at_s: 406      # d=7223m，v=12m/s，t_start=30；spec 建議 406s（±30s 調校）
      mitigating_at_s: 489    # spec 建議 489s
      neutralized_at_s: 519   # 489 + 30s
      operator_bearing_deg: 270
      operator_distance_m: 350

    - uid: TRK-E0C
      model: "Skydio 2+"
      detected_at_s: 600      # d=8485m，v=12m/s，t_start=60 → (8485-2000)/12+60 = 600.4s
      mitigating_at_s: 684    # (8485-1000)/12+60 = 683.8s；spec 建議 684s
      neutralized_at_s: 716   # 684+32s（原 714+2s，調整使 E0A(706)/E0C(716) 間隔≥10s，符合 FR-SCN-017）
      operator_bearing_deg: 45
      operator_distance_m: 280
  ```
  確認三機里程碑間隔 ≥10s：M3 min(600-580)=20s ✓，M4 min(684-666)=18s ✓，NEUTRALIZED min(716-706)=10s ✓

---

## Phase 4：EchoShield E2E 設定（US1 + US2）

**目的**：建立 EchoShield 以 SP 為中心、max_range=3200m 的 e2e 設定檔，解決 dev-launcher.sh 硬編碼 sensor@(24.0,121.0) 距 SP 約 80.9km 的問題。
依賴：T001（目錄存在）。可與 T010–T021 並行。

- [ ] T030 [P] [US1] [US2] 建立 `services/echoshield-sim/config/e2e_scenario.yaml`：
  ```yaml
  # EchoShield E2E 劇本設定
  # sensor 設在 SP 中心，確保 M2（drone 進入 3km 感測圈）可靠觸發
  sensor_lat: 24.725806    # SP — 偵測雷達部署於戰略要點
  sensor_lon: 121.033750   # SP
  sensor_alt_m: 10.0
  max_range_m: 3200        # 3km 閾值 + 200m 緩衝（GPS 噪點 ±5m，reliable trigger）
  update_rate_hz: 10
  lost_grace_sec: 2.0
  position_noise_m: 5.0
  velocity_noise_ms: 0.5
  noise_seed: null
  # 以下三個欄位由 dev-launcher.sh --echoshield-config 模式動態覆寫：
  # map_sim_url: （dev-launcher 覆寫）
  # feed_host:   （dev-launcher 覆寫）
  # feed_port:   （dev-launcher 覆寫）
  ```
  說明：max_range_m=3200 讓劇本一 M2 在 t≈386s 觸發（drone 距 SP=3200m），劇本二 E0A M2 在 t≈482s

---

## Phase 5：dev-launcher.sh 擴充（US1 + US2）

**目的**：擴充 `scripts/dev-launcher.sh` 支援 `--echoshield-config <path>` 參數，讓 e2e 劇本可指定 sensor 位置設定。

### Group 5A：現況確認

- [ ] T040 [US1] 檢查 `scripts/dev-launcher.sh` 是否已支援 `--uds-scenario` 和 `--sentrycs-scenario` 參數：
  執行 `grep -n -- '--uds-scenario\|--sentrycs-scenario\|--echoshield-config' scripts/dev-launcher.sh`
  記錄結果：(a) 若已支援 --uds-scenario 與 --sentrycs-scenario 則可直接進 T041；(b) 若不存在則也在 T041 一併新增

### Group 5B：新增 --echoshield-config 支援（T040 後執行）

- [ ] T041 [US1] 修改 `scripts/dev-launcher.sh`，新增 `--echoshield-config` 參數支援。
  變更清單（依 plan.md §Phase F）：
  
  1. **Defaults 區塊**：新增 `ECHOSHIELD_CONFIG=""`
  
  2. **Argument parsing 區塊**：新增
     ```bash
     --echoshield-config)  ECHOSHIELD_CONFIG="$2"; shift 2 ;;
     ```
  
  3. **usage() Scenarios 段落**：新增
     ```
       --echoshield-config <path>  EchoShield 設定檔路徑（e.g. services/echoshield-sim/config/e2e_scenario.yaml）
                                    若提供，覆寫 map_sim_url/feed_host/feed_port 三個動態欄位；
                                    不提供則使用 launcher 生成的預設值（sensor@24.0,121.0）
     ```
  
  4. **`launch_echoshield_sim()` 函式**：改為 if/else 邏輯；`if [[ -n "${ECHOSHIELD_CONFIG}" ]]` 時：
     - 檢查檔案存在（`[[ -f ... ]] || die ...`）
     - 以 Python3 inline script（或 sed）複製原始設定並覆寫三欄位（`map_sim_url`、`feed_host`、`feed_port`）至 `${GEN_DIR}/echoshield.yaml`
     - else 保留原有的 heredoc 生成邏輯（sensor@24.0,121.0，max_range=4800）
  
  5. **log 輸出**：`[[ -n "${ECHOSHIELD_CONFIG}" ]] && log "  echoshield config : ${ECHOSHIELD_CONFIG}"`
  
  驗證：`bash -n scripts/dev-launcher.sh`（語法檢查通過），`scripts/dev-launcher.sh --help | grep echoshield-config`（出現說明）

---

## Phase 6：驗證腳本實作（US3 + US4）

**目的**：實作驗證腳本，使 Phase 1 的失敗單元測試轉為通過。
依賴：T002（validate_scenario.py test-first）、T003（validate_cot.py test-first）。

### Group 6A：validate_scenario.py（US3）

- [ ] T050 [US3] 實作 `specs/007-scenario/scripts/validate_scenario.py`（依賴 T002 test-first 已完成）。
  
  **模組結構**：
  ```
  specs/007-scenario/scripts/validate_scenario.py
  ├── def haversine_m(lat1, lon1, lat2, lon2) -> float
  ├── def destination_point(lat, lon, bearing_deg, distance_m) -> tuple[float, float]
  ├── class MilestoneStatus(Enum): PENDING/PASS/FAIL/TIMEOUT
  ├── @dataclass MilestoneCheck（來自 data-model.md §3）
  ├── @dataclass ValidationResult（來自 data-model.md §3）
  ├── class MilestoneChecker:
  │   ├── check_m1_drone_appears(objects, drone_id) -> MilestoneStatus
  │   ├── check_m2_echo_cot(log_lines, uid) -> MilestoneStatus（找 uid=ECHO-{id}，type=a-u-A-M-F-Q-r）
  │   ├── check_m3_fused_cot(log_lines, uid) -> MilestoneStatus（找 stale-clear 後接 FUSED uid）
  │   └── check_m4_mitigating(log_lines, uid) -> MilestoneStatus（找 MITIGATING_TAKEOVER）
  └── def main(): argparse（--scenario, --cot-log, --map-sim-url, --offline, --wait）
  ```
  
  **驗證邏輯**（依 plan.md §Phase G）：
  - M1：輪詢 `GET {map_sim_url}/objects`，確認 drone_id 出現（timeout=60s，間隔 2s）
  - M2：正則掃描 log，找 `uid=ECHO-TRK-E0X.*type=a-u-A-M-F-Q-r`
  - M3：找 stale-clear 事件（`uid=ECHO-TRK-E0X.*stale=<past>`）後，找首筆 `uid=FUSED-TRK-E0X.*type=a-h-A-M-F-Q-r`；驗證時序（stale-clear 必須在 FUSED 前）
  - M4：找 `uid=FUSED-TRK-E0X.*status=MITIGATING_TAKEOVER`
  - LANDED：找最後一筆 `uid=FUSED-TRK-E0X` 的 lat/lon，計算 haversine_m 至 HP，確認 ≤50m
  
  **常數**：`SP_LAT=24.725806, SP_LON=121.033750, HP_LAT=24.725806, HP_LON=121.071889`
  
  **多機模式**（--scenario multi）：對 TRK-E0A/B/C 三機各執行完整里程碑序列（共 12 項）；uid_cross_contamination 計數（FUSED-E0A 座標不應落在 B/C 路徑附近 500m 內）
  
  **輸出格式**：每行 `[PASS|FAIL] M{n}-{drone_id}: {description}`，結尾 `RESULT: PASS|FAIL ({n}/{total} milestones validated)`；exit code 0=全通過，1=有失敗
  
  確認：`python -m pytest specs/007-scenario/scripts/test_validate_scenario.py -v` 全部通過

### Group 6B：validate_cot.py（US4）

- [ ] T051 [US4] 實作 `specs/007-scenario/scripts/validate_cot.py`（依賴 T003 test-first 已完成）。
  
  **模組結構**：
  ```
  specs/007-scenario/scripts/validate_cot.py
  ├── @dataclass(frozen=True) CotEvent（來自 data-model.md §5）
  │   ├── uid, cot_type, lat, lon, time, stale, status
  │   ├── property uid_prefix -> str（ECHO/SENTRYCS/FUSED/UNKNOWN）
  │   ├── property stale_delta_s -> float
  │   └── property is_stale_clear -> bool
  ├── EXPECTED_TYPE = {"ECHO-": "a-u-A-M-F-Q-r", "SENTRYCS-": "a-u-A-M-F-Q-r", "FUSED-": "a-h-A-M-F-Q-r"}
  ├── def expected_stale(time, status) -> datetime（三段式：stale-clear=time，NEUTRALIZED=+30s，else=+11s）
  ├── class CotComplianceChecker:
  │   ├── check_type_compliance(event) -> bool
  │   ├── check_stale_compliance(event, tolerance_s=1.0) -> bool
  │   ├── check_uid_prefix(event) -> str（PASS/WARN）
  │   ├── check_dual_message(events_by_uid) -> int（missing stale-clear 計數）
  │   ├── check_cross_contamination(events, scenario="multi") -> int（跨機 uid 混淆計數）
  │   └── check_all(events) -> ValidationResult（summary）
  └── def main(): argparse（--cot-log，--tap-host/port 用於直連 cot-gateway TCP）
  ```
  
  **CoT 合規規則**（依 research.md §Decision 7 + plan.md §Phase H）：
  - **type 驗證**：uid 前綴 → 預期 type（ECHO/SENTRYCS → a-u-A-M-F-Q-r；FUSED → a-h-A-M-F-Q-r）
  - **stale 驗證**：依 status 計算預期 stale，允許 ±1s 容差（FR-SCN-038）
  - **uid 前綴**：必須以 ECHO-/SENTRYCS-/FUSED- 開頭；不符輸出 WARN
  - **雙訊息機制**：FUSED uid 首次出現前，同 track 舊 uid 必須有 stale-clear 事件（`stale ≤ time`）
  - **跨機混淆**（劇本二）：`FUSED-TRK-E0A` 座標距 TRK-E0B/C 飛行路徑 > 500m 才判為不混淆
  
  **輸出格式**（FR-SCN-038）：逐筆 `[PASS|FAIL|WARN] {uid}: {check_type} — {detail}`，結尾統計行
  
  確認：`python -m pytest specs/007-scenario/scripts/test_validate_cot.py -v` 全部通過

---

## Phase 7：測試執行驗收（US3 + US4）

**目的**：執行測試確認 T002/T003 的失敗測試在 T050/T051 實作後全部通過，並進行端對端冒煙測試。
依賴：T050、T051。

- [ ] T060 [US3] [US4] 執行全部驗證腳本單元測試：
  ```bash
  python -m pytest specs/007-scenario/scripts/test_validate_scenario.py specs/007-scenario/scripts/test_validate_cot.py -v --tb=short
  ```
  預期：所有測試通過（綠燈）。若有失敗，修正 T050/T051 對應實作直到通過。
  記錄通過數量（預期 ≥18 個測試案例）

- [ ] T061 [US1] 端對端手動冒煙測試：劇本一快樂路徑（依賴 T040、T041、T010、T020、T030 全部完成）。
  執行：
  ```bash
  scripts/dev-launcher.sh \
    --uds-scenario services/uds/scenarios/e2e_single_drone.yaml \
    --sentrycs-scenario services/sentrycs-sim/config/e2e_single_drone.yaml \
    --echoshield-config services/echoshield-sim/config/e2e_scenario.yaml
  ```
  觀察 `tak-client-sim` console，在 10 分鐘內確認：
  - [ ] M1：看到 `TRK-E01` 出現於 map-sim（t≈5s）
  - [ ] M2：看到 `uid=ECHO-TRK-E01`，type=`a-u-A-M-F-Q-r`（t≈386s）
  - [ ] M3：看到 `stale-clear` for ECHO-TRK-E01，再看到 `uid=FUSED-TRK-E01`，type=`a-h-A-M-F-Q-r`（t≈460s）
  - [ ] M4：看到 `MITIGATING_TAKEOVER`（t≈525s）
  
  若任何里程碑未出現：排查對應 YAML 設定（參考 quickstart.md §troubleshooting）

---

## Phase 8：里程碑文件與腳本 README（US1 + US2 + US3）

**目的**：提供人工驗收 checklist 與腳本使用說明，作為 Demo 前必查清單及 CI 整合參考。
依賴：T060（確認驗證腳本行為）。T070/T071/T072 可並行。

- [ ] T070 [P] [US1] 建立 `specs/007-scenario/checklists/scenario1-milestones.md`，人工驗收 checklist 格式：

  每個里程碑包含：
  - `### M{n}: {名稱}` 標題
  - **觸發條件**、**場景時間**（at_s ± 容差）、**預期 drone 位置**（lat/lon WGS-84）、**預期 CoT 事件**（uid、type、stale 規則）、**驗收方式**（人工觀察 OR validate_scenario.py 指令）
  
  里程碑清單（劇本一，TRK-E01）：
  
  | ID | 名稱 | at_s | 距 SP | 預期 CoT uid | 預期 type |
  |----|------|------|-------|-------------|----------|
  | M1 | 起飛 / map-sim 出現 | 0 ± 60s | 8,989m | — | — |
  | M2 | EchoShield 首偵 | 386 ± 60s | ~3,200m | ECHO-TRK-E01 | a-u-A-M-F-Q-r |
  | M3 | Sentrycs DETECTED / uid 切換 | 460 ± 60s | ~2,000m | FUSED-TRK-E01 | a-h-A-M-F-Q-r |
  | M4 | MITIGATING_TAKEOVER / 接管指令 | 525 ± 60s | ~1,000m | FUSED-TRK-E01 | a-h-A-M-F-Q-r |
  | LANDED | 降落於 HP 附近 | ≈841s | HP ±50m | FUSED-TRK-E01 最後位置 | — |
  
  文件末尾附快速驗收指令：`python specs/007-scenario/scripts/validate_scenario.py --scenario single`

- [ ] T071 [P] [US2] 建立 `specs/007-scenario/checklists/scenario2-milestones.md`，三機里程碑 checklist：
  
  對 TRK-E0A/E0B/E0C 三機各列出 M1/M2/M3/M4/LANDED 五個里程碑（共 15 項），含：
  - 各機 at_s 時間（依 research.md §Decision 3 劇本二計算表）
  - 預期 uid 系列（ECHO-TRK-E0A/B/C → FUSED-TRK-E0A/B/C）
  - 跨機 uid 混淆驗收項目（FR-SCN-019：三機 FUSED uid 各自獨立，不交叉）
  - 里程碑碰撞確認（FR-SCN-017：相鄰事件間隔 ≥10s）
  
  ```
  Drone A: M3=t580s, M4=t666s, NEUTRALIZED=t706s
  Drone B: M3=t406s, M4=t489s, NEUTRALIZED=t519s  
  Drone C: M3=t600s, M4=t684s, NEUTRALIZED=t716s
  ```
  
  文件末尾附快速驗收指令：`python specs/007-scenario/scripts/validate_scenario.py --scenario multi`

- [ ] T072 [P] [US3] 建立 `specs/007-scenario/scripts/README.md`，腳本使用說明：
  
  **必要內容**：
  1. **前提條件**：Python 3.11+、`requests` 套件、全棧以 dev-launcher.sh 啟動中
  2. **validate_scenario.py 參數說明**：`--scenario {single|multi}`、`--cot-log <path>`、`--map-sim-url <url>`、`--offline`、`--wait`；附範例指令
  3. **validate_cot.py 參數說明**：`--cot-log <path>`、`--tap-host/port`；附範例
  4. **預期輸出範例**（PASS 情境 + FAIL 情境）
  5. **CI YAML 片段**（FR-SCN-040）：
     ```yaml
     # .github/workflows/e2e-smoke.yml（片段）
     - name: Run scenario validation
       run: |
         python specs/007-scenario/scripts/validate_scenario.py \
           --scenario single --offline \
           --cot-log .dev-runtime/logs/tak-client-sim.log
     ```
  6. **故障排除**：M2 未觸發（EchoShield sensor 位置確認）、M3 未觸發（Sentrycs detected_at_s 確認）

---

## 依賴圖（Dependency Graph）

```
T001 (目錄)
 ├─▶ T002 (test: validate_scenario) ─▶ T050 (impl) ─▶ T060 (test run)
 ├─▶ T003 (test: validate_cot)      ─▶ T051 (impl) ─▶ T060
 ├─▶ T010 (UDS劇本一) ──┐
 ├─▶ T011 (UDS劇本二) ──┤
 ├─▶ T020 (Sentrycs劇本一) ──┤─▶ T061 (e2e冒煙) ─▶ T070/T071/T072
 ├─▶ T021 (Sentrycs劇本二) ──┤
 ├─▶ T030 (EchoShield cfg) ──┤
 └─▶ T040 (launcher確認) ─▶ T041 (launcher擴充) ─▶ T061
```

**可並行執行的任務組**：
- `{T002, T003, T010, T011, T020, T021, T030}` — 全部可在 T001 完成後並行（各自不同檔案）
- `{T050, T051}` — T002/T003 完成後可並行（不同腳本）
- `{T070, T071, T072}` — T060 完成後可並行（不同文件）

---

## 並行執行範例

### Sprint 1（T001 後可立即並行）

```
工作流 A：T002 → T050 → T060
工作流 B：T003 → T051 → T060（等 A+B 都完成）
工作流 C：T010 → T020 → T061（等 T041 也完成）
工作流 D：T011 → T021
工作流 E：T030
工作流 F：T040 → T041
```

### Sprint 2（T060 後並行）

```
工作流 G：T070
工作流 H：T071
工作流 I：T072
```

---

## 實作策略（MVP 優先）

### MVP（User Story 1 — 劇本一單機快樂路徑）

完成 T001 → T002 → T010 → T020 → T030 → T040 → T041 → T050 → T060 → T061 即可交付劇本一可演示版本。

### Increment 2（User Story 2 — 劇本二三機）

在 MVP 基礎上新增 T003 → T011 → T021 → T051 → T060。

### Increment 3（User Story 3 + 4 — CI 自動化驗收）

完成文件任務 T070 → T071 → T072，提供 CI YAML 片段。

---

## 格式驗證摘要

**任務總計**：20 個任務（T001–T072）

| Phase | 任務 | User Story | 說明 |
|-------|------|-----------|------|
| 0 Setup | T001 | — | 目錄建立 |
| 1 Test-First | T002, T003 | US3, US4 | G1 失敗測試先寫 |
| 2 UDS YAML | T010, T011 | US1, US2 | [P] 可並行 |
| 3 Sentrycs YAML | T020, T021 | US1, US2 | [P] 可並行 |
| 4 EchoShield | T030 | US1+2 | [P] 可並行 |
| 5 Launcher | T040, T041 | US1 | 循序（T040→T041） |
| 6 Scripts | T050, T051 | US3, US4 | 依賴 T002/T003 |
| 7 Test Run | T060, T061 | US3, US1 | 依賴 T050/T051 |
| 8 Docs | T070, T071, T072 | US1, US2, US3 | [P] 可並行 |

**每個 User Story 的任務數**：
- US1：T010, T020, T030, T040, T041, T050（US3 共用）, T060（US3 共用）, T061, T070 → **9 項**
- US2：T011, T021, T071 → **3 項**
- US3：T002, T050, T060, T072 → **4 項**
- US4：T003, T051, T060（共用） → **3 項**

**並行機會**：3 個並行窗口（Phase 0 後、Phase 1 內、Phase 7 後）
