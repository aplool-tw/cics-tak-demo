# Map Simulator（地圖模擬器）規格

---

| 欄位 | 內容 |
|------|------|
| **文件編號** | 02b |
| **版本** | v0.1 |
| **日期** | 2026-04-22 |
| **作者** | 系統架構小組 |
| **狀態** | 草稿 |

---

## 1. 目的與範圍

### 1.1 角色說明

Map Simulator 是感測層的**物件狀態中央登錄表（Central Object Registry）**。它作為 Unified Drone Simulator（UDS）與感測器模擬器（EchoShield Simulator、Sentrycs Simulator）之間的中介層，維護所有無人機的即時位置與狀態，並提供基於地理範圍的查詢 API。

### 1.2 架構定位

```
Unified Drone Simulator
        │
        │ POST /objects/update（每秒 push）
        ↓
  Map Simulator（Port :8090）
  物件狀態登錄表
   ┌────────────────────────────────────────┐
   │ drone_id / lat / lon / alt_m          │
   │ speed_ms / heading_deg / status       │
   │ last_seen_at（TTL 判斷）               │
   └────────────────────────────────────────┘
        ↑                          ↑
        │ GET /objects?            │ GET /objects?
        │ lat=&lon=&radius_m=4800  │ lat=&lon=&radius_m=8000
EchoShield Simulator        Sentrycs Simulator
（雷達偵測範圍查詢）          （RF 偵測範圍查詢）
```

### 1.3 設計理由

| 問題 | Map Simulator 解決方案 |
|------|----------------------|
| EchoShield Simulator 與 Sentrycs Simulator 各自維護位置狀態，造成狀態不一致 | 統一由 Map Simulator 維護，單一事實來源（Single Source of Truth）|
| 多感測器查詢位置邏輯重複 | Map Simulator 提供通用地理範圍查詢 API |
| 感測器需要自行實作 TTL 清理 | Map Simulator 統一管理 TTL，感測器無需關心過期邏輯 |
| 未來擴充新感測器型別 | 新感測器只需呼叫 `GET /objects?` 即可取得範圍內物件 |

---

## 2. 功能需求

| ID | 需求描述 | 優先級 |
|----|---------|-------|
| FR-MS-001 | 接收 Unified Drone Simulator 的 POST /objects/update，更新物件登錄表 | 必要 |
| FR-MS-002 | 提供 `GET /objects?lat=&lon=&radius_m=` 地理範圍查詢，回傳範圍內所有活躍物件（含距離排序）| 必要 |
| FR-MS-003 | 支援同時維護最少 20 架無人機的狀態（PoC 場景最多 5 架）| 必要 |
| FR-MS-004 | TTL 機制：物件超過 5 秒未更新則標記為 `status: lost`；超過 10 秒則從登錄表移除 | 必要 |
| FR-MS-005 | 提供 `GET /objects/all` 取得所有物件（含 lost 狀態，用於除錯）| 重要 |
| FR-MS-006 | 提供 `DELETE /objects/{drone_id}` 手動移除特定物件（測試用）| 選填 |
| FR-MS-007 | `GET /objects?` 回傳物件需包含 `distance_m`（從查詢中心到物件的距離）| 必要 |
| FR-MS-008 | 提供健康確認端點 `GET /health` | 重要 |
| FR-MS-009 | 提供 CLI 介面，支援 --port, --ttl-warn-s, --ttl-remove-s, --verbose 參數 | 必要 |
| FR-MS-010 | 以本機 asyncio aiohttp Server 執行，Port 預設 8090 | 必要 |

---

## 3. REST API 規格

### 3.1 POST /objects/update

**用途**：Unified Drone Simulator 每秒推送無人機狀態更新。

**Request**：
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

**欄位說明**：

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `drone_id` | string | ✅ | UDS 的無人機識別碼 |
| `lat` | float | ✅ | WGS84 緯度 |
| `lon` | float | ✅ | WGS84 經度 |
| `alt_m` | float | ✅ | 高度（公尺，HAE）|
| `speed_ms` | float | ✅ | 速度（m/s）|
| `heading_deg` | float | ✅ | 飛行方向（度，正北為 0）|
| `status` | string | ✅ | UDS FlightState（FLYING_NORMAL / MITIGATING_TAKEOVER / LANDING / LANDED）|
| `timestamp` | string | ✅ | ISO 8601 UTC |

**Response 200 OK**：
```json
{"status": "updated", "drone_id": "TRK-001", "registered_at": "2026-04-22T08:00:01.015Z"}
```

**Response 400 Bad Request**：
```json
{"status": "error", "reason": "missing required field: drone_id"}
```

### 3.2 GET /objects

