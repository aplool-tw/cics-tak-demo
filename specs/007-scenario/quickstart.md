# Quickstart: 007-e2e-scenarios

**Feature**: `007-e2e-scenarios`
**Created**: 2026-05-03

---

## 前提條件

- Python 3.11+ 已安裝於 `services/*/` 虛擬環境
- 所有服務依賴已透過各自 `pyproject.toml` 安裝（`pip install -e .`）
- 從 **repo 根目錄** 執行所有指令
- TAK Server 不是必要前提（`tak-client-sim` 本身扮演被動接收角色）

```bash
# 確認服務依賴已安裝（首次執行或新機器）
for svc in uds map-sim echoshield-sim sentrycs-sim cot-gateway tak-client-sim; do
  pip install -e services/$svc --quiet
done
```

---

## 劇本一：單機滲透攔截

### 啟動

```bash
scripts/dev-launcher.sh \
  --uds-scenario services/uds/scenarios/e2e_single_drone.yaml \
  --sentrycs-scenario services/sentrycs-sim/config/e2e_single_drone.yaml \
  --echoshield-config services/echoshield-sim/config/e2e_scenario.yaml
```

> **注意**：`--echoshield-config` 參數在 Phase G（dev-launcher.sh 擴充）後生效。
> 詳見 `specs/007-scenario/plan.md` Phase G。

### 狀態確認

```bash
# 另開終端機
scripts/dev-launcher.sh --status
```

預期輸出（30s 內）：
```
[OK] map-sim        pid=12345  port=8090
[OK] uds            pid=12346  port=8080
[OK] echoshield-sim pid=12347  port=9000
[OK] sentrycs-sim   pid=12348  port=7070
[OK] cot-gateway    pid=12349
[OK] tak-client-sim pid=12350  port=8089
```

### 觀察 TAK 事件流

```bash
tail -f .dev-runtime/logs/tak-client-sim.log
```

預期里程碑輸出（依時序）：

```
# M1: t≈0s — UDS 啟動，drone 出現於 map-sim
[2026-05-03T10:00:00.100Z] uid=TRK-E01 status=FLYING_NORMAL lat=24.806556 lon=121.033750

# M2: t≈399s — EchoShield 偵測，灰色圖標
[2026-05-03T10:06:39.300Z] uid=ECHO-TRK-E01 type=a-u-A-M-F-Q-r lat=24.752726 lon=121.033750 stale=2026-05-03T10:06:50.300Z status=Active

# M3: t≈460s — Sentrycs DETECTED，清場舊 uid + 發送融合 uid（紅色圖標）
[2026-05-03T10:07:40.000Z] uid=ECHO-TRK-E01 type=a-u-A-M-F-Q-r lat=24.743736 lon=121.033750 stale=2026-05-03T10:07:40.000Z status=Lost
[2026-05-03T10:07:40.100Z] uid=FUSED-TRK-E01 type=a-h-A-M-F-Q-r lat=24.743736 lon=121.033750 stale=2026-05-03T10:07:51.100Z status=DETECTED

# M4: t≈525s — Sentrycs MITIGATING，接管指令發出
[2026-05-03T10:08:45.000Z] uid=FUSED-TRK-E01 type=a-h-A-M-F-Q-r lat=24.734736 lon=121.033750 stale=2026-05-03T10:08:56.000Z status=MITIGATING_TAKEOVER

# LANDED: t≈841s（估算）— drone 抵達 HP ±50m
[2026-05-03T10:14:01.000Z] uid=FUSED-TRK-E01 type=a-h-A-M-F-Q-r lat=24.725806 lon=121.071889 stale=2026-05-03T10:14:31.000Z status=NEUTRALIZED
```

### 執行驗證腳本

```bash
# 劇本執行完成後（或同時以 --wait 模式監聽）
python specs/007-scenario/scripts/validate_scenario.py \
  --scenario single \
  --cot-log .dev-runtime/logs/tak-client-sim.log

# 離線模式（使用已有 log）
python specs/007-scenario/scripts/validate_scenario.py \
  --scenario single \
  --cot-log .dev-runtime/logs/tak-client-sim.log \
  --offline
```

