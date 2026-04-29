# Implementation Plan: 007-e2e-scenarios

**Feature**: `007-e2e-scenarios`
**Feature Branch**: `feature/007-e2e-scenarios`
**Phase**: Plan
**Created**: 2026-05-03
**Status**: Draft

---

## Problem Statement

本系統目前 6 個服務（uds, map-sim, echoshield-sim, sentrycs-sim, cot-gateway, tak-client-sim）
各自通過了單元與整合測試，但缺少以**真實戰略座標**驅動的端對端情境劇本，導致：

1. **跨服務整合無法驗收**：接管閉環（Detect → Track → Fuse → Takeover → Hold）在實際座標下是否正確觸發，沒有自動化驗收標準。
2. **Demo 不可重複**：每次 Demo 前需人工調整座標，容易出錯。
3. **CI 無護欄**：沒有可在 PR merge 後自動執行的 e2e 冒煙測試。

**Goal**：交付兩套以宜蘭戰略座標（SP: 24.725806N / 121.033750E）為基礎的劇本 YAML、驗證腳本、及 dev-launcher.sh 擴充，實現一鍵啟動與自動里程碑驗收。

---

## Technical Context

### 座標基準

| 地點 | 緯度 | 經度 | 說明 |
|------|------|------|------|
| SP（Strategic Point） | 24.725806 | 121.033750 | 受保護目標（所有里程碑距離基準） |
| HP（Holding Point） | 24.725806 | 121.071889 | 接管後降落目標，SP 正東方 ~3.86 km |

### 凍結契約依賴

| 契約 | 來源 spec | 影響本功能的欄位 |
|------|---------|--------------|
| UDS push 8 欄位 | 001-uds | `drone_id, lat, lon, alt_m, speed_ms, heading_deg, status, timestamp` |
| Map Sim GET /objects | 002-map-sim | `is_lost: bool`（不覆寫 status） |
| UDS POST /command/takeover | 001-uds | `{drone_id, target_lat, target_lon, target_alt_m}`；409 視為成功 |
| EchoShield NDJSON | 003-echoshield-sim | `track_status ∈ {"Active","Lost"}`；`track_id=ECHO-NNNNNN` |
| Sentrycs /detections | 004-sentrycs-sim | 14 欄位；status `DETECTED/MITIGATING/NEUTRALIZED`；hold 30s |
| CoT XML | 005-cot-gateway | type 不隨狀態切換；stale 三段式 |

### 技術約束

- **G6 No Persistence**：服務皆為記憶體狀態；重啟即重置
- **G7 Minimal Dependencies**：驗證腳本用標準庫 + `requests`；Haversine 自實作；禁用 `geopy`/`lxml`
- **G1 Test-First**：驗證腳本的 unit test 須在 implement 前寫並確認 FAIL
- 不修改任何 `services/*/src/**/*.py`；僅新增 YAML 與腳本

### 關鍵發現（來自 research.md）

1. **EchoShield 感測位置問題**（高影響）：dev-launcher.sh 硬編碼 sensor at (24.0, 121.0)，距 SP 約 80.9km，e2e 劇本中 drone 永遠不會被偵測。**必須** 擴充 dev-launcher.sh 加入 `--echoshield-config` 參數。

2. **FR-SCN-010 12 分鐘矛盾**（低影響）：物理降落時間 ≈ 841s（14 min）超出「≤12 min」。依 SC-SCN-001 量化基準（M1-M4 CoT 事件在 720s 內）解讀，M4 at≈525s = 8.75 min 完全符合。物理降落時間不是驗收基準。

3. **TRK-E0B timing 差異**（低影響）：spec 建議 detected_at_s=406 對應幾何計算距離 ~2.7km（而非 2km）。使用 spec 建議值，在 ±30s 調校容差內。

---

## Constitution Check

> `.specify/memory/constitution.md` 為 placeholder；依 AGENTS.md §3.1 自律準則 G1-G7 逐項檢查。

