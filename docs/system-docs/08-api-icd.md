# API 介面控制文件（ICD）

---

| 欄位 | 內容 |
|------|------|
| **文件編號** | 08 |
| **版本** | v0.5 |
| **日期** | 2026-04-23 |
| **作者** | 系統架構小組 |
| **狀態** | 草稿 |

---

## 1. 介面清單

> **部署環境說明（v0.2 修訂）**：PoC 階段所有服務（TAK Server、模擬器、CoT Gateway）均部署於同一台 展示環境主機。TAK Server 對 Android ATAK 裝置開放 LAN IP（同 Wi-Fi 網段）。

| 介面 ID | 名稱 | 來源 | 目的地 | 協定 | 格式 | Port |
|---------|------|------|--------|------|------|------|
| ICD-001 | EchoShield TCP JSON API | EchoShield Simulator | EchodyneAdapter（CoT Gateway）| TCP | JSON（換行分隔）| 9000 |
| ICD-002 | Sentrycs JSON Status API | Sentrycs Simulator | SentrycsAdapter（CoT Gateway）| HTTP | JSON | 7070 |
| ICD-003 | CoT Gateway → TAK Server | TakTransmitter（CoT Gateway）| TAK Server | TCP SSL | CoT XML | 8089 |
| ICD-004 | EchodyneAdapter 內部介面 | EchodyneAdapter | TrackCorrelator | Python In-process | Track dataclass | — |
| ICD-005 | SentrycsAdapter 內部介面 | SentrycsAdapter | TrackCorrelator | Python In-process | Track dataclass | — |

---

## 2. ICD-001：EchoShield TCP JSON API

### 2.1 連線規格

| 項目 | 規格 |
|------|------|
| 協定 | TCP（明文，無 SSL）|
| 角色 | EchoShield Simulator 為 Server，EchodyneAdapter 為 Client |
| Server Port | 9000（Simulator 預設值，可設定）|
| 編碼 | UTF-8 |
| 訊息分隔符 | 換行符（`\n`, 0x0A）|
| 方向 | Server → Client（Server 推送，Client 接收）|
| 連線數 | 支援多個 Client 同時連線 |
| 更新頻率 | 預設 10 Hz（每 100ms 廣播一次所有活躍航跡）|

### 2.2 訊息格式

每筆訊息為一個 JSON 物件，以換行符結尾：

```
{"track_id":"TRK-001","lat":25.033,"lon":121.5654,...}\n
{"track_id":"TRK-001","lat":25.0328,"lon":121.5652,...}\n
```

