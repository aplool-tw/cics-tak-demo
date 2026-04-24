# Contract: Sentrycs Poller（Gateway 上游消費端）

本契約定義 CoT Gateway 的 `SentrycsAdapter` 如何以 HTTP 1 Hz 輪詢 Sentrycs Simulator 的 Status API。

**上游權威 schema**：[`specs/004-sentrycs-sim/contracts/http-status-api.md`](../../004-sentrycs-sim/contracts/http-status-api.md)。
本檔僅定義 Gateway 側的**消費規則**（輪詢策略、欄位對應、錯誤處理），不重新定義 API schema 本身；
API schema 若變更以 004 為準。

---

## 1. Transport

| 項目 | 值 |
| --- | --- |
| 協議 | HTTP/1.1（明文，無 TLS；PoC 內網） |
| 端點 | `GET http://{sentrycs.host}:{sentrycs.port}/detections`，預設 `http://sentrycs-sim:7070/detections` |
| 輪詢頻率 | 1 Hz（`poll_interval_s=1.0`；FR-GW-005） |
| Timeout | `timeout_s=2.0`（低於 poll_interval 以免堆積） |
| Client | `aiohttp.ClientSession`（單例，整個 Gateway 生命週期） |
| Content-Type 接受 | `application/json` |

---

## 2. Response Shape（上游契約摘要；權威見 004）

```json
[
  {
    "uid": "DRN-001",
    "lat": 25.0598,
    "lon": 121.5654,
    "alt_m": 101.0,
    "model": "DJI Mavic 3",
    "status": "DETECTED",
    "is_landed": false,
    "operator_lat": 25.0589,
    "operator_lon": 121.5661,
    "operator_distance_m": 120.0,
    "operator_bearing_deg": 45.0,
    "timestamp": "2026-04-24T12:34:56.789Z",
    "takeover_sent": false,
    "sensor_id": "SNTRX-01"
  },
  ...
]
```

- 空陣列 `[]` 合法（IDLE 無偵測）；HTTP 200，**非** 404（004 FR-SC-016 保證）。
- `status` ∈ `{DETECTED, MITIGATING, NEUTRALIZED}`（IDLE 不在回傳中）。
- Gateway **不使用**：`is_landed`、`operator_distance_m`、`operator_bearing_deg`、`takeover_sent`、
  `sensor_id`（僅 Sentrycs 內部 / 其他下游感興趣）。

---

## 3. 欄位對應（JSON → UnifiedTrack）

```python
UnifiedTrack(
    source=TrackSource.SENTRYCS,
    track_id=d["uid"],
    radar_track_id=None,
    rf_track_id=d["uid"],                       # Sentrycs uid == drone_id
    correlation_id=None,
    lat=d["lat"],
    lon=d["lon"],
    alt_m=d["alt_m"],                           # ← 命名對齊（alt_m 與 UnifiedTrack 同名）
    velocity_ms=0.0,                            # Sentrycs 不提供速度
    azimuth_deg=0.0,                            # 不提供
    elevation_deg=0.0,                          # 不提供
    timestamp=parse_iso8601(d["timestamp"]),
    received_at=datetime.now(tz=UTC),
    last_updated=datetime.now(tz=UTC),
    track_status="Active",                      # Sentrycs 無 Lost 概念；老化由 Correlator TTL 推導
    classification="DRONE",                     # 固定
    detection_status=d["status"],               # DETECTED/MITIGATING/NEUTRALIZED
    drone_model=d["model"],
    operator_lat=d["operator_lat"],
    operator_lon=d["operator_lon"],
)
```

---

## 4. 錯誤處理（FR-GW-007 / FR-GW-008）

| 情況 | 處理 | 日誌 level | event name |
| --- | --- | --- | --- |
| HTTP 200 + 空陣列 `[]` | 跳過（不清 `rf_tracks`；老化交 TTL） | DEBUG | `sentrycs_empty` |
| HTTP 200 + 陣列 | 對每筆轉 UnifiedTrack → enqueue `track_queue` | INFO (throttled) | `sentrycs_poll` |
| HTTP 4xx | skip 本次、下秒重試 | WARNING | `sentrycs_poll_failed` |
| HTTP 5xx | skip 本次、下秒重試 | WARNING | `sentrycs_poll_failed` |
| `aiohttp.ClientConnectionError` / timeout | skip 本次、下秒重試 | WARNING | `sentrycs_poll_failed` |
| JSON 解析失敗 / schema 不合 | skip 本次、下秒重試 | WARNING | `sentrycs_poll_failed` |

**隔離原則**：SentrycsAdapter 任何錯誤 MUST NOT 影響 EchodyneAdapter / TakTransmitter。

---

## 5. 輪詢時序（固定週期、非 drift）

```python
async def run(self):
    while not self._stop.is_set():
        tick_start = time.monotonic()
        try:
            detections = await self._fetch()
            for d in detections:
                self.track_queue.put_nowait(self._to_unified_track(d))
        except Exception as e:
            self._log.warning("sentrycs_poll_failed", error=str(e))
        elapsed = time.monotonic() - tick_start
        await asyncio.sleep(max(0.0, self.poll_interval_s - elapsed))
```

- 若處理耗時 > `poll_interval_s`（不應發生於 PoC），下一 tick 立即執行（不 skip、不堆積）。
- 若 `track_queue.put_nowait` 拋 `QueueFull` → 該筆 drop + WARNING（理論上 `track_queue=1000` 不會滿）。

---

## 6. Contract test 覆蓋（`tests/contract/test_sentrycs_poller.py`）

1. ✅ Stub 回 `[]` → 不產生 UnifiedTrack；無 ERROR 日誌；Gateway 持續輪詢。
2. ✅ Stub 回 2 筆偵測 → enqueue 2 個 UnifiedTrack，欄位對應正確（`detection_status` from `status`、
   `drone_model` from `model`）。
3. ✅ Stub 回 HTTP 503 → skip、WARNING；下秒恢復後正常。
4. ✅ Stub 連線 refused → WARNING；EchoShield 資料流不受影響（檢查另一 adapter 仍在 enqueue）。
5. ✅ Stub 回非法 JSON → WARNING skip。
6. ✅ 1 Hz tick 穩定：5 秒內收到 5 次 poll（freezegun + tick 斷言）。
7. ✅ 輪詢處理時間 > 1 s（stub 延遲 1.5 s）不會造成並行重疊請求（單一 in-flight）。
