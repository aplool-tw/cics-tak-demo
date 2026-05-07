# Implementation Plan: Sentrycs Simulator

**Branch**: `004-sentrycs-sim` | **Date**: 2026-04-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/004-sentrycs-sim/spec.md`

## Summary

Sentrycs Simulator 取代真實 Sentrycs C-UAS（被動 RF 偵測）硬體，作為 PoC 的第二顆感測器兼主動接管
觸發者。它以 2 Hz（0.5s 週期）向 Map Simulator（`GET /objects`，:18090）查詢感測器安裝點 8000 m 半徑
內的無人機，依場景 YAML 預排的時序（`detected_at_s / mitigating_at_s / neutralized_at_s`）推進每架目標
的 `IDLE → DETECTED → MITIGATING → NEUTRALIZED → IDLE` 狀態機；在 `DETECTED → MITIGATING`
轉移的那一刻對 UDS（`POST /command/takeover`，:18080）發出**且僅發出一次**接管請求，並將下游回覆
（200 / 409=視為成功、400/404=失敗保留 DETECTED）編入狀態。對外則以 aiohttp.web 起一個 HTTP
JSON Status API（:17070），提供 `GET /detections`、`GET /detection/{uid}`、`GET /health`
三個端點，供 CoT Gateway 的 SentrycsAdapter 以 1 Hz 輪詢取用；每筆偵測 JSON 內含無人機位置、型號、
狀態、`is_landed`，以及由場景 YAML（`operator_bearing_deg` + `operator_distance_m`，200–500m）
一次性以 WGS84 大地距離公式推算並**永久鎖定**的操控者地面位置（`operator_lat/lon`），整個場景期間
零抖動。

**技術取向**：async-first 單進程 asyncio；`aiohttp` 同時擔任 Map Sim/UDS 的 HTTP client 與對外
Status API 的 HTTP server；`pydantic v2` 統一 scenario YAML 與 wire response schema 驗證；
`structlog` 結構化 JSON 日誌；`pytest + pytest-asyncio + freezegun` 驅動 contract / integration /
unit 三層測試。服務目錄 `services/sentrycs-sim/`，模組與測試布局嚴格對齊 `services/uds/`、
`services/map-sim/`、`services/echoshield-sim/`。

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**:

- runtime：
  - `aiohttp>=3.9`（雙用：作為 HTTP client 查 Map Sim `GET /objects` 與呼叫 UDS `POST /command/takeover`，以及 `aiohttp.web` 起 :17070 JSON Status API server）
  - `asyncio`（stdlib，主迴圈、per-drone async task、signal handler）
  - `pydantic>=2.6`（`SentrycsConfig` + `DroneScenario` YAML schema；`DetectionResponse` wire schema）
  - `structlog>=24.1`（JSON 結構化日誌）
  - `pyyaml`（讀 scenario YAML）
- dev：
  - `pytest>=8.0`、`pytest-asyncio>=0.23`（`asyncio_mode=auto`）
  - `freezegun>=1.4`（凍結 `timestamp` 於 contract / state machine 測試）
  - `aiohttp`（test stub server，reuse runtime dep）
  - `jsonschema>=4.0`（contract schema 凍結）
  - `ruff>=0.4`、`black>=24.3`

**Storage**: N/A（純 in-memory；`uid → DroneTrack` 快照與 `uid → model` 場景表皆在記憶體中；程序重啟即從 YAML 重新載入）。

**Testing**: pytest，目錄 `tests/{contract,integration,unit}/`，與 `services/echoshield-sim/tests/` 同構。

**Target Platform**: Linux server（單主機 PoC，與 Map Sim / UDS / CoT Gateway 同機）。

**Project Type**: single service / CLI（`sentrycs-sim --scenario path.yaml`）。

**Performance Goals**:

- Map Sim 輪詢主迴圈穩定 2 Hz（FR-SC-006；≤ 1 s 的偵測→輸出延遲以符合 SC-SC-001、SC-SC-002、SC-SC-005）。
- `GET /detections` 在 5 個並發 Client 以 1 Hz 輪詢情境下 p95 < 100 ms、錯誤率 0%（SC-SC-003）。
- `detected_at_s` → `/detections` 首次出現該目標 < 1 s（SC-SC-001）。
- `mitigating_at_s` → UDS 收到 takeover < 500 ms（SC-SC-001）。
- 啟動就緒 < 2 s（SC-SC-011）；優雅關閉 < 3 s（SC-SC-012）。

**Constraints**:

- 每目標 takeover **恰一次**（FR-SC-010）——以 `DroneTrack.takeover_sent: bool` 守門，409 亦視同成功不重送（FR-SC-011）。
- Map Sim 連線失敗 MUST 不回退既有非 IDLE 狀態，指數退避 1/2/4/10 s（FR-SC-009、SC-SC-007）。
- MITIGATING 期間目標自 Map Sim 消失的 10 s 寬限後 fallback 為 NEUTRALIZED（Edge Cases §4）。
- `operator_lat/lon` 全生命週期**完全等值**（不可每 tick 重算導致浮點抖動）（SC-SC-004）。
- `is_lost=true` 的 Map Sim 物件 100% 過濾（FR-SC-007、SC-SC-009）。
- 場景 YAML 時序矛盾（`detected_at_s > mitigating_at_s` 或 `mitigating_at_s > neutralized_at_s`）MUST fail fast 拒絕啟動（Edge Cases §7）。
- Map Sim `/objects` 不提供 `model`，Sentrycs 啟動時由 YAML 建 `uid → model` 查表（FR-SC-016 Clarification）。

**Scale/Scope**:

- PoC 同時 ≤ 5 架無人機（SC-SC-006，單核 CPU < 20%）；≤ 20 架不崩潰。
- `GET /detections` 並發 Client ≥ 5（FR-SC-018、SC-SC-003）。
- 單主機單進程；無水平擴展。

## Constitution Check

> `.specify/memory/constitution.md` 尚未初始化（仍為 template placeholder）。本 plan 沿用 `003-echoshield-sim`
> 已建立的 **PoC 自律準則**作為替代檢核門檻；當專案憲章正式建立後，本節 **MUST** 重新評估。

**Gate: PoC Self-Discipline（取代正式 Constitution Check）**

| 準則 | 檢核 | 狀態 |
| --- | --- | --- |
| G1. 測試先行（Test-First） | contract（`/detections` 與 `/detection/{uid}` JSON schema + Takeover caller request schema）、integration（完整生命週期 / 409 / 多機 / Map Sim 下線 / 優雅關閉）、unit（狀態機 / operator geo / scenario YAML / config / logging）三層先寫 | PASS |
| G2. 契約凍結（Contract Freeze） | 對外契約 = `contracts/http-status-api.md`；對下游 UDS 的呼叫契約 = `contracts/takeover-caller.md`（引用 `specs/001-uds/contracts/rest-api.md §1`，不得漂移） | PASS |
| G3. 結構化日誌（Structured Logging） | 全程 structlog JSON；`--verbose` 下每次狀態轉移、Map Sim 查詢摘要、UDS 請求/回應皆單筆結構化 event（FR-SC-024、SC-SC-010） | PASS |
| G4. 可觀測性（Observability） | 關鍵 event：`state_transition`、`mapsim_query`、`mapsim_unavailable`（throttled）、`takeover_request`、`takeover_response`、`operator_locked`、`unregistered_uid`、`http_request`、`shutdown` | PASS |
| G5. 結構對稱（Layout Symmetry） | 嚴格對齊 `services/echoshield-sim/src/echoshield_sim/`（`cli.py` / `config.py` / `logging.py` / `__main__.py` + 次級 package `models/ geo/ mapsim/ …`）；tests 三層與 `services/echoshield-sim/tests/` 同構 | PASS |
| G6. 無新存儲（No Persistence） | 不引入 DB / 檔案；狀態機純 in-memory；重啟即失效 | PASS |
| G7. 依賴最小化（Dependency Minimalism） | runtime 僅 `aiohttp`（同時做 client 與 server，省一層 FastAPI）、`pydantic`、`structlog`、`pyyaml`；未引入 FastAPI / uvicorn / numpy / geopy（操控者經緯以手寫 WGS84 destination formula 實作）；dev 與 echoshield 同組 | PASS |

**Pre-Phase-0 Gate**: ✅ PASS。無違反，不需 Complexity Tracking。

**Post-Phase-1 Gate**（§Phase 1 完成後重評）: ✅ PASS。設計仍滿足 G1–G7；特別確認：

- `contracts/` 僅 2 份檔案（對外 + 對下游 caller），皆指向既有或本服務 wire schema，無重複定義（G2）；
- `data-model.md` 所有實體皆為 in-memory runtime 物件（G6）；
- `quickstart.md` 以現成 `curl`、`python -m sentrycs_sim` 為主，未引入額外工具鏈（G4）；
- `geopy` 雖在 spec Assumptions 中提及「可用」，實作改以手寫 WGS84 direct/destination formula（約 15 行）即可，以守 G7；若未來要算精確 operator 距離，再評估引入。

## Project Structure

### Documentation (this feature)

```text
specs/004-sentrycs-sim/
├── spec.md                    # 既存 /speckit.specify 產物（含 Clarifications）
├── plan.md                    # 本檔
├── research.md                # Phase 0 產物
├── data-model.md              # Phase 1 產物
├── quickstart.md              # Phase 1 產物
├── contracts/
│   ├── http-status-api.md     # 對外 :17070 JSON Status API（GET /detections、/detection/{uid}、/health）
│   └── takeover-caller.md     # Sentrycs 作為 Client 呼叫 UDS POST /command/takeover 的呼叫端契約
└── tasks.md                   # Phase 2 產物（/speckit.tasks 產生，非本命令）
```

### Source Code (repository root)

```text
services/sentrycs-sim/
├── pyproject.toml                        # 同 echoshield-sim 樣式（setuptools、ruff、black、pytest-asyncio）
├── README.md
├── scripts/
│   └── smoke.sh                          # 對齊 services/echoshield-sim/scripts/smoke.sh
├── config/
│   └── local.yaml                        # 範例場景 YAML（1 sensor + 2 drones）
├── src/
│   └── sentrycs_sim/
│       ├── __init__.py
│       ├── __main__.py                   # python -m sentrycs_sim
│       ├── cli.py                        # argparse：--scenario、--api-port、--verbose
│       ├── config.py                     # pydantic Settings：SentrycsConfig + DroneScenario YAML loader + fail-fast 校驗
│       ├── logging.py                    # structlog JSON configurator
│       ├── models/
│       │   ├── __init__.py
│       │   ├── detection.py              # DetectionStatus Enum + DroneTrack + DetectionResponse（wire schema）
│       │   ├── operator.py               # OperatorEstimate（不可變 frozen model）
│       │   └── takeover.py               # TakeoverRequest / TakeoverResult（呼叫紀錄）
│       ├── geo/
│       │   ├── __init__.py
│       │   └── wgs84.py                  # destination_point(lat, lon, bearing_deg, distance_m) → (lat, lon)
│       ├── mapsim/
│       │   ├── __init__.py
│       │   └── client.py                 # aiohttp client：GET /objects?lat=&lon=&radius_m=8000，指數退避
│       ├── uds/
│       │   ├── __init__.py
│       │   └── client.py                 # aiohttp client：POST /command/takeover（200/409 → 成功；400/404 → 失敗）
│       ├── state/
│       │   ├── __init__.py
│       │   └── machine.py                # StateMachine：IDLE/DETECTED/MITIGATING/NEUTRALIZED 轉移規則與副作用
│       ├── api/
│       │   ├── __init__.py
│       │   └── server.py                 # aiohttp.web :17070；GET /detections、/detection/{uid}、/health
│       └── loop.py                       # 2 Hz 主迴圈 + per-drone 時序 task + signal handler + graceful shutdown
└── tests/
    ├── __init__.py
    ├── conftest.py                       # 共用 fixture：map_sim_stub、uds_stub、scenario loader、frozen clock
    ├── contract/
    │   ├── __init__.py
    │   ├── test_detections_schema.py     # /detections 回應 JSON schema 凍結（FR-SC-016 全欄位）
    │   ├── test_detection_by_uid.py      # /detection/{uid} 200/404 行為
    │   └── test_takeover_caller.py       # Sentrycs 打出的 POST /command/takeover body 欄位（drone_id/target_lat/lon/alt_m）
    ├── integration/
    │   ├── __init__.py
    │   ├── test_end_to_end_lifecycle.py  # User Story 1：IDLE→DETECTED→MITIGATING→NEUTRALIZED→移除
    │   ├── test_operator_static.py       # User Story 2：operator_lat/lon 整個場景零抖動
    │   ├── test_multi_drone.py           # User Story 3：多機並行 + 409 隔離
    │   ├── test_mapsim_unavailable.py    # Map Sim 下線指數退避、狀態不回退、恢復後追上
    │   ├── test_mitigating_disappear.py  # MITIGATING 期間目標消失 10s 寬限 → NEUTRALIZED
    │   ├── test_takeover_409.py          # UDS 409 視為成功（SC-SC-008）
    │   ├── test_takeover_400_404.py      # 400/404 保留 DETECTED，不重送
    │   ├── test_is_lost_filter.py        # is_lost=true 100% 過濾（SC-SC-009）
    │   ├── test_api_concurrency.py       # 5 並發 Client、p95 < 100 ms、一致快照（SC-SC-003、FR-SC-018）
    │   └── test_graceful_shutdown.py     # SIGINT 3 秒內關閉（SC-SC-012）
    └── unit/
        ├── __init__.py
        ├── test_config.py                # YAML 載入、fail-fast、時序矛盾、缺欄位、operator_distance_m 200–500 邊界
        ├── test_state_machine.py         # 全部合法與非法轉移；takeover_sent 守門
        ├── test_operator_geo.py          # destination_point：正北/正東/225° 準確度 < 1m（SC-SC-004）
        ├── test_scenario_unknown_uid.py  # 場景未登記 uid → model="Unknown" + error log
        ├── test_mapsim_client.py         # aiohttp client retry backoff、timeout
        └── test_logging.py               # verbose 下 event 欄位
```

**Structure Decision**: 單服務 CLI + library 布局，目錄 `services/sentrycs-sim/`。
模組 layout 嚴格鏡像 `services/echoshield-sim/src/echoshield_sim/`（`cli.py`、`config.py`、`logging.py`、
`__main__.py`、次級 package `models/ geo/ mapsim/ …`），額外新增 `uds/`（下游 Client）、`state/`
（狀態機）、`api/`（對外 Status API）。測試層級與 `services/echoshield-sim/tests/` 一致（contract /
integration / unit 三層）。`pyproject.toml` 的 build / lint / pytest 區段沿用 echoshield 設定，僅調整
`[project].name`、`[project.scripts]` 入口（`sentrycs-sim = sentrycs_sim.cli:main`），並移除 `numpy`
（本服務無高斯噪點需求）。

## Complexity Tracking

> N/A — Constitution Check（PoC 自律準則）所有 gate 均 PASS，無違反需要說明。