### 2.3 完整 JSON Schema（Draft-07）

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "EchoShieldTrack",
  "description": "EchoShield 雷達輸出的單一航跡資料（每筆換行分隔）",
  "type": "object",
  "required": [
    "track_id",
    "lat",
    "lon",
    "altitude_m",
    "velocity_ms",
    "azimuth_deg",
    "elevation_deg",
    "timestamp",
    "track_status",
    "classification"
  ],
  "properties": {
    "track_id": {
      "type": "string",
      "description": "航跡唯一識別碼，整個飛行過程保持不變",
      "pattern": "^TRK-[0-9]{3,6}$",
      "example": "TRK-001"
    },
    "lat": {
      "type": "number",
      "description": "緯度（WGS84 十進位度）",
      "minimum": -90,
      "maximum": 90,
      "example": 25.0330147
    },
    "lon": {
      "type": "number",
      "description": "經度（WGS84 十進位度）",
      "minimum": -180,
      "maximum": 180,
      "example": 121.5654032
    },
    "altitude_m": {
      "type": "number",
      "description": "高度（公尺，HAE - Height Above Ellipsoid）",
      "minimum": 0,
      "maximum": 5000,
      "example": 120.5
    },
    "velocity_ms": {
      "type": "number",
      "description": "地速（m/s）",
      "minimum": 0,
      "maximum": 150,
      "example": 15.2
    },
    "azimuth_deg": {
      "type": "number",
      "description": "飛行方位角（度，正北 0°，順時針）",
      "minimum": 0,
      "maximum": 360,
      "example": 181.5
    },
    "elevation_deg": {
      "type": "number",
      "description": "飛行俯仰角（度，水平 0°，向上正值）",
      "minimum": -90,
      "maximum": 90,
      "example": -2.3
    },
    "timestamp": {
      "type": "string",
      "description": "雷達量測時間（ISO 8601，UTC，毫秒精度）",
      "format": "date-time",
      "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\.\\d{3}Z$",
      "example": "2025-07-10T08:00:01.234Z"
    },
    "track_status": {
      "type": "string",
      "description": "航跡狀態：NEW=首次偵測，UPDATED=持續追蹤，LOST=超出偵測範圍",
      "enum": ["NEW", "UPDATED", "LOST"],
      "example": "UPDATED"
    },
    "classification": {
      "type": "string",
      "description": "目標分類結果",
      "enum": ["DRONE", "BIRD", "UNKNOWN"],
      "example": "DRONE"
    },
    "snr_db": {
      "type": "number",
      "description": "信噪比（dB）【選填】，模擬器隨機生成 10–30 dB",
      "example": 18.5
    },
    "rcs_dbsm": {
      "type": "number",
      "description": "雷達截面積（dBsm）【選填】，模擬器隨機生成 -20~0 dBsm",
      "example": -12.3
    }
  },
  "additionalProperties": false
}
```

### 2.4 範例訊息（三種 track_status）

**NEW 狀態（首次偵測）**

```json
{"track_id":"TRK-001","lat":25.0598234,"lon":121.5654012,"altitude_m":101.0,"velocity_ms":15.0,"azimuth_deg":180.0,"elevation_deg":-1.5,"timestamp":"2025-07-10T08:00:00.000Z","track_status":"NEW","classification":"DRONE","snr_db":22.1,"rcs_dbsm":-11.5}
```

**UPDATED 狀態（正常追蹤中）**

```json
{"track_id":"TRK-001","lat":25.0584745,"lon":121.5654089,"altitude_m":100.8,"velocity_ms":15.1,"azimuth_deg":180.2,"elevation_deg":-1.4,"timestamp":"2025-07-10T08:00:01.000Z","track_status":"UPDATED","classification":"DRONE","snr_db":22.4,"rcs_dbsm":-11.3}
```

**LOST 狀態（超出偵測範圍）**

```json
{"track_id":"TRK-001","lat":25.0182156,"lon":121.5654501,"altitude_m":98.5,"velocity_ms":0.0,"azimuth_deg":180.0,"elevation_deg":0.0,"timestamp":"2025-07-10T08:03:00.000Z","track_status":"LOST","classification":"DRONE","snr_db":5.2,"rcs_dbsm":-18.9}
```

### 2.5 錯誤情境

| 情境 | 行為 | EchodyneAdapter 處理 |
|------|------|---------------------|
| TCP 連線中斷 | Socket 關閉，EOF | 等待 5s 後嘗試重連，無限重試 |
| JSON 格式錯誤（非法 JSON）| 收到無效 JSON 字串 | 記錄 ERROR，跳過該筆，繼續讀取 |
| 缺少必填欄位 | JSON 缺少 `track_id` 等 | 記錄 ERROR，跳過該筆 |
| 欄位值超出範圍（lat=999）| JSON 值不合法 | 記錄 WARNING，跳過該筆 |
| Server 長時間無資料（>30s）| 疑似 Server 異常 | 記錄 WARNING，主動關閉並重連 |

---

## 3. ICD-002：Sentrycs JSON Status API（HTTP Port 7070）

### 3.1 連線規格

| 項目 | 規格 |
|------|------|
| 協定 | TCP（明文，無 SSL）|
| 角色 | Sentrycs Simulator 為 HTTP Server（:17070），SentrycsAdapter 為 HTTP Client（輪詢）|
| Port | 7070 |
| Server 位址 | `127.0.0.1`（本機，不需跨網段）|
| 加密 | 無（本機通訊，不需 SSL）|
| 訊息分隔符 | 換行符（`\n`, 0x0A）|
| 方向 | Server → Client（Sentrycs 推送 JSON，SentrycsAdapter 接收）|
| Push 頻率 | 穩定狀態：1 Hz，狀態變化時：立即推送 |
| IDLE 狀態 | 不推送（無輸出）|

### 3.2 JSON 完整 Schema（Draft-07）

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "SentrycsDetection",
  "description": "Sentrycs Simulator 輸出的偵測資料（每筆換行分隔）",
  "type": "object",
  "required": ["drone_id", "model", "lat", "lon", "alt_m", "status", "operator_lat", "operator_lon", "timestamp"],
  "properties": {
    "drone_id": {
      "type": "string",
      "description": "對應 UDS 的 drone_id（如 TRK-001）",
      "example": "TRK-001"
    },
    "model": {
      "type": "string",
      "description": "無人機型號",
      "enum": ["DJI Mavic 3", "DJI Matrice 30T", "Autel EVO II"]
    },
    "lat": {"type": "number", "minimum": -90, "maximum": 90},
    "lon": {"type": "number", "minimum": -180, "maximum": 180},
    "alt_m": {"type": "number", "minimum": 0, "maximum": 5000, "description": "高度（公尺，HAE）"},
    "velocity_ms": {"type": "number", "minimum": 0, "maximum": 150},
    "azimuth_deg": {"type": "number", "minimum": 0, "maximum": 360},
    "status": {
      "type": "string",
      "enum": ["DETECTED", "MITIGATING", "NEUTRALIZED"],
      "description": "Sentrycs 偵測狀態（IDLE 狀態不輸出）"
    },
    "operator_lat": {"type": "number", "minimum": -90, "maximum": 90},
    "operator_lon": {"type": "number", "minimum": -180, "maximum": 180},
    "operator_distance_m": {"type": "number", "description": "操控者距無人機距離（公尺）"},
    "operator_bearing_deg": {"type": "number", "minimum": 0, "maximum": 360},
    "timestamp": {
      "type": "string",
      "format": "date-time",
      "description": "偵測時間（ISO 8601 UTC）"
    }
  },
  "additionalProperties": false
}
```