**用途**：以地理圓形範圍查詢活躍物件（EchoShield / Sentrycs 呼叫）。

**Query Parameters**：

| 參數 | 型別 | 必填 | 說明 | 範例 |
|------|------|------|------|------|
| `lat` | float | ✅ | 查詢圓心緯度（感測器位置）| `25.0330` |
| `lon` | float | ✅ | 查詢圓心經度 | `121.5654` |
| `radius_m` | float | ✅ | 查詢半徑（公尺）| `4800`（雷達）/ `8000`（RF）|
| `include_lost` | bool | ❌ | 是否包含 `lost` 狀態物件（預設 false）| `false` |

**Response 200 OK**：
```json
{
  "query": {
    "lat": 25.0330,
    "lon": 121.5654,
    "radius_m": 4800.0,
    "timestamp": "2026-04-22T08:00:01.500Z"
  },
  "count": 2,
  "objects": [
    {
      "drone_id": "TRK-001",
      "lat": 25.0584745,
      "lon": 121.5654089,
      "alt_m": 100.8,
      "speed_ms": 15.1,
      "heading_deg": 180.2,
      "status": "FLYING_NORMAL",
      "distance_m": 2831.5,
      "last_seen_s": 0.3
    },
    {
      "drone_id": "TRK-002",
      "lat": 25.0410,
      "lon": 121.5800,
      "alt_m": 150.0,
      "speed_ms": 18.0,
      "heading_deg": 270.0,
      "status": "FLYING_NORMAL",
      "distance_m": 1563.2,
      "last_seen_s": 0.1
    }
  ]
}
```

> **`distance_m`**：Map Simulator 計算查詢中心到每個物件的 Haversine 距離（公尺），已按距離由近到遠排序。
> **`last_seen_s`**：物件最後一次更新距現在的秒數。

**Response 400 Bad Request**：
```json
{"status": "error", "reason": "missing required parameter: radius_m"}
```

### 3.3 GET /objects/all

**用途**：取得登錄表內所有物件（含 lost 狀態），用於除錯。

**Response 200 OK**：
```json
{
  "total": 3,
  "active": 2,
  "lost": 1,
  "objects": [
    {"drone_id": "TRK-001", "status": "FLYING_NORMAL", "last_seen_s": 0.5, "lat": 25.0584, "lon": 121.5654},
    {"drone_id": "TRK-002", "status": "LANDING", "last_seen_s": 1.2},
    {"drone_id": "TRK-003", "status": "lost", "last_seen_s": 7.8}
  ]
}
```

### 3.4 GET /health

```json
{"status": "ok", "registered_objects": 3, "uptime_s": 125.4}
```

---

## 4. 資料模型

### 4.1 DroneObject Dataclass

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

