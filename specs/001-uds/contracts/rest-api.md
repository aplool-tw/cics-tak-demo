# Contract: UDS REST API

本檔案定義 UDS 對外的 HTTP 介面契約。**正式契約（normative）** 僅 §1。§2 為 `--debug` 下的除錯端點，
**不納入契約測試**；§3 為 UDS 作為 HTTP Client 呼叫 Map Simulator 的客戶端契約。

---

## 1. 正式契約（Normative）— `POST :8080/command/takeover`

**唯一正式契約端點**（Clarification Q3 / FR-UDS-003）。契約測試 `tests/contract/test_takeover_contract.py`
必須完整覆蓋 §1 的所有行為；`spec.md` User Story 2 的 Acceptance Scenarios 1–8 各對一個 case。

### 1.1 Request

- Method / Path：`POST /command/takeover`
- Headers：`Content-Type: application/json`
- Body schema（JSON）：

| 欄位 | 型別 | 必填 | 值域 | 說明 |
|------|------|------|------|------|
| `drone_id` | string | ✅ | 非空 | UDS 的無人機識別碼（如 `TRK-001`） |
| `target_lat` | number | ✅ | `[-90, 90]` | 降落點緯度（WGS84） |
| `target_lon` | number | ✅ | `[-180, 180]` | 降落點經度（WGS84） |
| `target_alt_m` | number | ✅ | `≥ 0` | 降落高度（公尺，HAE）；**無預設值**，呼叫端必須顯式傳入 |
| `descent_speed_ms` | number | ❌ | `> 0`；預設 `3.0` | 降落速度（m/s） |

- 未知欄位：必須拒絕（`extra = "forbid"` 等效）→ 400 `unknown field: <name>`。

**範例**：

```json
{
  "drone_id": "TRK-001",
  "target_lat": 25.0250,
  "target_lon": 121.5654,
  "target_alt_m": 0.0,
  "descent_speed_ms": 3.0
}
```

### 1.2 Response

#### 1.2.1 `200 OK` — 接受（首次或覆寫）

```json
{
  "status": "accepted",
  "drone_id": "TRK-001",
  "previous_state": "FLYING_NORMAL",
  "new_state": "MITIGATING_TAKEOVER",
  "estimated_landing_s": 45.2
}
```

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `status` | string | ✅ | 固定 `"accepted"` |
| `drone_id` | string | ✅ | echo request |
| `previous_state` | string | ✅ | 收到指令 **前** 的 `FlightState`（字串）。覆寫情境下為 `MITIGATING_TAKEOVER` 或 `LANDING` |
| `new_state` | string | ✅ | 固定 `"MITIGATING_TAKEOVER"` |
| `estimated_landing_s` | number | ✅ | 由 UDS 以 Haversine 距離 / `descent_speed_ms` 估算的降落秒數 |

**覆寫行為（Clarification Q5）**：對同一 `drone_id` 在尚未 `LANDED` 前連續呼叫 → 仍回 `200 accepted`；
回應 body **不得** 新增任何「overwrite flag」或「overwrite count」欄位。

#### 1.2.2 `400 Bad Request` — 請求無效

Body：

```json
{"status": "error", "reason": "<error-reason>"}
```

`reason` 必須屬以下集合之一（字串匹配穩定，契約測試依此斷言）：

| 觸發條件 | `reason` |
|---------|---------|
| 缺必填欄位 | `missing field: <field-name>` |
| 型別錯誤 | `invalid type: <field-name>` |
| `target_lat ∉ [-90, 90]` 或 `target_lon ∉ [-180, 180]` | `invalid coordinates` |
| `target_alt_m < 0` 或缺 `target_alt_m` | `invalid altitude` |
| `descent_speed_ms ≤ 0` | `invalid descent speed` |
| request body 非合法 JSON | `invalid json` |
| `drone_id` 不存在 | `drone_id not found` |
| 目標 `flight_state = LANDED` | `already landed` |
| 未知欄位 | `unknown field: <name>` |

#### 1.2.3 `409 Conflict` — 尚未起飛

目標無人機 `flight_state = IDLE`：

```json
{"status": "error", "reason": "drone not airborne"}
```

**禁止** 用 400 代替 409；「IDLE」與「LANDED」兩種情境 HTTP 狀態碼必須區分。

#### 1.2.4 `500 Internal Server Error`

僅在 UDS 內部異常（state machine 不一致等）時回傳；契約測試不驗證 500 情境。

### 1.3 副作用與時序保證

- `200` 回應回傳前，目標無人機的 `DroneState.flight_state` 已更新為 `MITIGATING_TAKEOVER`、
  `DroneState.takeover_cmd` 已以本次 request 完全覆寫。
