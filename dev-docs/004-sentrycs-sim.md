# Feature 004 — Sentrycs Simulator 開發紀錄

| 欄位 | 內容 |
|------|------|
| Feature ID | 004 |
| 分支 | `004-sentrycs-sim` → `develop` |
| 日期 | 2026-04-24 |
| 狀態 | 已實作、測試通過（110/110）、lint 乾淨 |

## 一、範圍

感測層 RF 反制設備模擬器。2 Hz 查詢 Map Sim `GET /objects`、以場景 YAML 驅動狀態機（DETECTED → MITIGATING → NEUTRALIZED）、MITIGATING 時呼叫 UDS `POST /command/takeover`、對外提供 HTTP JSON Status API :17070 供 CoT Gateway 輪詢。

實作位置：`services/sentrycs-sim/`。

## 二、Speckit 產出

- `specs/004-sentrycs-sim/{spec,plan,research,data-model,contracts/{http-status-api,takeover-caller},quickstart,tasks}.md`
- 64 tasks 分 6 phases，全數完成

## 三、關鍵 Clarification

**Q1 `drone_model` 來源**：Map Sim `GET /objects` 契約不含 model 欄位。決議：由場景 YAML 每架無人機必填 `model` 字串，Sentrycs 以 `uid` 對應查得。查到 Map Sim 有出現但場景未登記 → 輸出 `model: "Unknown"` + error log，不阻塞 demo。

## 四、契約（對外凍結）

### HTTP Status API :17070

| 端點 | 說明 |
|------|------|
| `GET /detections` | 陣列，14 欄位 × N 無人機 |
| `GET /detection/{uid}` | 單一；不存在回 404 |
| `GET /health` | `{"status":"ok"}` 200；就緒後無副作用 |

`/detections` item schema（14 欄位）：
```json
{
  "uid": "DRN-001",
  "model": "DJI Mavic 3",
  "lat": 25.0345, "lon": 121.5670, "alt_m": 152.4,
  "speed_ms": 18.7, "heading_deg": 85.3,
  "operator_lat": 25.0300, "operator_lon": 121.5600,
  "status": "MITIGATING",
  "first_seen": "2026-04-24T09:12:30Z",
  "last_updated": "2026-04-24T09:12:45Z",
  "takeover_issued": true,
  "takeover_result_http": 200
}
```

不變式：
- `status ∈ {DETECTED, MITIGATING, NEUTRALIZED}`
- NEUTRALIZED 保留 30s 後自 `/detections` 移除
- 並發查詢輸出快照一致（狀態不會「跳」）

### Takeover Caller（Sentrycs → UDS）

- `POST /command/takeover` `{drone_id, target_lat, target_lon, target_alt_m: 0.0}`（四欄位）
- 觸發：場景時序抵達 `mitigating_at_s`，per-drone 只觸發一次（latch）
- 200 → MITIGATING；**409 亦視為成功**（目標已被接管）latch 並進入 MITIGATING
- 400/404 → 不重試、記 error log、保留 DETECTED
- 5xx / timeout → 指數退避 1/2/4/10s 重試

## 五、狀態機

```
                                  +-- 5xx/timeout --> retry backoff 1/2/4/10s
                                  |
DETECTED --(t≥mitigating_at_s)--> [call UDS takeover]
                                  |-- 200/409 --> MITIGATING --(t≥neutralized_at_s)--> NEUTRALIZED --(+30s)--> 移除
                                  |-- 400/404 --> DETECTED (no retry, error log)
```

特殊規則：
- **DETECTED 消失**：Map Sim 不再回報該 uid → 視為誤報，立即自 registry 移除
- **MITIGATING 消失**：寬限 10 ticks，若仍未回則轉 NEUTRALIZED（視為接管完成）
- **NEUTRALIZED 階段目標存在與否皆繼續顯示**，僅以 30s 計時為準

## 六、場景 YAML Schema

```yaml
mapsim:
  base_url: "http://localhost:18090"
  query_center: {lat: 25.0330, lon: 121.5654}
  radius_m: 8000
uds:
  base_url: "http://localhost:8080"
api:
  host: "0.0.0.0"
  port: 7070
poll:
  hz: 2
scenario:
  drones:
    - uid: "DRN-001"
      model: "DJI Mavic 3"
      detected_at_s: 5
      mitigating_at_s: 15
      neutralized_at_s: 35
      operator_bearing_deg: 210.0
      operator_distance_m: 450.0
    - uid: "DRN-002"
      model: "Autel EVO II"
      ...
```

