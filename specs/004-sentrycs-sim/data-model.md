# Phase 1 Data Model: Sentrycs Simulator

本檔描述 Sentrycs Simulator 所有 runtime 實體（pydantic models + Enum + in-memory registry）。所有實體皆
存活於單一 asyncio event loop，**無持久化**；程序重啟 = 從 scenario YAML 重新載入。

## 1. Enum: `DetectionStatus`

```python
class DetectionStatus(str, Enum):
    IDLE = "IDLE"                # 未偵測（不輸出至 /detections）
    DETECTED = "DETECTED"        # 已偵測，未接管
    MITIGATING = "MITIGATING"    # takeover 已發送且成功（200/409）
    NEUTRALIZED = "NEUTRALIZED"  # 目標已 LANDED 或 MITIGATING 消失寬限到期
```

**合法轉移矩陣**（非列則禁止；違反即 `state_transition` 事件以 ERROR level 拒絕）：

| From | To | 觸發條件 |
| --- | --- | --- |
| `IDLE` | `DETECTED` | 場景時鐘 ≥ `detected_at_s` 且 Map Sim 於 8 km 內可見此 `uid` 且 `is_lost=false` |
| `DETECTED` | `IDLE` | 目標於 DETECTED 階段自 Map Sim 移除（誤報 rollback，不送 takeover）|
| `DETECTED` | `MITIGATING` | 場景時鐘 ≥ `mitigating_at_s` 且 UDS takeover 回 200 或 409 |
| `DETECTED` | `DETECTED` | UDS takeover 回 400 / 404（保留狀態，不重送）|
| `MITIGATING` | `NEUTRALIZED` | Map Sim 回傳 `status == "LANDED"`；或目標自 Map Sim 消失 ≥ 10 s 寬限 |
| `NEUTRALIZED` | `IDLE`（= 從 registry 移除）| 進入 NEUTRALIZED 起算 30 s |

## 2. Config Entities（scenario YAML → pydantic，fail-fast）

### 2.1 `SentrycsConfig`（root）

| 欄位 | 型別 | 必填 | 值域 / 預設 | 說明 |
| --- | --- | --- | --- | --- |
| `sensor_lat` | float | ✅ | `[-90, 90]` | 感測器安裝緯度 |
| `sensor_lon` | float | ✅ | `[-180, 180]` | 感測器安裝經度 |
| `detection_radius_m` | float | ❌ | 預設 `8000.0`（固定）| Map Sim 查詢半徑；固定 8 km |
| `poll_interval_s` | float | ❌ | 預設 `0.5`（2 Hz）| Map Sim 輪詢週期 |
| `map_sim_url` | string | ❌ | 預設 `http://localhost:18090` | Map Sim base URL |
| `map_sim_timeout_s` | float | ❌ | 預設 `1.0` | Map Sim 單次查詢逾時 |
| `uds_url` | string | ❌ | 預設 `http://localhost:18080` | UDS base URL |
| `uds_timeout_s` | float | ❌ | 預設 `3.0` | UDS takeover 逾時 |
| `api_host` | string | ❌ | 預設 `0.0.0.0` | Status API 綁定 host |
| `api_port` | int | ❌ | `[1, 65535]`，預設 `7070` | Status API 綁定 port；CLI `--api-port` 可覆寫 |
| `neutralized_hold_s` | float | ❌ | 預設 `30.0` | NEUTRALIZED 保留時間（FR-SC-005）|
| `mitigating_disappear_grace_s` | float | ❌ | 預設 `10.0` | MITIGATING 期間目標消失寬限（Edge Cases §4）|
| `drones` | list[`DroneScenario`] | ✅ | `len ≥ 1` | 場景無人機清單 |

**`@model_validator(after)`** 層級交叉規則：

- `drones[*].uid` 全域 unique。

### 2.2 `DroneScenario`（每架無人機必填 7 欄，對應 FR-SC-021）

