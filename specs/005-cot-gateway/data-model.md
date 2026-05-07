# Phase 1 Data Model: CoT Gateway

本檔描述 CoT Gateway 所有 runtime 實體（dataclasses / pydantic models / Enum / in-memory registry）。
所有實體皆存活於單一 asyncio event loop，**無持久化**；程序重啟 = 全部清空。

---

## 1. Enum: `TrackSource`

```python
class TrackSource(str, Enum):
    ECHOSHIELD = "ECHOSHIELD"   # 雷達單源（uid 前綴 ECHO-）
    SENTRYCS = "SENTRYCS"       # RF 單源（uid 前綴 SENTRYCS-）
    FUSED = "FUSED"             # 雷達 + RF 融合（uid 前綴 FUSED-，以 Sentrycs drone_id 為主鍵）
```

**Source 切換圖（同一實體生命週期可能經歷）**：

```
ECHOSHIELD ──(50m/3s 命中 RF)──► FUSED ──(RF 消失 > time_window)──► ECHOSHIELD
SENTRYCS   ──(50m/3s 命中雷達)──► FUSED ──(雷達 TTL 過期)──► SENTRYCS（或 Lost）
任一 source ──(track_status=Lost 或 TTL)──► 刪除 + stale=time 最終 CoT
```

每次 source 切換 process_loop MUST 對舊 uid 發 `stale=time` 最終 CoT，再發新 uid 首筆（FR-GW-014）。

---

## 2. Core: `UnifiedTrack`

跨模組流通的唯一航跡物件。dataclass（非 pydantic，性能優先；欄位驗證由 Adapter 層在解析時完成）。

```python
@dataclass
class UnifiedTrack:
    # --- 識別 ---
    source: TrackSource
    track_id: str                  # 內部主鍵；ECHOSHIELD=radar_track_id、SENTRYCS=rf_track_id、FUSED=f"FUSED-{rf_track_id}"
    radar_track_id: str | None = None   # e.g. "TRK-001"
    rf_track_id: str | None = None      # Sentrycs drone_id, e.g. "DRN-001"
    correlation_id: str | None = None   # FUSED 才有；= f"FUSED-{rf_track_id}"

    # --- 位置動態（融合時取雷達）---
    lat: float                     # [-90, 90]
    lon: float                     # [-180, 180]
    alt_m: float                   # HAE meters
    velocity_ms: float = 0.0
    azimuth_deg: float = 0.0       # course, [0, 360)
    elevation_deg: float = 0.0

    # --- 時間（皆 timezone-aware UTC）---
    timestamp: datetime            # sensor 端時戳（用於關聯時間窗；不進 CoT time）
    received_at: datetime          # Gateway 本機收到 message 的時戳
    last_updated: datetime         # TTL 基準；每次同 track_id 的更新都刷新

    # --- 狀態 ---
    track_status: Literal["Active", "Lost"] = "Active"      # 雷達生命週期（或 TTL 推導）
    classification: str = "UNKNOWN"                          # e.g. "DRONE"
    detection_status: Literal["DETECTED", "MITIGATING", "NEUTRALIZED"] | None = None  # 僅 SENTRYCS/FUSED

    # --- RF 才有 ---
    drone_model: str | None = None        # e.g. "DJI Mavic 3"
    operator_lat: float | None = None
    operator_lon: float | None = None
```

**不變性規則**：

- `source=ECHOSHIELD` → `radar_track_id` 必填、`rf_track_id` 與 `detection_status` 必為 None。
- `source=SENTRYCS` → `rf_track_id` 必填、`radar_track_id` 必為 None、`detection_status` 必填。
- `source=FUSED` → 兩者皆填、`detection_status` 必填、`correlation_id = f"FUSED-{rf_track_id}"`、位置欄
  取自雷達、model/operator/status 取自 RF。

---

## 3. Registry（TrackCorrelator 擁有）

```python
class TrackCorrelator:
    radar_tracks: dict[str, UnifiedTrack]   # key = radar_track_id（例 "TRK-001"）
    rf_tracks:    dict[str, UnifiedTrack]   # key = rf_track_id（例 "DRN-001"）
    fused_tracks: dict[str, UnifiedTrack]   # key = rf_track_id（與 rf_tracks 同 key 便於交叉查）
    distance_threshold_m: float = 50.0
    time_window_s: float = 3.0
    ttl_s: float = 10.0
```

**公開方法**（FR-GW-009 / 010 / 011 / 012 / 013）：

| 方法 | 契約 |
| --- | --- |
| `correlate(track) -> UnifiedTrack` | 依 `track.source` 分派；ECHO 入 `radar_tracks` 並找 RF 配對；SENTRYCS 入 `rf_tracks`（不主動與雷達配對，由下一筆 ECHO 觸發）；回傳原始或新建的 FUSED Track |
| `update_ttl(now) -> list[str]` | 回傳所有已標記 Lost 的 uid（供 process_loop 發最終 CoT + 從 seen_uids 移除） |
| `get_all_active_tracks() -> list[UnifiedTrack]` | 回傳所有 `track_status=Active` 的 Track（測試 / 監控用） |

**匹配演算法**（FR-GW-010）：

```
給定 radar_track R：
  候選 = { rf in rf_tracks.values()
           | rf.track_status == "Active"
             and haversine(R, rf) <= 50.0
             and abs((R.timestamp - rf.timestamp).total_seconds()) <= 3.0 }
  if 候選非空:
      best = min(候選, key=lambda rf: haversine(R, rf))
      return build_fused(radar=R, rf=best)
  else:
      return R  # 原樣回傳，不丟棄（FR-GW-012）
```

