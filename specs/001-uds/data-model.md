# Phase 1 — Data Model: UDS

本檔案定義 UDS 內部的主要資料結構、列舉與 YAML schema。欄位命名、值域與 `spec.md` §3 及
`docs/system-docs/08-api-icd.md` 保持一致；以 Python `dataclass` / `Enum` / `pydantic` 作為
參考實作形式。

> 重要：本檔案中的欄位值域（lat / lon / alt / action 白名單 / HTTP 錯誤映射）是後續契約測試
> 與 scenario loader 的唯一真值（single source of truth）。

---

## 1. `FlightState`（Enum）

以 **字串值** 的 Enum（而非 `auto()`），方便直接序列化至 `POST /objects/update` 的 `status` 欄位
與 debug 端點的 `flight_state` 欄位。

```python
from enum import Enum

class FlightState(str, Enum):
    IDLE = "IDLE"
    FLYING_NORMAL = "FLYING_NORMAL"
    MITIGATING_TAKEOVER = "MITIGATING_TAKEOVER"
    LANDING = "LANDING"
    LANDED = "LANDED"
```

### 1.1 允許的狀態轉移

| From | Event / 條件 | To | 副作用 |
|------|-------------|----|-------|
| `IDLE` | 場景 `timeline.start_flying` 觸發 | `FLYING_NORMAL` | 加入 push 清單 |
| `FLYING_NORMAL` | 合法 `POST /command/takeover` | `MITIGATING_TAKEOVER` | 重算 bearing 至 `takeover_cmd.target_*`；開始降高 |
| `MITIGATING_TAKEOVER` | Haversine 距目標 ≤ 100 m | `LANDING` | 速度遞減（斜坡至 `descent_speed_ms`）|
| `LANDING` | `alt_m ≤ 2.0` **且** `velocity_ms ≤ 0.5` | `LANDED` | 同週期推送最後一筆（`flight_state="LANDED"`），之後停推 |
| `LANDED` | 場景重置（PoC 未必實作） | `IDLE` | 從 push 清單移除 |

**其他任何轉移**（含 `LANDED → *`）皆為不合法；主迴圈必須忽略並 log `state.transition.invalid`。

### 1.2 IDLE 的特別規則

- `IDLE` 狀態的無人機 **不** 出現在 `POST /objects/update` 任何呼叫中。
- 對 `IDLE` 無人機下 `POST /command/takeover` → **HTTP 409 `drone not airborne`**。

### 1.3 LANDED 收尾規則（FR-UDS-006 / Clarification Q2）

- 狀態由 `LANDING` 切換到 `LANDED` 的 **同一個** 主迴圈週期內，必須對該 `drone_id` 推送恰一筆
  `POST /objects/update`（`flight_state = "LANDED"`）作為收尾旗標。
- 自下一個主迴圈週期起，該 `drone_id` 從推送排程中剔除，直到（未來可選的）`LANDED → IDLE` 重置。

---

## 2. `DroneState`（dataclass）

單一無人機的完整執行期狀態。由 `ScenarioLoader` 從 YAML 初始化，由主迴圈每週期就地更新（mutate）。

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass(slots=True)
class DroneState:
    # 識別
    drone_id: str                  # 如 "TRK-001"，對應 ICD 的 track_id
    model: str                     # 如 "DJI Mavic 3"；需屬 ICD-002 §3.2 enum

    # 位置（WGS84）
    lat: float                     # [-90, 90]
    lon: float                     # [-180, 180]
    alt_m: float                   # ≥ 0，HAE 公尺

    # 運動學
    velocity_ms: float             # ≥ 0，m/s
    heading_deg: float             # [0, 360)，正北順時針
    waypoint_index: int = 0        # 目前目標 waypoint 指標

    # 狀態機
    flight_state: FlightState = FlightState.IDLE
    takeover_cmd: Optional["TakeoverCommand"] = None

    # 操控者位置（供下游 Sentrycs 使用，非 UDS 計算）
    operator_lat: float = 0.0
    operator_lon: float = 0.0

    # 感測輔助欄位（固定值，由 YAML / 預設給定，UDS 不更新）
    snr_db: float = 22.0
    rcs_dbsm: float = -11.5

    # 內部：LANDED 收尾標記
    landed_finalized: bool = False  # True 表示收尾訊息已送出，之後停推

    # 最後一次 tick 的時間（wall-clock），用於 dt 計算
    last_tick_ts: Optional[datetime] = None