| 準則 | 符合性 | 說明 |
|------|--------|------|
| G1 Test-First | ✅ PASS | Phase E/F 的驗證腳本需先寫失敗測試（Tasks 階段規劃） |
| G2 Contract Freeze | ✅ PASS | 不修改任何跨服務 wire 契約 |
| G3 Structured Logging | ✅ N/A | 本功能不新增服務，驗證腳本允許 `print()` |
| G4 Observability | ✅ N/A | 不新增服務 lifecycle |
| G5 Structural Symmetry | ✅ N/A | 不新增服務目錄 |
| G6 No Persistence | ✅ PASS | 劇本 YAML 為設定檔，非持久化狀態 |
| G7 Minimal Dependencies | ✅ PASS | 驗證腳本僅用標準庫 + `requests`；Haversine 自實作 |

**Gate Result**: ✅ PASS — 無阻擋項

---

## Timing 計算表

### 劇本一（TRK-E01，15 m/s，起點距 SP = 8,989m）

| 里程碑 | 觸發條件 | 精確計算（s） | YAML 設定值 | 差異 |
|--------|---------|------------|-----------|------|
| M1 start_flying | at_s=0 | 0 | 0 | — |
| M2 EchoShield 偵測 | drone 進入 3200m 感測圈 | ≈ 386 | 約 386（auto） | — |
| M3 DETECTED | drone at ~2km from SP | 465.9 | `detected_at_s: 460` | -5.9s ✓ |
| M4 MITIGATING + takeover | drone at ~1km from SP | 532.6 | `mitigating_at_s: 525` | -7.6s ✓ |
| NEUTRALIZED | takeover confirmed | — | `neutralized_at_s: 565` | +32.4s ✓ |
| LANDED（估算，非驗收點） | 物理降落於 HP | ≈ 841 | — | — |

### 劇本二（三機，12 m/s）

| Drone | 起點距 SP | t_start | M3（spec） | M4（spec） | NEUTRALIZED |
|-------|---------|---------|----------|----------|------------|
| TRK-E0A | 8,989m | 0 | 580 | 666 | 706 |
| TRK-E0B | 7,223m | 30 | 406 | 489 | 519 |
| TRK-E0C | 8,485m | 60 | 600 | 684 | **716** |

> TRK-E0C neutralized_at_s 調整為 716（原 714），使 E0A/E0C 間隔 10s ≥ FR-SCN-017 要求。

---

## Implementation Phases

### Phase A：UDS 劇本一 YAML

**交付物**：`services/uds/scenarios/e2e_single_drone.yaml`

**內容**：
- `scenario.name: "e2e_single_drone_invasion"`
- 1 架 drone：TRK-E01，起點 (24.806556, 121.033750)，speed=15m/s，heading=180°，alt=150m
- waypoints[0]：SP (24.725806, 121.033750, alt=150m)
- landing_point：HP (24.725806, 121.071889, alt=0.0, descent=3.0)
- operator_bearing_deg=225，operator_distance_m=300
- timeline：`[{at_s: 0, action: start_flying, drone_id: TRK-E01}]`
- update_hz: 10，command_api_port: 8080

**完整 YAML 見** `specs/007-scenario/contracts/scenario-yaml.md` §劇本一示例

**依賴**：無

---

### Phase B：Sentrycs 劇本一設定

**交付物**：`services/sentrycs-sim/config/e2e_single_drone.yaml`

**內容**：
- sensor_lat: 24.725806，sensor_lon: 121.033750（SP）
- drones[0]：uid=TRK-E01，detected_at_s=460，mitigating_at_s=525，neutralized_at_s=565
- 其餘欄位保持預設值（dev-launcher 啟動時覆寫 URL）

**完整 YAML 見** `specs/007-scenario/contracts/sentrycs-yaml.md` §劇本一示例

**依賴**：Phase A（確認 drone_id 正確）

---

### Phase C：UDS 劇本二 YAML

**交付物**：`services/uds/scenarios/e2e_multi_drone.yaml`

**內容**：
- `scenario.name: "e2e_multi_drone_invasion"`
- 3 架 drone：TRK-E0A（N→S），TRK-E0B（W→E），TRK-E0C（NE→SW）
- 各自 waypoints[0]：SP；landing_point：HP
- timeline：3 個 start_flying 事件，at_s=0/30/60

**完整 YAML 見** `specs/007-scenario/contracts/scenario-yaml.md` §劇本二示例

**依賴**：Phase A（確認 YAML schema 格式一致）

---

### Phase D：Sentrycs 劇本二設定

