# Contract: Map Simulator REST API

本檔案定義 Map Sim 對外的 HTTP 介面契約。**正式契約（normative）** 為 §3.1 / §3.2 / §3.3 的三個端點
（契約測試必須完整覆蓋）；§4 的除錯端點 `GET /objects/all`、`DELETE /objects/{drone_id}` 在預設啟動下
**即註冊可用**，但其回應 schema 的跨版本穩定性等級**低於** §3（下游 EchoShield / Sentrycs 的正式運行
路徑**不得**依賴 §4）。

**監聽**：`http://127.0.0.1:18090`（CLI `--port` 可覆寫；預設綁 `127.0.0.1`）。

---

## 1. 通用規範

### 1.1 編碼 / 頭

- Request / Response Content-Type：`application/json; charset=utf-8`
- 所有 timestamp 以 ISO 8601 UTC 表示，接受 `Z` 後綴或 `+00:00`（request 側）；response 側一律以 `Z` 後綴
  輸出（與 `specs/001-uds/contracts/rest-api.md` §3.2 一致）。

### 1.2 錯誤 body schema（所有 4xx 共用）

```json
{"status": "error", "reason": "<stable-reason-string>"}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `status` | string | 固定 `"error"` |
| `reason` | string | **穩定字串**（契約一部份）。契約測試以精確字串匹配 |

`reason` 字串集合見 §5「錯誤速查表」。`reason` 字串不隨 Map Sim 版本漂移（v1.x 向後相容承諾）。

### 1.3 副作用隔離（FR-MS-015）

任何 `4xx` / `5xx` 回應 **MUST NOT**：
- 變更 `ObjectRegistry` 狀態
- 更新任何 `drone_id` 的 `last_seen_at`
- 觸發 TTL cleanup

---

## 2. 必填欄位與寬鬆欄位原則

- `POST /objects/update` 的 request body **必填 8 欄位**（§3.1）：漏一即 `400 missing required field`。
- `POST /objects/update` body 中 **未知欄位必須靜默忽略**（FR-MS-002）：`model` / `operator_lat` /
  `operator_lon` 等 Sentrycs 專屬欄位或任何未來欄位，Map Sim MUST 正常回 `200`，**不得**回 400。
- `GET /objects` 的 query 參數中，**必填**為 `lat` / `lon` / `radius_m`；**選填** `include_lost`（預設
  `false`）。未知 query 參數一律忽略。

---

## 3. 正式契約端點（Normative）

### 3.1 `POST /objects/update`

**用途**：UDS（或任何授權的上游）推送無人機狀態。

#### 3.1.1 Request

- Method / Path：`POST /objects/update`
- Headers：`Content-Type: application/json`
- Body schema（JSON；對齊 `specs/001-uds/contracts/rest-api.md` §3.2 的 8 欄位）：

| 欄位 | 型別 | 必填 | 值域 | 說明 |
|------|------|------|------|------|
| `drone_id` | string | ✅ | 非空 | UDS 的無人機識別碼（如 `TRK-001`） |
| `lat` | number | ✅ | `[-90, 90]`（由呼叫端保證；server 不驗值域）| WGS84 緯度 |
| `lon` | number | ✅ | `[-180, 180]`（同上）| WGS84 經度 |
| `alt_m` | number | ✅ | 實數 | 高度（公尺，HAE） |
| `speed_ms` | number | ✅ | 實數 | 速度（m/s）|
| `heading_deg` | number | ✅ | `[0, 360)`（呼叫端保證）| 飛行方向（正北為 0）|
| `status` | string | ✅ | 非空字串 | UDS FlightState 字串；Map Sim 不白名單驗證，任何非空字串接受 |
| `timestamp` | string | ✅ | ISO 8601 UTC | request 側接受 `Z` 或 `+00:00` |

- **未知欄位**：**必須靜默接受**（`extra = "ignore"` 等效）→ `200 OK`。不得回 400。
- **多餘欄位**（例如 `model` / `operator_lat` / `operator_lon`）：同上，靜默忽略。
- 重複 `drone_id`：最新一筆完全覆寫舊值（無合併、無歷史、無版本計數）；`last_seen_at` 重設為當下。

**範例**：

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

#### 3.1.2 Response

##### 3.1.2.1 `200 OK` — 寫入成功

```json
{
  "status": "updated",
  "drone_id": "TRK-001",
  "registered_at": "2026-04-22T08:00:01.015Z"
}
```

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `status` | string | ✅ | 固定 `"updated"` |
| `drone_id` | string | ✅ | echo request |
| `registered_at` | string | ✅ | Map Sim 本地時鐘記錄的 `last_seen_at`，ISO 8601 UTC（以 `Z` 後綴） |

##### 3.1.2.2 `400 Bad Request`

Body schema 同 §1.2。`reason` 必屬下表之一：

| 觸發條件 | `reason` |
|---------|---------|
| 非合法 JSON（parse 失敗）| `invalid json` |
| 缺必填欄位 | `missing required field: <field-name>` |
| 型別錯誤（數值欄位非數、字串欄位非字串） | `invalid type: <field-name>` |
| `drone_id` 或 `status` 為空字串 | `invalid type: <field-name>` |
| `timestamp` 非 ISO 8601 | `invalid type: timestamp` |

**不回 400 的情境（MUST 回 200）**：request body 含未在上表 8 欄位中的任何額外欄位。

##### 3.1.2.3 `5xx`

僅在 Map Sim 內部異常（寫入過程中非預期錯誤）時回傳；契約測試不驗證 5xx 情境。`5xx` 必不修改 registry。

#### 3.1.3 副作用與時序

- `200` 回應回傳前，目標 `drone_id` 的 `DroneObject` 已寫入 / 覆寫 registry，`last_seen_at` 已設為
  `registered_at`。
- `400` / `5xx` 回應 **MUST NOT** 修改 registry，**MUST NOT** 更新 `last_seen_at`。

---

### 3.2 `GET /objects`

**用途**：地理範圍查詢。下游 EchoShield（radius 4800）/ Sentrycs（radius 8000）正式資料來源。

#### 3.2.1 Request

- Method / Path：`GET /objects`
- Query Parameters：

| 參數 | 型別 | 必填 | 值域 | 預設 | 說明 |
|------|------|------|------|------|------|
| `lat` | float | ✅ | `[-90, 90]` | — | 查詢圓心緯度 |
| `lon` | float | ✅ | `[-180, 180]` | — | 查詢圓心經度 |
| `radius_m` | float | ✅ | `> 0` | — | 查詢半徑（公尺）|
| `include_lost` | bool | ❌ | `true` / `false`（case-insensitive）| `false` | 是否包含 `is_lost=true` 的物件 |

- 未知 query 參數：靜默忽略。

#### 3.2.2 Response

##### 3.2.2.1 `200 OK`

```json
{
  "query": {
    "lat": 25.0330,
    "lon": 121.5654,
    "radius_m": 4800.0,
    "include_lost": false,
    "timestamp": "2026-04-22T08:00:01.500Z"
  },
  "count": 2,
  "objects": [
    {
      "drone_id": "TRK-002",
      "lat": 25.0410,
      "lon": 121.5800,
      "alt_m": 150.0,
      "speed_ms": 18.0,
      "heading_deg": 270.0,
      "status": "FLYING_NORMAL",
      "timestamp": "2026-04-22T08:00:00.900Z",
      "distance_m": 1563.2,
      "last_seen_s": 0.1,
      "is_lost": false
    },
    {
      "drone_id": "TRK-001",
      "lat": 25.0584745,
      "lon": 121.5654089,
      "alt_m": 100.8,
      "speed_ms": 15.1,
      "heading_deg": 180.2,
      "status": "FLYING_NORMAL",
      "timestamp": "2026-04-22T08:00:01.000Z",
      "distance_m": 2831.5,
      "last_seen_s": 0.3,
      "is_lost": false
    }
  ]
}
```

**欄位契約**：

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `query.lat` / `query.lon` / `query.radius_m` | number | ✅ | echo |
| `query.include_lost` | bool | ✅ | echo（即使 request 未帶，必以 `false` 輸出）|
| `query.timestamp` | string | ✅ | Map Sim 產生此回應的時間（ISO 8601 UTC, `Z` 後綴）|
| `count` | integer | ✅ | `objects` 陣列長度 |
| `objects` | array | ✅ | 過濾 + 排序後的物件集合；empty 查詢為 `[]` 而非 null |
| `objects[].drone_id` | string | ✅ | |
| `objects[].lat` / `lon` / `alt_m` / `speed_ms` / `heading_deg` | number | ✅ | DroneObject 原值 |
| `objects[].status` | string | ✅ | **DroneObject.status 原值**；此欄位 **MUST NEVER** 被覆寫為 `"lost"` 或任何 TTL 衍生值 |
| `objects[].timestamp` | string | ✅ | request body 中的 timestamp 原值（ISO 8601 UTC, `Z` 後綴）|
| `objects[].distance_m` | number | ✅ | Haversine 距離（公尺），`round(_, 1)` |
| `objects[].last_seen_s` | number | ✅ | `now - last_seen_at` 秒數，`round(_, 1)` |
| `objects[].is_lost` | bool | ✅ | TTL 狀態：`last_seen_s >= ttl_warn_s` 時為 `true` |

**排序契約**：`objects[]` **MUST** 依 `distance_m` 由近到遠升冪排序；相同距離的 tie-break 順序**不**納入契約。

**過濾契約**：
1. `haversine_m(center, obj) <= radius_m` — 範圍內。
2. `obj.age_s() < ttl_remove_s` — 尚未逾 remove 線（即使 `include_lost=true` 也不包含已過 remove 線的物件；
   FR-MS-006 末段）。
3. `include_lost=false`（預設）時：額外要求 `obj.age_s() < ttl_warn_s`。
4. `include_lost=true` 時：跳過 (3)，允許 `is_lost=true` 的物件出現。

**Clarification Q1 落點（`status` 不覆寫、`is_lost` 獨立欄位）**：
- `objects[].status` 永遠是 `DroneObject.status` 原值（`FLYING_NORMAL` / `MITIGATING_TAKEOVER` / `LANDING`
  / `LANDED`，或任何 UDS 未來擴充的非空字串）。**不得**在 `is_lost=true` 時被改寫為 `"lost"`。
- `objects[].is_lost` 為**獨立布林欄位**：
  - `last_seen_s >= ttl_warn_s` → `true`（僅在 `include_lost=true` 的回應中可能為 `true`；
    `include_lost=false` 的回應中所有物件此欄必為 `false`，因為 `is_lost=true` 者已被過濾）。
  - `last_seen_s < ttl_warn_s` → `false`。
- `is_lost` 欄位 **MUST 明確輸出**為 `true` 或 `false`，**不得省略**（`include_lost=false` 下仍輸出 `false`）。
  這與 spec §Clarifications Q1 「擇一實作並於 contracts 固定」一致；本契約固定為「明確輸出」一路。

**空結果**（FR-MS-004）：若過濾後 `objects` 為空，仍回 `200`、`count: 0`、`objects: []`。**不得**回 404。

##### 3.2.2.2 `400 Bad Request`

Body schema 同 §1.2。`reason` 必屬下表之一：

| 觸發條件 | `reason` |
|---------|---------|
| 缺 `lat` / `lon` / `radius_m` 任一 | `missing required parameter: <param-name>` |
| `lat` / `lon` / `radius_m` 無法 parse 為 float | `invalid type: <param-name>` |
| `radius_m <= 0`（含 `0` 與負值）| `radius_m must be > 0` |
| `lat ∉ [-90, 90]` 或 `lon ∉ [-180, 180]` | `invalid coordinates` |
| `include_lost` 值非 `"true"` / `"false"`（case-insensitive）| `invalid type: include_lost` |

---

### 3.3 `GET /health`

**用途**：liveness / readiness 檢查；SC-MS-008 要求在 100 req/s POST 壓力下仍 < 50 ms。

#### 3.3.1 Request

- Method / Path：`GET /health`
- 無 query / body。

#### 3.3.2 Response

##### 3.3.2.1 `200 OK`

```json
{
  "status": "ok",
  "registered_objects": 3,
  "uptime_s": 125.4
}
```

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `status` | string | ✅ | 固定 `"ok"` |
| `registered_objects` | integer | ✅ | registry 內當前物件數（含 `is_lost=true` 但尚未被 cleanup 的；對齊 `GET /objects/all` 的 `total`）|
| `uptime_s` | number | ✅ | 自 server 啟動至今秒數，`round(_, 1)` |

`GET /health` 不回 4xx（無 request 輸入可錯）；僅在 server 嚴重故障時回 5xx。

---

## 4. 除錯端點（預設啟用，但**非正式契約**）

下列端點在預設啟動下即註冊可用（不需 `--debug` 旗標），但回應 schema 的跨版本穩定性**低於** §3。
下游 EchoShield / Sentrycs **MUST NOT** 在正式資料流中呼叫這些端點；僅供人工除錯 / 本地整合測試使用。

### 4.1 `GET /objects/all`

**用途**：取得 registry 內所有物件（含 `is_lost=true` 但尚未被 cleanup 者），用於除錯。

**Response `200 OK`**：

```json
{
  "total": 3,
  "active": 2,
  "lost": 1,
  "objects": [
    {"drone_id": "TRK-001", "lat": 25.0584, "lon": 121.5654, "alt_m": 100.8,
     "speed_ms": 15.1, "heading_deg": 180.2, "status": "FLYING_NORMAL",
     "timestamp": "2026-04-22T08:00:00.900Z", "last_seen_s": 0.5, "is_lost": false},
    {"drone_id": "TRK-002", "lat": 25.0410, "lon": 121.5800, "alt_m": 150.0,
     "speed_ms": 18.0, "heading_deg": 270.0, "status": "LANDING",
     "timestamp": "2026-04-22T08:00:00.800Z", "last_seen_s": 1.2, "is_lost": false},
    {"drone_id": "TRK-003", "lat": 25.0700, "lon": 121.5900, "alt_m": 80.0,
     "speed_ms": 0.0, "heading_deg": 90.0, "status": "LANDED",
     "timestamp": "2026-04-22T07:59:52.000Z", "last_seen_s": 7.8, "is_lost": true}
  ]
}
```

- `active = #{is_lost == false}`
- `lost = #{is_lost == true}`
- `total = active + lost`
- `objects[]` **不**含 `distance_m`（無查詢中心）；其餘欄位同 §3.2.2.1，`status` 同樣保留原始值、`is_lost`
  同樣明確輸出。