```

**欄位約束**：
- `lat ∈ [-90, 90]`、`lon ∈ [-180, 180]`、`alt_m ≥ 0`、`velocity_ms ≥ 0`、`heading_deg ∈ [0, 360)`。
- 初始化時 `flight_state = IDLE`，`timeline.start_flying` 到達前不進入 push 清單。
- `waypoint_index` 超過 `waypoints` 長度 → 切入 `landing_point`（若已有 `takeover_cmd` 以其目標優先）。

**推導規則（每 tick）**：

| 情況 | 行為 |
|------|------|
| `IDLE` | 不動；跳過積分 |
| `FLYING_NORMAL` | 往下一 waypoint 直線飛；到達則 `waypoint_index += 1` |
| `MITIGATING_TAKEOVER` | 目標改為 `takeover_cmd.target_*`；高度以線性或梯度遞減（降至 `target_alt_m`） |
| `LANDING` | 速度梯度遞減至 `descent_speed_ms`；高度持續下降 |
| `LANDED` | 位置凍結；`velocity_ms = 0` |

**平滑轉向**：新 heading 與舊 heading 的差 normalize 至 `[-180, 180]` 後 clamp 至 `±30°/週期`。

---

## 3. `TakeoverCommand`（dataclass + pydantic request model）

### 3.1 執行期物件（存於 `DroneState.takeover_cmd`）

```python
@dataclass(slots=True)
class TakeoverCommand:
    drone_id: str
    target_lat: float     # 必填，∈ [-90, 90]
    target_lon: float     # 必填，∈ [-180, 180]
    target_alt_m: float   # 必填，無預設值，≥ 0（公尺，HAE）
    descent_speed_ms: float = 3.0  # 選填，> 0
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
```

**覆寫語意（Clarification Q5 / FR-UDS-004）**：對同一 `drone_id` 在尚未 `LANDED` 前重複接管，以最新一筆
`TakeoverCommand` **完全覆寫** 舊值（`target_lat/target_lon/target_alt_m/descent_speed_ms` 一併取代）；
**不** 保留歷史、**不** 新增旗標或覆寫計數欄位。

### 3.2 HTTP Request schema（pydantic v2）

```python
from pydantic import BaseModel, Field, field_validator

class TakeoverRequest(BaseModel):
    drone_id: str = Field(..., min_length=1)
    target_lat: float = Field(..., ge=-90, le=90)
    target_lon: float = Field(..., ge=-180, le=180)
    target_alt_m: float = Field(..., ge=0)      # 必填、無預設
    descent_speed_ms: float | None = Field(default=None, gt=0)
    model_config = {"extra": "forbid"}
```

### 3.3 驗證→HTTP 錯誤映射

| 驗證結果 | HTTP | body `reason` |
|---------|------|---------------|
| 缺 `drone_id` / `target_lat` / `target_lon` / `target_alt_m` | 400 | `missing field: <name>` |
| `target_lat ∉ [-90, 90]` 或 `target_lon ∉ [-180, 180]` | 400 | `invalid coordinates` |
| `target_alt_m < 0`（或缺失） | 400 | `invalid altitude` |
| `descent_speed_ms ≤ 0` | 400 | `invalid descent speed` |
| `drone_id` 不存在於場景 | 400 | `drone_id not found` |
| 目標 `flight_state = IDLE` | **409** | `drone not airborne` |
| 目標 `flight_state = LANDED` | 400 | `already landed` |
| 已處於 `MITIGATING_TAKEOVER` / `LANDING`（尚未 LANDED） | **200** | `accepted`（覆寫） |
| 正常 `FLYING_NORMAL` | 200 | `accepted` |

所有錯誤回應 **不得** 變更目標無人機的 `flight_state`，也 **不得** 產生 `POST /objects/update` 副作用
（FR-UDS-015）。

---

## 4. Scenario YAML Schema

頂層鍵固定為 `scenario`。`ScenarioLoader` 使用下列 pydantic 模型解析；任一欄位型別錯 / 缺失 /
值域外 / `timeline.action` 非白名單 → 印出人類可讀錯誤訊息並以 exit code **2** 結束（fail-fast）。

```python
from pydantic import BaseModel, Field
from typing import Literal

