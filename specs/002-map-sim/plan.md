# Implementation Plan: Map Simulator (Map Sim)

**Branch**: `002-map-sim` | **Date**: 2026-04-25 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-map-sim/spec.md`（含 2026-04-24 Clarification Q1：
`is_lost` 以獨立布林欄位表達 TTL 狀態，原始 `status` 永不被覆寫）

## Summary

Map Simulator（Map Sim）是反無人機 TAK PoC 感測層的**物件狀態中央登錄表**。以單一 asyncio 行程承載：
(1) aiohttp REST Server（`:8090`），提供 `POST /objects/update` 接收 UDS 每 tick per-drone 推送
（對齊 `specs/001-uds/contracts/rest-api.md` §3.2 的 8 欄位 payload）；
(2) `GET /objects?lat=&lon=&radius_m=&include_lost=` 地理範圍查詢端點（Haversine 排序、回傳 `distance_m` / `last_seen_s` / `is_lost`，下游 EchoShield 4800 m / Sentrycs 8000 m 共用）；
(3) `GET /objects/all` / `DELETE /objects/{drone_id}` / `GET /health` 除錯與運維端點；
(4) 以 `asyncio.Lock` 守護的 `ObjectRegistry`（in-memory dict，單一全域鎖 PoC 量級已足）；
(5) 背景 TTL cleanup task（每 2 s 掃一次；`ttl_warn_s=5.0` 預設隱藏於查詢、`ttl_remove_s=10.0` 預設從登錄表移除）；
(6) 結構化日誌（structlog）。

**行為關鍵點（來自 spec Clarification Q1 / FR-MS-006）**：物件進入 `[ttl_warn_s, ttl_remove_s)` lost 區間時，
回應中 `status` 欄位 **保留原始 FlightState 值不被覆寫**；以獨立布林欄位 `is_lost: bool` 表達 TTL 狀態
（`last_seen_s >= ttl_warn_s` → `true`）。此語意打破 `03-map-simulator-spec.md` §4.1 範例程式碼中
「`status if is_active else "lost"`」的覆寫式寫法，**本 feature 以 spec clarification 為準**。

**寬鬆接收原則（FR-MS-002）**：`POST /objects/update` 的 request body 必填欄位為 UDS 已凍結的 8 個；
若 body 另含 `model` / `operator_lat` / `operator_lon` 等 Sentrycs 專屬欄位或任何未知欄位，Map Sim MUST
靜默忽略並正常回 200，**不得**因此回 400。

## Technical Context

**Language/Version**: Python 3.11+（與 `services/uds/` 對齊；需 `asyncio.timeout()` / `TaskGroup` / `datetime.fromisoformat` 對 `Z` 後綴的手動轉換）

**Primary Dependencies**（與 UDS 統一）：
- `aiohttp` ≥ 3.9（REST Server；同 event loop 驅動背景 cleanup task）
- `pydantic` ≥ 2.6（`POST /objects/update` request schema；`extra="ignore"` 達成寬鬆欄位；query 參數以手動 parse + 明確 `reason` 字串為主，避免 pydantic 預設錯誤訊息漂移契約字串）
- `structlog` ≥ 24.1（JSON 結構化日誌；`--verbose` → DEBUG）

**Storage**: N/A（純記憶體；`Dict[str, DroneObject]`；重啟即空，上游 UDS 下 tick 會重新推）

**Testing**: `pytest` ≥ 8.0、`pytest-asyncio` ≥ 0.23（`asyncio_mode = "auto"`）、
`aiohttp.test_utils`（契約測試）、`freezegun` ≥ 1.4（TTL 時序測試；不依賴真實 sleep 避免 CI flake）

**Target Platform**: Linux / macOS；PoC 本機綁 `127.0.0.1:8090`

**Project Type**: asyncio HTTP service（server-only；不主動呼叫其他服務）

**Performance Goals**（引自 spec §4 Success Criteria）：
- `POST /objects/update` 平均延遲 < 5 ms @ 100 req/s 穩態（SC-MS-001）
- `GET /objects` 端到端 p95 < 20 ms @ 20 drones（SC-MS-002）
- TTL warn / remove 時序誤差 ≤ 2 s（SC-MS-003 / SC-MS-004，對應 2 s 清理週期）
- 查詢正確性：誤判率 0、`distance_m` 誤差 < 0.5%（SC-MS-005）
- 記憶體 < 50 MB、單核 CPU < 15% @ 20 drones（SC-MS-007）

**Constraints**：
- 單一 `asyncio.Lock` 守護整個 registry（PoC 併發量：≈100 req/s POST + ≈20 req/s GET + 0.5 Hz cleanup，
  鎖內工作為 dict ops + Haversine loop；見 research.md §3 選型）
- 不持久化、不跨行程、不 TLS、不 auth（信任本機邊界）
- `last_seen_at` 以 Map Sim 本地 `datetime.now(timezone.utc)` 為準（spec §5 Assumptions：避免 UDS 時鐘漂移）
- request body `timestamp` 僅原樣保留供下游參考，**不**參與 TTL 計算
- CLI `--port` / `--ttl-warn-s` / `--ttl-remove-s` / `--verbose` 必須可覆寫預設；其他參數不接受
- `status` 值域信任 UDS（不白名單驗證；非空字串即接受），但 Map Sim **不得**把 `status` 覆寫成 `"lost"`

**Scale/Scope**: 最多 20 個 `drone_id`、單一 YAML 場景上游、2 個下游感測器客戶端；3 個正式契約端點 + 2 個除錯端點

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` 仍為未填充模板，所有 PRINCIPLE / SECTION 欄位皆為占位符。無批准的治理
原則可檢查；比照 `specs/001-uds/plan.md` 同段處置，以 PoC 最佳實務自我約束：

