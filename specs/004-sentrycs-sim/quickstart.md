# Quickstart: Sentrycs Simulator

本文件示範在本機以最少步驟啟動 Sentrycs Simulator、驗證完整的偵測 → 接管 → 制壓流程。假設 Map Simulator
（:18090）與 UDS（:18080）已依 `specs/001-uds/quickstart.md`、`specs/002-map-sim/quickstart.md` 啟動。

## 0. 前置

- Python 3.11+
- 已切到 feature branch：`004-sentrycs-sim`
- Map Sim 跑在 `localhost:18090`，UDS 跑在 `localhost:18080`
- 本服務原始碼位於 `services/sentrycs-sim/`

## 1. 安裝

```bash
cd services/sentrycs-sim
pip install -e '.[dev]'
```

## 2. 最小場景 YAML

`services/sentrycs-sim/config/local.yaml`（專案已附範例，此處為參考格式）：

```yaml
sensor_lat: 25.0330
sensor_lon: 121.5654

# 以下皆為預設值，可省略
poll_interval_s: 0.5
map_sim_url: http://localhost:18090
uds_url: http://localhost:18080
api_host: 0.0.0.0
api_port: 7070
neutralized_hold_s: 30.0
mitigating_disappear_grace_s: 10.0

drones:
  - uid: TRK-001
    model: "DJI Mavic 3"
    detected_at_s: 5
    mitigating_at_s: 20
    neutralized_at_s: 35
    operator_bearing_deg: 225
    operator_distance_m: 300

  - uid: TRK-002
    model: "Autel EVO II"
    detected_at_s: 10
    mitigating_at_s: 25
    neutralized_at_s: 45
    operator_bearing_deg: 45
    operator_distance_m: 350
```

## 3. 啟動

```bash
python -m sentrycs_sim --scenario config/local.yaml --verbose
# 或
sentrycs-sim --scenario config/local.yaml --verbose
```

預期結構化日誌（範例）：

```json
{"event": "startup", "api_host": "0.0.0.0", "api_port": 7070, "drones": 2, "scenario": "config/local.yaml"}
{"event": "mapsim_query", "count": 0, "latency_ms": 3.1}
{"event": "state_transition", "uid": "TRK-001", "from": "IDLE", "to": "DETECTED", "reason": "scheduled"}
```

## 4. 驗證 Story 1：完整生命週期

### 4.1 Ready probe（啟動 < 2 s）

```bash
curl -s localhost:17070/health | jq
# {"status":"ok","uptime_s":1.3,"tracked_drones":0,"map_sim_reachable":true}
```

### 4.2 IDLE（t < 5 s）

```bash
curl -s localhost:17070/detections | jq
# []
```

### 4.3 DETECTED（5 s ≤ t < 20 s）

先用 UDS 把 TRK-001 推到 Map Sim 感測半徑內（依既有 UDS quickstart；或使用 Map Sim 的 `/objects/update`
直接注入）：

```bash
curl -s -X POST localhost:18090/objects/update -H 'content-type: application/json' -d '{
  "drone_id": "TRK-001",
  "lat": 25.0430, "lon": 121.5700, "alt_m": 120.0,
  "speed_ms": 12.0, "heading_deg": 180.0,
  "status": "FLYING_NORMAL",
  "timestamp": "2026-04-22T08:00:05.000Z"
}'
```

於 t≈6 s 輪詢：

```bash
curl -s localhost:17070/detections | jq '.[] | {uid, detection_status, is_landed, operator_lat, operator_lon}'
# {
#   "uid": "TRK-001",
#   "detection_status": "DETECTED",
#   "is_landed": false,
#   "operator_lat": 25.0411...,    # 西南方 300m，整個場景期間完全不變
#   "operator_lon": 121.5678...
# }
```

### 4.4 MITIGATING（t ≥ 20 s）

於 t≈20 s，Sentrycs 應對 UDS 發出恰好 1 次 takeover：

```text
{"event": "takeover_request",  "uid": "TRK-001", "drone_id": "TRK-001",
 "target_lat": 25.0430, "target_lon": 121.5700, "target_alt_m": 0.0}
{"event": "takeover_response", "uid": "TRK-001", "http_status": 200,
 "result": "accepted", "latency_ms": 18.7}
{"event": "state_transition",  "uid": "TRK-001", "from": "DETECTED", "to": "MITIGATING"}
```