### 3.3 對應 CoT XML（由 CoT Gateway CotGenerator 產生）

> **架構說明**：以下 CoT XML 由 CoT Gateway 的 CotGenerator 根據 SentrycsAdapter 轉換後的 Track 物件產生，不再由 Sentrycs Simulator 直接輸出。Sentrycs Simulator 僅輸出 JSON（見 3.2）。

---

## 4. ICD-003：CoT Gateway → TAK Server

### 4.1 連線規格

與 ICD-003 使用相同的 TCP SSL Port 8089，差別在於使用 `gateway.p12` 客戶端憑證。

### 4.2 EchoShield 偵測（未關聯）CoT 範例

```xml
<?xml version="1.0" encoding="UTF-8"?>
<event version="2.0"
       uid="ECHOSHIELD-TRK-001"
       type="a-u-A-M-F-Q-r"
       time="2025-07-10T08:00:01.234Z"
       start="2025-07-10T08:00:01.234Z"
       stale="2025-07-10T08:00:16.234Z"
       how="m-g">
  <point lat="25.0584745" lon="121.5654089" hae="100.8" ce="10.0" le="5.0"/>
  <detail>
    <contact callsign="ECHOSHIELD-TRK-001"/>
    <remarks>Source: ECHOSHIELD | Speed: 15.1m/s | Alt: 101m</remarks>
    <track speed="15.10" course="180.20"/>
  </detail>
</event>
```