Pydantic `extra="forbid", frozen=True`，欄位缺失、時序矛盾 (`detected > mitigating` 等) 即 fail-fast。

## 七、操控者位置模擬

於 **首次 DETECTED** 的那一刻：
1. 取無人機當時 `(lat, lon)` 作為 RF 天線追蹤基準
2. 以場景 `operator_bearing_deg` + `operator_distance_m` 套 WGS84 destination formula（手寫、不引 geopy）
3. 結果 latch：後續無論無人機移動多少，`operator_lat/lon` **bit-for-bit 不變**（模擬 RF 首次定向鎖定）

SC-SC-005 驗證：15 個 tick 內 operator 欄位與首次鎖定值 bit-identical。

## 八、測試摘要

| 類型 | 數量 | 覆蓋 |
|------|------|------|
| Contract | 7 | /detections schema, /detection/{uid}, /health, takeover caller |
| Unit | 53 | config / logging / state machine / geo / mapsim client / uds client / scenario loader |
| Integration | 17 | e2e lifecycle, is_lost 過濾, 400/404 no-retry, Map Sim unavailable, disappear grace, graceful shutdown, operator_static, multi-drone, 409 handling, API concurrency, 5-drone scale |
| **合計** | **110** | **100% pass** |

### 效能驗證
- API concurrency：5 clients × 30 calls，p95 < 100 ms ✅ (SC-SC-003)
- 啟動到 `/health` 200 < 2s ✅ (SC-SC-011)

## 九、結構化日誌事件

| event | 說明 |
|-------|------|
| `cli_start` / `startup` / `ready` | 啟動生命週期 |
| `detection_new` | 新物件進入 DETECTED |
| `operator_locked` | 首次操控者位置鎖定（含 bearing/distance） |
| `takeover_issued` | UDS 呼叫 |
| `takeover_success` / `takeover_conflict_409` | latch 成功 |
| `takeover_error_4xx` | 400/404 不重試 |
| `takeover_retry` | 5xx/timeout 退避 |
| `state_transition` | DETECTED→MITIGATING→NEUTRALIZED |
| `detection_removed` | NEUTRALIZED 30s 後移除 / DETECTED 誤報移除 |
| `map_sim_unavailable` | 節流 |
| `unknown_uid` | 場景 YAML 未登記 uid（error） |

## 十、下游介面（供 Feature 005 CoT Gateway）

CoT Gateway 的 **SentrycsAdapter** 將：
1. 以 HTTP client 輪詢 `http://sentrycs-sim:17070/detections`（建議 1 Hz）
2. 依 `uid` 為 key 比對前次快照，判定 CoT NEW/UPDATED/REMOVED
3. `model` + `operator_lat/lon` 為 Sentrycs 獨有欄位，將與 EchoShield 雷達資料（高精度位置）在 TrackCorrelator 融合
4. `status ∈ {DETECTED, MITIGATING, NEUTRALIZED}` 對應 CoT 事件類型或自訂 detail 欄位

## 十一、已知遺留

- `operator_distance_m` 由場景 YAML 靜態指定，真實 Sentrycs 應提供動態誤差；PoC 不模擬。
- WGS84 destination formula 為球面近似（不用橢球修正），對 <10km 距離誤差 < 0.5 m，PoC 可接受。
- Constitution 仍為 template placeholder，沿用 PoC 自律準則 G1–G7。

## 十二、檔案清單

```
services/sentrycs-sim/
├── pyproject.toml
├── README.md
├── config/local.yaml
├── scripts/smoke.sh
├── src/sentrycs_sim/
│   ├── __init__.py  __main__.py  cli.py  config.py  logging.py  loop.py
│   ├── models/   (drone_track, scenario, takeover)
│   ├── state/    (machine, registry)
│   ├── geo/      (wgs84)
│   ├── mapsim/   (client)
│   ├── uds/      (client)
│   └── api/      (server, handlers)
└── tests/
    ├── contract/    (4 檔)
    ├── unit/        (8 檔)
    └── integration/ (15 檔)
```

53 支原始碼檔案、64 task、110 測試、ruff + black 乾淨。
