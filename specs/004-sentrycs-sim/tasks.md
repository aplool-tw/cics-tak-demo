---
description: "Task list for Sentrycs Simulator (004-sentrycs-sim)"
---

# Tasks: Sentrycs Simulator

**Input**: Design documents from `/specs/004-sentrycs-sim/`
**Prerequisites**: plan.md (✅), spec.md (✅), research.md (✅), data-model.md (✅),
contracts/ (`http-status-api.md`, `takeover-caller.md`), quickstart.md (✅)

**Tests**: TDD enabled — contract → unit → integration，每層皆 MUST 先寫且先 FAIL 再進到實作。

**Organization**: 按 User Story（US1 / US2 / US3）分相；每相可獨立實作並獨立驗收。Setup
（Phase 1）與 Foundational（Phase 2）完成後，US1/US2/US3 可並行推進。

**Service root**: `services/sentrycs-sim/`（嚴格鏡像 `services/echoshield-sim/` 布局；plan.md §Project Structure）。

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: 可並行（不同檔、無未完成依賴）
- **[Story]**: 對應 spec.md User Story（US1 / US2 / US3）；Setup / Foundational / Polish 無 Story 標籤
- 所有路徑皆為**相對於 repo root** 的絕對路徑片段

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 建立 `services/sentrycs-sim/` 目錄骨架、pyproject、lint/format 與 pytest-asyncio 設定；對齊 `services/echoshield-sim/`。

- [X] T001 建立服務根目錄與 src/tests layout：`services/sentrycs-sim/{src/sentrycs_sim/,tests/{contract,integration,unit}/,config/,scripts/}`，全部放 `__init__.py`（plan.md §Project Structure）
- [X] T002 撰寫 `services/sentrycs-sim/pyproject.toml`：`[project].name=sentrycs-sim`、`requires-python=">=3.11"`、runtime deps `aiohttp>=3.9,pydantic>=2.6,structlog>=24.1,pyyaml`、dev deps `pytest>=8.0,pytest-asyncio>=0.23,freezegun>=1.4,jsonschema>=4.0,ruff>=0.4,black>=24.3`、`[project.scripts] sentrycs-sim = "sentrycs_sim.cli:main"`（不含 numpy；對齊 echoshield-sim 但移除 numpy）
- [X] T003 [P] 撰寫 `services/sentrycs-sim/pyproject.toml` 的 `[tool.ruff]`、`[tool.black]`、`[tool.pytest.ini_options]`（`asyncio_mode = "auto"`、`testpaths = ["tests"]`）等設定段（從 `services/echoshield-sim/pyproject.toml` 複製並調整）
- [X] T004 [P] 撰寫 `services/sentrycs-sim/README.md`（引用 quickstart.md 要點：安裝 → 啟動 → 驗證三段）
- [X] T005 [P] 建立 `services/sentrycs-sim/config/local.yaml`（與 quickstart.md §2 一字不差的 2-drone 範例）
- [X] T006 [P] 建立 `services/sentrycs-sim/scripts/smoke.sh`（對齊 `services/echoshield-sim/scripts/smoke.sh`；用 curl 驗 `/health` → 啟動後 <2s 回 200）
- [X] T007 [P] 建立 `services/sentrycs-sim/tests/conftest.py` 骨架：匯出共用 fixture placeholder（`map_sim_stub`、`uds_stub`、`scenario_yaml_factory`、`frozen_clock`）；實作留到 T020–T023

**Checkpoint**: `pip install -e '.[dev]'` 可成功，`pytest -q` 可收集到空測試。

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 所有 User Story 共享的 runtime 基礎：enum、pydantic models、logging、config loader、WGS84 helper、registry。**MUST** 先完成此相再動任何 User Story。

**TDD note**: 本相純基礎庫，unit test 與實作一併完成（測試先寫、先 FAIL）。

### Foundational Tests (先寫且先 FAIL)

