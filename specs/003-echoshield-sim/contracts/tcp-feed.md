# Contract: EchoShield TCP JSON Feed (`:9000`)

**Feature**: `003-echoshield-sim`
**Version**: `1.0.0`（凍結；任何變更需 bump minor/major + 更新 spec）
**Endpoint**: `tcp://{feed_host}:{feed_port}`（預設 `tcp://0.0.0.0:9000`）
**Direction**: Server → Client（單向 push；Server 不讀 Client 的任何輸入）
**Transport**: Plain TCP（無 TLS、無認證；PoC only）
**Encoding**: UTF-8
**Framing**: **每筆 track 一行 JSON，以 `\n`（0x0A）結尾**。**無** batch array、**無** keepalive、
**無** handshake、**無** header。

> 下游消費者：CoT Gateway EchodyneAdapter。本契約對應 spec FR-ES-005 / -013 / -015 與
> §Key Entities `RadarTrack`。與 `docs/system-docs/08-api-icd.md` (ICD-001) 若有衝突，以**本契約**為準
> （見 spec §Assumptions）。

---

## 1. Connection Semantics

| Behaviour                      | Requirement                                                                                |
| ------------------------------ | ------------------------------------------------------------------------------------------ |
| 並發連線                       | Server **MUST** 支援 ≥ 2 個 Client 同時連線，彼此 fan-out 相同 bytes（FR-ES-013 / SC-ES-007） |
| 新連線                         | 立即加入廣播名單，**從下一輪 tick 起**接收；**MUST NOT** 回放歷史（FR-ES-015）             |
| 主動關閉 / RST / EOF           | Server **MUST** 從廣播名單移除該 writer，**MUST NOT** 影響其他 Client / 主迴圈（FR-ES-014）  |
| Client 端 slow consumer        | PoC **MAY** 於 `drain()` 失敗時直接移除該 Client（不做 queue 背壓；預期 < 1 MB/s 流量）     |
| 無 Client 連線                 | 主迴圈 **MUST** 繼續執行；可跳過 socket write（FR-ES-016）                                  |
| Keepalive / heartbeat          | **不**支援；依賴 TCP 本身與下游 timeout（spec §Assumptions）                                |
| 反向輸入（Client → Server）    | Server **MUST** 忽略（不讀取 / 不解析）                                                     |

---

## 2. Message Frame

```
<json-object><LF>
```

- `<json-object>` = 緊湊 JSON（**無**換行、**無**多餘空白；`json.dumps(obj, separators=(",", ":"))`）。
- `<LF>` = 單一 `0x0A` byte。**禁止** CRLF。
- 每行**僅**一個 JSON object；**禁止** array、**禁止** multi-line pretty-print。
- Client 解析建議：buffered read until `\n`，每行 `json.loads()`。

### 2.1 安靜模式

當**本輪無任何 track 輸出**（無 Active、無當輪到期的 Lost），Server **MUST NOT** 寫任何 bytes，
包含**不**寫空行（FR-ES-011 / SC-ES-011）。TCP 連線保持開啟。

---

## 3. JSON Schema