預期輸出：
```
[PASS] M1: TRK-E01 appears in map-sim within 10s
[PASS] M2: ECHO-TRK-E01 CoT (gray) observed at t=399s
[PASS] M3: FUSED-TRK-E01 CoT (red) observed, stale-clear for ECHO-TRK-E01 present
[PASS] M4: MITIGATING_TAKEOVER received, drone heading HP
[PASS] LANDED: TRK-E01 at (24.725806, 121.071842), dist=5.3m ≤ 50m

RESULT: PASS (5/5 milestones validated)
```

### CoT 合規驗證

```bash
python specs/007-scenario/scripts/validate_cot.py \
  --cot-log .dev-runtime/logs/tak-client-sim.log
```

預期輸出：
```
[PASS] COT-TYPE: ECHO-TRK-E01 → a-u-A-M-F-Q-r (43 events)
[PASS] COT-TYPE: FUSED-TRK-E01 → a-h-A-M-F-Q-r (318 events)
[PASS] COT-STALE-CLEAR: ECHO-TRK-E01 stale-now present before FUSED-TRK-E01
[PASS] COT-STALE: all 361 events within ±1s tolerance

SUMMARY:
  Total CoT events : 361
  Type violations  : 0
  Stale violations : 0
  Missing stale-clear: 0
  UID cross-contamination: 0

RESULT: PASS
```

### 停止服務

```bash
scripts/dev-launcher.sh --stop
```

---

## 劇本二：三機多方向同時滲透

### 啟動

```bash
scripts/dev-launcher.sh \
  --uds-scenario services/uds/scenarios/e2e_multi_drone.yaml \
  --sentrycs-scenario services/sentrycs-sim/config/e2e_multi_drone.yaml \
  --echoshield-config services/echoshield-sim/config/e2e_scenario.yaml
```

### 觀察

```bash
tail -f .dev-runtime/logs/tak-client-sim.log | grep -E "(ECHO|FUSED|SENTRYCS)"
```

預期三個 uid 系列均出現，各自獨立：
```
# Drone B 首先到達感測圈（t≈382s）
[...] uid=ECHO-TRK-E0B type=a-u-A-M-F-Q-r ...

# Drone A（t≈499s）
[...] uid=ECHO-TRK-E0A type=a-u-A-M-F-Q-r ...

# Drone C（t≈517s）
[...] uid=ECHO-TRK-E0C type=a-u-A-M-F-Q-r ...

# Sentrycs DETECTED 切換（B 最早：t≈406s）
[...] uid=ECHO-TRK-E0B stale=<stale-clear> ...
[...] uid=FUSED-TRK-E0B type=a-h-A-M-F-Q-r ...
```

### 執行驗證腳本

```bash
python specs/007-scenario/scripts/validate_scenario.py \
  --scenario multi \
  --cot-log .dev-runtime/logs/tak-client-sim.log
```

預期輸出（12 個里程碑：3 drones × 4 milestones）：
```
[PASS] M1-A: TRK-E0A appears in map-sim within 10s of at_s=0
[PASS] M1-B: TRK-E0B appears in map-sim within 10s of at_s=30
[PASS] M1-C: TRK-E0C appears in map-sim within 10s of at_s=60
[PASS] M2-A: ECHO-TRK-E0A CoT (gray) observed at t=499s
[PASS] M2-B: ECHO-TRK-E0B CoT (gray) observed at t=382s
[PASS] M2-C: ECHO-TRK-E0C CoT (gray) observed at t=517s
[PASS] M3-A: FUSED-TRK-E0A CoT (red) observed, stale-clear present
[PASS] M3-B: FUSED-TRK-E0B CoT (red) observed, stale-clear present
[PASS] M3-C: FUSED-TRK-E0C CoT (red) observed, stale-clear present
[PASS] M4-A: MITIGATING_TAKEOVER for TRK-E0A received
[PASS] M4-B: MITIGATING_TAKEOVER for TRK-E0B received
[PASS] M4-C: MITIGATING_TAKEOVER for TRK-E0C received
  UID cross-contamination: 0

RESULT: PASS (12/12 milestones validated)
```