- [X] T008 [P] 撰寫 `services/sentrycs-sim/tests/unit/test_logging.py`：驗證 `configure_logging(verbose=True)` 產生 JSON 輸出、`--verbose` off 時省略 DEBUG（對應 FR-SC-024、research.md R10）
- [X] T009 [P] 撰寫 `services/sentrycs-sim/tests/unit/test_config.py`：覆蓋 data-model.md §2 全部 fail-fast 規則——欄位缺失、`detected_at_s > mitigating_at_s`、`mitigating_at_s > neutralized_at_s`、`operator_distance_m` 超出 [200,500]、`operator_bearing_deg` 不在 [0,360)、`uid` 重複、未知欄位（`extra="forbid"`）各自拋 `ValueError`
- [X] T010 [P] 撰寫 `services/sentrycs-sim/tests/unit/test_operator_geo.py`：以正北（bearing=0）、正東（bearing=90）、西南（bearing=225）三方向 × distance=200/300/500m 驗證 `destination_point(25.0330, 121.5654, bearing, dist)` 反算誤差 < 1m（SC-SC-004、research.md R3）
- [X] T011 [P] 撰寫 `services/sentrycs-sim/tests/unit/test_state_machine.py`：覆蓋 data-model.md §1 合法轉移矩陣與所有非法轉移（違反即 ERROR log + 拒絕）；`takeover_sent` latch 守門——`ACCEPTED/ALREADY_TAKEN_OVER/REJECTED_*` 皆 latch，`FAILED_TRANSPORT` 不 latch

### Foundational Implementation

- [X] T012 [P] 實作 `services/sentrycs-sim/src/sentrycs_sim/logging.py`：structlog JSON 配置（與 `services/echoshield-sim/src/echoshield_sim/logging.py` 同構）
- [X] T013 [P] 實作 `services/sentrycs-sim/src/sentrycs_sim/models/__init__.py` + `detection.py`：`DetectionStatus` Enum、`DroneTrack`（mutable）、`DetectionResponse`（`extra="forbid"`、14 欄位、`Literal["DETECTED","MITIGATING","NEUTRALIZED"]`；data-model.md §1、§3.1、§4）
- [X] T014 [P] 實作 `services/sentrycs-sim/src/sentrycs_sim/models/operator.py`：`OperatorEstimate`（`ConfigDict(frozen=True)`，4 欄位；data-model.md §3.2）
- [X] T015 [P] 實作 `services/sentrycs-sim/src/sentrycs_sim/models/takeover.py`：`TakeoverRequest`、`TakeoverResult` Enum（5 個值；data-model.md §3.3）
- [X] T016 [P] 實作 `services/sentrycs-sim/src/sentrycs_sim/geo/__init__.py` + `wgs84.py`：`destination_point(lat, lon, bearing_deg, distance_m) -> (lat, lon)`（research.md R3 公式 15 行）
- [X] T017 實作 `services/sentrycs-sim/src/sentrycs_sim/config.py`：`SentrycsConfig` + `DroneScenario` pydantic model（data-model.md §2），`load_scenario(path) -> SentrycsConfig`；所有 `@model_validator(after)` 規則（T009 覆蓋）；載入失敗丟 `ValueError`
- [X] T018 [P] 實作 `services/sentrycs-sim/src/sentrycs_sim/state/__init__.py` + `machine.py`：`StateMachine` 類；轉移方法 `advance(track, now, scenario, ...)`、`apply_takeover_result(track, result)`；每次轉移觸發 `state_transition` structlog event（research.md R10）
- [X] T019 實作 `services/sentrycs-sim/src/sentrycs_sim/models/registry.py`（或放在 `models/__init__.py`）：`DroneRegistry.snapshot() -> list[DetectionResponse]`、`get(uid)`；以 `list(self._tracks.values())` 原子複製（data-model.md §5；FR-SC-018）

### Shared Fixtures（補完 T007）