- 排序**不**納入契約（實作可為 insertion order）。

### 4.2 `DELETE /objects/{drone_id}`

**用途**：手動移除特定物件（測試用）。

**Response `200 OK`**：

```json
{"status": "removed", "drone_id": "TRK-001"}
```

或當目標 `drone_id` 不存在：

```json
{"status": "not_found", "drone_id": "TRK-001"}
```

**注意**：此端點仍回 `200`（by design；對應 spec §3.3 風格），**不**回 `404`。`drone_id` 不存在是正常
情境。

---

## 5. 錯誤速查表

| 端點 | HTTP | `reason` | 觸發 |
|------|------|---------|------|
| `POST /objects/update` | 200 | `status: "updated"` | 成功（首次或覆寫）|
| `POST /objects/update` | 400 | `invalid json` | body 非合法 JSON |
| `POST /objects/update` | 400 | `missing required field: <name>` | 缺 8 欄位中任一 |
| `POST /objects/update` | 400 | `invalid type: <name>` | 欄位型別錯；`timestamp` 格式錯 |
| `GET /objects` | 200 | — | 成功（含 `count=0`）|
| `GET /objects` | 400 | `missing required parameter: <name>` | 缺 `lat`/`lon`/`radius_m` |
| `GET /objects` | 400 | `invalid type: <name>` | `lat`/`lon`/`radius_m`/`include_lost` 格式錯 |
| `GET /objects` | 400 | `radius_m must be > 0` | `radius_m <= 0` |
| `GET /objects` | 400 | `invalid coordinates` | `lat ∉ [-90,90]` 或 `lon ∉ [-180,180]` |
| `GET /health` | 200 | `status: "ok"` | 始終 |
| `GET /objects/all` | 200 | — | 始終（非契約）|
| `DELETE /objects/{id}` | 200 | `status: "removed"` / `"not_found"` | 非契約 |

---

## 6. 向後相容承諾

Map Sim v1.x MUST NOT：
- 移除 / 重命名 §3.1 / §3.2 / §3.3 任何必填欄位。
- 移除 / 重命名 §3.2.2.1 response 中的 `is_lost` / `distance_m` / `last_seen_s` / `count` / `objects` /
  `status`（物件層 status）/ `timestamp`（物件層 timestamp） 欄位。
- 變更 §5 `reason` 字串集合中任一字串的拼寫（新增字串不違反相容）。
- 變更 `objects[]` 的 `distance_m` 升冪排序契約。
- 把 `objects[].status` 改為隨 TTL 狀態覆寫的衍生值（Clarification Q1 永久鎖定原值）。

新增**選填**欄位、新增**選填** query 參數、放寬（而非收緊）輸入驗證，**不**視為破壞性變更。
