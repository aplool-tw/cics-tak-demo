# Phase 0 Research: EchoShield Simulator

**Feature**: `003-echoshield-sim`
**Date**: 2026-04-24
**Status**: Complete — 無遺留 NEEDS CLARIFICATION（spec §Clarifications 已於 2026-04-24 決議
track grace window 與 noise seed；Technical Context 由使用者直接提供，無待解項）。

## Unknowns 檢查

Spec 與 Technical Context 中的項目全部已解。以下紀錄為「關鍵決策 + 為何是這個」，以供 Phase 1 與
後續 implementation 的依據。

---

## R1：10 Hz 主迴圈 + 單 in-flight 查詢策略

- **Decision**：使用 `asyncio` + 一個 `asyncio.Task` 作為 tick scheduler；每 100ms 以
  `loop.call_at(next_deadline, …)` 觸發，**不**使用 `asyncio.sleep(0.1)` 累加。以 `asyncio.Lock`
  或 `in_flight: bool` flag 實作「同時最多一個 Map Sim 請求」：若上一 tick 的 HTTP 仍在飛，當
  tick 直接 `tick_overrun` 事件並跳過該輪（FR-ES-004）。
- **Rationale**：
  - `call_at(deadline)` 可吸收單輪抖動、避免 `sleep` 累加漂移（10 Hz 運行 1h 不漂移 > 幾 ms）。
  - Flag 比 `asyncio.Semaphore(1) + try_lock` 簡單，行為可測（`pytest-asyncio + freezegun`）。
- **Alternatives considered**：
  - `anyio` / `trio`：不必要，map-sim 與 uds 也僅用 stdlib asyncio，保持一致。
  - 獨立 `threading.Thread` 做 HTTP：違反 async-first；會讓 broadcast fan-out 多一層鎖。
  - `aiojobs`：額外依賴，本場景只有 1 個背景任務，不需要。

## R2：aiohttp ClientSession 與 Map Sim 查詢 timeout

- **Decision**：整個進程 lifetime 單一 `aiohttp.ClientSession`（在 main 建立、shutdown 關閉），
  `GET /objects` 以 `ClientTimeout(total=1.0)`；連線 reuse keep-alive。URL 參數序列化依賴
  aiohttp 的 `params=` 機制（dict），避免手工拼接。
- **Rationale**：
  - 單一 session 復用 TCP 連線，本機環境下查詢 overhead <1ms，達 SC-ES-002 p95 ≤ 10ms。
  - `total=1.0s` 滿足 FR-ES-003，與 FR-ES-001 的 100ms tick 間隔搭配時，最多占用 10 個 tick；
    實務上本機通常 <5ms，不會造成 overrun。
- **Alternatives considered**：
  - `httpx`：可同步/非同步雙棧，但 map-sim 與 uds 已用 aiohttp，為 dependency footprint 考量不引入。
  - `requests` + thread pool：阻塞主迴圈，違反 async-first。

## R3：asyncio TCP Server 與 broadcast fan-out

- **Decision**：`asyncio.start_server(handler, feed_host, feed_port)`；每個 connection 由 handler
  註冊 `StreamWriter` 進 `set[StreamWriter]`（broadcast 集合）。發送流程：
  1. 每輪序列化所有 RadarTrack 為 `b"<json>\n"` bytes list。
  2. 對集合快照 iterate，`writer.write(bytes)`，之後 `await asyncio.gather(*drain_tasks, return_exceptions=True)`。
  3. 對任何 `ConnectionResetError / BrokenPipeError / write 後 writer.is_closing()` 之 client 從集合移除。
- **Rationale**：
  - `write() + drain()` pattern 是 asyncio TCP 標準作法；`return_exceptions=True` 避免一個 client
    斷線影響其他（FR-ES-014、SC-ES-008）。
  - 集合「快照」（`list(clients)`）避免在 iterate 時 mutate。
- **Alternatives considered**：
  - 自行維護 per-client queue + writer task：更彈性（可做 slow client 背壓），但 PoC 量級
    （3 client、每輪 <5KB）過度設計。
  - 使用 `websockets` / `asyncio.Protocol`：wire protocol 已定義為原生 TCP+newline JSON，直接用
    stream API 最簡。

## R4：高斯噪點與可重現性（numpy + seed 優先序）

- **Decision**：使用 `numpy.random.default_rng(seed)` 產生 `Generator`，單一 instance 貫穿
  lat / lon / alt / speed 全部取樣。seed 解析順序：CLI `--seed` > YAML `noise_seed` > `None`
  （= 使用系統熵源，由 `default_rng()` 自動取得）。lat/lon 的 σ 以 `σ_m / 111320` 近似為度
  （PoC 容忍 cos(lat) 失真，SC-ES-004 測試靜止目標不跨緯度所以誤差可接受）。