- [X] T020 [P] 在 `services/sentrycs-sim/tests/conftest.py` 實作 `scenario_yaml_factory` fixture：接受 dict / overrides，寫成 tmp YAML，回傳 `SentrycsConfig`
- [X] T021 [P] 在 `services/sentrycs-sim/tests/conftest.py` 實作 `map_sim_stub` fixture：aiohttp test server，路由 `GET /objects`，支援以 list 推入物件 + 模擬 5xx/timeout/connection_refused
- [X] T022 [P] 在 `services/sentrycs-sim/tests/conftest.py` 實作 `uds_stub` fixture：aiohttp test server，路由 `POST /command/takeover`，支援 per-uid 指定回應（200/400/404/409/timeout/5xx）
- [X] T023 [P] 在 `services/sentrycs-sim/tests/conftest.py` 實作 `frozen_clock` fixture：封裝 `freezegun.freeze_time` + 可注入 `fake_sleep: Callable[[float], Awaitable[None]]`（research.md R8）

**Checkpoint**: `pytest tests/unit -q` 全綠；models / config / state machine / geo / registry 可獨立 import。

---

## Phase 3: User Story 1 — 完整偵測-接管-制壓流程對外提供狀態查詢 (Priority: P1) 🎯 MVP

**Goal**: 以單一無人機走完 `IDLE → DETECTED → MITIGATING → NEUTRALIZED → 移除` 的主流程；`GET /detections` 對外提供狀態；`POST /command/takeover` 在 MITIGATING 觸發恰一次（spec.md US1、FR-SC-001..018、SC-SC-001/002/005/007/008/009/011/012）。

**Independent Test**: 啟動服務 + `map_sim_stub` + `uds_stub`，以 HTTP client 每秒輪詢 `/detections`，35s 內依序觀察到 `[]` → `DETECTED` → `MITIGATING` → `NEUTRALIZED` → `[]`，UDS 收到 1 次 takeover（quickstart.md §4）。

### Contract Tests for US1 (先寫且先 FAIL) ⚠️

- [X] T024 [P] [US1] 撰寫 `services/sentrycs-sim/tests/contract/test_detections_schema.py`：凍結 `GET /detections` wire schema（contracts/http-status-api.md §2.1.3 全 14 欄位、`extra="forbid"`、`IDLE` 不得出現、`[]` 為空語意、`is_landed ⇔ NEUTRALIZED`、`timestamp` 以 `Z` 結尾）
- [X] T025 [P] [US1] 撰寫 `services/sentrycs-sim/tests/contract/test_detection_by_uid.py`：`GET /detection/{uid}` 200 schema 同 §2.1.3、404 body `{"status":"error","reason":"not_found"}`、IDLE 目標亦回 404（contracts §2.2）
- [X] T026 [P] [US1] 撰寫 `services/sentrycs-sim/tests/contract/test_takeover_caller.py`：完整覆蓋 contracts/takeover-caller.md §6 測試矩陣——`test_takeover_body_exact_4_fields`、`test_takeover_drone_id_is_uid`、`test_takeover_target_alt_m_is_zero`、`test_takeover_sent_once_per_drone`、`test_takeover_200_transitions_to_mitigating`、`test_takeover_400_stays_detected_no_retry`、`test_takeover_404_stays_detected_no_retry`、`test_takeover_timeout_retries_next_tick`、`test_takeover_no_body_parsing_required`、`test_takeover_no_in_flight_dup`（409 測試移到 US3）
- [X] T027 [P] [US1] 撰寫 `services/sentrycs-sim/tests/contract/test_health_schema.py`：`GET /health` 200 + `{status,uptime_s,tracked_drones,map_sim_reachable}` 四欄位（contracts §2.3；SC-SC-011）

### Unit Tests for US1 (先寫且先 FAIL) ⚠️