> **CoT type `a-u-A-M-F-Q-r` 說明**：
> - `a` = Atom（點狀目標）
> - `u` = Unknown（未知敵我）→ TAK 顯示為**灰色**
> - `A` = Air（空中目標）
> - `M-F-Q-r` = Military Fixed Wing Quality rotary（旋翼機品質）

### 4.3 融合航跡（FUSED）CoT 範例

```xml
<?xml version="1.0" encoding="UTF-8"?>
<event version="2.0"
       uid="FUSED-TRK-001"
       type="a-h-A-M-F-Q-r"
       time="2025-07-10T08:00:06.234Z"
       start="2025-07-10T08:00:06.234Z"
       stale="2025-07-10T08:00:21.234Z"
       how="m-g">
  <point lat="25.0316987" lon="121.5653998" hae="115.5" ce="10.0" le="5.0"/>
  <detail>
    <contact callsign="FUSED-TRK-001"/>
    <remarks>Source: FUSED | Model: DJI Mavic 3 | Status: Detected | Speed: 15.0m/s | Alt: 116m</remarks>
    <track speed="15.00" course="180.10"/>
  </detail>
</event>
```

> **CoT type `a-h-A-M-F-Q-r` 說明**：
> - `h` = Hostile（確認敵對）→ TAK 顯示為**紅色**（含型號識別後升級）

### 4.4 uid 命名規則

| Track.source | uid 格式 | 範例 |
|-------------|---------|------|
| `ECHOSHIELD`（未關聯）| `ECHOSHIELD-{track_id}` | `ECHOSHIELD-TRK-001` |
| `FUSED`（雷達+RF 融合）| `FUSED-{radar_track_id}` | `FUSED-TRK-001` |

### 4.5 CoT Type 完整映射表

| 情境 | CoT Type | 顏色 | 備註 |
|------|---------|------|------|
| EchoShield 偵測，未識別 | `a-u-A-M-F-Q-r` | 灰色 | 純雷達，無型號資訊 |
| FUSED，Sentrycs DETECTED | `a-h-A-M-F-Q-r` | 紅色 | 融合且 RF 確認威脅 |
| FUSED，Sentrycs MITIGATING | `a-h-A-M-F-Q-r` | 橘色閃爍 | remarks 含 "Mitigating" |
| FUSED，Sentrycs NEUTRALIZED | `a-h-A-M-F-Q-r` | 藍色 | remarks 含 "Neutralized" |

> **v0.4 架構說明**：所有 CoT type 的判斷邏輯現在均在 CoT Gateway 的 CotGenerator 執行；Sentrycs Simulator 僅提供 `detection_status` 字串，Gateway 負責映射至正確的 CoT type。

---

## 5. ICD-004：EchodyneAdapter 內部介面

### 5.1 Track dataclass 完整定義

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone

class TrackSource(Enum):
    ECHOSHIELD = "ECHOSHIELD"
    SENTRYCS = "SENTRYCS"
    FUSED = "FUSED"

class TrackStatus(Enum):
    NEW = "NEW"
    UPDATED = "UPDATED"
    LOST = "LOST"

@dataclass
class Track:
    """
    系統統一航跡物件，在各模組間傳遞。
    由 EchodyneAdapter 創建，流經 TrackCorrelator → CotGenerator → TakTransmitter。
    """
    track_id: str
    source: TrackSource
    lat: float
    lon: float
    alt_m: float
    velocity_ms: float
    azimuth_deg: float
    elevation_deg: float
    timestamp: datetime
    track_status: TrackStatus
    classification: str
    drone_model: Optional[str] = None
    detection_status: Optional[str] = None
    correlation_id: Optional[str] = None
    radar_track_id: Optional[str] = None
    rf_track_id: Optional[str] = None
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
```

### 5.2 序列化方法

```python
def track_to_dict(track: Track) -> dict:
    """Track 物件序列化為 dict（用於日誌、除錯）"""
    return {
        "track_id": track.track_id,
        "source": track.source.value,
        "lat": track.lat,
        "lon": track.lon,
        "alt_m": track.alt_m,
        "velocity_ms": track.velocity_ms,
        "azimuth_deg": track.azimuth_deg,
        "elevation_deg": track.elevation_deg,
        "timestamp": track.timestamp.isoformat(),
        "track_status": track.track_status.value,
        "classification": track.classification,
        "drone_model": track.drone_model,
        "detection_status": track.detection_status,
        "correlation_id": track.correlation_id,
        "radar_track_id": track.radar_track_id,
        "rf_track_id": track.rf_track_id,
    }

