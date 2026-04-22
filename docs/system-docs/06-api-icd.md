# API 介面控制文件（ICD）

---

| 欄位 | 內容 |
|------|------|
| **文件編號** | 06 |
| **版本** | v0.3 |
| **日期** | 2026-04-22（修訂：部署環境更新為 MacBook Pro 本機，移除 WinTAK）|
| **作者** | 系統架構小組 |
| **狀態** | 草稿 |

---

## 1. 介面清單

> **部署環境說明（v0.2 修訂）**：PoC 階段所有服務（TAK Server、模擬器、CoT Gateway）均部署於同一台 MacBook Pro 本機。TAK Server 對 Android ATAK 裝置開放 LAN IP（同 Wi-Fi 網段）。

| 介面 ID | 名稱 | 來源 | 目的地 | 協定 | 格式 | Port |
|---------|------|------|--------|------|------|------|
| ICD-001 | EchoShield TCP JSON API | EchoShield Simulator | EchodyneAdapter（CoT Gateway）| TCP | JSON（換行分隔）| 9000 |
| ICD-002 | Sentrycs TAK Push | Sentrycs Simulator | TAK Server（直通）| TCP SSL | CoT XML | 8089 |
| ICD-003 | CoT Gateway → TAK Server | TakTransmitter（CoT Gateway）| TAK Server | TCP SSL | CoT XML | 8089 |
| ICD-004 | EchodyneAdapter 內部介面 | EchodyneAdapter | TrackCorrelator | Python In-process | Track dataclass | — |

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

## 3. ICD-002：Sentrycs TAK Push CoT XML

### 3.1 連線規格

| 項目 | 規格 |
|------|------|
| 協定 | TCP + TLS 1.2 |
| 角色 | Sentrycs Simulator 為 Client，TAK Server（MacBook Docker）為 Server |
| Server Port | 8089 |
| Server 位址 | `localhost`（本機）或 `<MacBook-LAN-IP>`（Android 裝置用）|
| 憑證 | 客戶端憑證（PKCS#12，sentrycs.p12）|
| Truststore | 包含 TAK-POC-CA 根憑證 |
| 訊息分隔符 | 換行符（`\n`）|
| 方向 | Client → Server（Sentrycs 推送 CoT）|
| Push 頻率 | 穩定狀態：1 Hz，狀態變化時：立即推送 |

### 3.2 憑證要求

| 憑證 | 格式 | 用途 | 來源 |
|------|------|------|------|
| `sentrycs.p12` | PKCS#12 | Sentrycs Simulator 客戶端身份 | TAK Server makeCert.sh |
| `truststore.p12` / `truststore.pem` | PKCS#12 / PEM | 驗證 TAK Server 伺服器憑證 | TAK Server makeRootCa.sh |

### 3.3 CoT XML Schema（關鍵欄位）

```xml
<!-- event 元素必填屬性 -->
<event
  version="2.0"                    <!-- CoT 協定版本，固定 "2.0" -->
  uid="{唯一識別碼}"                <!-- 必填，全域唯一，詳見 uid 命名規則 -->
  type="{CoT type}"                <!-- 必填，MIL-STD-2525C -->
  time="{ISO8601 UTC}"            <!-- 必填，訊息產生時間 -->
  start="{ISO8601 UTC}"           <!-- 必填，等於 time -->
  stale="{ISO8601 UTC}"           <!-- 必填，訊息失效時間（time + 15s 或 30s）-->
  how="m-g">                      <!-- 必填，固定 "m-g"（machine-generated）-->

  <!-- point 元素（位置）-->
  <point
    lat="{float}"                  <!-- WGS84 緯度，7 位小數 -->
    lon="{float}"                  <!-- WGS84 經度，7 位小數 -->
    hae="{float}"                  <!-- 高度（公尺，HAE）-->
    ce="{float}"                   <!-- 水平誤差圓（公尺）-->
    le="{float}"/>                 <!-- 垂直誤差（公尺）-->

  <!-- detail 元素（詳細資訊）-->
  <detail>
    <contact callsign="{string}"/> <!-- 顯示名稱 -->
    <remarks>{string}</remarks>    <!-- 狀態說明（決定 TAK 圖標顏色變化）-->
    <sensor model="{string}"       <!-- 無人機型號 -->
            status="{string}"      <!-- Detected/Mitigating/Neutralized -->
            source="Sentrycs"/>    <!-- 感測器來源 -->
    <operator                      <!-- 操控者位置（僅無人機 CoT 含此元素）-->
      lat="{float}"
      lon="{float}"
      distance_m="{float}"
      bearing_deg="{float}"/>
  </detail>
</event>
```

### 3.4 DETECTED 狀態 CoT 完整範例

```xml
<?xml version="1.0" encoding="UTF-8"?>
<event version="2.0"
       uid="SENTRYCS-DJI-Mavic3-001"
       type="a-h-A-M-F-Q-r"
       time="2025-07-10T08:00:05.000Z"
       start="2025-07-10T08:00:05.000Z"
       stale="2025-07-10T08:00:20.000Z"
       how="m-g">
  <point lat="25.0330000" lon="121.5654000" hae="120.5" ce="25.0" le="10.0"/>
  <detail>
    <contact callsign="DJI-Mavic3-001"/>
    <usericon iconsetpath="34ae1613-9645-4222-a9d2-e5f243dea2865/Military/Air_Enemy.png"/>
    <remarks>Sentrycs: Detected | Model: DJI Mavic 3 | Speed: 15.0m/s</remarks>
    <sensor model="DJI Mavic 3" status="Detected" source="Sentrycs"/>
    <operator lat="25.0309929" lon="121.5632836" distance_m="300" bearing_deg="225"/>
  </detail>
</event>
```