---

## 常見問題排查

### 問題 1：服務啟動失敗（port 佔用）

```bash
# 確認 port 狀態
ss -tlnp | grep -E "8080|8090|9000|7070|8089"

# 清除殘留 PID
scripts/dev-launcher.sh --stop
rm -f .dev-runtime/pids/*.pid
```

### 問題 2：UDS YAML 路徑錯誤

```
[launcher] ERROR: UDS scenario not found: services/uds/scenarios/e2e_single_drone.yaml
```

確認檔案存在：
```bash
ls -la services/uds/scenarios/e2e_single_drone.yaml
ls -la services/sentrycs-sim/config/e2e_single_drone.yaml
ls -la services/echoshield-sim/config/e2e_scenario.yaml
```

### 問題 3：tak-client-sim log 無輸出

可能原因：
1. cot-gateway 尚未連接到 TAK Server（tak-client-sim）
2. EchoShield 感測位置未更新（見 `--echoshield-config` 問題）

確認：
```bash
tail -50 .dev-runtime/logs/cot-gateway.log
tail -50 .dev-runtime/logs/echoshield-sim.log
```

### 問題 4：EchoShield 無法偵測 drone（缺少 `--echoshield-config`）

若 dev-launcher.sh 尚未支援 `--echoshield-config` 參數（Phase G 尚未完成），
EchoShield sensor 將在預設位置 (24.0, 121.0)，無法偵測 e2e 劇本中的 drone。

臨時解法（手動覆寫）：
```bash
# 直接編輯 dev-launcher.sh 中的 launch_echoshield_sim() 函式，
# 將 sensor_lat/lon 改為 24.725806 / 121.033750，max_range_m 改為 3200
# 此為暫時方案，待 Phase G 完成後使用 --echoshield-config 參數
```

### 問題 5：驗證腳本找不到 tak-client-sim log

```bash
# 確認 log 路徑
ls -la .dev-runtime/logs/tak-client-sim.log

# 指定自訂路徑
python specs/007-scenario/scripts/validate_scenario.py \
  --scenario single \
  --cot-log /path/to/custom/tak-client-sim.log
```

### 問題 6：M3/M4 里程碑超時

可能原因：sentrycs-sim 未啟動，或 takeover 端口衝突。

```bash
# 確認 sentrycs-sim 運行
curl http://localhost:17070/health

# 確認 UDS 接受接管
curl http://localhost:18080/objects  # 確認 TRK-E01 存在
```

---

## CI Pipeline 整合範例

```yaml
# .github/workflows/e2e-smoke.yml
name: E2E Smoke Test

on: [push, pull_request]

jobs:
  e2e-scenario-single:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - name: Install dependencies
        run: |
          for svc in uds map-sim echoshield-sim sentrycs-sim cot-gateway tak-client-sim; do
            pip install -e services/$svc
          done
          pip install requests

      - name: Start e2e scenario 1
        run: |
          scripts/dev-launcher.sh \
            --uds-scenario services/uds/scenarios/e2e_single_drone.yaml \
            --sentrycs-scenario services/sentrycs-sim/config/e2e_single_drone.yaml \
            --echoshield-config services/echoshield-sim/config/e2e_scenario.yaml &
          sleep 30  # 等待服務啟動

      - name: Wait for scenario to complete
        run: sleep 620  # 等待 M4 里程碑（t≈525s）+ 30s 緩衝

      - name: Validate scenario
        run: |
          python specs/007-scenario/scripts/validate_scenario.py \
            --scenario single \
            --cot-log .dev-runtime/logs/tak-client-sim.log \
            --offline

      - name: Validate CoT compliance
        run: |
          python specs/007-scenario/scripts/validate_cot.py \
            --cot-log .dev-runtime/logs/tak-client-sim.log

      - name: Cleanup
        if: always()
        run: scripts/dev-launcher.sh --stop || true
```
