# Feature 003 — EchoShield Simulator 開發紀錄

| 欄位 | 內容 |
|------|------|
| Feature ID | 003 |
| 分支 | `003-echoshield-sim` → `develop` |
| 日期 | 2026-04-24 |
| 狀態 | 已實作、測試通過（74/74）、lint 乾淨 |

## 一、範圍

感測層雷達模擬器。10 Hz 查詢 Map Sim `GET /objects`、加入高斯雷達誤差、計算方位/俯仰、透過 TCP :9000 以 newline-delimited JSON 廣播給 CoT Gateway。

實作位置：`services/echoshield-sim/`。

## 二、Speckit 產出

- `specs/003-echoshield-sim/{spec,plan,data-model,research,contracts/tcp-feed,quickstart,tasks}.md`
- 48 tasks 分 6 phases，全數完成

## 三、關鍵 Clarifications

1. **Q1 Grace Window**：drone_id 消失 → 啟 2 秒 grace window；window 內重新出現則沿用原 `track_id`，**不**發 Lost；逾時才發恰一筆 Lost 並釋放。解決 Map Sim 瞬斷導致下游 TrackCorrelator 抖動。
2. **Q2 Noise Seed**：支援可重現隨機種子。優先序 `CLI --seed > config noise_seed > 系統熵源`；`noise_seed: null` 預設隨機。供 SC-ES-004 統計驗證 (10k 樣本 σ∈[4,6]m) 使用。

## 四、契約（對外凍結）

### TCP Feed :9000 — newline-delimited JSON

```json
{
  "track_id": "ECHO-000042",
  "timestamp": "2026-04-24T09:12:34.100Z",
  "latitude": 25.0345,
  "longitude": 121.5670,
  "altitude_m": 152.4,
  "speed_ms": 18.7,
  "heading_deg": 85.3,
  "azimuth_deg": 42.1,
  "elevation_deg": 8.6,
  "range_m": 3421.0,
  "track_status": "Active"
}
```

- `track_status ∈ {"Active", "Lost"}`（以 `docs/04-echoshield-simulator-spec.md` 為準；與 ICD-001 的 `NEW/UPDATED/LOST` 差異由下游 CoT Gateway EchodyneAdapter 做映射）。
- Fan-out：多 client 同一 tick 收到 **bit-identical** bytes。
- 安靜模式：無 track 時不送任何 bytes（連線保持）。
- 斷線客戶端：下次 broadcast 立即剔除，不影響其他 client。

### 上游依賴

- Map Sim `GET /objects?lat=&lon=&radius_m=`（:8090）
  - `radius_m = radar.max_range_m`（預設 8000）
  - 過濾 `is_lost=true`
  - 逾時 1s，HTTP/network 錯誤 → 當 tick 空結果（觸發 grace）、log 節流

## 五、雷達誤差模型

| 項目 | 分佈 | 預設 σ |
|------|------|--------|
| 位置 (lat/lon) | 獨立高斯、σ/111320 deg | 5 m |
| 高度 | 獨立高斯 | 2 m |
| 速度 | 高斯、clamp ≥ 0 | 1.5 m/s |

- lon 未做 `cos(lat)` 修正（PoC 近似，高緯度偏小，SC 容忍 [4.0, 6.0]m）。
- bearing：大圓公式；elevation：`atan2(dh, horiz)`；`horiz < 1m → ±90°`。
- 輸出 round 至 spec 精度（lat/lon 7 位、alt/速度 1 位、角度 1 位、距離整數）。

## 六、狀態機

```
SEEN(first tick)         GRACE (on miss)          LOST(once) → released
   │                         │                        ▲
   ▼                         ▼                        │
ACTIVE ──miss──> GRACE ──miss>2s──> LOST(event) ──────┘
  ▲                 │
  │ hit             │ hit (≤2s)
  └─────────────────┘  (沿用 track_id, 不發 Lost)
```

