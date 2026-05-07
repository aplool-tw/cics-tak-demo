# Implementation Plan: Unified Drone Simulator (UDS)

**Branch**: `001-uds` | **Date**: 2026-04-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-uds/spec.md`

## Summary

UDS 是反無人機 TAK PoC 中「無人機真實位置」的 Single Source of Truth。以單一 asyncio 行程承載：
(1) YAML 場景載入器；(2) 主迴圈軌跡引擎（WGS84 Haversine / bearing，10 Hz 預設）；(3) per-drone HTTP 推送器
（每週期對每架 `flight_state ≠ IDLE` 的無人機各發一次 `POST :18090/objects/update`，10 架 × 10 Hz = 100 req/s）；
(4) aiohttp REST Server（`:18080`），正式契約僅 `POST /command/takeover`，`GET /status/{drone_id}` 與
`GET /drones` 僅在 `--debug` 旗標下註冊，不納入契約測試；(5) 結構化日誌（structlog）。
飛行狀態機 `IDLE → FLYING_NORMAL → MITIGATING_TAKEOVER → LANDING → LANDED`，`LANDED` 在同週期推送最後一筆
（`flight_state="LANDED"`），之後停推該 `drone_id`。

## Technical Context

**Language/Version**: Python 3.11+（需 `asyncio.timeout()`、`TaskGroup`）
**Primary Dependencies**:
- `aiohttp` ≥ 3.9（同時作為 REST Server 與 HTTP Client 推送；client 走 `ClientSession` 連線池）
- `PyYAML` ≥ 6.0（場景載入）
- `geopy` ≥ 2.4（Haversine 距離；bearing / 座標偏移以內建公式自行實作以確保精度與決定性）
- `structlog` ≥ 24.1（JSON 結構化日誌）
- `pydantic` ≥ 2.6（Takeover request / Scenario YAML schema 驗證，決定 400/409 的一致錯誤回應）
**Storage**: N/A（記憶體內；每次啟動由 YAML 重新初始化）
**Testing**: `pytest` ≥ 8.0、`pytest-asyncio` ≥ 0.23、`aiohttp.test_utils`（契約測試 / 整合測試）、`freezegun`（軌跡重現性）
**Target Platform**: Linux / macOS（PoC 本機 `127.0.0.1`），單行程單機
**Project Type**: asyncio CLI service（兼 HTTP server + client）
**Performance Goals**:
- 穩態 per-drone 10 ± 0.5 Hz（SC-001），10 架時總推送 95–105 req/s（SC-004）
- `POST /command/takeover` p99 HTTP 回應 ≤ 200 ms，且 ≤ 1 個主迴圈週期內反映於 Map Simulator 推送（SC-003）
- 主迴圈 tick jitter ≤ 10 ms（@10 Hz）
**Constraints**:
- Per-drone push 非 batch；需 `aiohttp.ClientSession` 連線池 + 有界背壓策略（每架無人機一個推送 queue，maxsize=2，滿則丟棄最舊，記錄 warning）
- `LANDED` 同週期推送最後一筆後必須停推，不得再出現於任何後續請求
- `timeline[].action` 白名單僅 `start_flying`；其他值 fail-fast（載入期非零 exit）
- 場景規模 ≤ 10 架；wall-clock `dt` 上限 1.0 s（時鐘跳變保護）
- 本機明文 HTTP，無 TLS / 認證
**Scale/Scope**: ≤ 10 架無人機、1 個 YAML 場景、2 個對外介面（:18080 REST、:18090 HTTP client 推送）

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

專案 `.specify/memory/constitution.md` 目前仍為未填充模板（所有 PRINCIPLE / SECTION 欄位皆為占位）。
在無已批准治理原則可檢查的情況下，本 plan 依 PoC 最佳實務自我約束：

- **Simplicity**：單一行程、單一 Python 專案、單一 asyncio 迴圈；不引入 DB / message broker / 微服務拆分。
- **Test-first for contracts**：`POST /command/takeover` 必備契約測試（Acceptance Scenarios US2 1–8）；
  Map Simulator 客戶端以 `aiohttp` testserver fixture 做整合測試。除錯端點不寫契約測試（僅 smoke test）。
- **Observability**：structlog JSON、每次狀態轉移與每次推送失敗皆 log；`--verbose` 降低 log level 至 DEBUG。
- **Explicit boundaries**：Scenario YAML 採封閉白名單，fail-fast；接管 request 必填欄位與值域錯誤回應固定。

**Gate result**: PASS（無 constitution violation；Complexity Tracking 區段保持空白）。
若日後 constitution 完成正式化，需在 `/speckit.analyze` 重新評估。

## Project Structure

### Documentation (this feature)

```text
specs/001-uds/
├── plan.md              # This file
├── research.md          # Phase 0 — 技術選型 / Haversine / bearing 決策
├── data-model.md        # Phase 1 — DroneState / FlightState / TakeoverCommand / Scenario schema
├── quickstart.md        # Phase 1 — 啟動、YAML 範例、測試指令
├── contracts/
│   └── rest-api.md      # :18080 正式契約 + :18090 客戶端契約 + --debug 端點（非契約）
├── checklists/          # （已存在）
└── tasks.md             # Phase 2 output（由 /speckit.tasks 產生）
```

### Source Code (repository root)

選用結構：`services/uds/`（monorepo 下以「服務（service）」為單位劃分，與本 repo 另外將 map-sim、sentrycs-sim、
echoshield-sim 等視為同儕服務的長期方向一致）。不採用 `apps/uds/`（apps 慣例偏 UI/前端），也不採用
`src/unified_drone_simulator/`（把 PoC 當作單一頂層 Python 套件，無法容納之後加入的 map-sim / sentrycs-sim）。

```text
services/
└── uds/
    ├── pyproject.toml              # Python 專案（Python ≥ 3.11、依賴、entry point）
    ├── README.md                   # 指向本 spec + quickstart
    ├── src/
    │   └── uds/
    │       ├── __init__.py
    │       ├── __main__.py         # `python -m uds`
    │       ├── cli.py              # argparse → --scenario / --api-port / --map-sim-url / --hz / --verbose / --debug
    │       ├── config.py           # Settings dataclass（CLI + env 合併）
    │       ├── logging.py          # structlog 初始化
    │       ├── models/
    │       │   ├── __init__.py
    │       │   ├── drone_state.py  # DroneState dataclass
    │       │   ├── flight_state.py # FlightState Enum
    │       │   └── takeover.py     # TakeoverCommand + pydantic request model
    │       ├── scenario/
    │       │   ├── __init__.py
    │       │   ├── loader.py       # ScenarioLoader（YAML → Scenario object；白名單 fail-fast）
    │       │   └── schema.py       # pydantic Scenario / Drone / Timeline 模型
    │       ├── geo/
    │       │   ├── __init__.py
    │       │   └── wgs84.py        # haversine_m / bearing_deg / offset_wgs84 / clamp_turn
    │       ├── engine/
    │       │   ├── __init__.py
    │       │   ├── state_machine.py # FlightState 轉移規則
    │       │   ├── trajectory.py    # dt 積分、平滑轉向、降落梯度
    │       │   └── loop.py          # 主迴圈（tick、發佈狀態變更事件）
    │       ├── push/
    │       │   ├── __init__.py
    │       │   └── map_client.py   # aiohttp ClientSession；per-drone queue；LANDED 收尾；失敗重試策略
    │       └── api/
    │           ├── __init__.py
    │           ├── server.py       # aiohttp App；生命週期；--debug 時註冊 debug 路由
    │           ├── takeover.py     # POST /command/takeover handler（正式契約）
    │           └── debug.py        # GET /status/{id}、GET /drones（僅 --debug）
    ├── scenarios/
    │   ├── single_drone_invasion.yaml
    │   └── drone_swarm.yaml
    └── tests/
        ├── conftest.py             # 共用 fixture（aiohttp app、fake map server、frozen clock）
        ├── contract/
        │   └── test_takeover_contract.py   # US2 Acceptance 1–8（正式契約）
        ├── integration/
        │   ├── test_push_loop.py           # US3：per-drone 速率、LANDED 收尾、容錯
        │   ├── test_takeover_closure.py    # US1：端到端狀態閉環
        │   └── test_scenario_loader.py     # FR-UDS-007：timeline 白名單 fail-fast
        └── unit/
            ├── test_wgs84.py
            ├── test_state_machine.py
            └── test_trajectory.py
