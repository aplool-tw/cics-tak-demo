# Contract: Sentrycs HTTP Status API

本檔定義 Sentrycs Simulator 對 CoT Gateway `SentrycsAdapter` 提供的 **HTTP JSON Status API**（:7070）契約。
**正式契約（normative）**：§2.1 `GET /detections`、§2.2 `GET /detection/{uid}`、§2.3 `GET /health` 三個端點。
`tests/contract/test_detections_schema.py` 與 `tests/contract/test_detection_by_uid.py` 必須完整覆蓋
§2 的所有回應行為。

**監聽**：`http://0.0.0.0:7070`（CLI `--api-port` 或 scenario YAML `api_port` 可覆寫）。

---

## 1. 通用規範

### 1.1 編碼 / 頭

- Response Content-Type：`application/json; charset=utf-8`
- 所有 timestamp 以 ISO 8601 UTC 表示，**必以 `Z` 後綴**輸出（與 `specs/002-map-sim/contracts/rest-api.md` §1.1、
  `specs/001-uds/contracts/rest-api.md` §3.2 一致）。

### 1.2 錯誤 body schema（僅 §2.2 `/detection/{uid}` 可能 404）

```json
{"status": "error", "reason": "not_found"}
```

`reason` 集合目前僅 `not_found`（穩定字串，契約測試以精確匹配）。

### 1.3 並發與快照一致性

- **至少 5 個並發 HTTP Client**以 1 Hz 輪詢情境下 `GET /detections` 回應 p95 < 100 ms、錯誤率 0%（SC-SC-003）。
- 同一時刻的不同 Client 請求 MUST 取得**一致快照**（主 registry 以 `list(...)` 原子複製後逐筆投影）。

### 1.4 空快照語意

- `GET /detections`：所有無人機皆 `IDLE`（或尚未到 `detected_at_s`）時回 HTTP 200 + body `[]`，**絕不**回 404。

---

## 2. 正式契約端點（Normative）

### 2.1 `GET /detections`

**用途**：回傳所有**非 IDLE** 偵測目標陣列。CoT Gateway 正式輪詢端點。

#### 2.1.1 Request

- Method / Path：`GET /detections`
- Query Parameters：無。未知 query 參數一律靜默忽略。

#### 2.1.2 Response: `200 OK`

```json
[
  {
    "uid": "TRK-001",
    "model": "DJI Mavic 3",
    "detection_status": "MITIGATING",
    "lat": 25.0584745,
    "lon": 121.5654089,
    "alt_m": 100.8,
    "velocity_ms": 15.1,
    "azimuth_deg": 180.2,
    "operator_lat": 25.0559810,
    "operator_lon": 121.5628041,
    "operator_distance_m": 300.0,
    "operator_bearing_deg": 225.0,
    "timestamp": "2026-04-22T08:00:01.500Z",
    "is_landed": false
  },
  {
    "uid": "TRK-002",
    "model": "Unknown",
    "detection_status": "DETECTED",
    "lat": 25.0410,
    "lon": 121.5800,
    "alt_m": 150.0,
    "velocity_ms": 18.0,
    "azimuth_deg": 270.0,
    "operator_lat": 25.0435,
    "operator_lon": 121.5775,
    "operator_distance_m": 350.0,
    "operator_bearing_deg": 45.0,
    "timestamp": "2026-04-22T08:00:01.500Z",
    "is_landed": false
  }
]
```

#### 2.1.3 欄位契約（每個 array 元素；對應 FR-SC-016 14 欄位）

| 欄位 | 型別 | 必填 | 值域 | 說明 |
| --- | --- | --- | --- | --- |
| `uid` | string | ✅ | 非空 | 對應 Map Simulator 的 `drone_id`，整個場景生命週期穩定 |
| `model` | string | ✅ | 非空字串；場景未登記時為 `"Unknown"` | 來自 scenario YAML `drones[*].model`；**不**來自 Map Sim |
| `detection_status` | string | ✅ | 列舉 `"DETECTED"` / `"MITIGATING"` / `"NEUTRALIZED"`（不含 `"IDLE"`）| IDLE 目標不出現於 array |
| `lat` | number | ✅ | `[-90, 90]` | 最近一次 Map Sim 同步的 WGS84 緯度；Map Sim 下線時保留上次 |
| `lon` | number | ✅ | `[-180, 180]` | 同上，經度 |
| `alt_m` | number | ✅ | 實數 | 高度（公尺，HAE）|
| `velocity_ms` | number | ✅ | `≥ 0` | Map Sim `speed_ms` echo |
| `azimuth_deg` | number | ✅ | `[0, 360)` | Map Sim `heading_deg` echo（正北為 0）|
| `operator_lat` | number | ✅ | `[-90, 90]` | 建立 track 時一次性計算後**永久鎖定**（SC-SC-004）|
| `operator_lon` | number | ✅ | `[-180, 180]` | 同上，經度 |
| `operator_distance_m` | number | ✅ | `[200, 500]` | echo from scenario |
| `operator_bearing_deg` | number | ✅ | `[0, 360)` | echo from scenario |
| `timestamp` | string | ✅ | ISO 8601 UTC, `Z` 結尾 | 該筆狀態的最新更新時間（位置更新或狀態轉移）|
| `is_landed` | bool | ✅ | `true` / `false` | `detection_status == "NEUTRALIZED"` 時為 `true`，否則 `false` |

