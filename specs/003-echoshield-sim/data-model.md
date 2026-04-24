# Data Model: EchoShield Simulator

**Feature**: `003-echoshield-sim`
**Date**: 2026-04-24
**Scope**: in-memory data structures（純 PoC，無持久化）。Wire schema 在
[`contracts/tcp-feed.md`](./contracts/tcp-feed.md) 另行定義，本檔描述 Python 側的模型與狀態機。

---

## 1. RadarConfig（啟動期載入，不可變）

對應 spec §Key Entities `RadarConfig` 與 FR-ES-021。由 YAML + CLI 載入，啟動後不得 mutate。

| Field              | Type             | Default              | Validation                                | Source                      |
| ------------------ | ---------------- | -------------------- | ----------------------------------------- | --------------------------- |
| `sensor_lat`       | `float`          | —（required）        | `-90 ≤ x ≤ 90`                            | YAML                        |
| `sensor_lon`       | `float`          | —（required）        | `-180 ≤ x ≤ 180`                          | YAML                        |
| `sensor_alt_m`     | `float`          | `0.0`                | `-500 ≤ x ≤ 10000`                        | YAML                        |
| `max_range_m`      | `float`          | `4800.0`             | `> 0`                                     | YAML                        |
| `update_rate_hz`   | `float`          | `10.0`               | `> 0 且 ≤ 50`                             | YAML                        |
| `lost_grace_sec`   | `float`          | `2.0`                | `≥ 0`                                     | YAML                        |
| `position_noise_m` | `float`          | `5.0`                | `≥ 0`                                     | YAML                        |
| `velocity_noise_ms`| `float`          | `0.5`                | `≥ 0`                                     | YAML                        |
| `noise_seed`       | `int \| None`    | `None`               | —                                         | YAML `noise.seed` + CLI `--seed`（CLI 優先） |
| `map_sim_url`      | `str`            | `http://localhost:8090` | URL shape                              | YAML                        |
| `feed_host`        | `str`            | `0.0.0.0`            | —                                         | YAML                        |
| `feed_port`        | `int`            | `9000`               | `1 ≤ x ≤ 65535`                           | YAML                        |

**Rules**
- Pydantic v2，`model_config = ConfigDict(extra="forbid", frozen=True)`。
- CLI `--seed` 於 `cli.py` 明確覆寫 `noise_seed`（即使 YAML 已有值），反映 spec §Clarifications。

---

## 2. MapSimObject（輸入快取，per tick）

Map Sim `GET /objects` 回應中 `objects[]` 單一元素的子集。Simulator **僅**讀取下列欄位；其他
（`status`、`model`、`distance_m`、…）**忽略**。Simulator 採 pydantic `extra="ignore"`，以
容忍 Map Sim 未來擴充。

| Field         | Type    | Semantics                                                           |
| ------------- | ------- | ------------------------------------------------------------------- |
| `drone_id`    | `str`   | Map Sim 主鍵；Simulator 用來 key 進 `TrackRegistry`                 |
| `lat`         | `float` | WGS84 緯度（真實位置，未加噪）                                      |
| `lon`         | `float` | WGS84 經度                                                          |
| `alt_m`       | `float` | HAE 公尺                                                            |
| `speed_ms`    | `float` | 地速 m/s                                                            |
| `is_lost`     | `bool`  | FR-ES-012：若為 `true`（僅 include_lost=true 時），視同「不在回應中」 |

> 注意：spec 明確要求 **MUST NOT** 使用 `objects[].status` 影響輸出（FR-ES-012），因此
> 本模型不納入 `status` 欄位，即使 pydantic 會以 `extra="ignore"` 悄悄吃掉它。

---

## 3. TrackState（per drone_id，in-memory）

Simulator 內部每個被看到過的 `drone_id` 維護一筆 `TrackState`。

| Field            | Type               | Description                                                 |
| ---------------- | ------------------ | ----------------------------------------------------------- |
| `drone_id`       | `str`              | Map Sim 主鍵                                                |
| `track_id`       | `str`              | `echo-{8-hex}`（`uuid4().hex[:8]`），Active 期間不變         |
| `last_seen_mono` | `float`            | `time.monotonic()` 時間戳（最後一次在 Map Sim 回應中出現）   |
| `last_known`     | `MapSimObject`     | 最後一次已知的真實位置 + 速度，供 Lost 事件輸出最後已知值    |
| `phase`          | `Literal["active", "grace"]` | 狀態枚舉（見 §4 狀態機）                          |

> `TrackRegistry = dict[str, TrackState]`，key = `drone_id`。

---

## 4. Track Lifecycle State Machine

```
                ┌─────────┐  drone_id 首次出現
     (none) ────▶│ ACTIVE  │◀──────────────┐
        │        └────┬────┘               │
        │  grace 內   │ drone_id           │ drone_id 再出現
        │  再出現     │ 消失於當輪回應      │（in grace）
        │             ▼                    │
        │        ┌─────────┐               │
        │        │ GRACE   │───────────────┘
        │        └────┬────┘
        │   逾時 (now − last_seen > lost_grace_sec)
        │             │  → 發 1 筆 Lost + 釋放映射
        ▼             ▼
     (none)  ←────────┘
        │
        │ drone_id 於 Lost 後再出現
        ▼
     [新的 ACTIVE，分配「新的」 track_id（不復用）]
```