- [X] T028 [P] [US1] 撰寫 `services/sentrycs-sim/tests/unit/test_mapsim_client.py`：`fetch_objects_with_retry` 指數退避 1→2→4→10s（可注入 `fake_sleep`）；timeout / 5xx / connection refused 各自進退避；成功後恢復 0.5s；`is_lost=true` 物件於 client 層或 loop 層過濾（FR-SC-007、FR-SC-009；research.md R5）
- [X] T029 [P] [US1] 撰寫 `services/sentrycs-sim/tests/unit/test_uds_client.py`：`call_takeover(track)` 對 200/400/404/409/timeout/5xx/connection_refused 各回對應 `TakeoverResult`；body 僅 4 欄位（`drone_id/target_lat/target_lon/target_alt_m`）、`target_alt_m == 0.0`、無 `descent_speed_ms`（takeover-caller.md §2）
- [X] T030 [P] [US1] 撰寫 `services/sentrycs-sim/tests/unit/test_scenario_unknown_uid.py`：Map Sim 回傳場景 YAML 未登記的 `uid` 時，DroneTrack `model="Unknown"` 並產生 1 筆 `unregistered_uid` WARN/ERROR event（FR-SC-016、data-model.md §3.1）

### Integration Tests for US1 (先寫且先 FAIL) ⚠️

- [X] T031 [P] [US1] 撰寫 `services/sentrycs-sim/tests/integration/test_end_to_end_lifecycle.py`：freeze_time + map_sim_stub + uds_stub，驗證 `detected_at_s=5 / mitigating_at_s=20 / neutralized_at_s=35` 場景下 `/detections` 的狀態序列與時序（SC-SC-001 <1s、<500ms；SC-SC-005）；NEUTRALIZED 後 30s 移除（FR-SC-005）
- [X] T032 [P] [US1] 撰寫 `services/sentrycs-sim/tests/integration/test_is_lost_filter.py`：Map Sim 回 `is_lost=true` 的物件 100% 不出現於 `/detections` 且不觸發狀態轉移（SC-SC-009）
- [X] T033 [P] [US1] 撰寫 `services/sentrycs-sim/tests/integration/test_takeover_400_404.py`：UDS 400/404 → track 保留 `DETECTED`、`takeover_sent=True`（不重送）、下一 tick 不再發出；其他正常目標不受影響
- [X] T034 [P] [US1] 撰寫 `services/sentrycs-sim/tests/integration/test_mapsim_unavailable.py`：Map Sim 下線 30s 期間 `/detections` 持續 200、既有非 IDLE 狀態不回退；恢復後 ≤1s 追上最新位置（SC-SC-007、FR-SC-009）
- [X] T035 [P] [US1] 撰寫 `services/sentrycs-sim/tests/integration/test_mitigating_disappear.py`：MITIGATING 期間目標自 Map Sim 消失 10s 寬限後轉 NEUTRALIZED（Edge Cases §4；data-model.md §1）
- [X] T036 [P] [US1] 撰寫 `services/sentrycs-sim/tests/integration/test_detected_disappear_rollback.py`：目標於 DETECTED 階段自 Map Sim 移除 → 回 IDLE（自 registry 移除），不觸發 takeover（Edge Cases）
- [X] T037 [P] [US1] 撰寫 `services/sentrycs-sim/tests/integration/test_graceful_shutdown.py`：SIGINT 觸發後 `runner.cleanup()` + cancel tasks + `ClientSession.close()` 在 3s 內完成；關閉階段不再發新 takeover（FR-SC-025、SC-SC-012；research.md R9）
- [X] T038 [P] [US1] 撰寫 `services/sentrycs-sim/tests/integration/test_health_ready.py`：CLI 啟動後 <2s `GET /health` 回 200（SC-SC-011）

### Implementation for US1