- `track_id` 格式：`ECHO-{seq:06d}`，單調遞增，釋放後不重用。
- Lost 行 position 使用 `last_known + 當 tick 新噪點樣本`（與 Active 相同 pipeline）。

## 七、Config / CLI

`config/local.yaml`（pydantic `extra="forbid", frozen=True`）：

```yaml
radar:
  origin_lat: 25.0330
  origin_lon: 121.5654
  origin_alt_m: 30.0
  max_range_m: 8000
  max_elevation_deg: 85.0
  hz: 10
  lost_grace_sec: 2.0
  position_noise_m: 5.0
  altitude_noise_m: 2.0
  velocity_noise_ms: 1.5
  noise_seed: null       # null=隨機；CLI --seed 可覆蓋（model_copy）
mapsim:
  base_url: "http://localhost:8090"
  timeout_sec: 1.0
tcp_feed:
  host: "0.0.0.0"
  port: 9000
```

CLI：`python3 -m echoshield_sim --config config/local.yaml [--seed INT] [--verbose]`

## 八、測試摘要

| 類型 | 數量 | 覆蓋 |
|------|------|------|
| Contract | 11 | RadarTrack JSON schema 凍結、TCP NDJSON framing、bit-exact replay |
| Unit | 48 | config / logging / serialization / lifecycle / mapsim client / bearing / noise |
| Integration | 15 | multi-client fan-out、quiet mode、e2e、grace window、mapsim-unavailable、performance、memory |
| **合計** | **74** | **100% pass** |

### 效能驗證
- 50 tick 查詢→輸出 p95 < 50 ms（遠低於 spec 的 < 100 ms 目標）
- 3000 tick `tracemalloc` peak < 100 MB、registry 無洩漏

## 九、結構化日誌事件

| event | 節流 | 說明 |
|-------|------|------|
| `cli_start` / `startup` | — | 啟動 |
| `tcp_server_listening` | — | TCP :9000 就緒 |
| `client_connected` / `client_disconnected` | — | client 生命週期 |
| `tick_completed` | — | 每 tick 統計（track 數、延遲） |
| `map_sim_unavailable` | 每 key 1s | Map Sim HTTP/timeout 錯誤 |
| `track_lost` | — | Lost 事件發出 |
| `broadcast_error` | 每 key 1s | client write 失敗 |

## 十、下游介面（供 Feature 005 CoT Gateway）

CoT Gateway 的 **EchodyneAdapter** 將：
1. 以 TCP client 連線 `echoshield-sim:9000`。
2. 逐行讀取 UTF-8 JSON（`\n` framing）。
3. 將 `track_status: "Active"` 映射至 CoT `a-n-A`（NEW 或 UPDATED 依 TrackCorrelator 狀態決定），`"Lost"` 觸發移除。
4. `track_id` 格式穩定 `ECHO-\d{6}`，可直接當 CoT uid 前綴。

## 十一、已知遺留

- 雷達座標仍以 `docs/04-echoshield-simulator-spec.md` 的 `Active/Lost` 值域為準；與 `docs/08-api-icd.md` ICD-001 的 `NEW/UPDATED/LOST` 差異待 CoT Gateway 實作時於 Adapter 層對齊（不影響本模組）。
- 經度噪點未 `cos(lat)` 修正（PoC 可接受）。
- Constitution 尚未初始化，沿用 PoC 自律準則 G1–G7。

## 十二、檔案清單

```
services/echoshield-sim/
├── pyproject.toml
├── README.md
├── config/local.yaml
├── scripts/smoke.sh
├── src/echoshield_sim/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── config.py
│   ├── logging.py
│   ├── loop.py
│   ├── models/{__init__,track,lifecycle}.py
│   ├── mapsim/{__init__,client}.py
│   ├── feed/{__init__,tcp_server}.py
│   └── geo/{__init__,bearing,noise}.py
└── tests/
    ├── contract/    (3 檔)
    ├── unit/        (7 檔)
    └── integration/ (7 檔)
```

38 支原始碼檔案、48 task、74 測試、ruff + black 乾淨。
