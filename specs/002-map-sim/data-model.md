# Phase 1 Data Model — Map Simulator

本文件定義 Map Sim 的內部資料模型與對外 response schema。對應 spec.md §3 Key Entities 與 contracts
/rest-api.md。

---

## 1. 總覽

```
POST /objects/update           GET /objects[?...include_lost=]
        │                               │
        ▼                               ▼
  UpdatePayload (pydantic)         QueryParams (handler-parsed)
        │                               │
        ▼                               ▼
  ObjectRegistry.update()         ObjectRegistry.query_radius()
        │                               │
        ▼                               ▼
  Dict[drone_id, DroneObject]     List[DroneObject (snapshot)]
        │                               │
        │                               ▼
        │                         serialize(center) → QueryResponseObject
        ▼
  background ttl_task → cleanup_expired()
```

核心原則：
1. **`status` 欄位永不被覆寫**。無論 TTL 狀態如何，response 中 `status` 一律等於 `DroneObject.status`
   （原始 UDS FlightState 字串）。
2. TTL 狀態以**獨立布林欄位 `is_lost`** 表達（Clarification Q1）。
3. `last_seen_at` 以 Map Sim 本地時鐘為準（`datetime.now(timezone.utc)`）；request body 的 `timestamp`
   不參與 TTL 計算。

---

## 2. DroneObject（in-memory）

```python
# src/map_sim/models/drone_object.py
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

@dataclass
class DroneObject:
    """Map Simulator 登錄表中單架無人機的即時狀態快照。

    8 個欄位由 UDS POST /objects/update 的 request body 直接寫入；
    last_seen_at 由 Map Sim 本地時鐘設定，是 TTL 判斷的唯一基準。
    """

    # ---- UDS 契約欄位（8 個；FR-MS-001）----
    drone_id: str          # 非空
    lat: float             # [-90, 90]；未做 server-side 值域檢查（信任 UDS 契約）
    lon: float             # [-180, 180]；同上
    alt_m: float           # 實數；未做 >= 0 檢查（信任 UDS）
    speed_ms: float        # 實數
    heading_deg: float     # [0, 360)；未做 server-side normalize
    status: str            # FlightState 字串；非空即接受（FR-MS-006 要求永不覆寫）
    timestamp: datetime    # 來自 request body；僅保存、不參與 TTL；ISO 8601 UTC 已解析

    # ---- Map Sim 自行維護 ----
    last_seen_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ---- 衍生行為 ----
    def age_s(self, now: Optional[datetime] = None) -> float:
        """距 last_seen_at 至今秒數（now 參數僅供 freezegun 測試注入；預設取 now()）。"""
        if now is None:
            now = datetime.now(timezone.utc)
        return (now - self.last_seen_at).total_seconds()

    def is_lost(self, ttl_warn_s: float, now: Optional[datetime] = None) -> bool:
        """TTL 狀態布林旗標。True ⇔ age_s >= ttl_warn_s。"""
        return self.age_s(now) >= ttl_warn_s
```

**不變量**：
- `drone_id` 為登錄表的唯一鍵；任何改動都是「整筆替換」（update 完全覆寫、無合併）。
- `timestamp` 原樣保存；即使 UDS 時鐘回撥，也不對 `last_seen_at` 造成影響。
- `last_seen_at` 單調前進：每次 `update()` 呼叫將其重設為當下；TTL 從此刻開始重新計時。

**為什麼不把 `is_active` 放在 DroneObject**：`ttl_warn_s` 是 registry 級別的配置、非 DroneObject 屬性；
把 threshold 傳入 method 比耦合為 instance state 更清晰（同時利於測試）。

---

## 3. ObjectRegistry