class LatLon(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)

class Waypoint(LatLon):
    alt_m: float = Field(..., ge=0)

class LandingPoint(Waypoint):
    descent_speed_ms: float = Field(3.0, gt=0)

class DroneSpec(BaseModel):
    drone_id: str = Field(..., min_length=1)
    model: Literal["DJI Mavic 3", "DJI Matrice 30T", "Autel EVO II"]
    start_lat: float = Field(..., ge=-90, le=90)
    start_lon: float = Field(..., ge=-180, le=180)
    start_alt_m: float = Field(..., ge=0)
    speed_ms: float = Field(..., ge=0, le=150)
    heading_deg: float = Field(..., ge=0, lt=360)
    operator_bearing_deg: float = Field(..., ge=0, lt=360)
    operator_distance_m: float = Field(..., ge=0)
    waypoints: list[Waypoint] = Field(default_factory=list)
    landing_point: LandingPoint
    snr_db: float = 22.0
    rcs_dbsm: float = -11.5

class TimelineEvent(BaseModel):
    at_s: float = Field(..., ge=0)
    action: Literal["start_flying"]   # 封閉白名單（Clarification Q4）
    drone_id: str = Field(..., min_length=1)

class Servers(BaseModel):
    command_api_port: int = Field(8080, ge=1, le=65535)
    # echoshield_tcp_port 保留相容性接受但忽略（已移出 UDS 職責）
    echoshield_tcp_port: int | None = None

class Scenario(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    update_hz: int = Field(10, ge=1, le=20)
    servers: Servers = Servers()
    drones: list[DroneSpec] = Field(..., min_length=1, max_length=10)
    timeline: list[TimelineEvent] = Field(default_factory=list)

class ScenarioFile(BaseModel):
    scenario: Scenario
```

### 4.1 跨欄位檢查

- `timeline[].drone_id` 必須存在於 `drones[].drone_id`，否則 fail-fast 訊息：
  `timeline references unknown drone_id: <value>`。
- `drones[].drone_id` 必須唯一；重複 → `duplicate drone_id: <value>`。

### 4.2 fail-fast 錯誤訊息範例

| 情境 | Stderr 訊息 | Exit |
|------|-------------|------|
| `timeline[0].action: "takeoff"` | `unknown action: takeoff` | 2 |
| `timeline[2].action: ""` | `unknown action: ''` | 2 |
| `drones[0].start_lat: 999` | `invalid coordinates: drones[0].start_lat=999 not in [-90, 90]` | 2 |
| 缺 `scenario.drones` | `missing field: scenario.drones` | 2 |
| `drones` 長度 > 10 | `too many drones: 12 (max 10)` | 2 |

---

## 5. 推送 payload（UDS → Map Simulator）

每週期對每架 `flight_state ≠ IDLE` 且未 `landed_finalized=True` 的無人機產生：

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

欄位完全對齊 `docs/system-docs/03-map-simulator-spec.md` §3.1。其中：
- `speed_ms` ← `DroneState.velocity_ms`（注意欄位名對應：UDS 內部 `velocity_ms` → 推送 payload `speed_ms`）。
- `status` ← `DroneState.flight_state.value`（字串）。
- `timestamp` ← tick 的 wall-clock，UTC ISO 8601，毫秒精度。

進入 `LANDED` 的那個 tick 推送一筆 `status = "LANDED"` 後立刻設 `landed_finalized = True`，下個 tick 起跳過。

---

## 6. 狀態總表（速查）

| 結構 | 用途 | 生命週期 |
|------|------|---------|
| `FlightState` | 狀態機 enum | 全程常駐 |
| `DroneState` | 每架 1 份執行期物件 | 由 YAML 初始化；主迴圈 mutate |
| `TakeoverCommand` | 附掛於 `DroneState`；最新一筆覆寫舊筆 | 收到 takeover 時建立；`LANDED` 後可清 |
| `Scenario*` pydantic 模型 | 啟動期 YAML 驗證 + 轉 dataclass | 啟動時建立一次 |
| 推送 payload | 對 Map Simulator 的 JSON body | 每 tick 每架產生一筆 |