```bash
curl -s localhost:17070/detection/TRK-001 | jq '.detection_status, .is_landed'
# "MITIGATING"
# false
```

### 4.5 NEUTRALIZED（Map Sim 回報 LANDED）

模擬 UDS 將目標落地（或直接用 `/objects/update` 送 `status=LANDED`）：

```bash
curl -s -X POST localhost:18090/objects/update -H 'content-type: application/json' -d '{
  "drone_id": "TRK-001",
  "lat": 25.0430, "lon": 121.5700, "alt_m": 0.0,
  "speed_ms": 0.0, "heading_deg": 0.0,
  "status": "LANDED",
  "timestamp": "2026-04-22T08:00:35.000Z"
}'
```

下一次輪詢（≤ 1 s 後）：

```bash
curl -s localhost:17070/detection/TRK-001 | jq '.detection_status, .is_landed'
# "NEUTRALIZED"
# true
```

30 s 後該目標從 `/detections` 陣列移除（回到 IDLE）：

```bash
sleep 31
curl -s localhost:17070/detection/TRK-001 -o /dev/null -w '%{http_code}\n'
# 404
```

## 5. 驗證 Story 2：operator 位置零抖動

```bash
for i in $(seq 1 10); do
  curl -s localhost:17070/detection/TRK-001 | jq -c '{ol: .operator_lat, on: .operator_lon}'
  sleep 1
done
# 10 行 output 完全相同（SC-SC-004 抖動 = 0）
```

## 6. 驗證 Story 3：多機並行與 409 隔離

在 TRK-001 已 MITIGATING 後，再對它發一次 takeover（模擬 EchoShield 也觸發了）；UDS 會對 Sentrycs 之後的
請求回 409。Sentrycs 對同一目標只發一次，不會再打 UDS；若某一目標因網路錯誤失敗，**其他目標不受影響**：

```bash
curl -s localhost:17070/detections | jq 'map(.uid)'
# ["TRK-001", "TRK-002"]   # 兩機獨立推進
```

## 7. 容錯：Map Sim 下線 30 s

```bash
# 停掉 Map Sim 後
curl -s localhost:17070/detections | jq 'length'
# 仍回最後一次快照；不崩潰（SC-SC-007）
# 日誌每退避週期 1 筆：
# {"event": "mapsim_unavailable", "error": "connection refused", "retry_in_s": 1.0}
# {"event": "mapsim_unavailable", "error": "connection refused", "retry_in_s": 2.0}
# {"event": "mapsim_unavailable", "error": "connection refused", "retry_in_s": 4.0}
# {"event": "mapsim_unavailable", "error": "connection refused", "retry_in_s": 10.0}
```

恢復 Map Sim 後 ≤ 1 s 追上最新位置。

## 8. 優雅關閉

```bash
kill -INT $(pgrep -f sentrycs_sim)
# 日誌：
# {"event": "shutdown", "signal": "SIGINT", "duration_ms": 142}
# 程序在 3 秒內退出（SC-SC-012）
```

## 9. 執行測試

```bash
cd services/sentrycs-sim
pytest -q                      # 全部（contract + integration + unit）
pytest -q tests/contract       # 僅契約測試（schema 凍結）
pytest -q tests/unit           # 僅單元（狀態機、operator geo、config）
pytest -q -k lifecycle         # 僅跑 end-to-end lifecycle
```

## 10. 常見錯誤

| 症狀 | 原因 | 解法 |
| --- | --- | --- |
| 啟動立即 exit code 2 | scenario YAML 欄位缺失、時序矛盾、operator_distance 超出 [200,500] | 讀 stderr 的 pydantic error，修 YAML |
| `/detections` 永遠空 | Map Sim 未收到 `drone_id` 對應的 `/objects/update`；或 `is_lost=true` | 檢查 Map Sim `/objects` 是否看得到該 uid |
| takeover 未觸發 | 仍在 `DETECTED` 但 `mitigating_at_s` 已過 | 檢查 UDS 是否可達；看 `takeover_response` event 的 `http_status` |
| `model: "Unknown"` | Map Sim 給了場景 YAML 未登記的 `uid` | 補齊 scenario YAML 的 drones[] |