### 3.1 `RadarTrack`（JSON Schema draft-2020-12）

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://cics-tak/echoshield/RadarTrack.json",
  "title": "RadarTrack",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "track_id",
    "latitude",
    "longitude",
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
      "pattern": "^echo-[0-9a-f]{8}$",
      "description": "`echo-{8-hex}`, stable during a single Active lifecycle."
    },
    "latitude":      { "type": "number", "minimum":  -90, "maximum":  90, "description": "WGS84 deg, noised; 7 decimal places" },
    "longitude":     { "type": "number", "minimum": -180, "maximum": 180, "description": "WGS84 deg, noised; 7 decimal places" },
    "altitude_m":    { "type": "number", "description": "HAE meters, noised; 1 decimal place" },
    "velocity_ms":   { "type": "number", "minimum": 0,                     "description": "Ground speed m/s, noised + max(0, ·); 2 decimal places" },
    "azimuth_deg":   { "type": "number", "minimum": 0, "exclusiveMaximum": 360, "description": "Bearing from sensor, clockwise from true north; 2 dp" },
    "elevation_deg": { "type": "number", "minimum": -90, "maximum": 90,    "description": "Elevation from sensor; 2 dp" },
    "timestamp":     { "type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\.\\d{3}Z$", "description": "UTC ISO-8601, millisecond precision, Z suffix" },
    "track_status":  { "type": "string", "enum": ["Active", "Lost"] },
    "classification":{ "type": "string", "const": "UAV" }
  }
}
```

### 3.2 欄位補充

| Field             | Rule                                                                                         |
| ----------------- | -------------------------------------------------------------------------------------------- |
| `track_id`        | `echo-` + `uuid4().hex[:8]`。Active 生命週期內不變；Lost 後釋放，再出現 → **新**的 track_id   |
| `latitude`/`longitude` | 真實位置 + Gaussian σ=5m（以 `σ/111320` 近似換算為度），`round(x, 7)`                     |
| `altitude_m`      | 真實 HAE + Gaussian σ=2m，`round(x, 1)`                                                       |
| `velocity_ms`     | 真實 speed + Gaussian σ=0.5m/s，`max(0.0, ·)`，`round(x, 2)`                                  |
| `azimuth_deg`     | 以 `(sensor_lat, sensor_lon)` → `(noised_lat, noised_lon)` 的大圓 bearing，`% 360`，`round(x, 2)` |
| `elevation_deg`   | `atan2(noised_alt − sensor_alt, haversine_horiz)`，水平距離 `< 1m` 時 = `±90.0`（FR-ES-020） |
| `timestamp`       | Simulator 主機 UTC 牆上時鐘；format `YYYY-MM-DDTHH:MM:SS.sssZ`（毫秒，`Z` 後綴）              |
| `track_status`    | 僅 `"Active"` 或 `"Lost"`（首字大寫；**禁**用 ICD-001 的 `NEW/UPDATED/LOST`）                 |
| `classification`  | 固定字串 `"UAV"`                                                                              |

### 3.3 Example

```json
{"track_id":"echo-1a2b3c4d","latitude":24.0008934,"longitude":121.0001205,"altitude_m":98.7,"velocity_ms":12.34,"azimuth_deg":3.21,"elevation_deg":5.07,"timestamp":"2026-04-24T08:15:30.123Z","track_status":"Active","classification":"UAV"}
```

---

## 4. Broadcast Timing

| Property                 | Value / Requirement                                                              |
| ------------------------ | -------------------------------------------------------------------------------- |
| Push rate（有 track 時） | 10 Hz（可由 `update_rate_hz` 調整），SC-ES-001 允許 ±10% 抖動                     |
| Lost 事件                | 於 `last_seen_mono` + `lost_grace_sec` 逾時的「**下一輪 tick**」送出**恰一筆**    |
| Fan-out 一致性           | 同一 tick 中，所有 Client **MUST** 收到**相同 bytes**（同一次序列化結果）         |
| Per-tick 輸出量          | 當前 Active 數 + 當輪到期 Lost 數；可能為 0（→ 安靜模式）                          |

---

## 5. Non-Goals（本契約**不**涵蓋，以免未來混淆）

- ❌ `snr_db` / `rcs_dbsm` / `source`：ICD-001 的選填欄位，本版本**不**輸出（`additionalProperties: false`）。
- ❌ Batch array（`[{track},{track}]`）：固定 NDJSON。
- ❌ 二進位 framing / length prefix：純文字 NDJSON。
- ❌ Client 端訂閱 / 過濾：所有 Client 拿到相同內容。
- ❌ TLS、auth、replay / history：PoC 明文、無歷史。

---

## 6. Contract Test Expectations（給 `tests/contract/test_radar_track_schema.py`）

實作完成後，契約測試 **MUST** 至少覆蓋：

1. 以 stub Map Sim 餵固定 `objects[]`，接收 ≥ 1 筆 JSON 行後：
   - 每行 byte 末 = `0x0A`，且行內無其他 `0x0A`。
   - `json.loads(line)` 成功，結果通過 §3.1 JSON Schema 驗證。
2. 固定 seed（`--seed 42`）+ `freezegun` 凍結時間 → 輸出 JSON 完全 bit-identical（回歸保護）。
3. Map Sim 回 `count=0` 連續 5 秒 → Server 對 socket 寫入 `0` bytes（安靜模式）。
4. `track_status` 僅出現 `"Active"` 或 `"Lost"`，其餘字串即為違約。