**Transition 表**

| From    | Event                                            | To      | Output this tick                                                             |
| ------- | ------------------------------------------------ | ------- | ---------------------------------------------------------------------------- |
| (none)  | drone_id 首次出現                                 | ACTIVE  | 1 筆 `track_status: "Active"`（新 track_id，last_seen=now）                    |
| ACTIVE  | drone_id 再次出現（is_lost=false）                 | ACTIVE  | 1 筆 `track_status: "Active"`（同 track_id，更新 last_seen + last_known）       |
| ACTIVE  | drone_id 不在回應中 / `is_lost=true`              | GRACE   | （靜默，不廣播）                                                              |
| GRACE   | drone_id 再次出現且 `now − last_seen ≤ grace`      | ACTIVE  | 1 筆 `track_status: "Active"`（沿用原 track_id，更新 last_seen + last_known）   |
| GRACE   | `now − last_seen > lost_grace_sec`               | (none)  | 1 筆 `track_status: "Lost"`（沿用原 track_id，位置=last_known + 噪點，timestamp=now）→ 釋放映射 |

**Invariants**
- 同一個 `drone_id`，一次 Active 生命週期內 `track_id` 恒定（FR-ES-009）。
- Lost 事件每次生命週期結束**恰發一次**（SC-ES-010）；發送後 `drone_id` 再出現分配全新 `track_id`。
- `TrackRegistry` 大小上限 = 當前 Active + GRACE 總數；Lost 後立即釋放，無洩漏（SC-ES-012）。

---

## 5. NoiseGenerator（無狀態 wrapper，但內部 RNG 有狀態）

| Field        | Type                        | Description                                                |
| ------------ | --------------------------- | ---------------------------------------------------------- |
| `rng`        | `numpy.random.Generator`    | 由 `default_rng(noise_seed)` 建立（`None` → OS 熵源）       |
| `pos_sigma_m`| `float`                     | 複製自 `RadarConfig.position_noise_m`                      |
| `alt_sigma_m`| `float`                     | 固定 `2.0`（spec FR-ES-017）                               |
| `vel_sigma` | `float`                     | 複製自 `RadarConfig.velocity_noise_ms`                     |

**Methods（純函式語義，但會 advance RNG 狀態）**
- `perturb_position(lat, lon) -> (lat', lon')`：`lat' = lat + N(0, σ/111320)`、
  `lon' = lon + N(0, σ/111320)`（PoC 近似，見 research.md R4）。
- `perturb_altitude(alt_m) -> alt_m'`：`alt_m + N(0, 2.0)`。
- `perturb_velocity(speed_ms) -> max(0.0, speed_ms + N(0, σ))`（FR-ES-018 clamp）。

---

## 6. TCPClient（廣播集合元素）

| Field          | Type                      | Description                                       |
| -------------- | ------------------------- | ------------------------------------------------- |
| `writer`       | `asyncio.StreamWriter`    | 連線 writer                                        |
| `remote_addr`  | `str`                     | `ip:port`（logging 用）                           |
| `connected_at` | `float`                   | `time.monotonic()`                                 |

`FeedServer` 維護 `clients: set[TCPClient]`；連線時 add、寫入失敗 / EOF 時 discard。
絕無 per-client queue（PoC 不做背壓），write 失敗即踢出。

---

## 7. 欄位映射總覽：MapSimObject → RadarTrack（wire）

對應 contracts/tcp-feed.md §Field mapping：

| RadarTrack 欄位    | 來源                                                                                    |
| ------------------ | --------------------------------------------------------------------------------------- |
| `track_id`         | `TrackState.track_id`                                                                   |
| `latitude`         | `NoiseGenerator.perturb_position(MapSimObject.lat, .lon)[0]`（round 7）                 |
| `longitude`        | `NoiseGenerator.perturb_position(.lat, .lon)[1]`（round 7）                              |
| `altitude_m`       | `NoiseGenerator.perturb_altitude(MapSimObject.alt_m)`（round 1）                         |
| `velocity_ms`      | `NoiseGenerator.perturb_velocity(MapSimObject.speed_ms)`（round 2，clamped）             |
| `azimuth_deg`      | `geo.bearing(sensor, perturbed_pos)`（round 2，`[0, 360)`）                              |
| `elevation_deg`    | `geo.elevation(sensor, perturbed_pos, perturbed_alt)`（round 2，`[-90, 90]`）            |
| `timestamp`        | `datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms:03d}Z"`                    |
| `track_status`     | `"Active"` / `"Lost"`（由狀態機決定）                                                    |
| `classification`   | 固定 `"UAV"`（FR-ES-007）                                                                |
