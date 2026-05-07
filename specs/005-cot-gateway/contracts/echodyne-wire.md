# Contract: EchoShield Wire Parser（Gateway 上游消費端）

本契約定義 CoT Gateway 的 `EchodyneAdapter` 如何消費 EchoShield Simulator（或真實雷達硬體）
從 TCP `:19000` 輸出的 newline-delimited JSON 串流。

**上游權威 schema**：[`specs/003-echoshield-sim/contracts/`](../../003-echoshield-sim/contracts/)。
本檔僅定義 Gateway 側的**消費規則**（欄位對應、錯誤處理、首見旗標職責），不重新定義 wire schema
本身；wire schema 若變更以 003 為準。

---

## 1. Transport

| 項目 | 值 |
| --- | --- |
| 協議 | TCP（明文，無 TLS） |
| 端點 | 設定檔 `echoshield.host:port`，預設 `echoshield-sim:19000` |
| 框架 | Newline-delimited JSON；UTF-8；分隔符 `\n` (0x0A) |
| 連線模式 | Gateway 為 client；長連線；EOF 或 ConnectionResetError 即視為斷線 |
| 重連 | 固定 `reconnect_interval_s=5.0`；**無限重試**（FR-GW-004） |
| 頻率 | ~10 Hz per track（由上游決定；Gateway 純被動消費） |

---

## 2. Required JSON Fields（FR-GW-002）

每筆 JSON object MUST 含以下 10 個欄位：

| 欄位 | 型別 | 值域 |
| --- | --- | --- |
| `track_id` | string | e.g. `"TRK-001"`；非空 |
| `lat` | number | [-90, 90] |
| `lon` | number | [-180, 180] |
| `altitude_m` | number | 任意 float（HAE 公尺） |
| `velocity_ms` | number | ≥ 0 |
| `azimuth_deg` | number | [0, 360) |
| `elevation_deg` | number | [-90, 90] |
| `timestamp` | string | ISO 8601 UTC（含 `Z` 或 `+00:00`） |
| `track_status` | string | `"Active"` 或 `"Lost"`（**僅此二值**；Clarification §1） |
| `classification` | string | e.g. `"DRONE"`、`"UNKNOWN"` |

---

## 3. 欄位對應（JSON → UnifiedTrack）

```python
UnifiedTrack(
    source=TrackSource.ECHOSHIELD,
    track_id=msg["track_id"],
    radar_track_id=msg["track_id"],
    rf_track_id=None,
    correlation_id=None,
    lat=msg["lat"],
    lon=msg["lon"],
    alt_m=msg["altitude_m"],            # ← 命名對齊（altitude_m → alt_m）
    velocity_ms=msg["velocity_ms"],
    azimuth_deg=msg["azimuth_deg"],
    elevation_deg=msg["elevation_deg"],
    timestamp=parse_iso8601(msg["timestamp"]),
    received_at=datetime.now(tz=UTC),
    last_updated=datetime.now(tz=UTC),
    track_status=msg["track_status"],
    classification=msg["classification"],
    detection_status=None,
    drone_model=None,
    operator_lat=None,
    operator_lon=None,
)
```

---

## 4. 錯誤處理（FR-GW-002）

| 情況 | 處理 | 日誌 level | event name |
| --- | --- | --- | --- |
| 非 UTF-8 / 非 JSON | 跳過單筆 | ERROR | `invalid_json` |
| 缺必填欄位 | 跳過單筆 | ERROR | `invalid_wire_fields` |
| `lat`/`lon` 超出值域 | 跳過單筆 | WARNING | `invalid_wire_range` |
| `track_status` ∉ {Active, Lost} | 跳過單筆 | WARNING | `invalid_wire_enum` |
| TCP ConnectionRefusedError | 等 5 s 重試 | WARNING | `echoshield_disconnected` |
| TCP EOF / ConnectionResetError | 等 5 s 重試 | WARNING | `echoshield_disconnected` |

**鐵則**：任何**單筆**錯誤 MUST NOT 中止串流或關閉連線；Gateway 主程序 MUST NOT 因 adapter 失敗而退出
（FR-GW-024）。

---

## 5. 首見旗標（Gateway 的職責，非 wire 職責；Clarification §1）

**EchodyneAdapter MUST NOT** 從 wire 判斷「首見 vs 後續更新」。wire 上只有 `{Active, Lost}`，沒有 NEW /
UPDATED 概念。

「首見」語意由 Gateway 主程序以 `seen_uids: set[str]` 管理：

- 首次 enqueue 某 uid 的 CoT 時 → 加入 `seen_uids` + 記錄 INFO `track_first_seen`。
- Correlator TTL 回報 Lost 時 → 從 `seen_uids` 移除。
- Source 切換時 → 舊 uid 移除、新 uid 加入（雙訊息模式，見 `cot-xml.md §3`）。

Adapter 層**僅**負責 wire 解析與 enqueue，不知道 `seen_uids` 的存在。

---

## 6. Contract test 覆蓋（`tests/contract/test_echodyne_wire.py`）

1. ✅ 合法 JSON 10 欄位 → 產生正確 UnifiedTrack（`source=ECHOSHIELD`、`alt_m==altitude_m`）。
2. ✅ `track_status="Active"` / `"Lost"` 兩者皆通過；`"NEW"` / `"UPDATED"` / `"LOST"`（大寫）→ WARNING
   skip。
3. ✅ `lat=999` → WARNING skip；後續 JSON 正常處理（不中止）。
4. ✅ 缺 `track_id` → ERROR skip。
5. ✅ 非 JSON 文本（`"garbage"`） → ERROR skip；連線不關閉。
6. ✅ TCP 伺服器 EOF → 5 s 後重連；主程序不退出；日誌有 `echoshield_disconnected` WARNING + 重連後的
   `echoshield_connected` INFO。
7. ✅ EchodyneAdapter **未**設定 `seen_uids` 屬性；`track_first_seen` 事件由 process_loop 而非 adapter
   發出（反射 / log inspection 檢驗）。
