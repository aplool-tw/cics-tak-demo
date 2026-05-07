# Contract: CoT 2.0 XML（Gateway 對外輸出）

本契約定義 CoT Gateway 產出並送往 TAK Server 的 MIL-STD-2525C / CoT 2.0 XML schema。
凍結此契約後，任何變更須同步更新 `contracts/tak-uplink.md`、integration test、以及 08-api-icd.md §4。

---

## 1. Wire format

- 字元集：UTF-8（無 BOM）。
- 每筆 CoT XML 後接 `\n`（0x0A）分隔符，無 length-prefix（FR-GW-020）。
- 單筆事件結構：單一 `<event>` root；是否含 `<?xml?>` 宣告頭由 `tak_server.xml_declaration` 設定控制（預設 `false` = 無宣告頭，較簡潔；設為 `true` 則前綴 `<?xml version='1.0' encoding='UTF-8' standalone='yes'?>` 以符合 ATAK/WinTAK 等真實 TAK Server 的期望）。

---

## 2. XML Schema

```xml
<event version="2.0"
       uid="{UID}"
       type="{TYPE}"
       time="{ISO8601_MS_Z}"
       start="{ISO8601_MS_Z}"
       stale="{ISO8601_MS_Z}"
       how="m-g">
  <point lat="{LAT}" lon="{LON}" hae="{HAE}" ce="10.0" le="5.0"/>
  <detail>
    <uid Droid="{UID}"/>
    <contact callsign="{UID}"/>
    <remarks>{REMARKS_STRING}</remarks>
    <track speed="{VELOCITY_MS}" course="{AZIMUTH_DEG}"/>
  </detail>
</event>
```

**欄位說明**：

| 屬性 / 節點 | 型別 | 規則 |
| --- | --- | --- |
| `version` | 字串 | 固定 `"2.0"` |
| `uid` | 字串 | 依 §3；與 `<uid Droid>` 及 `<contact callsign>` 相同（ATAK 合規） |
| `type` | 字串 | 依 §4；同一 source 生命週期固定 |
| `time` | ISO 8601 UTC 毫秒 | Gateway 產 CoT 當下 `datetime.now(timezone.utc)`，格式 `YYYY-MM-DDTHH:MM:SS.sssZ` |
| `start` | 同上 | 等於 `time` |
| `stale` | 同上 | 依 §5 三段式計算 |
| `how` | 字串 | 固定 `"m-g"`（machine-generated） |
| `<point lat lon>` | float, 6 位小數以上 | 自 UnifiedTrack |
| `<point hae>` | float, 1 位小數 | UnifiedTrack.alt_m（FR-GW-003 EchoShield altitude_m → alt_m → hae） |
| `<point ce>` | 固定 `10.0` | 水平誤差圓（公尺），PoC 統一 |
| `<point le>` | 固定 `5.0` | 線性誤差（公尺），PoC 統一 |
| `<uid Droid>` | 字串 | `<detail>` 首子元素；值等於 `event.uid`；ATAK 顯示名稱標準欄位 |
| `<contact callsign>` | 字串 | 等於 uid |
| `<remarks>` | 字串 | 依 §6 組合；XML entity escape（`<>&"'`）必須套用 |
| `<track speed>` | float, 1 位小數 | UnifiedTrack.velocity_ms |
| `<track course>` | float, 1 位小數 | UnifiedTrack.azimuth_deg |

---

## 3. UID 規則（FR-GW-014）

| Source | UID 模板 | 範例 |
| --- | --- | --- |
| `ECHOSHIELD` | `ECHO-{radar_track_id}` | `ECHO-TRK-001` |
| `SENTRYCS` | `SENTRYCS-{rf_track_id}` | `SENTRYCS-DRN-001` |
| `FUSED` | `FUSED-{rf_track_id}` | `FUSED-DRN-001` |

**Source 切換**（同一實體 uid 前綴改變時）：Gateway MUST 發雙訊息：

1. 對**舊 uid** 發 `stale=time` 的最終 CoT（清 ATAK 舊圖示）；
2. 對**新 uid** 發首筆 CoT（含當下完整資訊）；
3. `seen_uids` 集合移除舊 uid、加入新 uid。

---

## 4. Type 規則（FR-GW-015，**生命週期固定，不隨狀態切換**）

| Source | Type | ATAK 顏色 |
| --- | --- | --- |
| `ECHOSHIELD` | `a-u-A-M-F-Q-r` | 灰色（Unknown, Air） |
| `SENTRYCS` | `a-u-A-M-F-Q-r` | 灰色（Unknown, Air — 尚未融合確認） |
| `FUSED` | `a-h-A-M-F-Q-r` | 紅色（Hostile, Air） |

**禁止**在 `type` 上編碼 `detection_status` 或 `track_status`；狀態差異只透過 `<remarks>` 與 `stale` 表達。

---

## 5. Stale 規則（FR-GW-017，三段式 + 優先級）

以 `time` 為基準計算 `stale`：

| 優先級 | 條件 | `stale - time` | 語意 |
| --- | --- | --- | --- |
| (a) 最高 | `track_status == "Lost"`（含 TTL 推導） | `0 s` | `stale = time`，ATAK 立即老化移除 |
| (b) | `detection_status == "NEUTRALIZED"` | `+30 s` | 對齊 Sentrycs 30 s 保留期 |
| (c) 預設 | 其他（Active、DETECTED、MITIGATING） | `+11 s` | TTL 10 s + 1 s 緩衝 |

規則 (a) > (b) > (c)。

**毫秒誤差容忍**：SC-GW-012 要求 `(stale - time) - expected` ≤ 1 ms；因 Gateway 以單次
`datetime.now(timezone.utc)` 同時算出 `time` 與 `stale`，實務誤差為 0 ms。