- `200` 回應後 **≤ 1 個主迴圈週期**（預設 10 Hz ⇒ ≤ 100 ms）內，UDS → Map Simulator 的推送必須
  帶 `status = "MITIGATING_TAKEOVER"`（SC-003）。
- `400` / `409` 回應 **不得** 變更任何無人機狀態，也 **不得** 產生 `POST /objects/update` 副作用（FR-UDS-015）。

### 1.4 向後相容承諾

- `POST /command/takeover` 為正式契約端點；UDS v1.x 不得移除 / 重命名既有必填欄位或既有 `reason` 字串。
- 新增選填欄位不視為破壞；預設必須保持「與呼叫端不送該欄位」一致行為。

---

## 2. Debug 端點（`--debug` only，**非契約**）

以下端點 **僅在啟動時帶 `--debug` 旗標才註冊**（預設關閉；未帶旗標時 HTTP 路由不存在，請求回 `404 Not Found`）。
回應 schema 不保證跨版本穩定，**不納入契約測試**。Sentrycs Simulator 的正式運行路徑不得依賴。

### 2.1 `GET /status/{drone_id}`

- 用途：PoC 除錯；取得單架無人機當前狀態。
- 預設模式：404 Not Found（路由未註冊）。
- `--debug` 模式：

  **200 OK** 範例：
  ```json
  {
    "drone_id": "TRK-001",
    "lat": 25.0330,
    "lon": 121.5654,
    "alt_m": 120.5,
    "velocity_ms": 15.0,
    "heading_deg": 180.0,
    "flight_state": "FLYING_NORMAL",
    "model": "DJI Mavic 3",
    "operator_lat": 25.0310,
    "operator_lon": 121.5634,
    "is_landed": false
  }
  ```
  **404 Not Found**：`drone_id` 不存在（`{"error": "not found"}`）。

- 資料新鮮度：SC-006 要求回應來自最近一個已完成主迴圈週期；屬觀測性指標，非契約。

### 2.2 `GET /drones`

- 用途：PoC 除錯；列出所有活躍無人機摘要（含 `IDLE`）。
- 預設模式：404 Not Found。
- `--debug` 模式：

  ```json
  {
    "drones": [
      {"drone_id": "TRK-001", "model": "DJI Mavic 3", "flight_state": "FLYING_NORMAL"},
      {"drone_id": "TRK-002", "model": "DJI Matrice 30T", "flight_state": "MITIGATING_TAKEOVER"}
    ]
  }
  ```

### 2.3 觀測 note

若未來需要結構穩定的狀態查詢 API，應在新的正式契約端點（如 `POST /query/state`）中規範，
**不得** 把 `GET /status` / `GET /drones` 升格為正式契約（保持 debug 邊界明確）。

---

## 3. Client 契約 — UDS → Map Simulator `POST :8090/objects/update`

UDS 作為 HTTP **Client** 呼叫 Map Simulator 的端點。介面由 `03-map-simulator-spec.md` §3.1 定義；
本節以 **UDS 的使用義務（SHALL / MUST）** 切面描述，確保 UDS 實作與 Map Simulator 端規格對齊。

### 3.1 呼叫粒度（Clarification Q1）

- 每個主迴圈週期，對每架 `flight_state ≠ IDLE` **且** 未 `landed_finalized` 的無人機各發 **一次** 請求。
- 一次請求 body 對應單一無人機（**不 batch**）。
- 10 架 × 10 Hz 預期總請求速率 ≈ 100 req/s，允許 ±5% 抖動（SC-001 / SC-004）。

### 3.2 Request

- Method / Path：`POST {map-sim-url}/objects/update`（預設 `http://127.0.0.1:8090`，由 `--map-sim-url` 覆寫）。
- Headers：`Content-Type: application/json`。
- Body schema（JSON；對齊 Map Simulator §3.1）：

| 欄位 | 型別 | 必填 | 說明 / 值域 |
|------|------|------|------------|
| `drone_id` | string | ✅ | `DroneState.drone_id` |
| `lat` | number | ✅ | `[-90, 90]` |
| `lon` | number | ✅ | `[-180, 180]` |
| `alt_m` | number | ✅ | `≥ 0` |
| `speed_ms` | number | ✅ | `DroneState.velocity_ms`（注意欄位名換算） |
| `heading_deg` | number | ✅ | `[0, 360)` |
| `status` | string | ✅ | `FlightState.value` ∈ `{FLYING_NORMAL, MITIGATING_TAKEOVER, LANDING, LANDED}`。`IDLE` 永不出現 |
| `timestamp` | string | ✅ | ISO 8601 UTC（毫秒精度），tick 的 wall-clock |

範例：