---

## 4. Gateway 主程序狀態

**`seen_uids: set[str]`**（process_loop 擁有）：

- 用途：判斷某 uid 是否首次出現（觸發 INFO `track_first_seen` 日誌；無副作用，僅觀測）。
- 新增：process_loop 首次 enqueue 該 uid 的 CoT 時。
- 移除：(a) Correlator `update_ttl` 回報 Lost 時；(b) source 切換時移除舊 uid（FR-GW-014）。

**`prev_uid_by_entity_key: dict[str, str]`**（process_loop 擁有；research §R5）：

- key：`radar:{radar_track_id}` 或 `rf:{rf_track_id}`。
- value：該實體上次 enqueue 的 uid。
- 用途：偵測 source 切換；每個 Track 可能對應 1–2 個 key（FUSED 同時含 radar_track_id + rf_track_id，兩個
  key 都更新）。

---

## 5. Queues

```python
track_queue: asyncio.Queue[UnifiedTrack]   # maxsize=1000，由兩個 adapter 餵入、process_loop 消費
cot_queue:   asyncio.Queue[str]            # maxsize=500，由 process_loop + ttl_loop 餵入、tak_sender 消費
```

**背壓策略**：

- `track_queue`：`put`（阻塞）；預算充足（20 s 緩衝）若塞滿代表下游嚴重異常。
- `cot_queue`：`put_nowait`；`QueueFull` → drop-newest + WARNING `queue_full_drop`（FR-GW-022）。

---

## 6. `CotEvent`

型別 = `str`（CoT 2.0 XML 字串）。不建 dataclass，因為 TakTransmitter 只需要 bytes 寫入 socket；CotGenerator
為純函式 `UnifiedTrack -> str`。

XML 結構見 `contracts/cot-xml.md`。

---

## 7. `TakConnection`（TakTransmitter 內部）

```python
class TakTransmitter:
    _reader: asyncio.StreamReader | None
    _writer: asyncio.StreamWriter | None
    _cot_queue: asyncio.Queue[str]
    _connected: asyncio.Event
    _retry_count: int
    _ssl_context: ssl.SSLContext        # 啟動時載入 gateway.p12
    _config: TakServerConfig
```

**狀態機**：

```
DISCONNECTED ──(_connect_with_retry 成功)──► CONNECTED
CONNECTED ──(ConnectionResetError/BrokenPipeError)──► DISCONNECTED ──(退避 1→2→4→…→60s)──►
DISCONNECTED ──(retry_count == max_retries=5)──► FATAL（raise → Gateway exit code != 0）
```

---

## 8. `GatewayConfig`（pydantic v2，root model）

見 `research.md §R8` 的 YAML schema。pydantic validator 關鍵檢查（config.py fail-fast）：

- `echoshield.port` ∈ (0, 65535]、`sentrycs.port` 同、`tak_server.port` 同；
- `correlator.distance_threshold_m > 0`、`time_window_s > 0`、`ttl_s > 0`；
- `tak_server.cert_file` 存在（os.path.exists）；若 `use_ssl=true` 必填；
- `tak_server.max_retries >= 1`、`backoff_initial_s <= backoff_cap_s`；
- `logging.level` ∈ {DEBUG, INFO, WARNING, ERROR}。

任一驗證失敗 → pydantic `ValidationError`，Gateway exit code = 2。

---

## 9. 欄位命名對齊速查（Edge Case §10）

| 概念 | EchoShield JSON | Sentrycs JSON | `UnifiedTrack` | CoT XML |
| --- | --- | --- | --- | --- |
| 高度 | `altitude_m` | `alt_m` | `alt_m` | `<point hae="…">` |
| 速度 | `velocity_ms` | —（無） | `velocity_ms` | `<track speed="…">` |
| 航向 | `azimuth_deg` | —（無） | `azimuth_deg` | `<track course="…">` |
| sensor 時戳 | `timestamp` | `timestamp` | `timestamp` | —（不進 CoT；CoT time 為 Gateway 當下時間） |
| 生命週期 | `track_status` ∈ {Active,Lost} | —（由 SENTRYCS detection_status 生命週期推導） | `track_status` | 影響 `stale` |
| RF 處置狀態 | — | `status` ∈ {DETECTED,MITIGATING,NEUTRALIZED} | `detection_status` | 影響 `<remarks>` 與 `stale`(NEUTRALIZED=30s) |
| 型號 | —（只有 classification） | `model` | `drone_model` | `<remarks>` Model: 段 |

---

## 10. Runtime 狀態總覽（ASCII）

```
┌───────────────────────────────────────────────────────────────────┐
│                         CoT Gateway Process                       │
│                                                                   │
│  EchodyneAdapter ──enqueue──►  track_queue  ──dequeue──► process  │
│  SentrycsAdapter ──enqueue──►   (1000)                    _loop   │
│                                                             │     │
│                                TrackCorrelator ◄────────────┤     │
│                                 radar_tracks                │     │
│                                 rf_tracks                   │     │
│                                 fused_tracks                │     │
│                                                             ▼     │
│                                                       CotGenerator │
│                                                             │     │
│  ttl_loop (1Hz) ──Lost uids──►  process_loop ──enqueue──► cot_queue│
│                                      │                       (500) │
│                                seen_uids                       │   │
│                                prev_uid_by_entity_key          ▼   │
│                                                           tak_sender│
│                                                                │   │
│                                                             SSL+TCP │
│                                                                ▼   │
│                                                          TAK :18089 │
└───────────────────────────────────────────────────────────────────┘
```