def track_from_echoshield_json(data: dict) -> Track:
    """從 EchoShield JSON dict 建立 Track 物件"""
    return Track(
        track_id=data["track_id"],
        source=TrackSource.ECHOSHIELD,
        lat=data["lat"],
        lon=data["lon"],
        alt_m=data["altitude_m"],
        velocity_ms=data["velocity_ms"],
        azimuth_deg=data["azimuth_deg"],
        elevation_deg=data["elevation_deg"],
        timestamp=datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00")),
        track_status=TrackStatus[data["track_status"]],
        classification=data["classification"],
    )
```

---

## 6. 端對端訊息流範例

### 6.0 Sentrycs 路徑端對端說明

Sentrycs 數據現在透過 CoT Gateway 融合：

1. Sentrycs Simulator → HTTP JSON Status API（HTTP :17070，aiohttp Server）
2. SentrycsAdapter → 接收 → 轉換為 `Track(source=SENTRYCS, drone_model="DJI Mavic 3", detection_status="DETECTED")`
3. TrackCorrelator → 與 EchoShield Track 距離≤50m 時融合 → `Track(source=FUSED)`
4. CotGenerator → `a-h-A-M-F-Q-r`（紅色）/ `a-u-A-M-F-Q-r`（灰色，純雷達）
5. TakTransmitter → TCP SSL :18089 → TAK Server → ATAK

### 6.1 完整轉換範例：EchoShield JSON → Track → CoT XML

**步驟 1：EchoShield Simulator 輸出 JSON**

```json
{"track_id":"TRK-001","lat":25.0584745,"lon":121.5654089,"altitude_m":100.8,"velocity_ms":15.1,"azimuth_deg":180.2,"elevation_deg":-1.4,"timestamp":"2025-07-10T08:00:01.000Z","track_status":"UPDATED","classification":"DRONE","snr_db":22.4,"rcs_dbsm":-11.3}
```

**步驟 2：EchodyneAdapter 解析為 Track 物件**

```python
Track(
    track_id="TRK-001",
    source=TrackSource.ECHOSHIELD,
    lat=25.0584745,
    lon=121.5654089,
    alt_m=100.8,
    velocity_ms=15.1,
    azimuth_deg=180.2,
    elevation_deg=-1.4,
    timestamp=datetime(2025, 7, 10, 8, 0, 1, tzinfo=timezone.utc),
    track_status=TrackStatus.UPDATED,
    classification="DRONE",
    drone_model=None,         # 尚未關聯 RF
    correlation_id=None,
    received_at=datetime(2025, 7, 10, 8, 0, 1, 15000, tzinfo=timezone.utc)  # +15ms
)
```

**步驟 3a：TrackCorrelator 無關聯 → 回傳原始 ECHOSHIELD Track**

**步驟 3b（若有關聯）：建立 FUSED Track**

```python
Track(
    track_id="FUSED-TRK-001",
    source=TrackSource.FUSED,
    lat=25.0584745,           # 雷達位置
    lon=121.5654089,
    alt_m=100.8,
    velocity_ms=15.1,
    azimuth_deg=180.2,
    elevation_deg=-1.4,
    timestamp=datetime(2025, 7, 10, 8, 0, 1, tzinfo=timezone.utc),
    track_status=TrackStatus.UPDATED,
    classification="DRONE",
    drone_model="DJI Mavic 3",        # RF 型號
    detection_status="Detected",       # RF 狀態
    correlation_id="FUSED-TRK-001",
    radar_track_id="TRK-001",
    rf_track_id="RF-001"
)
```

**步驟 4a（未關聯）：CotGenerator 產生 CoT XML**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<event version="2.0"
       uid="ECHOSHIELD-TRK-001"
       type="a-u-A-M-F-Q-r"
       time="2025-07-10T08:00:01.015Z"
       start="2025-07-10T08:00:01.015Z"
       stale="2025-07-10T08:00:16.015Z"
       how="m-g">
  <point lat="25.0584745" lon="121.5654089" hae="100.8" ce="10.0" le="5.0"/>
  <detail>
    <contact callsign="ECHOSHIELD-TRK-001"/>
    <remarks>Source: ECHOSHIELD | Speed: 15.1m/s | Alt: 101m</remarks>
    <track speed="15.10" course="180.20"/>
  </detail>
</event>
```

