# Quickstart — Unified Drone Simulator (UDS)

本指南適用於 PoC 開發者：啟動 UDS、載入場景、驗證接管閉環、跑測試。

> 前置：本 plan 尚未進入 `/speckit.tasks`；實際程式碼由後續 tasks 階段建立。下列指令描述的是
> **完成 tasks 後** 的使用者體驗，保持與本 spec/plan 的 CLI 與介面承諾一致。

---

## 1. 前置需求

- Python **3.11+**
- `pip install -e services/uds[dev]`（安裝 runtime + 測試依賴；`pyproject.toml` 由 tasks 階段建立）
- Map Simulator（`:18090`）已啟動（可選；UDS 在 Map Simulator 不可用時仍會執行並印 warning）

---

## 2. 啟動 UDS（預設模式）

```bash
# 從 repo 根目錄
python -m uds \
  --scenario services/uds/scenarios/single_drone_invasion.yaml \
  --api-port 8080 \
  --map-sim-url http://127.0.0.1:18090 \
  --hz 10
```

- `:18080` 僅註冊 `POST /command/takeover`（正式契約）。
- `GET /status/{drone_id}` 與 `GET /drones` **未註冊**，呼叫回 404。
- 每秒對每架活躍無人機各發 10 次 `POST :18090/objects/update`。

### 2.1 Debug 模式

```bash
python -m uds --scenario services/uds/scenarios/single_drone_invasion.yaml --debug --verbose
```

- 加註 `GET /status/{drone_id}` 與 `GET /drones`（**非契約**，僅供除錯）。
- `--verbose` 將 structlog level 降至 DEBUG，印每次推送的 `drone_id` / HTTP 狀態。

### 2.2 CLI 旗標一覽

| 旗標 | 預設 | 說明 |
|------|------|------|
| `--scenario <path>` | （必填） | YAML 場景檔 |
| `--api-port <int>` | `8080` | REST API 埠號 |
| `--map-sim-url <url>` | `http://127.0.0.1:18090` | Map Simulator base URL |
| `--hz <int>` | `10`（或 YAML 覆寫） | 主迴圈頻率（1–20） |
| `--verbose` | 關閉 | log level → DEBUG |
| `--debug` | 關閉 | 註冊除錯端點 `GET /status`、`GET /drones` |

---

## 3. YAML 場景範例

`services/uds/scenarios/single_drone_invasion.yaml`：

```yaml
scenario:
  name: "single_drone_invasion"
  description: "單架 DJI Mavic 3 從北方入侵，Sentrycs 識別並接管"
  update_hz: 10
  servers:
    command_api_port: 8080

  drones:
    - drone_id: "TRK-001"
      model: "DJI Mavic 3"
      start_lat: 25.0598
      start_lon: 121.5654
      start_alt_m: 120.0
      speed_ms: 15.0
      heading_deg: 180.0
      operator_bearing_deg: 225
      operator_distance_m: 300
      waypoints:
        - { lat: 25.0330, lon: 121.5654, alt_m: 100.0 }
      landing_point:
        lat: 25.0250
        lon: 121.5654
        alt_m: 0.0
        descent_speed_ms: 3.0

  timeline:
    - at_s: 0
      action: start_flying
      drone_id: "TRK-001"
```

> `timeline[].action` 僅允許 `start_flying`（封閉白名單，Clarification Q4）。其他值 / 拼寫錯誤 → UDS 啟動
> 時 fail-fast 並以 exit code 2 結束。

---

## 4. 驗證接管閉環（手動 smoke test）

### 4.1 觀察推送

（假設 Map Simulator 已啟動）在另一個終端機：

```bash
curl 'http://127.0.0.1:18090/objects?lat=25.0330&lon=121.5654&radius_m=5000' | jq
```

應看到 `TRK-001` 位置每 100 ms 更新一次。

### 4.2 送接管指令

```bash
curl -X POST http://127.0.0.1:18080/command/takeover \
  -H 'Content-Type: application/json' \
  -d '{
        "drone_id": "TRK-001",
        "target_lat": 25.0250,
        "target_lon": 121.5654,
        "target_alt_m": 0.0,
        "descent_speed_ms": 3.0
      }'
```

預期回應（200 OK）：

```json
{
  "status": "accepted",
  "drone_id": "TRK-001",
  "previous_state": "FLYING_NORMAL",
  "new_state": "MITIGATING_TAKEOVER",
  "estimated_landing_s": 45.2
}
```

### 4.3 錯誤情境速查

| 指令 | 預期 |
|------|------|
| `-d '{"drone_id":"TRK-404","target_lat":0,"target_lon":0,"target_alt_m":0}'` | 400 `drone_id not found` |
| 對 `TRK-001` 在起飛前（`timeline.start_flying` 尚未觸發）送接管 | **409** `drone not airborne` |
| `target_lat: 999` | 400 `invalid coordinates` |
| 省略 `target_alt_m` | 400 `invalid altitude` |
| 對已 `LANDED` 的 `TRK-001` 再送接管 | 400 `already landed` |
| 預設模式下 `curl :18080/drones` | 404（路由未註冊） |
| `--debug` 模式下 `curl :18080/drones` | 200，回傳 drone 清單 |

---

## 5. 測試指令

```bash
# 全部測試
cd services/uds
pytest

# 只跑正式契約測試（POST /command/takeover）
pytest tests/contract -v

# 整合測試（per-drone 推送頻率 / LANDED 收尾 / 接管閉環）
pytest tests/integration -v

# 單元測試（WGS84 / state machine / trajectory）
pytest tests/unit -v

# 覆蓋率（選配）
pytest --cov=uds --cov-report=term-missing
```

### 5.1 測試與 Spec Acceptance Scenarios 的對照

- `tests/contract/test_takeover_contract.py` ↔ User Story 2 的 Acceptance 1–8（見 `contracts/rest-api.md` §5）。
- `tests/integration/test_push_loop.py` ↔ User Story 3 的 Acceptance 1–3（含 per-drone 速率、LANDED 收尾）。
- `tests/integration/test_takeover_closure.py` ↔ User Story 1 的 Acceptance 1–3（端到端狀態閉環）。
- `tests/integration/test_scenario_loader.py` ↔ FR-UDS-007 白名單 fail-fast（Edge Cases §「場景 YAML `action` 未知值」）。

---

## 6. 常見問題

- **UDS 啟動時直接退出、exit code 2**：多半是 YAML schema 錯（如 `timeline[].action` 不是 `start_flying`、
  欄位缺失、值域越界）。錯誤訊息印在 stderr。
- **接管回 409 而非 400**：目標無人機仍處於 `IDLE`（`timeline.start_flying` 還沒觸發）。這是刻意
  區分的語意（Clarification Q5）。
- **Map Simulator 關機 UDS 不崩**：符合 FR-UDS-014；UDS 會每 tick 送並 log 錯誤，Map Simulator 恢復後
  自動重新同步。
- **`LANDED` 後 curl Map Simulator 還看到該無人機**：那是 Map Simulator 自己的保留策略（`include_lost`
  等），非 UDS 職責；UDS 端確認不再發出該 `drone_id` 的任何 `POST /objects/update` 即合規。