| 欄位 | 型別 | 必填 | 值域 | 說明 |
| --- | --- | --- | --- | --- |
| `uid` | string | ✅ | 非空字串 | 對應 Map Simulator `/objects` 回傳的 `drone_id` |
| `model` | string | ✅ | 非空字串 | 例 "DJI Mavic 3"；輸出至 `/detections.model`（FR-SC-016） |
| `detected_at_s` | float | ✅ | `≥ 0` | 場景時鐘進入 DETECTED 的秒數 |
| `mitigating_at_s` | float | ✅ | `≥ detected_at_s` | 場景時鐘送 takeover 的秒數 |
| `neutralized_at_s` | float | ✅ | `≥ mitigating_at_s` | 期望制壓完成秒數（參考；實際落地以 Map Sim `status=LANDED` 為準）|
| `operator_bearing_deg` | float | ✅ | `[0, 360)` | 操控者相對無人機初始位置的方位（正北為 0） |
| `operator_distance_m` | float | ✅ | `[200, 500]` | 操控者距無人機初始位置（公尺） |

**`@model_validator(after)`** 層級交叉規則：

- `detected_at_s <= mitigating_at_s <= neutralized_at_s`（違反 → fail fast）。

**任一欄位缺失或違反值域 → `ValueError`，CLI 以 exit code 2 + 結構化 error log 結束**（FR-SC-021、Edge Cases §7）。

## 3. Runtime Entities（in-memory，無持久化）

### 3.1 `DroneTrack`（mutable，單 event loop 讀寫）

| 欄位 | 型別 | 生成時機 | 說明 |
| --- | --- | --- | --- |
| `uid` | string | `IDLE → DETECTED` 首次建立 | 與 scenario / Map Sim 相同 |
| `model` | string | 首次建立 | `uid → model` 表查得；未登記填 `"Unknown"` + error log（FR-SC-016） |
| `status` | `DetectionStatus` | 建立即 `DETECTED` | 受 `StateMachine` 推進 |
| `status_changed_at` | datetime (UTC) | 每次轉移時更新 | 用於 30 s NEUTRALIZED 倒數、10 s MITIGATING 消失寬限 |
| `lat` / `lon` / `alt_m` | float | 每次 Map Sim 查詢成功後更新 | Map Sim 下線時保留上一次值 |
| `velocity_ms` | float | 同上 | 來自 Map Sim `speed_ms` |
| `azimuth_deg` | float | 同上 | 來自 Map Sim `heading_deg` |
| `is_landed` | bool | `status == NEUTRALIZED` 時為 `True` | 輸出欄位，與 `status` 一致推導 |
| `timestamp` | datetime (UTC) | 每次狀態或位置更新 | 輸出至 `/detections.timestamp`（ISO 8601, `Z`）|
| `operator` | `OperatorEstimate` | 首次建立 | **不可變** |
| `takeover_sent` | bool | 首次 UDS 呼叫發出後 latch | `FR-SC-010` 守門；不論 200/409/400/404 皆 latch |
| `takeover_result` | `TakeoverResult \| None` | 收到 UDS 回應後 | 用於日誌 / 除錯 |
| `last_seen_at` | datetime (UTC) | 每次 Map Sim 查到此 `uid` 時更新 | MITIGATING 消失寬限計時基準 |

**Invariants**:

- `takeover_sent == True` → 同一 `uid` 不得再次呼叫 UDS `/command/takeover`（FR-SC-010）。
- `status == DETECTED` 時 `is_landed == False`。
- `status == NEUTRALIZED` 時 `is_landed == True`（spec.md Acceptance Scenario 1.2）。
- `status == MITIGATING` 時 `is_landed == False`（落地前的接管中）。

### 3.2 `OperatorEstimate`（**frozen** pydantic model）

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `operator_lat` | float | 以 WGS84 destination formula 一次性計算（research R3）|
| `operator_lon` | float | 同上 |
| `operator_distance_m` | float | echo from scenario |
| `operator_bearing_deg` | float | echo from scenario |

**Invariant**: 一旦實例化就**絕對不變**（`ConfigDict(frozen=True)`）；輸出到 `/detections` 時整個場景期間完全
等值（SC-SC-004 抖動 = 0）。