- [X] T039 [P] [US1] 實作 `services/sentrycs-sim/src/sentrycs_sim/mapsim/__init__.py` + `client.py`：aiohttp ClientSession；`fetch_objects(lat, lon, radius_m=8000)`、`fetch_objects_with_retry(..., sleep=asyncio.sleep)` 指數退避 1/2/4/10s、throttled `mapsim_unavailable` log（research.md R5、R10）
- [X] T040 [P] [US1] 實作 `services/sentrycs-sim/src/sentrycs_sim/uds/__init__.py` + `client.py`：aiohttp ClientSession（`ClientTimeout(total=uds_timeout_s)`）、`call_takeover(track) -> TakeoverResult`、pre-send latch `if track.takeover_sent: return`、發送 `takeover_request` / `takeover_response` 結構化 event（takeover-caller.md §4、§5）
- [X] T041 [US1] 實作 `services/sentrycs-sim/src/sentrycs_sim/api/__init__.py` + `server.py`：`aiohttp.web.Application`、`GET /detections`（`registry.snapshot()`）、`GET /detection/{uid}`（200/404）、`GET /health`（`uptime_s`、`tracked_drones`、`map_sim_reachable`）；handler 以純 dict 投影，無副作用（contracts §2）
- [X] T042 [US1] 實作 `services/sentrycs-sim/src/sentrycs_sim/loop.py`：主 2Hz 迴圈——`while not shutdown.is_set(): await mapsim.fetch_objects_with_retry(); registry.sync(objects); for track: state_machine.advance(track, now); schedule takeover tasks`；per-drone asyncio.Task；`shutdown` asyncio.Event；`map_sim_reachable` 旗標（research.md R4、R9）
- [X] T043 [US1] 實作 `services/sentrycs-sim/src/sentrycs_sim/cli.py`：argparse `--scenario` / `--api-port` / `--verbose`；`main()` = 載入 config → configure_logging → 起 aiohttp runner :7070 → 起 loop task → signal handler → graceful shutdown 3s timeout（FR-SC-021..025）
- [X] T044 [US1] 實作 `services/sentrycs-sim/src/sentrycs_sim/__main__.py`：`from .cli import main; main()`（quickstart.md §3）

**Checkpoint**: `pytest tests/contract tests/unit -q -k "not us2 and not us3"` 全綠；`pytest tests/integration/test_end_to_end_lifecycle.py -q` 全綠；quickstart.md §4 手動流程可跑通 → MVP 可對外 demo。

---

## Phase 4: User Story 2 — 操控者 RF 定向位置模擬 (Priority: P1)

**Goal**: 每筆偵測 JSON 於 DroneTrack 建立時一次性計算 `operator_lat/operator_lon`（WGS84 destination formula），整個場景期間**完全不變**；輸出四個 operator_* 欄位（spec.md US2、FR-SC-019/020、SC-SC-004）。

**Independent Test**: 以 `operator_bearing_deg=225, operator_distance_m=300` 啟動；無人機位置隨時間變動；`/detections` 的 `operator_lat/operator_lon` 連續 10+ 次輪詢 float 完全相等（quickstart.md §5）。

### Integration Tests for US2 (先寫且先 FAIL) ⚠️

> operator 單點精度已由 T010 unit test 涵蓋；此階段專注「整場景不變」與「JSON 欄位輸出」

- [X] T045 [P] [US2] 撰寫 `services/sentrycs-sim/tests/integration/test_operator_static.py`：場景跑 60s 期間無人機位置改變 ≥ 10 次；每次 `/detection/TRK-001` 的 `operator_lat`、`operator_lon` **完全相等**（float bit-for-bit，SC-SC-004 抖動=0）；`operator_distance_m`、`operator_bearing_deg` echo 場景值
- [X] T046 [P] [US2] 撰寫 `services/sentrycs-sim/tests/integration/test_operator_locked_log.py`：`--verbose` 下每個 track 首次建立時產生 1 筆 `operator_locked` event（`uid, operator_lat, operator_lon, bearing_deg, distance_m`；research.md R10）

### Implementation for US2