- **Simplicity**：單一行程、單一 Python 專案、單一 asyncio 迴圈、單一全域鎖、單一 in-memory dict。
  不引入 DB / Redis / message broker / sharding / WebSocket。
- **Test-first for contracts**：`POST /objects/update` / `GET /objects` / `GET /health` 必備契約測試，
  覆蓋 spec User Story 1 / 2 / 3 的 Acceptance Scenarios 與 Edge Cases；TTL 時序測試以 `freezegun`
  取代真實 `asyncio.sleep`。`GET /objects/all` / `DELETE /objects/{id}` 為除錯/選填，僅做 smoke test。
- **Observability**：structlog JSON；每次 update / query / TTL cleanup 寫一筆 log（update/query 為
  DEBUG 級，cleanup 有移除時為 INFO）；400 錯誤以 WARNING 記 `reason` 字串。
- **Explicit boundaries**：Request 採 pydantic `extra="ignore"`（寬鬆）但**必填欄位漏一即 400**；
  error body 字串穩定為契約一部份，與 UDS 風格一致（`{"status": "error", "reason": "..."}`）。
- **Clarification 守門**：Q1（`is_lost` 獨立欄位、`status` 不覆寫）在 data-model.md §3 與
  contracts/rest-api.md §3.2 / §3.3 明文寫死，避免 implementation 又回到 `03-map-simulator-spec.md` 的
  覆寫式寫法。

**Gate result**: PASS（無 constitution violation；Complexity Tracking 區段保持空白）。
若日後 constitution 完成正式化，需在 `/speckit.analyze` 重新評估。

## Project Structure

### Documentation (this feature)

```text
specs/002-map-sim/
├── plan.md              # This file
├── research.md          # Phase 0 — Haversine / TTL 清理策略 / 併發鎖選型 / aiohttp 併發模型
├── data-model.md        # Phase 1 — DroneObject / ObjectRegistry / Query Response schema
├── quickstart.md        # Phase 1 — 啟動、curl 範例、測試指令
├── contracts/
│   └── rest-api.md      # :8090 正式契約（POST /objects/update、GET /objects、GET /health）+ 除錯端點
├── checklists/          # （已存在）
└── tasks.md             # Phase 2 output（由 /speckit.tasks 產生；本 plan 不產出）
```

### Source Code (repository root)

選用結構：`services/map-sim/`，對稱於已落地的 `services/uds/`。monorepo 下每個模擬器各自一個 Python
子專案（`pyproject.toml`）、各自可獨立 `pip install -e .` 與 `pytest`，避免把 map-sim、sentrycs-sim、
echoshield-sim 塞進同一套件命名空間。

```text
services/
└── map-sim/
    ├── pyproject.toml                    # Python ≥ 3.11；依賴 aiohttp / pydantic / structlog；[dev] pytest / pytest-asyncio / freezegun / ruff / black
    ├── README.md                         # 指向本 spec + quickstart
    ├── src/
    │   └── map_sim/
    │       ├── __init__.py
    │       ├── __main__.py               # `python -m map_sim`
    │       ├── cli.py                    # argparse → --port / --ttl-warn-s / --ttl-remove-s / --verbose
    │       ├── config.py                 # Settings dataclass（CLI → Settings；預設 port=8090）
    │       ├── logging.py                # structlog 初始化（與 uds 共用風格）
    │       ├── geo/
    │       │   ├── __init__.py
    │       │   └── haversine.py          # haversine_m（R=6_371_000.0；與 uds/geo/wgs84.py 同常數，獨立實作避免跨服務 import）
    │       ├── models/
    │       │   ├── __init__.py
    │       │   ├── drone_object.py       # DroneObject dataclass（見 data-model.md §2）
    │       │   └── request.py            # pydantic v2 UpdatePayload（extra="ignore"）、QueryParams 輔助
    │       ├── registry/
    │       │   ├── __init__.py
    │       │   └── object_registry.py    # ObjectRegistry（asyncio.Lock + 背景 cleanup 入口）
    │       ├── api/
    │       │   ├── __init__.py
    │       │   ├── server.py             # aiohttp App（lifecycle、啟動/關閉 cleanup task）
    │       │   ├── handlers_update.py    # POST /objects/update
    │       │   ├── handlers_query.py     # GET /objects, GET /objects/all
    │       │   ├── handlers_admin.py     # DELETE /objects/{id}, GET /health
    │       │   └── errors.py             # 穩定 reason 字串常數 + error_response helper
    │       └── cleanup/
    │           ├── __init__.py
    │           └── ttl_task.py           # 背景 TTL 清理 coroutine（週期 2 s，可由 config 覆寫供測試）
    └── tests/
        ├── conftest.py                   # aiohttp test client fixture、freezegun helper、registry fixture
        ├── contract/
        │   ├── test_update_contract.py   # US1 Acceptance 1–5 + FR-MS-001/002/015
        │   ├── test_query_contract.py    # US2 Acceptance 1–6 + FR-MS-003/004/005
        │   └── test_health_contract.py   # FR-MS-010
        ├── integration/
        │   ├── test_ttl_lifecycle.py     # US3 Acceptance 1–4（freezegun 推時間；驗 is_lost 切換、status 不覆寫）
        │   ├── test_concurrent_safety.py # FR-MS-007 / SC-MS-006（POST × GET × cleanup 併發）
        │   └── test_objects_all.py       # FR-MS-008（total/active/lost 計數以 is_lost=true 為準）
        └── unit/
            ├── test_haversine.py         # SC-MS-005 ground truth 比對（與 geopy 交叉驗證）
            ├── test_drone_object.py      # age_s / is_active / serialize
            └── test_object_registry.py   # update/query_radius/remove/cleanup_expired（含 lock 行為）
```