### 3.5 MITIGATING 狀態 CoT 完整範例

```xml
<?xml version="1.0" encoding="UTF-8"?>
<event version="2.0"
       uid="SENTRYCS-DJI-Mavic3-001"
       type="a-h-A-M-F-Q-r"
       time="2025-07-10T08:00:20.000Z"
       start="2025-07-10T08:00:20.000Z"
       stale="2025-07-10T08:00:35.000Z"
       how="m-g">
  <point lat="25.0312753" lon="121.5653945" hae="115.2" ce="25.0" le="10.0"/>
  <detail>
    <contact callsign="DJI-Mavic3-001"/>
    <usericon iconsetpath="34ae1613-9645-4222-a9d2-e5f243dea2865/Military/Air_Enemy.png"/>
    <remarks>Sentrycs: Mitigating | Model: DJI Mavic 3 | RF Jamming Active</remarks>
    <sensor model="DJI Mavic 3" status="Mitigating" source="Sentrycs"/>
    <operator lat="25.0309929" lon="121.5632836" distance_m="300" bearing_deg="225"/>
  </detail>
</event>
```

### 3.6 NEUTRALIZED 狀態 CoT 完整範例

```xml
<?xml version="1.0" encoding="UTF-8"?>
<event version="2.0"
       uid="SENTRYCS-DJI-Mavic3-001"
       type="a-h-A-M-F-Q-r"
       time="2025-07-10T08:00:35.000Z"
       start="2025-07-10T08:00:35.000Z"
       stale="2025-07-10T08:01:05.000Z"
       how="m-g">
  <point lat="25.0295506" lon="121.5653890" hae="110.8" ce="25.0" le="10.0"/>
  <detail>
    <contact callsign="DJI-Mavic3-001"/>
    <usericon iconsetpath="34ae1613-9645-4222-a9d2-e5f243dea2865/Military/Air_Enemy.png"/>
    <remarks>Sentrycs: Neutralized | Model: DJI Mavic 3 | RF Control Seized</remarks>
    <sensor model="DJI Mavic 3" status="Neutralized" source="Sentrycs"/>
    <operator lat="25.0309929" lon="121.5632836" distance_m="300" bearing_deg="225"/>
  </detail>
</event>
```

### 3.7 操控者位置 CoT 完整範例

```xml
<?xml version="1.0" encoding="UTF-8"?>
<event version="2.0"
       uid="SENTRYCS-OPERATOR-DJI-Mavic3-001"
       type="a-h-G-U-C-I"
       time="2025-07-10T08:00:05.000Z"
       start="2025-07-10T08:00:05.000Z"
       stale="2025-07-10T08:00:20.000Z"
       how="m-g">
  <point lat="25.0309929" lon="121.5632836" hae="0.0" ce="50.0" le="9999999.0"/>
  <detail>
    <contact callsign="OPERATOR-DJI-Mavic3-001"/>
    <remarks>Sentrycs: Operator Location | Drone: DJI-Mavic3-001 | Distance: 300m | Bearing: 225°</remarks>
  </detail>
</event>
```

### 3.8 stale time 計算規則

```
DETECTED 或 MITIGATING：stale = time + 15 秒
NEUTRALIZED：             stale = time + 30 秒
操控者位置：               stale = time + 15 秒
```

### 3.9 uid 命名規則

| 目標類型 | 命名格式 | 範例 |
|---------|---------|------|
| 無人機（DJI Mavic 3）| `SENTRYCS-DJI-Mavic3-{SEQ:03d}` | `SENTRYCS-DJI-Mavic3-001` |
| 無人機（DJI Matrice 30T）| `SENTRYCS-DJI-Matrice30T-{SEQ:03d}` | `SENTRYCS-DJI-Matrice30T-001` |
| 無人機（Autel EVO II）| `SENTRYCS-Autel-EVOII-{SEQ:03d}` | `SENTRYCS-Autel-EVOII-001` |
| 操控者 | `SENTRYCS-OPERATOR-{無人機uid的SENTRYCS-後半部}` | `SENTRYCS-OPERATOR-DJI-Mavic3-001` |

---

## 4. ICD-003：CoT Gateway → TAK Server

### 4.1 連線規格

與 ICD-002 相同（TCP SSL Port 8089，MacBook 本機 localhost），差別在於使用 `gateway.p12` 客戶端憑證。

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
| Sentrycs 直通 DETECTED | `a-h-A-M-F-Q-r` | 紅色 | ICD-002 路徑 |
| Sentrycs 直通 MITIGATING | `a-h-A-M-F-Q-r` | 橘色閃爍 | ICD-002 路徑 |
| Sentrycs 直通 NEUTRALIZED | `a-h-A-M-F-Q-r` | 藍色 | ICD-002 路徑 |
| 操控者位置（Sentrycs）| `a-h-G-U-C-I` | 橘色 | ICD-002 路徑 |

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

1. 在本文件（06-api-icd.md）更新對應 ICD 章節
2. 更新版本號與日期
3. 在 CHANGELOG 記錄變更內容
4. 更新相關模組的 unit test
5. 通知所有 ICD 使用方（Gateway、Simulator 開發人員）