- [X] T047 [US2] 在 `services/sentrycs-sim/src/sentrycs_sim/loop.py` 的 track-creation 路徑呼叫 `wgs84.destination_point(...)` 一次，構造 **frozen** `OperatorEstimate` 並賦給 `DroneTrack.operator`；後續 tick **MUST NOT** 重算（research.md R3；data-model.md §3.2 Invariant）
- [X] T048 [US2] 在 `services/sentrycs-sim/src/sentrycs_sim/models/detection.py` 的 `DetectionResponse.from_track()` 投影方法中直接 echo `track.operator.operator_lat/lon/distance_m/bearing_deg`（不再計算；FR-SC-020）
- [X] T049 [US2] 在 `state/machine.py` 或 `loop.py` 的首次建立 track 時新增 `operator_locked` structlog event（`uid, operator_lat, operator_lon, bearing_deg, distance_m`）

**Checkpoint**: `pytest tests/integration/test_operator_static.py -q` 全綠；quickstart.md §5 手動驗證通過。

---

## Phase 5: User Story 3 — 多無人機並行偵測與個別接管 (Priority: P2)

**Goal**: 單一場景 YAML 列多架無人機，各自獨立 async task 推進；一架 takeover 409 或錯誤不影響他架；`/detections` 並發 5 client p95 < 100 ms（spec.md US3、FR-SC-010/011/018/023、SC-SC-003/006/008）。

**Independent Test**: 載入 TRK-001 (`detected_at_s=5`) + TRK-002 (`detected_at_s=30`)；t=35s 時 `/detections` 同時含兩 uid，狀態獨立；UDS 對其一回 409 時另一架仍進展（quickstart.md §6）。

### Integration Tests for US3 (先寫且先 FAIL) ⚠️

- [X] T050 [P] [US3] 撰寫 `services/sentrycs-sim/tests/integration/test_multi_drone.py`：2 架無人機（不同 `detected_at_s` / `mitigating_at_s`）同時在 map_sim_stub；t=35s `/detections` 含兩 uid、狀態獨立；UDS 收到 2 次 takeover、各自 `drone_id` 不同
- [X] T051 [P] [US3] 撰寫 `services/sentrycs-sim/tests/integration/test_takeover_409.py`：UDS 對某一 uid 回 409 → ≤1s 內進入 MITIGATING、`takeover_sent=True`、不重送；另一 uid 狀態機持續推進（FR-SC-011、SC-SC-008）
- [X] T052 [P] [US3] 撰寫 `services/sentrycs-sim/tests/integration/test_per_drone_isolation.py`：uds_stub 對 TRK-002 注入 5s timeout；TRK-001 的 1Hz 快照更新仍 <1s/次（FR-SC-023、Edge Cases §7）
- [X] T053 [P] [US3] 撰寫 `services/sentrycs-sim/tests/integration/test_api_concurrency.py`：5 個並發 asyncio task 各以 1Hz 呼叫 `/detections` 共 30 次；p95 < 100 ms、錯誤率 0%、每次回傳為一致快照（所有 uid 同一 `timestamp` rail）（SC-SC-003、FR-SC-018）
- [X] T054 [P] [US3] 撰寫 `services/sentrycs-sim/tests/integration/test_multi_drone_scale.py`：5 架同時載入；每架狀態轉移時序誤差 < 1s（SC-SC-006；CPU 斷言可留 smoke-only）

### Implementation for US3

- [X] T055 [US3] 在 `services/sentrycs-sim/src/sentrycs_sim/loop.py` 為每個 track 建立 per-drone `asyncio.Task`（集中於 `asyncio.TaskGroup` 或 dict）；其中 takeover I/O 完全非阻塞主迴圈（research.md R4；FR-SC-023）
- [X] T056 [US3] 在 `uds/client.py` 新增 409 → `TakeoverResult.ALREADY_TAKEN_OVER` 映射；state_machine 將其與 200 同樣推進 DETECTED→MITIGATING 並 latch `takeover_sent`（takeover-caller.md §4、research.md R6）
- [X] T057 [US3] 在 `api/server.py` 確保 `/detections` handler 以 `list(registry._tracks.values())` 原子複製後逐筆投影（不 await 任何 I/O），使 5 並發 handler 共享同一主 loop 不互鎖（contracts §1.3、FR-SC-018）