**交付物**：`services/sentrycs-sim/config/e2e_multi_drone.yaml`

**內容**：
- sensor_lat: 24.725806，sensor_lon: 121.033750（SP）
- drones 陣列：TRK-E0A (580/666/706)，TRK-E0B (406/489/519)，TRK-E0C (600/684/716)
- 各自不同 operator_bearing_deg 反映不同操作員位置

**完整 YAML 見** `specs/007-scenario/contracts/sentrycs-yaml.md` §劇本二示例

**依賴**：Phase C

---

### Phase E：EchoShield E2E 設定檔

**交付物**：`services/echoshield-sim/config/e2e_scenario.yaml`

**內容**：
```yaml
sensor_lat: 24.725806    # SP
sensor_lon: 121.033750   # SP
sensor_alt_m: 10.0
max_range_m: 3200        # 覆蓋至 3.2km；M2 觸發於 drone 進入感測圈
update_rate_hz: 10
lost_grace_sec: 2.0
position_noise_m: 5.0
velocity_noise_ms: 0.5
noise_seed: null
# map_sim_url / feed_host / feed_port 由 dev-launcher 動態覆寫
```

**說明**：此檔案設定 EchoShield 以 SP 為中心、3.2km 半徑偵測範圍，
確保 M2 里程碑在正確時間觸發（drone 進入感測圈 ≈ t386s for scenario 1）。

**依賴**：無

---

### Phase F：dev-launcher.sh 擴充

**交付物**：更新 `scripts/dev-launcher.sh`

**變更**：

1. 在 Defaults 區塊新增：
   ```bash
   ECHOSHIELD_CONFIG=""    # 空 = 使用 dev-launcher 生成的預設設定
   ```

2. 在 Argument parsing 區塊新增：
   ```bash
   --echoshield-config)  ECHOSHIELD_CONFIG="$2"; shift 2 ;;
   ```

3. 在 usage() 中 Scenarios 段落新增：
   ```
     --echoshield-config <path>  EchoShield 設定檔路徑。若提供，直接使用此設定，
                                  並覆寫 map_sim_url, feed_host, feed_port 三個欄位；
                                  不提供則使用 launcher 生成的預設值。
   ```

4. 修改 `launch_echoshield_sim()` 函式：
   ```bash
   launch_echoshield_sim() {
     local cfg="${GEN_DIR}/echoshield.yaml"
     if [[ -n "${ECHOSHIELD_CONFIG}" ]]; then
       [[ -f "${ECHOSHIELD_CONFIG}" ]] || die "EchoShield config not found: ${ECHOSHIELD_CONFIG}"
       # 複製原始設定並覆寫動態欄位（map_sim_url, feed_host, feed_port）
       python3 - "${ECHOSHIELD_CONFIG}" "${cfg}" <<'PYEOF'
   import sys, re
   src, dst = sys.argv[1], sys.argv[2]
   with open(src) as f:
       content = f.read()
   import os
   replacements = {
       r'^map_sim_url:.*$': f'map_sim_url: {os.environ["ECHOSHIELD_MAP_SIM_URL"]}',
       r'^feed_host:.*$':   f'feed_host: {os.environ["BIND_HOST"]}',
       r'^feed_port:.*$':   f'feed_port: {os.environ["ECHOSHIELD_PORT"]}',
   }
   for pattern, repl in replacements.items():
       content = re.sub(pattern, repl, content, flags=re.MULTILINE)
   if 'feed_host:' not in content:
       content += f'\nfeed_host: {os.environ["BIND_HOST"]}'
   if 'feed_port:' not in content:
       content += f'\nfeed_port: {os.environ["ECHOSHIELD_PORT"]}'
   if 'map_sim_url:' not in content:
       content += f'\nmap_sim_url: {os.environ["ECHOSHIELD_MAP_SIM_URL"]}'
   with open(dst, 'w') as f:
       f.write(content)
   PYEOF
     else
       # 原有邏輯（生成預設設定）
       cat > "${cfg}" <<EOF
   sensor_lat: 24.0
   sensor_lon: 121.0
   sensor_alt_m: 10.0
   max_range_m: 4800
   update_rate_hz: 10
   lost_grace_sec: 2.0
   position_noise_m: 5.0
   velocity_noise_ms: 0.5
   noise_seed: null
   map_sim_url: ${ECHOSHIELD_MAP_SIM_URL}
   feed_host: ${BIND_HOST}
   feed_port: ${ECHOSHIELD_PORT}
   EOF
     fi
     spawn "echoshield-sim" "${ROOT_DIR}/services/echoshield-sim" \
       python3 -m echoshield_sim --config "${cfg}" ${VERBOSE_FLAG}
   }
   ```

