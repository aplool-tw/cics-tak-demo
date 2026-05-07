# Phase 0 Research: Sentrycs Simulator

## R1. HTTP Status API framework 選型

**Decision**: 使用 `aiohttp.web`（與 Client 同一套 `aiohttp`）起 :17070 JSON API。

**Rationale**:

- 既有 runtime 依賴 `aiohttp>=3.9`（必須用來查 Map Sim 與呼叫 UDS）；以同一套 framework 起對外 server 可
  **零新增依賴**，守 G7（依賴最小化）。
- 單進程 async 事件迴圈內 Client + Server 共用同一 `asyncio` loop，不必多跑一個 ASGI server（uvicorn/hypercorn），
  啟動時間更短（助 SC-SC-011 < 2 s 就緒）。
- `aiohttp.web` 原生支援 graceful shutdown（`runner.cleanup()`），與 SIGINT handler 串接可於 3 s 內結束
  （SC-SC-012）。
- 5 並發 Client 以 1 Hz 輪詢的壓力極低（本質為 in-memory snapshot dict 序列化），`aiohttp.web` 完全足以達成
  p95 < 100 ms（SC-SC-003）。

**Alternatives considered**:

- **FastAPI + uvicorn**：功能強、自動 OpenAPI；但新增 2 個重量級依賴（FastAPI、uvicorn、Starlette），與
  PoC 規模不相稱；啟動時間較長；需另一 event loop 管理。違反 G7。
- **Flask**：同步 framework，要與 async Map Sim Client / UDS Client 共用狀態需加 thread-safe lock，
  複雜度反而上升。
- **stdlib `http.server`**：太低階，需自己做 async；不划算。

## R2. Scenario YAML schema 與 fail-fast 校驗策略

**Decision**: 以 `pydantic v2 BaseModel`（`extra="forbid"`）定義 `SentrycsConfig` + `DroneScenario`，YAML
以 `pyyaml.safe_load` 讀入後直接 `model_validate`；所有跨欄位校驗（時序、operator_distance_m 範圍、uid 唯一性）
以 `@model_validator(mode="after")` 一次完成。發現任一違反即丟 `ValueError` → `cli.py` catch 後以 exit code 2 與
結構化 error log 結束。

**Rationale**:

- 直接使用 spec `FR-SC-021` 要求的「載入失敗 fail fast 且回報具名錯誤」；pydantic 的錯誤已自帶 `loc` 路徑。
- `extra="forbid"` 保證 scenario YAML 不接受未知欄位（避免 typo 默默失效）。
- `@model_validator` 可同時做：
  - `detected_at_s <= mitigating_at_s <= neutralized_at_s`
  - `200 <= operator_distance_m <= 500`
  - `0 <= operator_bearing_deg < 360`
  - `uid` 在 drones[] 中 unique
  - `sensor_lat/sensor_lon` 值域
- 與 `services/echoshield-sim/src/echoshield_sim/config.py` 的 YAML 載入模式一致（G5）。

**Alternatives considered**:

- **dataclasses + 手寫校驗**：要多寫 ~80 行 try/except，且錯誤訊息不如 pydantic 一致。
- **jsonschema**：校驗力強但需另一份 schema 檔，失同步風險；留給 **contract 測試**用來凍結 wire schema 即可，
  不在 runtime 再走一次。

## R3. WGS84 operator 位置推算（destination formula）

**Decision**: 手寫 15 行 WGS84 direct/destination formula（球面近似即可，200–500 m 範圍誤差 < 1 m 遠小於
SC-SC-004 要求），在 `DroneTrack` 初次由 `IDLE` 建立時（即首次從 Map Sim 看到該 `uid`）**計算一次並固定**
存入 `OperatorEstimate`，後續所有 `/detections` 輸出直接 echo，不再重算。

公式（以半徑 R=6378137 m 的球形地球為基準；方位角 `θ` 以正北為 0、順時針增加）：

```python
import math
R = 6_378_137.0  # WGS84 equatorial radius, m
def destination_point(lat_deg, lon_deg, bearing_deg, distance_m):
    phi1 = math.radians(lat_deg)
    lam1 = math.radians(lon_deg)
    theta = math.radians(bearing_deg)
    delta = distance_m / R
    phi2 = math.asin(math.sin(phi1) * math.cos(delta)
                     + math.cos(phi1) * math.sin(delta) * math.cos(theta))
    lam2 = lam1 + math.atan2(math.sin(theta) * math.sin(delta) * math.cos(phi1),
                             math.cos(delta) - math.sin(phi1) * math.sin(phi2))
    return math.degrees(phi2), (math.degrees(lam2) + 540) % 360 - 180
```