**不變式（context invariants，契約測試必須驗證）**：

1. **不含 IDLE**：array 內不得出現 `detection_status == "IDLE"` 的元素。
2. **is_landed ↔ NEUTRALIZED**：`is_landed == true` ⇔ `detection_status == "NEUTRALIZED"`。
3. **operator 不變**：同一 `uid` 在整個場景期間，每次輪詢 `operator_lat` / `operator_lon` 必為**完全相同 float**（SC-SC-004）。
4. **timestamp 單調**：同一 `uid` 連續兩次輪詢的 `timestamp` 不得倒退。
5. **排序**：array **不保證順序**；消費者 MUST 以 `uid` 為 key 比對（契約測試不得斷言順序）。
6. **空陣列**：無任何非 IDLE 目標時回 `[]`，HTTP 200（FR-SC-014、Story 1 AS3）。

---

### 2.2 `GET /detection/{uid}`

**用途**：單一目標查詢。

#### 2.2.1 Request

- Method / Path：`GET /detection/{uid}`，其中 `{uid}` 為 URL path parameter。
- Query Parameters：無。

#### 2.2.2 Response

**`200 OK`** — `uid` 存在於 registry 且 `detection_status != IDLE`：

```json
{
  "uid": "TRK-001",
  "model": "DJI Mavic 3",
  "detection_status": "MITIGATING",
  "lat": 25.0584745,
  "lon": 121.5654089,
  "alt_m": 100.8,
  "velocity_ms": 15.1,
  "azimuth_deg": 180.2,
  "operator_lat": 25.0559810,
  "operator_lon": 121.5628041,
  "operator_distance_m": 300.0,
  "operator_bearing_deg": 225.0,
  "timestamp": "2026-04-22T08:00:01.500Z",
  "is_landed": false
}
```

欄位契約同 §2.1.3（單一 element，非 array）。

**`404 Not Found`** — `uid` 不存在於 registry，**或** 存在但處於 `IDLE`（尚未到 `detected_at_s` 或已被 rollback）：

```json
{"status": "error", "reason": "not_found"}
```

### 2.3 `GET /health`

**用途**：liveness/readiness 探測。供 smoke test 與啟動就緒判斷。

#### 2.3.1 Request

- Method / Path：`GET /health`
- Query Parameters：無。

#### 2.3.2 Response: `200 OK`

```json
{
  "status": "ok",
  "uptime_s": 123.4,
  "tracked_drones": 2,
  "map_sim_reachable": true
}
```

| 欄位 | 型別 | 必填 | 說明 |
| --- | --- | --- | --- |
| `status` | string | ✅ | 固定 `"ok"`（健康；若主 loop crash 則整個程序已退出，不會回此 body）|
| `uptime_s` | number | ✅ | 自行程啟動起算的秒數，`round(_, 1)` |
| `tracked_drones` | integer | ✅ | 當前 registry 內非 IDLE 目標數量（= `GET /detections` 陣列長度）|
| `map_sim_reachable` | bool | ✅ | 最近一次 Map Sim 查詢是否成功；於指數退避期間為 `false` |

**不變式**：

- 啟動後 **< 2 s** 內 `GET /health` MUST 回 HTTP 200（SC-SC-011）。
- 此端點不觸發任何狀態機副作用、不寫入 registry。

---

## 3. 非契約端點（未來擴充保留）

**當前版本不提供**以下端點，消費者 MUST NOT 依賴其存在；若未來提供，將新增至本契約 §2 並附獨立契約測試：

- `GET /scenario`（回傳當前場景快照）
- `POST /scenario/reset`（重置場景時鐘）
- `GET /metrics`（Prometheus 格式）

---

## 4. 錯誤速查表

| HTTP Status | 觸發條件 | Body |
| --- | --- | --- |
| `404` | `GET /detection/{uid}` 之 `uid` 不存在或為 IDLE | `{"status": "error", "reason": "not_found"}` |
| `405` | 對 §2 端點使用非 GET method | aiohttp 預設 body（非契約範圍）|
| `500` | 程式內部錯誤（應視為 bug）| aiohttp 預設 body；CI 測試要求 0 次出現 |

**注意**：`GET /detections` 永不回 404；任何「無資料」情境一律回 200 + `[]`。