**Structure Decision**：`services/map-sim/` 下的單一 Python 專案；pyproject 提供 `map-sim` console script
（對稱於 `services/uds/` 的 `uds` console script）。與既有 `services/uds/` 為同儕服務，無互相 import；
契約共享僅以 `specs/` 目錄下的 Markdown 文件為準。

## Complexity Tracking

> 無 constitution 違例需要追蹤（constitution 目前為空模板）。保持本節空白。

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |

## Phase 0 — Research

見 [research.md](./research.md)。重點：
- **Haversine**：單一球面模型 R = 6_371_000.0 m；以 `math.radians / sin / cos / atan2` 實作；100 km 內誤差
  < 0.5%（已滿足 SC-MS-005）；不引入 Vincenty。
- **TTL 背景清理**：`asyncio.create_task` 於 `on_startup` 啟動 `ttl_task`，每 2 s 掃一次、`on_cleanup`
  cancel；週期 2 s 是 `ttl_warn_s=5`/`ttl_remove_s=10` 下 SC-MS-003/004 允許的最大誤差；測試可覆寫。
- **aiohttp 併發 read/write**：aiohttp handler 原生 coroutine，所有 handler 都在單一 event loop 串接；
  對 registry 的存取在 `asyncio.Lock` 之下序列化；鎖內工作 O(N) N ≤ 20，符合 SC-MS-002 延遲預算。
- **併發鎖策略**：採**單一全域 `asyncio.Lock`**（PoC 量級）。per-key lock 被明確拒絕，因 query 仍需遍歷
  全表、per-key 鎖並不增加平行度；單鎖邏輯更簡單且易於正確性測試。
- **時間/時鐘**：`last_seen_at` 用 `datetime.now(timezone.utc)`；測試以 `freezegun` 推進。

## Phase 1 — Design & Contracts

產出：
1. [data-model.md](./data-model.md) — `DroneObject` dataclass、`ObjectRegistry` 類、`Query Response` schema
   （含 `is_lost: bool` 語意與「`status` 不覆寫」的明文約束）。
2. [contracts/rest-api.md](./contracts/rest-api.md) — 正式契約 `POST /objects/update` / `GET /objects` /
   `GET /health`，含 error body schema、穩定 `reason` 字串集合、`is_lost` 欄位語意；除錯端點（
   `GET /objects/all`、`DELETE /objects/{drone_id}`）以「非契約但穩定」等級描述。
3. [quickstart.md](./quickstart.md) — 啟動、curl 範例、測試指令。
4. Agent context 更新：`.github/copilot-instructions.md` 的 `<!-- SPECKIT START/END -->` 區塊更新為指向
   本 plan.md 與 002-map-sim 的 artifacts。

### Re-check Constitution after design

Constitution 仍為空模板；設計：
- 無新永續化、無跨服務耦合（map-sim 不主動呼叫他人；僅被動接 UDS push、被動被感測器查詢）。
- 無新語言 / runtime / 疊。
- `is_lost` 設計打破上游 `03-map-simulator-spec.md` §4.1 範例的覆寫寫法，但已在 spec clarification Q1
  / contracts §3.2 固定；視為上游系統文件之 PoC 精化而非違反。

**Gate result: PASS**。

## Out of this plan

- `tasks.md`（由 `/speckit.tasks` 產生）
- 實際程式碼撰寫、CI、部署 compose（後續 tasks 階段安排）
- EchoShield / Sentrycs Simulator 的實作（各自的 feature）