```python
# src/map_sim/registry/object_registry.py
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from ..models.drone_object import DroneObject
from ..geo.haversine import haversine_m


class ObjectRegistry:
    """Thread-safe（對 asyncio 意義上）物件登錄表。所有 public method 皆取 self._lock。"""

    def __init__(self, ttl_warn_s: float = 5.0, ttl_remove_s: float = 10.0):
        assert ttl_remove_s >= ttl_warn_s > 0, "ttl_remove_s must be >= ttl_warn_s > 0"
        self._objects: Dict[str, DroneObject] = {}
        self.ttl_warn_s = ttl_warn_s
        self.ttl_remove_s = ttl_remove_s
        self._lock = asyncio.Lock()

    # ---- Write ----
    async def update(
        self,
        drone_id: str,
        lat: float,
        lon: float,
        alt_m: float,
        speed_ms: float,
        heading_deg: float,
        status: str,
        timestamp: datetime,
    ) -> datetime:
        """新增或覆寫；回傳 registered_at（= last_seen_at，UTC）。"""
        async with self._lock:
            now = datetime.now(timezone.utc)
            self._objects[drone_id] = DroneObject(
                drone_id=drone_id,
                lat=lat, lon=lon, alt_m=alt_m,
                speed_ms=speed_ms, heading_deg=heading_deg,
                status=status, timestamp=timestamp,
                last_seen_at=now,
            )
            return now

    # ---- Read ----
    async def query_radius(
        self,
        center_lat: float,
        center_lon: float,
        radius_m: float,
        include_lost: bool = False,
    ) -> List[Tuple[DroneObject, float]]:
        """回傳 (obj, distance_m) pairs，已依 distance 升冪排序，不含已過 ttl_remove_s 的物件。

        預設（include_lost=False）過濾掉 is_lost=True 的物件；include_lost=True 則保留直到 remove 線。
        """
        async with self._lock:
            now = datetime.now(timezone.utc)
            result: List[Tuple[DroneObject, float]] = []
            for obj in self._objects.values():
                if obj.age_s(now) >= self.ttl_remove_s:
                    # 已逾 remove 線的物件在此刻視同不存在；背景 task 很快會 GC 它
                    continue
                if (not include_lost) and obj.is_lost(self.ttl_warn_s, now):
                    continue
                dist = haversine_m(center_lat, center_lon, obj.lat, obj.lon)
                if dist <= radius_m:
                    result.append((obj, dist))
            result.sort(key=lambda pair: pair[1])
            return result

    async def get_all(self) -> List[DroneObject]:
        """除錯端點用；回傳尚未被 cleanup 的所有物件。"""
        async with self._lock:
            return list(self._objects.values())

    # ---- Admin ----
    async def remove(self, drone_id: str) -> bool:
        async with self._lock:
            return self._objects.pop(drone_id, None) is not None

    async def cleanup_expired(self) -> int:
        """移除所有 age_s > ttl_remove_s 的物件，回傳移除數量。由背景 task 定期呼叫。"""
        async with self._lock:
            now = datetime.now(timezone.utc)
            expired = [k for k, v in self._objects.items() if v.age_s(now) > self.ttl_remove_s]
            for k in expired:
                del self._objects[k]
            return len(expired)

    # ---- Introspection（health）----
    async def count(self) -> int:
        async with self._lock:
            return len(self._objects)
```

**鎖語意**（對應 research.md §3）：
- 所有 public method 一進入即 `async with self._lock`；鎖內**禁止** `await` 外部 I/O。
- `query_radius` 回傳的是 `(DroneObject, float)` 的新 list；由於 `DroneObject` 是不可變等價
  （dataclass，不頻繁 mutate），caller 可在鎖外安全 serialize。若日後加上 mutable 欄位，需改回傳
  deep-copy。

**`query_radius` 同時過濾 `>= ttl_remove_s` 的理由**：背景 cleanup 以 2 s 為週期，某物件可能已過
`ttl_remove_s` 但尚未被 GC；此時必須避免它在 `GET /objects?include_lost=true` 出現（spec
FR-MS-006：「`age_s > ttl_remove_s` 之後無論 `include_lost` 為何皆不可見」）。

---

## 4. Request/Response Schema

### 4.1 UpdatePayload（`POST /objects/update` request）

```python
# src/map_sim/models/request.py
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class UpdatePayload(BaseModel):
    """寬鬆 request schema：8 個必填欄位 + 未知欄位靜默忽略（FR-MS-002）。"""

    model_config = ConfigDict(extra="ignore")

    drone_id: str = Field(min_length=1)
    lat: float
    lon: float
    alt_m: float
    speed_ms: float
    heading_deg: float
    status: str = Field(min_length=1)
    timestamp: datetime     # pydantic 自動 parse ISO 8601；"Z" 後綴在 py3.11 可直接 fromisoformat
```

**注意**：`lat` / `lon` / `alt_m` **不做** server-side 值域校驗（信任 UDS 契約）。若 UDS bug 送了
`lat = 91`，Map Sim 仍接受；這與 spec §5 Assumptions「status 值域信任 UDS」一致。

### 4.2 UpdateResponse（`POST /objects/update` 200 OK）

