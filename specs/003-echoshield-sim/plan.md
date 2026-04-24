# Implementation Plan: EchoShield Simulator

**Branch**: `003-echoshield-sim` | **Date**: 2026-04-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-echoshield-sim/spec.md`

## Summary

EchoShield Simulator 取代真實 EchoShield® 4D Radar 硬體，作為 PoC 感測層。它以 10 Hz 週期向 Map
Simulator（`GET /objects`，:8090）查詢雷達安裝點周邊 `max_range_m` 內的無人機，對每筆結果疊加雷達量
測誤差（位置 σ=5m、高度 σ=2m、速度 σ=0.5m/s 的獨立 Gaussian 噪點），以安裝點為原點計算方位角與仰
角，並透過 asyncio TCP Server（:9000）以換行分隔 JSON（UTF-8）廣播給所有已連線的 Client
（CoT Gateway EchodyneAdapter）。Simulator 維護 `drone_id → track_id` 映射與 2.0s grace window 吸
收抖動；map_sim 不可用時靜默跳過該輪；無物件時靜默不送任何 bytes。

**技術取向**：async-first（單進程 asyncio）、aiohttp client 查 Map Sim、pydantic v2 做 config /
wire schema 驗證、structlog 做結構化日誌、pytest + pytest-asyncio + freezegun + numpy 做測試與
確定性噪點控制。服務目錄 `services/echoshield-sim/`，嚴格對齊現有 `services/uds/` 與
`services/map-sim/` 的 layout。

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**:
- runtime：`aiohttp>=3.9`（HTTP client 查 Map Sim `GET /objects`）、`asyncio`（stdlib，主迴圈與
  TCP server at :9000）、`pydantic>=2.6`（config / RadarTrack schema）、`structlog>=24.1`
  （結構化 JSON 日誌）、`numpy>=1.26`（高斯噪點取樣，`np.random.Generator`）、`pyyaml`（讀 config）。
- dev：`pytest>=8.0`、`pytest-asyncio>=0.23`（asyncio_mode=auto）、`freezegun>=1.4`（凍結
  `timestamp` 欄位）、`aiohttp`（test stub server，reuse runtime dep）、`ruff`、`black`。
**Storage**: N/A（純 in-memory；`drone_id → track_id` 映射不持久化，重啟即失效）
**Testing**: pytest，目錄 `tests/{contract,integration,unit}/`，與 `services/map-sim/tests/` 同構
**Target Platform**: Linux server（單主機 PoC，與 Map Sim / CoT Gateway 同機）
**Project Type**: single service / CLI（`echoshield-sim --config path.yaml`）
**Performance Goals**:
- 主迴圈穩定 10 Hz（FR-ES-001 / SC-ES-001，每 track 10s 內 [90, 110] 筆）
- 查詢 → 廣播 p95 ≤ 10ms（SC-ES-002，本機 socket 寫入，不含網路）
- 查詢 → 輸出延遲整體 p95 < 100ms（使用者需求，≤ 1 個 tick）
- 多 Client fan-out：≥ 3 個並發 Client 收到相同 bytes（SC-ES-007）
**Constraints**:
- 同時最多 1 個 in-flight Map Sim 請求（FR-ES-004），逾時 1.0s 則該輪跳過
- Map Sim 不可用時主迴圈 **MUST NOT** 退出（FR-ES-003、SC-ES-009）
- 安靜模式：無物件 / 無 Lost event 時 **MUST NOT** 送任何 bytes（FR-ES-011、SC-ES-011）
- 長時運行記憶體 < 100 MB 且無漏（SC-ES-012）
- `lost_grace_sec` 以牆上時鐘計時，非 tick 計數（Assumptions）
**Scale/Scope**:
- PoC 同時 ≤ 5 架無人機（≤ 20 不崩潰）
- 並發 TCP Client：PoC 預期 1–3 個（Gateway + 偵錯 `nc`）
- 單主機單進程；無水平擴展

## Constitution Check

> `.specify/memory/constitution.md` 尚未初始化（仍為 template placeholder）。本 plan 採用以下 PoC
> 自律準則作為替代檢核門檻；當專案憲章正式建立後，本節 **MUST** 重新評估。

**Gate: PoC Self-Discipline（取代正式 Constitution Check）**

| 準則                                   | 檢核                                                                                                     | 狀態 |
| -------------------------------------- | -------------------------------------------------------------------------------------------------------- | ---- |
| G1. 測試先行（Test-First）             | contract / integration / unit 三層測試先寫；契約測試對 `RadarTrack` JSON schema 凍結驗證                 | PASS |
| G2. 契約凍結（Contract Freeze）        | TCP wire protocol = `contracts/tcp-feed.md`；欄位命名以 spec §Key Entities RadarTrack 為準（非 ICD-001） | PASS |
| G3. 結構化日誌（Structured Logging）   | 全程 structlog JSON 輸出；含 `event`、`drone_id`、`track_id`、`tick_id`、`latency_ms`                    | PASS |
| G4. 可觀測性（Observability）          | 關鍵 event：`map_sim_query`、`map_sim_unavailable`（throttled）、`track_lifecycle`、`client_connected/disconnected`、`tick_overrun` | PASS |
| G5. 結構對稱（Layout Symmetry）        | 嚴格對齊 `services/uds/`、`services/map-sim/`（src 布局、pyproject.toml、tests 分層）                    | PASS |
| G6. 無新存儲（No Persistence）         | 不引入 DB / 檔案；track 映射純 in-memory                                                                 | PASS |
| G7. 依賴最小化（Dependency Minimalism）| 僅新增 `numpy`（噪點），其餘與 map-sim 同組；未引入 scipy、不引入 FastAPI、無 ORM                        | PASS |

**Pre-Phase-0 Gate**: ✅ PASS。無違反，不需 Complexity Tracking。

**Post-Phase-1 Gate**（§Phase 1 完成後重評）: ✅ PASS。設計仍滿足 G1–G7；特別確認：
- contracts/ 僅一個 wire schema 檔（G2）、
- data-model 不引入持久化實體（G6）、
- quickstart 演示以現成 `nc` / `curl` 為主（G4）。

## Project Structure

### Documentation (this feature)

```text
specs/003-echoshield-sim/
├── spec.md                    # 既存 /speckit.specify 產物
├── plan.md                    # 本檔
├── research.md                # Phase 0 產物
├── data-model.md              # Phase 1 產物
├── quickstart.md              # Phase 1 產物
├── contracts/
│   └── tcp-feed.md            # TCP JSON wire protocol（:9000）
├── checklists/                # 既存（by /speckit.checklist）
└── tasks.md                   # Phase 2 產物（/speckit.tasks 產生，非本命令）
```

### Source Code (repository root)

```text
services/echoshield-sim/
├── pyproject.toml                       # 同 map-sim 樣式（setuptools、ruff、black、pytest-asyncio）
├── README.md
├── scripts/
│   └── smoke.sh                         # 對齊 services/map-sim/scripts/smoke.sh
├── src/
│   └── echoshield_sim/
│       ├── __init__.py
│       ├── __main__.py                  # python -m echoshield_sim
│       ├── cli.py                       # argparse：--config、--verbose、--seed
│       ├── config.py                    # pydantic Settings：RadarConfig (YAML loader)
│       ├── logging.py                   # structlog JSON configurator
│       ├── models/
│       │   ├── __init__.py
│       │   ├── track.py                 # RadarTrack pydantic model（wire schema）
│       │   └── lifecycle.py             # TrackState / TrackRegistry（drone_id↔track_id + grace）
│       ├── geo/
│       │   ├── __init__.py
│       │   ├── bearing.py               # 大圓 azimuth、haversine、elevation
│       │   └── noise.py                 # Gaussian 噪點（numpy Generator；seedable）
│       ├── mapsim/
│       │   ├── __init__.py
│       │   └── client.py                # aiohttp client：GET /objects，timeout=1.0s，single-flight
│       ├── feed/
│       │   ├── __init__.py
│       │   └── tcp_server.py            # asyncio TCP server :9000，broadcast fan-out
│       └── loop.py                      # 10 Hz 主迴圈、tick scheduler、lifecycle 管理
└── tests/
    ├── conftest.py
    ├── contract/
    │   └── test_radar_track_schema.py   # RadarTrack JSON schema 凍結
    ├── integration/
    │   ├── test_end_to_end.py           # Map Sim stub + TCP client，驗證 10 Hz 廣播
    │   ├── test_lifecycle_grace.py      # grace window 2s 行為（Active→消失→recover / Lost）
    │   ├── test_mapsim_unavailable.py   # 連線拒絕 / 5xx / timeout 下主迴圈不退出
    │   └── test_multi_client.py         # 3 個 Client 同步收到一致 bytes / 斷線隔離
    └── unit/
        ├── test_config.py               # YAML 載入 + CLI --seed 覆寫順序
        ├── test_noise.py                # σ 分布統計（固定 seed）
        ├── test_bearing.py              # 正北 / 正東 / 上方 elevation 退化
        ├── test_lifecycle.py            # TrackRegistry 狀態轉換
        └── test_track_serialization.py  # JSON 欄位 / 小數位 / \n 結尾
```

**Structure Decision**: 單服務 CLI + library 布局，目錄 `services/echoshield-sim/`。
模組 layout 嚴格鏡像 `services/map-sim/src/map_sim/`（`cli.py`、`config.py`、`logging.py`、
`__main__.py`、次級 package `models/ geo/ …`）；測試層級與 `services/map-sim/tests/` 一致
（contract / integration / unit 三層）。`pyproject.toml` 的 build / lint / pytest 區段沿用
map-sim 設定，僅調整 `[project].name` 與 `[project.scripts]` 入口（`echoshield-sim = echoshield_sim.cli:main`）。

## Complexity Tracking

> N/A — Constitution Check（PoC 自律準則）所有 gate 均 PASS，無違反需要說明。