@dataclass
class DroneObject:
    """Map Simulator 登錄表中的單架無人機狀態"""

    drone_id: str
    lat: float
    lon: float
    alt_m: float
    speed_ms: float
    heading_deg: float
    status: str                      # UDS FlightState 字串
    timestamp: datetime              # 感測時間（來自 UDS）
    last_seen_at: datetime = field(  # Map Simulator 收到更新的時間
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def age_s(self) -> float:
        """距最後更新的秒數"""
        return (datetime.now(timezone.utc) - self.last_seen_at).total_seconds()

    def is_active(self, ttl_warn_s: float = 5.0) -> bool:
        """是否在 TTL 內視為活躍"""
        return self.age_s() < ttl_warn_s

    def to_dict(self, center_lat: Optional[float] = None, center_lon: Optional[float] = None) -> dict:
        """序列化為 API 回傳 dict，可選附帶距離計算"""
        d = {
            "drone_id": self.drone_id,
            "lat": self.lat,
            "lon": self.lon,
            "alt_m": self.alt_m,
            "speed_ms": self.speed_ms,
            "heading_deg": self.heading_deg,
            "status": self.status if self.is_active() else "lost",
            "last_seen_s": round(self.age_s(), 1),
        }
        if center_lat is not None and center_lon is not None:
            d["distance_m"] = round(haversine_distance(center_lat, center_lon, self.lat, self.lon), 1)
        return d
```

### 4.2 ObjectRegistry

```python
import asyncio
from typing import Dict, List, Optional

class ObjectRegistry:
    """管理所有 DroneObject 的字典，含 TTL 自動清理"""

    def __init__(self, ttl_warn_s: float = 5.0, ttl_remove_s: float = 10.0):
        self._objects: Dict[str, DroneObject] = {}
        self.ttl_warn_s = ttl_warn_s
        self.ttl_remove_s = ttl_remove_s
        self._lock = asyncio.Lock()

    async def update(self, drone_id: str, lat: float, lon: float, alt_m: float,
                     speed_ms: float, heading_deg: float, status: str, timestamp: datetime) -> None:
        """新增或更新物件"""
        async with self._lock:
            self._objects[drone_id] = DroneObject(
                drone_id=drone_id, lat=lat, lon=lon, alt_m=alt_m,
                speed_ms=speed_ms, heading_deg=heading_deg, status=status,
                timestamp=timestamp
            )

    async def query_radius(
        self, center_lat: float, center_lon: float, radius_m: float,
        include_lost: bool = False
    ) -> List[DroneObject]:
        """查詢指定圓形範圍內的活躍物件，按距離排序"""
        async with self._lock:
            result = []
            for obj in self._objects.values():
                dist = haversine_distance(center_lat, center_lon, obj.lat, obj.lon)
                if dist <= radius_m:
                    if include_lost or obj.is_active(self.ttl_warn_s):
                        result.append(obj)
            result.sort(
                key=lambda o: haversine_distance(center_lat, center_lon, o.lat, o.lon)
            )
            return result

    async def get_all(self) -> List[DroneObject]:
        """取得所有物件（除錯用）"""
        async with self._lock:
            return list(self._objects.values())

    async def remove(self, drone_id: str) -> bool:
        async with self._lock:
            if drone_id in self._objects:
                del self._objects[drone_id]
                return True
            return False

    async def cleanup_expired(self) -> int:
        """移除超過 ttl_remove_s 未更新的物件，回傳移除數量"""
        async with self._lock:
            expired = [k for k, v in self._objects.items() if v.age_s() > self.ttl_remove_s]
            for k in expired:
                del self._objects[k]
            return len(expired)
```

### 4.3 MapSimulator（主程式）

```python
import json
import math
import asyncio
from datetime import datetime, timezone
from aiohttp import web

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """計算兩 WGS84 點間距離（公尺）"""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class MapSimulator:
    """Map Simulator HTTP Server"""

    def __init__(self, port: int = 8090, ttl_warn_s: float = 5.0, ttl_remove_s: float = 10.0):
        self.port = port
        self.registry = ObjectRegistry(ttl_warn_s=ttl_warn_s, ttl_remove_s=ttl_remove_s)
        self._start_time = datetime.now(timezone.utc)

    async def start(self) -> None:
        app = web.Application()
        app.router.add_post("/objects/update", self._handle_update)
        app.router.add_get("/objects", self._handle_query)
        app.router.add_get("/objects/all", self._handle_all)
        app.router.add_delete("/objects/{drone_id}", self._handle_delete)
        app.router.add_get("/health", self._handle_health)

        # 啟動 TTL 清理背景任務
        asyncio.create_task(self._cleanup_loop())

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "localhost", self.port)
        await site.start()
        print(f"Map Simulator started on port {self.port}")
        await asyncio.Event().wait()

    async def _handle_update(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            required = ["drone_id", "lat", "lon", "alt_m", "speed_ms", "heading_deg", "status", "timestamp"]
            for f in required:
                if f not in data:
                    return web.json_response({"status": "error", "reason": f"missing required field: {f}"}, status=400)
            ts = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
            await self.registry.update(
                drone_id=data["drone_id"],
                lat=float(data["lat"]),
                lon=float(data["lon"]),
                alt_m=float(data["alt_m"]),
                speed_ms=float(data["speed_ms"]),
                heading_deg=float(data["heading_deg"]),
                status=data["status"],
                timestamp=ts,
            )
            return web.json_response({
                "status": "updated",
                "drone_id": data["drone_id"],
                "registered_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            return web.json_response({"status": "error", "reason": str(e)}, status=400)

    async def _handle_query(self, request: web.Request) -> web.Response:
        try:
            lat = float(request.query["lat"])
            lon = float(request.query["lon"])
            radius_m = float(request.query["radius_m"])
            include_lost = request.query.get("include_lost", "false").lower() == "true"
        except (KeyError, ValueError) as e:
            return web.json_response({"status": "error", "reason": f"invalid query parameter: {e}"}, status=400)

        objects = await self.registry.query_radius(lat, lon, radius_m, include_lost)
        return web.json_response({
            "query": {"lat": lat, "lon": lon, "radius_m": radius_m,
                      "timestamp": datetime.now(timezone.utc).isoformat()},
            "count": len(objects),
            "objects": [o.to_dict(center_lat=lat, center_lon=lon) for o in objects],
        })

    async def _handle_all(self, request: web.Request) -> web.Response:
        objects = await self.registry.get_all()
        active = sum(1 for o in objects if o.is_active(self.registry.ttl_warn_s))
        return web.json_response({
            "total": len(objects),
            "active": active,
            "lost": len(objects) - active,
            "objects": [o.to_dict() for o in objects],
        })

    async def _handle_delete(self, request: web.Request) -> web.Response:
        drone_id = request.match_info["drone_id"]
        removed = await self.registry.remove(drone_id)
        return web.json_response({"status": "removed" if removed else "not_found", "drone_id": drone_id})

    async def _handle_health(self, request: web.Request) -> web.Response:
        objects = await self.registry.get_all()
        uptime = (datetime.now(timezone.utc) - self._start_time).total_seconds()
        return web.json_response({"status": "ok", "registered_objects": len(objects), "uptime_s": round(uptime, 1)})

    async def _cleanup_loop(self) -> None:
        """每 2 秒清理一次過期物件"""
        while True:
            removed = await self.registry.cleanup_expired()
            if removed > 0:
                print(f"[MapSimulator] TTL cleanup: removed {removed} expired objects")
            await asyncio.sleep(2.0)
```

---

## 5. CLI 介面

```bash
python map_simulator.py \
  --port 8090 \
  --ttl-warn-s 5.0 \
  --ttl-remove-s 10.0 \
  --verbose

# 參數說明：
# --port         HTTP Server Port（預設 8090）
# --ttl-warn-s   物件標記為 lost 的超時秒數（預設 5.0）
# --ttl-remove-s 物件從登錄表移除的超時秒數（預設 10.0）
# --verbose      詳細日誌輸出
```

---

## 6. 與 Unified Drone Simulator 的整合

### 6.1 UDS 推送流程

Unified Drone Simulator 在每次 `update_all(dt)` 之後，對登錄表內所有活躍無人機推送狀態至 Map Simulator：

```python
async def _push_to_map_simulator(self, map_sim_url: str) -> None:
    """將所有無人機狀態 push 至 Map Simulator"""
    async with aiohttp.ClientSession() as session:
        for drone in self.flight_manager.drones.values():
            payload = {
                "drone_id": drone.drone_id,
                "lat": drone.lat,
                "lon": drone.lon,
                "alt_m": drone.alt_m,
                "speed_ms": drone.velocity_ms,
                "heading_deg": drone.heading_deg,
                "status": drone.flight_state.name,
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            }
            try:
                await session.post(f"{map_sim_url}/objects/update", json=payload)
            except Exception as e:
                logger.warning(f"UDS: failed to push to Map Simulator: {e}")
```

### 6.2 啟動順序

```bash
# 建議啟動順序：
# 1. 啟動 Map Simulator（先啟動，讓後續元件可以連線）
python map_simulator.py --port 8090

# 2. 啟動 Unified Drone Simulator（開始 push 狀態到 Map Sim）
python unified_drone_simulator.py --scenario scenarios/single_drone.yaml --map-sim-url http://localhost:8090

# 3. 啟動 EchoShield Simulator（向 Map Sim 查詢物件）
python echoshield_simulator.py --map-sim-url http://localhost:8090 --radar-lat 25.0330 --radar-lon 121.5654 --radar-range-m 4800

# 4. 啟動 Sentrycs Simulator（向 Map Sim 查詢物件）
python sentrycs_simulator.py --map-sim-url http://localhost:8090 --uds-url http://localhost:8080

# 5. 啟動 CoT Gateway
python gateway_main.py --config gateway_config.yaml

# 6. 啟動 TAK Server（Docker）
docker compose up -d
```

---

## 7. 單元測試需求

| ID | 測試項目 |
|----|---------|
| TR-MS-001 | POST /objects/update 成功新增物件 |
| TR-MS-002 | POST /objects/update 成功更新現有物件 |
| TR-MS-003 | GET /objects?lat=&lon=&radius_m= 回傳範圍內正確物件 |
| TR-MS-004 | GET /objects? 回傳物件按 distance_m 由近到遠排序 |
| TR-MS-005 | TTL warn：物件超過 5s 未更新，GET /objects? 不回傳（status 標記 lost）|
| TR-MS-006 | TTL remove：物件超過 10s 未更新，從登錄表移除 |
| TR-MS-007 | include_lost=true 時回傳 lost 物件 |
| TR-MS-008 | GET /objects/all 回傳所有物件 |
| TR-MS-009 | 多架並行（5 架），GET /objects? 正確計算各物件距離 |
| TR-MS-010 | GET /health 回傳正確物件數與 uptime |
| TR-MS-011 | DELETE /objects/{drone_id} 成功移除 |

---

## 8. 依賴清單

```
asyncio (stdlib)
aiohttp>=3.9
pytest>=7.0
pytest-asyncio>=0.23
```