```json
{
  "drone_id": "TRK-001",
  "lat": 25.0584745,
  "lon": 121.5654089,
  "alt_m": 100.8,
  "speed_ms": 15.1,
  "heading_deg": 180.2,
  "status": "FLYING_NORMAL",
  "timestamp": "2026-04-22T08:00:01.000Z"
}
```

### 3.3 連線與背壓

- 全程共用 **一個** `aiohttp.ClientSession`（HTTP keep-alive、連線池）。
- 每架 drone 各自有 `asyncio.Queue(maxsize=2)`：主迴圈 `put_nowait(payload)`；worker `get()` → `POST`。
- `QueueFull` → 丟棄佇列中最舊一筆、放入最新、記 warning log（`push.backpressure`、
  含 `drone_id` / `dropped_timestamp`）。
- 每次 `POST` 的 `asyncio.timeout` 上限：`500 ms`（寬鬆於一個 tick，避免 timeout 風暴）。

### 3.4 LANDED 收尾（Clarification Q2 / FR-UDS-006）

- 狀態切換到 `LANDED` 的 **同一 tick** 內 enqueue 恰一筆 `status = "LANDED"` 的 payload；
  送出後設 `DroneState.landed_finalized = True`。
- 後續 tick：該 `drone_id` 不再進入任何 `POST /objects/update` 請求（即便 queue 仍有殘留需 drain 並丟棄）。
- 契約測試 / 整合測試必須驗證「`LANDED` 恰出現 1 次，之後該 `drone_id` 的請求數 = 0」。

### 3.5 失敗容錯（FR-UDS-014）

| Map Simulator 回應 / 狀況 | UDS 行為 |
|---------------------------|---------|
| `2xx` | 成功；log `push.ok`（DEBUG 級） |
| `4xx` | log `push.client_error`（WARNING），**不** 重送；下個 tick 照常送最新狀態 |
| `5xx` | log `push.server_error`（WARNING），**不** 重送；下個 tick 照常送 |
| 連線拒絕 / DNS 錯誤 | log `push.conn_error`（WARNING），下個 tick 重試 |
| Timeout（> 500 ms） | log `push.timeout`（WARNING），取消當次請求，下個 tick 重試 |
| **任何錯誤都 MUST NOT 中斷主迴圈** | 確保 SC-007（連續 30 秒不可用仍存活） |

不實作指數退避或重送佇列：下一 tick 自然重試，且只送最新狀態（避免狀態陳舊）。

### 3.6 時序保證

- 從 `POST /command/takeover` `200` 回應到首次推送 `status = "MITIGATING_TAKEOVER"` 的 `POST /objects/update`
  送出，延遲 ≤ 1 個主迴圈週期（預設 ≤ 100 ms）。
- `LANDED` 收尾推送必須與狀態切換處於同一 tick；不得延後到下一 tick。

---

## 4. HTTP 錯誤回應速查表（`POST /command/takeover`）

| 情境 | HTTP | `reason` |
|------|------|---------|
| 一切合法（首次） | 200 | `accepted` |
| 一切合法（連續接管覆寫） | 200 | `accepted` |
| 缺必填 / 型別錯 | 400 | `missing field: …` / `invalid type: …` |
| 座標越界 | 400 | `invalid coordinates` |
| 高度負值或缺失 | 400 | `invalid altitude` |
| `descent_speed_ms ≤ 0` | 400 | `invalid descent speed` |
| 未知欄位 | 400 | `unknown field: …` |
| 非合法 JSON | 400 | `invalid json` |
| `drone_id` 不存在 | 400 | `drone_id not found` |
| 目標 `LANDED` | 400 | `already landed` |
| 目標 `IDLE` | **409** | `drone not airborne` |

---

## 5. Contract test 對照表

| Acceptance Scenario（US2） | 斷言要點 |
|---------------------------|---------|
| 1（`FLYING_NORMAL` + 合法 body） | 200、`status=accepted`、`new_state=MITIGATING_TAKEOVER`、`previous_state=FLYING_NORMAL`、含 `estimated_landing_s` |
| 2（`drone_id` 不存在） | 400、`reason=drone_id not found` |
| 3（`LANDED`） | 400、`reason=already landed` |
| 4（`IDLE`） | **409**、`reason=drone not airborne` |
| 5（缺 `target_lat` / 座標越界） | 400、`reason=missing field: target_lat` / `reason=invalid coordinates` |
| 6（`target_alt_m < 0` 或缺） | 400、`reason=invalid altitude` |
| 7（連續接管覆寫） | 200、`status=accepted`、`new_state=MITIGATING_TAKEOVER`、回應 body 不含覆寫旗標；`DroneState.takeover_cmd` 已是新值 |
| 8（未帶 `--debug` 下 `GET /status` / `GET /drones`） | 404、路由未註冊 |