**步驟 4b（已關聯）：CotGenerator 產生 FUSED CoT XML**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<event version="2.0"
       uid="FUSED-TRK-001"
       type="a-h-A-M-F-Q-r"
       time="2025-07-10T08:00:01.025Z"
       start="2025-07-10T08:00:01.025Z"
       stale="2025-07-10T08:00:16.025Z"
       how="m-g">
  <point lat="25.0584745" lon="121.5654089" hae="100.8" ce="10.0" le="5.0"/>
  <detail>
    <contact callsign="FUSED-TRK-001"/>
    <remarks>Source: FUSED | Model: DJI Mavic 3 | Status: Detected | Speed: 15.1m/s | Alt: 101m</remarks>
    <track speed="15.10" course="180.20"/>
  </detail>
</event>
```

**步驟 5：TakTransmitter 推送至 TAK Server（含換行符）**

```
[CoT XML 字串]\n
```

### 6.2 時間戳傳遞規則

| 欄位 | 規則 | 說明 |
|------|------|------|
| EchoShield JSON `timestamp` | 雷達量測時間（感測器時間）| 放入 Track.timestamp |
| CoT `<event time="...">` | `datetime.utcnow()`（Gateway 產生 CoT 的時間）| 非感測器時間 |
| CoT `<event stale="...">` | `time + 15s`（或 30s）| 讓 TAK 在 15s 後自動隱藏 |
| Track `received_at` | Gateway 收到 JSON 的時間 | 用於延遲量測 |

---

## 7. 介面版本控制

### 7.1 版本欄位命名規範

| 介面 | 版本欄位位置 | 目前版本 |
|------|-----------|---------|
| ICD-001（JSON API）| JSON 頂層欄位 `api_version`（選填）| `"1.0"` |
| ICD-002/003（CoT XML）| `<event version="2.0">` 屬性 | `"2.0"`（固定）|
| ICD-004（Track dataclass）| Python module `__version__` | `"1.0"` |

### 7.2 向後相容性策略

**JSON API（ICD-001）**：
- 新增選填欄位（如 `snr_db`）：直接新增，不影響現有 Client
- 更改必填欄位名稱：視為破壞性變更，需遞增主版本（`1.0` → `2.0`）
- EchodyneAdapter 對未知欄位應採 **ignore** 策略（不拋出例外）

**CoT XML（ICD-002/003）**：
- TAK CoT 協定版本固定為 `2.0`，本系統不修改此版本
- `<detail>` 內的自訂元素（如 `<sensor>`, `<operator>`）TAK 對未知元素採 ignore 策略

**Track dataclass（ICD-004）**：
- 新增選填欄位（`Optional[str] = None`）：不影響現有模組
- 更改現有欄位型別：需同步更新所有模組，並加入 migration test

### 7.3 介面變更流程

1. 在本文件(08-api-icd.md)更新對應 ICD 章節
2. 更新版本號與日期
3. 在 CHANGELOG 記錄變更內容
4. 更新相關模組的 unit test
5. 通知所有 ICD 使用方（Gateway、Simulator 開發人員）