**Checkpoint**: `pytest tests/integration -q`（全部 integration，含 US1/US2/US3）全綠；quickstart.md §6 手動驗證通過。

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 跨 Story 的可觀測性、文件、smoke、lint 收尾。

- [X] T058 [P] 補完 `services/sentrycs-sim/src/sentrycs_sim/logging.py` 的 event 欄位凍結：確保 `state_transition / mapsim_query / mapsim_unavailable / takeover_request / takeover_response / operator_locked / unregistered_uid / http_request / shutdown` 9 個 event 皆含 research.md R10 表定義欄位
- [X] T059 [P] 在 `services/sentrycs-sim/tests/unit/test_logging.py` 追加斷言：9 個 event 的必填欄位（FR-SC-024、SC-SC-010）
- [X] T060 [P] 為 `GET /health` 新增 http_request middleware：每筆 API 請求輸出 1 筆 `http_request` event（`method, path, status, latency_ms`）
- [X] T061 [P] 對 `services/sentrycs-sim/` 跑 `ruff check . && black --check .` 並修至 0 issue
- [X] T062 [P] 更新 `services/sentrycs-sim/README.md`：補 CLI 參數表、structured log event 清單、連結到 `specs/004-sentrycs-sim/quickstart.md`
- [X] T063 [P] 完成 `services/sentrycs-sim/scripts/smoke.sh`：啟動 → `/health` → `/detections` → SIGINT；< 10s 結束且 exit 0
- [X] T064 手動跑 `specs/004-sentrycs-sim/quickstart.md` §4–§8 全部步驟，記錄任何偏差並修復（最終 end-to-end 驗收）

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup** → 無依賴
- **Phase 2 Foundational** → 依賴 Phase 1；**阻擋**所有 User Story
- **Phase 3 US1 (P1 MVP)** → 依賴 Phase 2；為 MVP，MUST 先完成
- **Phase 4 US2 (P1)** → 依賴 Phase 2；T047/T048 需 T013/T014/T016（models + geo）與 T042（loop track 建立路徑），故在 US1 實作後期可並行
- **Phase 5 US3 (P2)** → 依賴 Phase 2 + Phase 3（loop、state_machine、uds client 已實作）；T055–T057 直接擴充 US1 既有檔
- **Phase 6 Polish** → 依賴所有 User Story 完成

### Task-level critical path

```text
T001 → T002 → T017（config，pydantic root）
                    ↘ T018（state machine）↘
T012 + T013..T016（models/logging/geo，可並行）→ T019（registry）→ T039/T040（mapsim/uds client）→ T041（api）→ T042（loop）→ T043（cli）→ T044（__main__）
                                                                                                                                  ↘ T047..T049（US2）
                                                                                                                                  ↘ T055..T057（US3）
```

### Within each User Story

- **測試順序（TDD）**：Contract → Unit → Integration → Implementation
- **實作順序**：models → clients（mapsim/uds）→ api handler → loop → cli
- 同層級測試 / 不同檔實作皆可並行（標 [P]）

### Parallel Opportunities（按 Phase 摘要）

- Phase 1：T003..T007 可並行
- Phase 2 測試：T008..T011 可並行；實作：T012..T016 可並行；fixtures T020..T023 可並行
- Phase 3 contract：T024..T027 可並行；unit：T028..T030 可並行；integration：T031..T038 可並行；實作：T039/T040 可並行（不同檔），T041/T042 序列（api 先 / loop 後）
- Phase 4 測試 T045/T046 可並行；實作 T047 先 → T048/T049 可並行
- Phase 5 測試 T050..T054 可並行；實作 T055→T056/T057 可並行
- Phase 6 幾乎全 [P]

### Parallel Example: 開始 Phase 2 測試（先 FAIL）

同一 developer session 可並行啟動：

```text
T008 (logging test) + T009 (config test) + T010 (operator_geo test) + T011 (state_machine test)
→ 全部 FAIL（尚無實作）→ 進入 T012..T019 實作 → 重跑全綠
```