5. 在 log 輸出區塊新增：
   ```bash
   [[ -n "${ECHOSHIELD_CONFIG}" ]] && log "  echoshield config   : ${ECHOSHIELD_CONFIG}"
   ```

**依賴**：Phase E

---

### Phase G：驗證腳本 validate_scenario.py

**交付物**：`specs/007-scenario/scripts/validate_scenario.py`

**功能**：
- `--scenario {single|multi}`：選擇驗收劇本
- `--cot-log <path>`：tak-client-sim log 路徑（預設 `.dev-runtime/logs/tak-client-sim.log`）
- `--map-sim-url <url>`：map-sim URL（預設 `http://127.0.0.1:8090`）
- `--offline`：不輪詢 map-sim，純 log 解析
- `--wait`：等待場景完成（輪詢直到 LANDED 或 timeout）

**里程碑驗證邏輯**：

```
M1：輪詢 map-sim GET /objects，確認 drone_id 出現（timeout=60s，每 2s 輪詢）
M2：掃描 log，找到 uid=ECHO-TRK-E0X + type=a-u-A-M-F-Q-r 的首筆事件
M3：掃描 log，找到：
    ① uid=ECHO-TRK-E0X + stale ≤ time（清場事件）
    ② 清場事件之後，uid=FUSED-TRK-E0X + type=a-h-A-M-F-Q-r（首筆融合）
    ② 必須晚於 ①（時序驗證）
M4：掃描 log，找到 uid=FUSED-TRK-E0X + status=MITIGATING_TAKEOVER
LANDED：掃描 log，找到最後一筆 uid=FUSED-TRK-E0X，計算 lat/lon 與 HP 的 Haversine 距離 ≤ 50m
```

**輸出格式**（FR-SCN-035）：
```
[PASS|FAIL] M{n}: {description}
...
RESULT: PASS|FAIL ({n}/{total} milestones validated)
```
exit code 0 = 全 PASS，1 = 任何 FAIL

**依賴**：Phase A, B, C, D, E, F（所有 YAML 已就位）

---

### Phase H：驗證腳本 validate_cot.py

**交付物**：`specs/007-scenario/scripts/validate_cot.py`

**功能**：
- `--cot-log <path>`：CoT log 路徑
- 逐筆輸出 type、stale、uid 合規結果
- 統計報告末行輸出（FR-SCN-038）

**驗證邏輯**：
```
CoT type：uid 前綴 → 預期 type（ECHO/SENTRYCS → a-u-A-M-F-Q-r；FUSED → a-h-A-M-F-Q-r）
stale：依 status 計算預期 stale（±1s tolerance）
uid 前綴格式：ECHO-/SENTRYCS-/FUSED- 開頭；不符則 WARN
雙訊息機制：FUSED uid 首次出現前，同 track 的舊 uid 必須有 stale-clear 事件
跨機混淆（multi）：FUSED-TRK-E0A 的座標不應出現在 B/C 的合理路徑上
```

**依賴**：Phase G

---

### Phase I：里程碑說明文件

**交付物**：
- `specs/007-scenario/scenario1-milestones.md`
- `specs/007-scenario/scenario2-milestones.md`

**格式**（每個里程碑）：
```markdown
### M{n}: {名稱}
- **觸發條件**：{距離閾值 / 時間條件}
- **場景時間**：at_s ≈ {value}（容差 ±30s）
- **預期 drone 位置**：lat={lat}, lon={lon}（WGS-84）
- **預期 CoT 事件**：uid={uid}, type={type}, stale={rule}
- **驗收方式**：{人工觀察 tak-client-sim 或 validate_scenario.py}
```

**依賴**：無（可並行）

---

### Phase J：腳本 README

**交付物**：`specs/007-scenario/scripts/README.md`

**內容**：腳本執行前提、參數說明、CI YAML 片段（FR-SCN-040）