**Rationale**:

- 200–500 m 下球形近似誤差 < 0.3 m，遠小於 SC-SC-004 的「< 1 m」要求。
- 避免引入 `geopy`（雖然 spec Assumptions 列它「可用」）以守 G7；`geopy.distance.distance(...).destination(...)`
  內部走 Karney geodesic，精度遠超需求、依賴卻多 1 個。
- **一次計算、永久鎖定**策略直接滿足 SC-SC-004（抖動 = 0）——不論浮點重算多少次都取同一個 dict 欄位。

**Alternatives considered**:

- `geopy.distance`：精度過剩；新依賴。
- Vincenty direct formula：200–500 m 不必要；複雜度上升。

## R4. 狀態機與 per-drone task 架構

**Decision**: 主 `loop` 每 0.5 s（2 Hz）查一次 Map Sim，將結果以 `uid` 分派到 per-drone `StateMachine`；
每架無人機擁有**獨立** `asyncio.Task` 處理其 `/command/takeover` I/O，主迴圈不會因單架 takeover 阻塞。

- 狀態資料在主 loop 的 `DroneRegistry`（dict[str, DroneTrack]）中集中管理；per-drone task 僅負責 takeover I/O。
- `DroneTrack` 的每次讀寫都在同一 event loop 上，無需鎖。
- `/detections` handler 走 `asyncio.Lock` 或「取即時快照 + `list(registry.values())`」原子複製，確保 5 並發
  請求取得一致快照（FR-SC-018）。

**Rationale**:

- 滿足 FR-SC-023「多架並行、互不阻塞」與 Edge Case「單目標處理逾時不得拖慢其他目標的 1 Hz 輸出」。
- 單 event loop 設計避免 asyncio.Lock / threading.Lock 複雜度。

**Alternatives considered**:

- 每架無人機獨立 loop / thread：記憶體浪費，測試難。
- 全同步迴圈：takeover HTTP 阻塞整個迴圈，違反「互不阻塞」。

## R5. Map Sim 退避與狀態保留

**Decision**: `mapsim.client.MapSimClient` 包一層 `fetch_objects_with_retry()`，採用指數退避
`1s → 2s → 4s → 10s`（達到 10s 後維持 10s）；在失敗期間主 loop **不觸發任何狀態轉移**，`DroneTrack`
保留上次 `(lat, lon, alt_m, status, timestamp)`；恢復後以最新值覆寫。

**Rationale**:

- 直接對應 FR-SC-009 + SC-SC-007：Map Sim 下線 30 s 期間 Sentrycs 不崩潰、`/detections` 持續回應、
  恢復後 ≤ 1 s 追上最新位置。
- 退避以「自上次成功查詢起算」為單位，不影響 2 Hz 節奏（成功後立即恢復 0.5 s 週期）。

**Alternatives considered**:

- 線性退避：對測試 freezegun 友善但不符常見實務。
- Circuit breaker：對本 PoC 過度設計。

## R6. UDS 409 / 400 / 404 處理

**Decision**:

| UDS Response | Sentrycs 行為 | `TakeoverResult` |
| --- | --- | --- |
| `200` | 轉入 `MITIGATING`，`takeover_sent=True` | `accepted` |
| `409` | **視為成功**，轉入 `MITIGATING`，`takeover_sent=True` | `already_taken_over` |
| `400` | 保留 `DETECTED`，`takeover_sent=True`（**不重送**） | `rejected_bad_request` |
| `404` | 保留 `DETECTED`，`takeover_sent=True`（**不重送**） | `rejected_not_found` |
| timeout / 5xx / connection error | 保留 `DETECTED`，`takeover_sent=False`（**下一輪迴圈會重試**一次） | `failed_transport` |

**Rationale**:

- `200/409` 同義成功：對齊 FR-SC-011、SC-SC-008，且 `specs/001-uds/contracts/rest-api.md §1.2` 明確
  定義 `409 already_taken_over`。
- `400/404` 屬「請求本身不合理」，重送只會重複失敗；Edge Case 明確要求「不重送以避免與真實場景差異擴大」。
- transport 失敗（非 HTTP 層）不視為請求已送達，允許 **下一個 tick** 重試一次——但若 `mitigating_at_s` 時
  窗已過一定秒數（例如 > 5 s）仍視為失敗；此細節放到 tasks 階段細化。
- `takeover_sent=True` 的 latch 確保同一目標絕對不送第二次（FR-SC-010）。

## R7. `/detections` wire schema 凍結來源