---

## 6. Remarks 組合規則（FR-GW-018）

依資料可用性拼接字串，缺欄位則整段省略：

```
Source: {src} | Model: {drone_model} | Status: {detection_status} | Speed: {v:.1f}m/s | Alt: {alt:.0f}m
```

- `{src}`：`ECHOSHIELD` / `SENTRYCS` / `FUSED`（永遠存在）；
- `Model:` 段：僅 `drone_model is not None` 時輸出；
- `Status:` 段：僅 `detection_status is not None` 時輸出；
- `Speed:` / `Alt:` 段：永遠存在（UnifiedTrack 必填，值可為 0）。

**XML 字元逸出**：`drone_model` 或 `remarks` 內部若出現 `< > & " '`，MUST 由 `xml.etree.ElementTree`
自動逸出（設值 via `Element.text`，非字串拼接）。PoC 期間型號為白名單（`DJI Mavic 3` 等），但實作預留。

---

## 7. 合規矩陣（SC-GW-012 — 8 類場景 100% 合規）

| 場景 | Source | detection_status | track_status | UID 前綴 | Type | stale - time |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | ECHOSHIELD | — | Active | `ECHO-` | `a-u-A-M-F-Q-r` | 11 s |
| 2 | ECHOSHIELD | — | Lost | `ECHO-` | `a-u-A-M-F-Q-r` | 0 s |
| 3 | SENTRYCS | DETECTED | Active | `SENTRYCS-` | `a-u-A-M-F-Q-r` | 11 s |
| 4 | SENTRYCS | MITIGATING | Active | `SENTRYCS-` | `a-u-A-M-F-Q-r` | 11 s |
| 5 | SENTRYCS | NEUTRALIZED | Active | `SENTRYCS-` | `a-u-A-M-F-Q-r` | 30 s |
| 6 | FUSED | DETECTED | Active | `FUSED-` | `a-h-A-M-F-Q-r` | 11 s |
| 7 | FUSED | MITIGATING | Active | `FUSED-` | `a-h-A-M-F-Q-r` | 11 s |
| 8 | FUSED | NEUTRALIZED | Active | `FUSED-` | `a-h-A-M-F-Q-r` | 30 s |

Contract test (`tests/contract/test_cot_xml_schema.py`) 以此表 parameterize 100 筆隨機樣本斷言。

---

## 8. 範例

### 8.1 ECHOSHIELD / Active

```xml
<event version="2.0" uid="ECHO-TRK-001" type="a-u-A-M-F-Q-r"
       time="2026-04-24T12:34:56.789Z" start="2026-04-24T12:34:56.789Z"
       stale="2026-04-24T12:35:07.789Z" how="m-g">
  <point lat="25.0598" lon="121.5654" hae="101.0" ce="10.0" le="5.0"/>
  <detail>
    <uid Droid="ECHO-TRK-001"/>
    <contact callsign="ECHO-TRK-001"/>
    <remarks>Source: ECHOSHIELD | Speed: 12.5m/s | Alt: 101m</remarks>
    <track speed="12.5" course="45.0"/>
  </detail>
</event>
```

### 8.2 FUSED / NEUTRALIZED

```xml
<event version="2.0" uid="FUSED-DRN-001" type="a-h-A-M-F-Q-r"
       time="2026-04-24T12:35:26.123Z" start="2026-04-24T12:35:26.123Z"
       stale="2026-04-24T12:35:56.123Z" how="m-g">
  <point lat="25.0601" lon="121.5655" hae="95.0" ce="10.0" le="5.0"/>
  <detail>
    <uid Droid="FUSED-DRN-001"/>
    <contact callsign="FUSED-DRN-001"/>
    <remarks>Source: FUSED | Model: DJI Mavic 3 | Status: NEUTRALIZED | Speed: 3.2m/s | Alt: 95m</remarks>
    <track speed="3.2" course="180.0"/>
  </detail>
</event>
```

### 8.3 Source 切換（ECHO → FUSED）雙訊息

```xml
<!-- T0：舊 uid 最終 CoT（清場），stale=time -->
<event version="2.0" uid="ECHO-TRK-001" type="a-u-A-M-F-Q-r"
       time="2026-04-24T12:35:10.456Z" start="2026-04-24T12:35:10.456Z"
       stale="2026-04-24T12:35:10.456Z" how="m-g">
  <point lat="25.0600" lon="121.5654" hae="98.0" ce="10.0" le="5.0"/>
  <detail>
    <uid Droid="ECHO-TRK-001"/>
    <contact callsign="ECHO-TRK-001"/>
    <remarks>Source: ECHOSHIELD | Speed: 8.0m/s | Alt: 98m</remarks>
    <track speed="8.0" course="90.0"/>
  </detail>
</event>

<!-- T0 + ε：新 uid 首筆 -->
<event version="2.0" uid="FUSED-DRN-001" type="a-h-A-M-F-Q-r"
       time="2026-04-24T12:35:10.457Z" start="2026-04-24T12:35:10.457Z"
       stale="2026-04-24T12:35:21.457Z" how="m-g">
  <point lat="25.0600" lon="121.5654" hae="98.0" ce="10.0" le="5.0"/>
  <detail>
    <uid Droid="FUSED-DRN-001"/>
    <contact callsign="FUSED-DRN-001"/>
    <remarks>Source: FUSED | Model: DJI Mavic 3 | Status: DETECTED | Speed: 8.0m/s | Alt: 98m</remarks>
    <track speed="8.0" course="90.0"/>
  </detail>
</event>
```