**依賴**：Phase G, H

---

## Dependencies — 服務間資料流依賴

```
UDS YAML (Phase A/C)
  └─▶ UDS service
        ├─▶ map-sim GET /objects ◀─ validate_scenario.py M1 poll
        └─▶ EchoShield (max_range=3200m, sensor at SP) ──▶ NDJSON ──▶ cot-gateway
                                                                            │
Sentrycs YAML (Phase B/D)                                                   ▼
  └─▶ sentrycs-sim (poll map-sim, trigger at detected/mitigating/neutralized_at_s)
        ├─▶ POST /command/takeover ──▶ UDS
        └─▶ /detections ──▶ cot-gateway ──▶ CoT XML ──▶ TAK ──▶ tak-client-sim.log
                                                                            │
validate_scenario.py / validate_cot.py ◀─────────────────────────────────┘
```

### 關鍵依賴

| 服務 | 設定來源 | 注意事項 |
|------|---------|---------|
| UDS | `--uds-scenario <path>` | YAML schema 已凍結（extra=forbid） |
| EchoShield | `--echoshield-config <path>`（Phase F） | sensor 位置必須在 SP；否則 M2 永不觸發 |
| Sentrycs | `--sentrycs-scenario <path>` | URL 由 dev-launcher 覆寫 |
| CoT Gateway | 自動推導服務地址 | 無需額外設定 |
| validate scripts | `.dev-runtime/logs/tak-client-sim.log` | 需確認 tak-client-sim log 格式 |

---

## Risk Register

| 風險 | 可能性 | 影響 | 緩解措施 |
|------|--------|------|---------|
| tak-client-sim log 格式與假設不符 | 中 | 高 | Phase G 前先確認 006 spec 的 FR-SCN-027 規定格式；若不符，調整 regex |
| sentrycs-sim takeover 目標座標行為未明（YAML 繼承 vs 服務邏輯） | 中 | 中 | 在 Tasks 階段加入探針測試確認行為；FR-SCN-009 已記錄此不確定性 |
| dev-launcher.sh Python inline script 跨平台相容性 | 低 | 低 | Phase F 改用 `sed -i` 替代 Python inline 以確保相容性 |
| EchoShield max_range_m=3200 在噪點下偶發漏偵測 | 低 | 低 | validate_scenario.py 允許 ±60s 容差；可調整為 3500m |

---

## Artifacts Summary

| 檔案 | 說明 | Phase |
|------|------|-------|
| `services/uds/scenarios/e2e_single_drone.yaml` | UDS 劇本一 | A |
| `services/sentrycs-sim/config/e2e_single_drone.yaml` | Sentrycs 劇本一 | B |
| `services/uds/scenarios/e2e_multi_drone.yaml` | UDS 劇本二 | C |
| `services/sentrycs-sim/config/e2e_multi_drone.yaml` | Sentrycs 劇本二 | D |
| `services/echoshield-sim/config/e2e_scenario.yaml` | EchoShield e2e 設定 | E |
| `scripts/dev-launcher.sh` | 新增 `--echoshield-config` 參數 | F |
| `specs/007-scenario/scripts/validate_scenario.py` | 里程碑驗證腳本 | G |
| `specs/007-scenario/scripts/validate_cot.py` | CoT 合規驗證腳本 | H |
| `specs/007-scenario/scenario1-milestones.md` | 劇本一里程碑文件 | I |
| `specs/007-scenario/scenario2-milestones.md` | 劇本二里程碑文件 | I |
| `specs/007-scenario/scripts/README.md` | 腳本說明 | J |

### 本 Plan 已產出（Plan 階段）

| 檔案 | 說明 |
|------|------|
| `specs/007-scenario/plan.md` | 本文件 |
| `specs/007-scenario/research.md` | 技術研究（Haversine、timing、EchoShield 問題） |
| `specs/007-scenario/data-model.md` | Pydantic schema、MilestoneCheck、ValidationResult |
| `specs/007-scenario/quickstart.md` | 快速啟動指南 |
| `specs/007-scenario/contracts/scenario-yaml.md` | UDS YAML schema 契約 |
| `specs/007-scenario/contracts/sentrycs-yaml.md` | Sentrycs YAML schema 契約 |