**Decision**: 對外 JSON schema 以 `contracts/http-status-api.md` 凍結；`src/sentrycs_sim/models/detection.py`
的 `DetectionResponse` pydantic model **必須** bit-by-bit 一致；contract 測試以 JSON schema（手寫 JSON 檔或
`DetectionResponse.model_json_schema()` 快照）驗證真實回應。

14 個欄位（FR-SC-016）：

- 識別：`uid`（string）、`model`（string；"Unknown" 允許）
- 狀態：`detection_status`（enum: `DETECTED` / `MITIGATING` / `NEUTRALIZED`）、`is_landed`（bool）
- 無人機位置：`lat`、`lon`、`alt_m`、`velocity_ms`、`azimuth_deg`
- 操控者位置：`operator_lat`、`operator_lon`、`operator_distance_m`、`operator_bearing_deg`
- 時間：`timestamp`（ISO 8601 UTC with `Z`）

**Rationale**:

- 直接對應 FR-SC-016；`IDLE` 目標不輸出（FR-SC-014）。
- `timestamp` 以 `Z` 結尾與 Map Sim / UDS 對外契約一致（`specs/002-map-sim/contracts/rest-api.md §1.1`）。

## R8. 測試時間控制

**Decision**: integration / state machine 單元測試使用 `freezegun.freeze_time`（同步模式）+ 手動
`asyncio.sleep(0)` 驅動事件迴圈；Map Sim Client 的退避 sleep 以可注入的 `sleep: Callable[[float], Awaitable[None]]`
參數取代直接 `asyncio.sleep`，測試時注入 fake。

**Rationale**:

- `freezegun` 不攔截 `asyncio.sleep`；用可注入 sleep 可讓 30 s 退避測試在 < 1 ms 跑完。
- 與 `services/echoshield-sim` 相同做法，守 G5。

## R9. 優雅關閉順序

**Decision**: SIGINT/SIGTERM 觸發 `asyncio.Event`；主迴圈與所有 per-drone tasks 監聽該 event。關閉序列：

1. 停止 aiohttp.web Runner（`runner.cleanup()`）——拒絕新連線、等現有 response 結束。
2. Cancel 所有 per-drone tasks + Map Sim 輪詢 task（`asyncio.gather(..., return_exceptions=True)` 收尾）。
3. 關閉 Map Sim / UDS `ClientSession`。
4. 以 `asyncio.wait_for(..., timeout=3.0)` 包住整個序列；逾時則 hard exit。

**Rationale**:

- 對應 FR-SC-025 + SC-SC-012「3 s 內結束、無懸掛連線」。

## R10. 日誌欄位凍結

**Decision**: `--verbose` 下關鍵 event 與欄位：

| event | 關鍵欄位 |
| --- | --- |
| `state_transition` | `uid`, `from`, `to`, `reason`, `timestamp` |
| `mapsim_query` | `count`, `latency_ms`, `backoff_s`（失敗時）|
| `mapsim_unavailable` | `error`, `retry_in_s`（節流為每次退避週期 1 筆）|
| `takeover_request` | `uid`, `drone_id`, `target_lat`, `target_lon`, `target_alt_m` |
| `takeover_response` | `uid`, `http_status`, `result`（`accepted` / `already_taken_over` / …）, `latency_ms` |
| `operator_locked` | `uid`, `operator_lat`, `operator_lon`, `bearing_deg`, `distance_m` |
| `unregistered_uid` | `uid`（以 WARN/ERROR level）|
| `http_request` | `method`, `path`, `status`, `latency_ms` |
| `shutdown` | `signal`, `duration_ms` |

**Rationale**:

- 對應 SC-SC-010（每次狀態轉移 / takeover / Map Sim 錯誤皆 1 筆結構化日誌含 `uid`、舊狀態、新狀態、時間戳）。
- `mapsim_unavailable` 節流為每退避週期 1 筆，避免在 30 s 下線期間灌爆日誌。

---

**所有 NEEDS CLARIFICATION 已解決**：

- `model` 欄位來源：spec Clarifications Session 2026-04-24 已決議由場景 YAML 每架必填 `model` 提供。
- Map Sim / UDS wire schema：已凍結於 `specs/002-map-sim/contracts/rest-api.md` §3.2 / `specs/001-uds/contracts/rest-api.md` §1。
- 查詢頻率：2 Hz（對應 FR-SC-006 明文「每 0.5 秒」，落在使用者要求的 1–2 Hz 區間）。
- 操控者計算：手寫 WGS84 destination formula（R3），200–500 m 範圍精度充足。