- **Rationale**：
  - `numpy.random.Generator` 是新 API（取代 legacy `RandomState`），seed-free 模式走 OS CSPRNG，
    與 spec §Assumptions 一致。
  - 單一 Generator 使測試以固定 seed 完整重現；freezegun 控制 `timestamp`，即可做 bit-exact 斷言。
- **Alternatives considered**：
  - `random.Random`：速度夠但無向量化；未來若要一次對 N 個目標批次取樣，numpy 更自然。
  - 每個欄位獨立 Generator：需要多個 sub-seed，複雜度無收益。

## R5：Azimuth / Elevation 計算

- **Decision**：
  - Azimuth：以標準大圓 bearing 公式 `atan2(sin(Δλ)·cosφ₂, cosφ₁·sinφ₂ − sinφ₁·cosφ₂·cos(Δλ))`，
    結果以 `% 360.0` 正規化至 `[0, 360)`。
  - Horizontal distance：haversine（`R=6371000m`）。
  - Elevation：`atan2(alt_target − alt_sensor, horiz_dist)`，以度返回；`horiz_dist < 1.0m` 時
    依 `alt_diff` 符號退化為 `+90.0` / `−90.0`（FR-ES-020）。
- **Rationale**：
  - PoC 範圍 ≤ 12 km，球面近似（非 ellipsoid）誤差 < 0.01°，遠小於 SC-ES-005 的 0.1° 門檻。
  - 噪點後位置做 bearing 計算符合 FR-ES-019「雷達量測值」語義。
- **Alternatives considered**：
  - WGS84 ellipsoid（geographiclib）：引入新依賴無收益。
  - ENU 座標轉換再取 bearing：步驟較多，誤差與直接球面公式等級相當。

## R6：Track Lifecycle + Grace Window（牆上時鐘）

- **Decision**：
  - `TrackRegistry` 維護 `{drone_id: (track_id, last_seen_mono: float)}`，`last_seen_mono` 使用
    `time.monotonic()`，不受系統時鐘跳動影響。
  - 每輪：新 drone_id → 分配 `track_id = f"echo-{uuid4().hex[:8]}"`、已存在 → 更新 `last_seen`。
  - 未出現於當輪回應的 drone_id：若 `now − last_seen ≤ lost_grace_sec` → 保持映射、靜默；
    若 `>` → 發一筆 `track_status: "Lost"`（用最後位置，timestamp=現在）→ 釋放映射。
  - 重新出現於 grace window 內 → 沿用 track_id 廣播 Active；逾時後才再次出現 → 視為新物件。
- **Rationale**：
  - `monotonic()` 是牆上時鐘概念（不回跳）的 async-safe 實作，符合 Assumptions。
  - 不綁定 tick 計數（10 Hz × 20 ticks = 2s）可讓 `update_rate_hz` 改變時 grace 語義不變。
- **Alternatives considered**：
  - Tick counter：簡單但 spec 明確要求與 rate 解耦。
  - 純 wall clock `time.time()`：受 NTP 調時影響，PoC 可接受但 monotonic 無額外成本。

## R7：日誌 / 可觀測性 schema

- **Decision**：structlog JSON renderer（stdout）。核心 event：
  - `map_sim_query`：`tick_id`、`latency_ms`、`count`、`status_code`。
  - `map_sim_unavailable`：throttle 至每秒最多 1 行（跟 FR-ES-003 實務要求一致）。
  - `track_lifecycle`：`drone_id`、`track_id`、`event=active|lost|recover`。
  - `tick_overrun`：`tick_id`、`reason=inflight|processing`。
  - `client_connected` / `client_disconnected`：`remote_addr`、`client_count`。
- **Rationale**：對齊 map-sim/uds logging 風格；支援 G4 可觀測性。
- **Alternatives considered**：stdlib `logging` 直用：欄位結構化不穩，不利後續 log aggregation。

## R8：pydantic v2 配置模型

- **Decision**：
  - `RadarConfig(BaseModel)`：7 大群參數（sensor / detection / noise / upstream / feed），
    `model_config = ConfigDict(extra="forbid")` 避免 typo。
  - YAML 載入：`yaml.safe_load` → `RadarConfig.model_validate(dict)`。
  - `noise_seed: int | None = None`（YAML flat key）。
- **Rationale**：`extra="forbid"` 符合「config 是 PoC 明確契約」立場；與 map-sim update 路徑用的
  `extra="ignore"` 區分（那是 wire payload，需寬容）。
- **Alternatives considered**：`pydantic-settings` + env var：PoC 單一 YAML 足夠，不引入新包。

---

## 結論

所有 Technical Context 項目均已敲定，無 NEEDS CLARIFICATION 遺留。Phase 1 可直接基於上述決策
產出 data-model、contracts 與 quickstart。