```json
{
  "status": "updated",
  "drone_id": "TRK-001",
  "registered_at": "2026-04-22T08:00:01.015Z"
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `status` | string | 固定 `"updated"` |
| `drone_id` | string | echo request |
| `registered_at` | string | ISO 8601 UTC；= `DroneObject.last_seen_at` |

### 4.3 QueryResponse（`GET /objects` 200 OK）

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
      "status": "LANDED",
      "timestamp": "2026-04-22T07:59:58.000Z",
      "distance_m": 2831.5,
      "last_seen_s": 6.3,
      "is_lost": true
    }
  ]
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `query.lat` / `query.lon` / `query.radius_m` | number | echo request 的 query params |
| `query.include_lost` | bool | echo（未帶時回 `false`）|
| `query.timestamp` | string | ISO 8601 UTC；Map Sim 產生回應的時間 |
| `count` | integer | `objects` 陣列長度（過濾後） |
| `objects[].drone_id` | string | |
| `objects[].lat` / `lon` / `alt_m` / `speed_ms` / `heading_deg` | number | DroneObject 原值 |
| `objects[].status` | string | **DroneObject.status 原值；永不被覆寫為 `"lost"`** |
| `objects[].timestamp` | string | request body 中的 timestamp 原值（ISO 8601 UTC）|
| `objects[].distance_m` | number | Haversine 距離（公尺），`round(_, 1)` |
| `objects[].last_seen_s` | number | `age_s`，`round(_, 1)` |
| `objects[].is_lost` | bool | `age_s >= ttl_warn_s`；在 `include_lost=false` 時此欄永為 `false` |

**Clarification Q1 落點**：上例第二筆 `TRK-001` 進入 lost 區間（`last_seen_s = 6.3 > ttl_warn_s = 5.0`），
`status` 仍為原始 `"LANDED"`，`is_lost: true`。這是 `include_lost=true` 的典型輸出。

**排序**：`objects[]` **MUST** 依 `distance_m` 升冪排序；相同距離的排序不保證穩定（PoC 不要求）。

### 4.4 ObjectsAllResponse（`GET /objects/all` 200 OK；除錯用）

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

| 欄位 | 型別 | 說明 |
|------|------|------|
| `total` | integer | registry 內所有物件數（含 `is_lost=true` 但尚未 remove）|
| `active` | integer | `is_lost=false` 的物件數 |
| `lost` | integer | `is_lost=true` 的物件數；`active + lost == total` |
| `objects[]` | array | 所有物件序列化；**無 `distance_m` 欄位**（無查詢中心）；其餘同 §4.3 |

### 4.5 HealthResponse（`GET /health` 200 OK）

```json
{
  "status": "ok",
  "registered_objects": 3,
  "uptime_s": 125.4
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `status` | string | 固定 `"ok"` |
| `registered_objects` | integer | registry 內當前物件數（等同 `GET /objects/all` 的 `total`，含 lost 但不含已 remove）|
| `uptime_s` | number | 自 server 啟動至今秒數，`round(_, 1)` |

### 4.6 ErrorResponse（所有端點共用的 4xx body schema）

```json
{"status": "error", "reason": "<stable-reason-string>"}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `status` | string | 固定 `"error"` |
| `reason` | string | 穩定字串常數；契約測試可依此字串做精確斷言（見 contracts/rest-api.md §5）|

---

## 5. Serialization Helpers

```python
# src/map_sim/models/drone_object.py（補充）
def serialize(
    obj: DroneObject,
    ttl_warn_s: float,
    now: datetime,
    *,
    center_lat: Optional[float] = None,
    center_lon: Optional[float] = None,
) -> dict:
    d = {
        "drone_id": obj.drone_id,
        "lat": obj.lat,
        "lon": obj.lon,
        "alt_m": obj.alt_m,
        "speed_ms": obj.speed_ms,
        "heading_deg": obj.heading_deg,
        "status": obj.status,                               # 永不覆寫
        "timestamp": obj.timestamp.isoformat().replace("+00:00", "Z"),
        "last_seen_s": round(obj.age_s(now), 1),
        "is_lost": obj.is_lost(ttl_warn_s, now),
    }
    if center_lat is not None and center_lon is not None:
        d["distance_m"] = round(haversine_m(center_lat, center_lon, obj.lat, obj.lon), 1)
    return d
```

- `serialize` **不**在鎖內呼叫；caller 拿到 `(obj, dist)` snapshot 後於鎖外序列化（見 registry §3
  鎖策略）。
- `now` 由 handler 傳入（通常為 `datetime.now(timezone.utc)`）；注入式設計方便 `freezegun` 測試。

---

## 6. State / TTL Transition

單一物件的生命週期（以 `update()` 收到第一筆為起點）：

```
t=0             update() → registry[id] = obj(last_seen_at=0)
                is_lost=false；active
 ↓ (update) 每次 update 重設 last_seen_at，重新開始計時
 ↓
t=ttl_warn_s    is_lost=true （query 預設不回；include_lost=true 可見）
                status 仍為原始 FlightState 字串
 ↓
t=ttl_remove_s  仍在 registry 中；但 query_radius 已排除（即使 include_lost=true）
 ↓
t=ttl_remove_s + period_s (≤ 2s)  cleanup_expired() 移除；registry 不再有此 id
                之後 GET /objects/all 也看不到
```

在 `[ttl_remove_s, ttl_remove_s + 2 s]` 區間，`GET /objects/all` 的 `total` 可能仍含此物件（`is_lost=true`，
`lost +=1`）——這是實作細節而非 bug；SC-MS-004 允許 2 s 誤差即已接受此行為。

---

## 7. 與 Clarification Q1 的逐點對照

| Clarification Q1 語意 | 本文件落點 |
|---------------------|----------|
| `status` 保留原始 FlightState 值、不被覆寫 | §2 `DroneObject.status` 定義；§4.3/§4.4 回應範例；§5 `serialize()` |
| 以獨立布林欄位 `is_lost` 表達 TTL 狀態 | §2 `is_lost()` method；§4.3/§4.4 schema；§5 serialize |
| `last_seen_s >= ttl_warn_s` 時 `is_lost=true` | §2 `is_lost()` 以 `>=` 比較；§3 `query_radius` 同閾值過濾 |
| 否則為 `false` 或省略；擇一實作並於 contracts 固定 | **本實作固定為 `is_lost: false`（明確輸出）**，見 §4.3；contracts/rest-api.md §3.2 亦明文化 |