### Parallel Example: Phase 3 US1 contract + unit + integration 測試先寫

```text
# Contract（4 檔）
T024 + T025 + T026 + T027
# Unit（3 檔）
T028 + T029 + T030
# Integration（8 檔）
T031 + T032 + T033 + T034 + T035 + T036 + T037 + T038
→ 全部 FAIL → 再進 T039..T044 實作
```

---

## Implementation Strategy

### MVP 路線（建議）

1. **Phase 1 + Phase 2**：2–3 個 session 完成骨架 + 基礎（~23 tasks）
2. **Phase 3 US1（MVP）**：專注單機生命週期 + status API + 主要容錯（21 tasks，T024–T044）→ 可對外 demo 主劇情
3. **Phase 4 US2**：5 tasks（T045–T049），在 US1 之後立刻補上 operator 位置（P1 但輕量）→ TAK 上操控者圖示到位
4. **Phase 5 US3**：8 tasks（T050–T057），多機擴展 + 409 隔離 + API 並發 → Demo 擴展場景
5. **Phase 6 Polish**：7 tasks，event 欄位凍結 + lint + smoke + quickstart 驗收

### Incremental Delivery Checkpoints

- **After Phase 2**：`pytest tests/unit -q` 全綠，無 runtime
- **After Phase 3 (MVP)**：`python -m sentrycs_sim --scenario config/local.yaml` 可跑通 quickstart.md §4 全部步驟；SC-SC-001/002/005/007/008/009/011/012 達標
- **After Phase 4**：quickstart.md §5 operator 零抖動達標；SC-SC-004 達標
- **After Phase 5**：quickstart.md §6 多機 + 409 達標；SC-SC-003/006 達標
- **After Phase 6**：SC-SC-010 日誌欄位凍結達標；smoke.sh / ruff / black 全綠

### Risk Mitigations

- **freezegun 不攔 asyncio.sleep**：T023 fixture 與 T039 mapsim client 設計以**可注入 sleep** 規避；unit test 退避 30s 可於 < 1ms 跑完
- **operator 位置抖動**：T047 在 track 首次建立時 **一次性** 計算 + `frozen=True` 凍結；T048 投影純 echo，無重算路徑
- **takeover 重送**：T040 pre-send latch（takeover-caller.md §5.1）+ T011 單元測試 + T026 契約測試雙保險
- **Map Sim 下線時狀態回退**：T034 integration 專測此情境；loop 設計上「查 Map Sim 失敗 → skip 本 tick 狀態轉移」，不得誤更新 DroneTrack

---

## Task Count Summary

| Phase | Count | 其中 Tests | 其中 Implementation |
| --- | --- | --- | --- |
| Phase 1 Setup | 7 | 0 | 7 |
| Phase 2 Foundational | 16 | 4 unit + 4 fixtures | 8 |
| Phase 3 US1 (MVP) | 21 | 4 contract + 3 unit + 8 integration | 6 |
| Phase 4 US2 | 5 | 2 integration | 3 |
| Phase 5 US3 | 8 | 5 integration | 3 |
| Phase 6 Polish | 7 | (log assertions 加進 T059) | 7 |
| **Total** | **64** | **30** | **34** |

**Suggested MVP scope**: Phase 1 + Phase 2 + Phase 3（T001–T044，共 44 tasks）。US2/US3 為增量交付。

**Independent Test Criteria 對映**：

- **US1**：quickstart.md §4 全步驟 / T031 test_end_to_end_lifecycle
- **US2**：quickstart.md §5 / T045 test_operator_static
- **US3**：quickstart.md §6 / T050 test_multi_drone + T053 test_api_concurrency

**Format validation**: ✅ 所有 64 個任務皆採 `- [ ] Txxx [P?] [US?] Description with file path` 格式；Setup / Foundational / Polish 無 Story 標籤；US1/US2/US3 皆有對應 `[US1]`/`[US2]`/`[US3]`；檔案路徑皆為相對 repo root 的精確 path。