### 3.3 `TakeoverRequest` / `TakeoverResult`

```python
class TakeoverRequest(BaseModel):
    drone_id: str          # = DroneTrack.uid（UDS 與 Map Sim 共用識別碼）
    target_lat: float
    target_lon: float
    target_alt_m: float    # 預設 0.0（地面降落）
    sent_at: datetime

class TakeoverResult(str, Enum):
    ACCEPTED = "accepted"                        # HTTP 200
    ALREADY_TAKEN_OVER = "already_taken_over"    # HTTP 409（視同成功）
    REJECTED_BAD_REQUEST = "rejected_bad_request"  # HTTP 400
    REJECTED_NOT_FOUND = "rejected_not_found"      # HTTP 404
    FAILED_TRANSPORT = "failed_transport"          # timeout / 5xx / connection error
```

**Mapping 到狀態機**（與 research R6 同步）：

- `ACCEPTED` / `ALREADY_TAKEN_OVER` → `DETECTED → MITIGATING`
- `REJECTED_BAD_REQUEST` / `REJECTED_NOT_FOUND` → 保留 `DETECTED`，**latch `takeover_sent=True`**（不重送）
- `FAILED_TRANSPORT` → 保留 `DETECTED`，**不 latch**（下一 tick 允許重試一次）

## 4. Wire Entity: `DetectionResponse`（對外 `/detections` 陣列元素）

依 FR-SC-016，14 個必填欄位，全部以 `DroneTrack` 投影而得：

```python
class DetectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uid: str
    model: str                            # 可能 "Unknown"
    detection_status: Literal["DETECTED", "MITIGATING", "NEUTRALIZED"]
    lat: float
    lon: float
    alt_m: float
    velocity_ms: float
    azimuth_deg: float
    operator_lat: float
    operator_lon: float
    operator_distance_m: float
    operator_bearing_deg: float
    timestamp: str                        # ISO 8601 UTC, 必以 "Z" 結尾
    is_landed: bool
```

**不輸出 `IDLE` 狀態**（FR-SC-014）——registry 裡若某目標回到 IDLE 則自 registry 移除，自動不出現於 `/detections`。

## 5. Registry（in-memory，主 event loop 所有權）

```python
class DroneRegistry:
    """dict[str, DroneTrack]，由主 loop 擁有；/detections handler 以原子複製取快照。"""
    _tracks: dict[str, DroneTrack]

    def snapshot(self) -> list[DetectionResponse]:
        """投影為對外 wire schema；僅包含非 IDLE 目標。"""

    def get(self, uid: str) -> DetectionResponse | None:
        """/detection/{uid} 使用；IDLE 或不存在皆回 None → HTTP 404。"""
```

**並發模型**：所有讀寫皆在主 event loop 的 coroutine 中發生；無跨 thread，無需 `Lock`。`snapshot()` 以一次
`list(self._tracks.values())` + 逐筆投影達到原子性，滿足 FR-SC-018「多 Client 並發一致快照」。

## 6. 關聯圖（text）

```text
scenario.yaml  --pydantic-->  SentrycsConfig
                                    │
                                    ├─ sensor_lat/lon ──> MapSimClient.query_center
                                    ├─ drones[*].uid ──> uid→model 查表
                                    │                     (FR-SC-016)
                                    └─ drones[*] scheduling ──> per-drone async task
                                                                     │
                                                                     ▼
   Map Sim GET /objects ──filter is_lost ──> update DroneTrack.lat/lon/...
                                                    │
                                                    ▼
   StateMachine (time-based + Map Sim status + UDS response)
      │
      ├── DETECTED → MITIGATING: UDS POST /command/takeover (once)
      │                               │
      │                               └─> TakeoverResult → latch takeover_sent
      │
      └── all transitions → DroneTrack.status_changed_at = now

   HTTP API :17070
      GET /detections      → DroneRegistry.snapshot()
      GET /detection/{uid} → DroneRegistry.get(uid)
      GET /health          → {"status": "ok", ...}
```