```

**Structure Decision**：`services/uds/` 下的單一 Python 專案。與 `docs/system-docs/` 已暗示的多服務結構對齊，
且不強迫把未來的 map-sim / sentrycs-sim 塞進同一個套件。pyproject 提供 `uds` console script。

## Complexity Tracking

> 無 constitution 違例需要追蹤（constitution 目前為空模板）。保持本節空白。

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |

## Phase 0 — Research

見 [research.md](./research.md)。重點：
- 語言 / 執行環境：Python 3.11+、單 asyncio 事件迴圈、無多進程。
- HTTP 疊：`aiohttp` 同時作 server 與 client（重用 event loop、`ClientSession` 連線池 + keep-alive）。
- 地理計算：自實作 WGS84 球面 Haversine / forward-azimuth bearing / destination point（offset），
  地球半徑常數 `R = 6_371_000.0 m`；`geopy.distance.distance` 僅作單元測試交叉驗證。
- 場景驗證：`pydantic v2` + `PyYAML`；`timeline[].action` 以 `Literal["start_flying"]` 達成白名單、
  載入期直接拋 `ValidationError` 並以 exit code 2 結束。
- 觀測：`structlog` + stdlib logging bridge；`--verbose` 切 DEBUG。
- 測試：`pytest` + `pytest-asyncio`（`asyncio_mode = "auto"`）+ `aiohttp` test server fixture。

## Phase 1 — Design & Contracts

產出：
1. [data-model.md](./data-model.md) — `DroneState` / `FlightState` / `TakeoverCommand` / Scenario YAML schema。
2. [contracts/rest-api.md](./contracts/rest-api.md) — 正式契約 `POST :18080/command/takeover`、
   `--debug` 端點、以及 UDS → Map Simulator 客戶端契約 `POST :18090/objects/update`。
3. [quickstart.md](./quickstart.md) — 啟動、YAML、測試指令。
4. Agent context：`.github/copilot-instructions.md` 的 `<!-- SPECKIT START/END -->` 區塊已指向本 plan.md。

### Re-check Constitution after design

Constitution 仍為空模板；設計未新增跨服務耦合、未引入永續化、未突破 PoC 邊界。Gate：**PASS**。

## Out of this plan

- `tasks.md`（由 `/speckit.tasks` 產生）
- 實際程式碼撰寫、CI、部署 compose（視後續 tasks 階段安排）
