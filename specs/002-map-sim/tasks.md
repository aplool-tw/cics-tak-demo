---
description: "Task list for Map Simulator (002-map-sim)"
---

# Tasks: Map Simulator (Map Sim)

**Input**: `specs/002-map-sim/` — `spec.md`、`plan.md`、`data-model.md`、`research.md`、
`contracts/rest-api.md`、`quickstart.md`

**Scope**：`services/map-sim/`（對稱 `services/uds/`），Python 3.11+ / aiohttp / pydantic v2 /
structlog / freezegun。所有路徑以 repo root 為基準；`services/map-sim/` 為本 feature 的 Python 子專案
根目錄。

**Test discipline**：契約測試（§Phase 2）與整合/單元測試（§Phase 3）**MUST** 先撰寫並在沒有
implementation 下 FAIL（紅燈），才進入 Phase 4 之後的實作。契約測試以 `contracts/rest-api.md` 的精確
`reason` 字串做斷言；TTL 時序測試以 `freezegun` 推進虛擬時鐘，**不**依賴真實 `asyncio.sleep`（見
research.md §2 與 quickstart.md §5.3）。

**Format**：`- [ ] T### [P?] [US?] 說明（含檔案路徑）`

- `[P]`：可與同 Phase 其他 `[P]` 任務併行（不同檔案、無交叉依賴）
- `[US1] / [US2] / [US3]`：對應 spec.md §2 的三個 user story；Setup / Foundational / Polish 階段無
  story 標籤

---

## Phase 1: Setup（Shared Infrastructure）

**Purpose**：建立 `services/map-sim/` Python 子專案骨架，使 `pip install -e ".[dev]"` 與 `pytest` 即可
執行（即使尚無測試通過）。

- [ ] T001 建立 `services/map-sim/` 目錄樹（src/map_sim/{api,cleanup,geo,models,registry}/、
  tests/{contract,integration,unit}/），各子目錄放入空 `__init__.py`（對齊 plan.md §Project Structure）。
- [ ] T002 撰寫 `services/map-sim/pyproject.toml`：`[project]` name=`map-sim`、python>=3.11、依賴
  `aiohttp>=3.9` / `pydantic>=2.6` / `structlog>=24.1`；`[project.optional-dependencies].dev` 含
  `pytest>=8.0` / `pytest-asyncio>=0.23` / `freezegun>=1.4` / `geopy>=2.4`（僅測試用）/ `ruff>=0.4` /
  `black>=24.3`；`[project.scripts]` `map-sim = "map_sim.cli:main"`；`[tool.pytest.ini_options]`
  `asyncio_mode = "auto"`、`testpaths = ["tests"]`（對齊 `services/uds/pyproject.toml`）。
- [ ] T003 [P] 撰寫 `services/map-sim/README.md`：一段描述 + 指向 `specs/002-map-sim/spec.md` 與
  `specs/002-map-sim/quickstart.md`；標註 `:8090` 預設 port 與 CLI 參數列表。
- [ ] T004 [P] 於 `services/map-sim/pyproject.toml` 加入 `[tool.ruff]` / `[tool.black]` 設定（line-length
  100、target-version py311），與 `services/uds/` 一致。
- [ ] T005 建立 `services/map-sim/tests/conftest.py`：提供 (a) `registry` fixture（獨立 `ObjectRegistry`
  instance，可覆寫 ttl 參數）、(b) `aiohttp_client` fixture（以 `aiohttp.test_utils.TestClient` 包裝
  建立好的 app、注入 in-memory registry）、(c) `frozen_time` helper（以 `freezegun.freeze_time` context
  manager 提供 `tick(seconds)` 便利函式）。Fixtures 先以 `pytest.importorskip`/skip 方式讓尚未存在的
  implementation 不阻斷 collection。

**Checkpoint**：`cd services/map-sim && pip install -e ".[dev]" && pytest --collect-only` 可成功 collect
（即使 0 tests passed）。

---

## Phase 2: Foundational Contract & Integration Tests（紅燈；必須先失敗）

**Purpose**：依 `contracts/rest-api.md` 與 spec.md Acceptance Scenarios / Edge Cases 撰寫契約與整合測試。
所有測試此時 **MUST FAIL**（因尚無 implementation）。此階段全部任務都是不同測試檔，互不衝突，絕大多數
可 `[P]`。

### 2.1 `POST /objects/update` 契約（User Story 1）

**Target file**：`services/map-sim/tests/contract/test_update_contract.py`（同檔多個 test function，
可併行撰寫但同一任務內）。

- [ ] T006 [P] [US1] 撰寫 `tests/contract/test_update_contract.py::test_update_happy_path`：
  POST 8 欄位合法 payload → 200、body 含 `status=="updated"`、`drone_id` echo、`registered_at` 為 ISO
  8601 UTC（`Z` 後綴）；隨後 `GET /objects/all` 能看到該物件（對應 US1 Acceptance 1、FR-MS-001）。
- [ ] T007 [P] [US1] 撰寫 `tests/contract/test_update_contract.py::test_update_overwrites_same_drone`：
  對同 `drone_id` 先後送兩筆不同 `lat/lon/status` → 第二筆完全覆寫；`last_seen_at` 重設（US1
  Acceptance 2、Edge Case「重複 drone_id 更新」）。
- [ ] T008 [P] [US1] 撰寫 `tests/contract/test_update_contract.py::test_update_accepts_extra_fields`
  —— **Clarification Q1 寬鬆 payload 斷言**：body 含 `model` / `operator_lat` / `operator_lon` 等非契約
  欄位 → 200；GET /objects/all 中該 drone 只含 8 個契約欄位（FR-MS-002、contracts §2、US1 Acceptance 4）。
- [ ] T009 [P] [US1] 撰寫 `tests/contract/test_update_contract.py::test_update_missing_required_field`
  —— 參數化 8 個欄位，逐一缺漏 → 400、`reason == "missing required field: <name>"`；**registry 不變**
  （FR-MS-015 副作用隔離；US1 Acceptance 3、Edge Case「缺必填欄位的 POST」）。
- [ ] T010 [P] [US1] 撰寫 `tests/contract/test_update_contract.py::test_update_invalid_type`：
  數值欄位給字串、`status` 為空字串、`drone_id` 為空字串 → 400 `reason == "invalid type: <name>"`
  （contracts §3.1.2.2）。
- [ ] T011 [P] [US1] 撰寫 `tests/contract/test_update_contract.py::test_update_invalid_timestamp`：
  `timestamp` 為 `"not-a-timestamp"` 或缺時區 → 400 `reason == "invalid type: timestamp"`
  （Edge Case「非法 timestamp 格式」）。
- [ ] T012 [P] [US1] 撰寫 `tests/contract/test_update_contract.py::test_update_invalid_json`：
  body 為 `"{not json"` → 400 `reason == "invalid json"`（contracts §5）。
- [ ] T013 [P] [US1] 撰寫 `tests/contract/test_update_contract.py::test_update_landed_is_accepted`：
  `status="LANDED"` → 200；物件仍保留於 registry、`status` 不被改寫（US1 Acceptance 5、FR-MS-014 前半）。
- [ ] T014 [P] [US1] 撰寫 `tests/contract/test_update_contract.py::test_update_400_does_not_mutate_registry`
  —— 明確 regression：呼叫一次成功 update，再發送一筆 400 payload（同 `drone_id`）→ registry 的
  `last_seen_at` 不變（以 freezegun 鎖時鐘比對；FR-MS-015、SC-MS-006 副作用邊界）。

### 2.2 `GET /objects` 契約（User Story 2）

**Target file**：`services/map-sim/tests/contract/test_query_contract.py`。

- [ ] T015 [P] [US2] 撰寫 `tests/contract/test_query_contract.py::test_query_happy_path_radar_radius`：
  預填 3 架（1 km / 3 km / 6 km 外）；`radius_m=4800` → 200、`count==2`、`objects[]` 依 `distance_m`
  升冪；每筆含完整 8 欄位 + `distance_m` + `last_seen_s` + `is_lost=false`（US2 Acceptance 1、
  FR-MS-003、contracts §3.2.2.1 排序契約）。
- [ ] T016 [P] [US2] 撰寫 `tests/contract/test_query_contract.py::test_query_sentrycs_radius`：
  同一資料集 `radius_m=8000` → 3 筆全出、升冪排序（US2 Acceptance 2）。
- [ ] T017 [P] [US2] 撰寫 `tests/contract/test_query_contract.py::test_query_empty_result_returns_200_count_0`：
  查詢中心在南太平洋 → 200、`count==0`、`objects==[]`；**不得**回 404（US2 Acceptance 3、FR-MS-004、
  Edge Case「未知 drone_id 的查詢」）。
- [ ] T018 [P] [US2] 撰寫 `tests/contract/test_query_contract.py::test_query_unknown_drone_id_empty`：
  registry 空 → `GET /objects?lat=0&lon=0&radius_m=1000` → 200、count=0（Edge Case「Map Sim 啟動
  時登錄表為空」）。
- [ ] T019 [P] [US2] 撰寫 `tests/contract/test_query_contract.py::test_query_include_lost_false_hides_lost`
  —— 以 freezegun 讓一物件進入 `[ttl_warn_s, ttl_remove_s)` lost 區間，**未帶** `include_lost` 或
  `include_lost=false` → 該物件不出現（US2 Acceptance 4、FR-MS-006）。
- [ ] T020 [P] [US2] 撰寫 `tests/contract/test_query_contract.py::test_query_include_lost_true_preserves_status`
  —— **Clarification Q1 核心斷言**：同情境但 `include_lost=true` → 該物件出現；response `objects[0].status`
  **等於原始 FlightState 字串**（例如 `"FLYING_NORMAL"` 或 `"LANDED"`），**絕不**為 `"lost"`；`is_lost=true`
  為明確布林欄位且必存在（US2 Acceptance 4、FR-MS-006、contracts §3.2.2.1 Q1 落點）。
- [ ] T021 [P] [US2] 撰寫 `tests/contract/test_query_contract.py::test_query_is_lost_explicit_false`：
  `include_lost=false` 正常情境下，回應中所有 `objects[].is_lost` 必為 `false`（明確輸出、非省略；
  contracts §3.2.2.1）。
- [ ] T022 [P] [US2] 撰寫 `tests/contract/test_query_contract.py::test_query_object_after_ttl_remove_hidden`
  —— 物件 `age_s >= ttl_remove_s` 但尚未被背景 cleanup 移除（覆寫 registry `ttl_remove_s=1`、freezegun
  tick 2 s）→ 即使 `include_lost=true` 也不可見（FR-MS-006 末段、data-model.md §3 query_radius 註）。
- [ ] T023 [P] [US2] 撰寫 `tests/contract/test_query_contract.py::test_query_missing_required_parameter`：
  分別缺 `lat` / `lon` / `radius_m` → 400、`reason == "missing required parameter: <name>"`（FR-MS-005、
  US2 Acceptance 5、contracts §3.2.2.2）。
- [ ] T024 [P] [US2] 撰寫 `tests/contract/test_query_contract.py::test_query_invalid_type`：
  `lat=abc` / `radius_m=xyz` / `include_lost=maybe` → 400 `reason == "invalid type: <name>"`
  （research.md §5、contracts §3.2.2.2）。
- [ ] T025 [P] [US2] 撰寫 `tests/contract/test_query_contract.py::test_query_radius_non_positive`：
  `radius_m=0` 與 `radius_m=-1` → 400、`reason == "radius_m must be > 0"`（US2 Acceptance 6、
  Edge Case「radius_m = 0 或負值」）。
- [ ] T026 [P] [US2] 撰寫 `tests/contract/test_query_contract.py::test_query_invalid_coordinates`：
  `lat=91` / `lon=181` → 400、`reason == "invalid coordinates"`（contracts §3.2.2.2）。
- [ ] T027 [P] [US2] 撰寫 `tests/contract/test_query_contract.py::test_query_radius_extreme_large`：
  `radius_m=2e7`（>地球半周長）→ 200、回傳所有活躍物件、仍按距離升冪（Edge Case「radius_m 極大值」）。
- [ ] T028 [P] [US2] 撰寫 `tests/contract/test_query_contract.py::test_query_include_lost_case_insensitive`：
  `include_lost=TRUE` / `True` / `false` → 皆接受；`include_lost=yes` → 400 `invalid type`（research.md §5）。
- [ ] T029 [P] [US2] 撰寫 `tests/contract/test_query_contract.py::test_query_unknown_params_ignored`：
  `?lat=&lon=&radius_m=&foo=bar` → 200；未知參數被忽略（contracts §2）。

### 2.3 Admin / Health 契約（除錯端點 + FR-MS-010）

**Target file**：`services/map-sim/tests/contract/test_health_contract.py`。

- [ ] T030 [P] 撰寫 `tests/contract/test_health_contract.py::test_health_ok`：
  `GET /health` → 200、`status=="ok"`、`registered_objects` 為整數、`uptime_s` 為非負 float（FR-MS-010、
  contracts §3.3）。
- [ ] T031 [P] 撰寫 `tests/contract/test_health_contract.py::test_health_registered_objects_matches_registry`：
  連推 3 筆不同 `drone_id` → `registered_objects == 3`（含 lost，對齊 `/objects/all` total）。
- [ ] T032 [P] 撰寫 `tests/contract/test_health_contract.py::test_objects_all_totals`：
  預填 2 筆 active + 1 筆 lost（freezegun）→ `GET /objects/all` 回 `total=3 / active=2 / lost=1`；
  `objects[]` 每筆均有 `is_lost` 欄位、**status 保留原值**（FR-MS-008、contracts §4.1、data-model.md §4.4）。
- [ ] T033 [P] 撰寫 `tests/contract/test_health_contract.py::test_delete_drone_removed_and_not_found`：
  DELETE 現存 id → 200 `{"status":"removed",...}`；DELETE 不存在 id → 200 `{"status":"not_found",...}`
  （FR-MS-009、contracts §4.2）。

---

## Phase 3: Foundational Integration & Unit Tests（紅燈續）

### 3.1 TTL lifecycle 整合測試（User Story 3）

**Target file**：`services/map-sim/tests/integration/test_ttl_lifecycle.py`（freezegun driven，不用真實
sleep）。

- [ ] T034 [P] [US3] 撰寫 `tests/integration/test_ttl_lifecycle.py::test_active_before_ttl_warn`：
  `ttl_warn_s=5, ttl_remove_s=10`；t=0 update → t=4.9 `GET /objects` 預設查詢見此物件、`is_lost=false`
  （US3 Acceptance 1 上半）。
- [ ] T035 [P] [US3] 撰寫 `tests/integration/test_ttl_lifecycle.py::test_lost_between_warn_and_remove`：
  t=6 → 預設查詢不回；`include_lost=true` 與 `/objects/all` 見之，`status` 原值未覆寫、
  `is_lost=true`、`last_seen_s >= 5.0`（US3 Acceptance 1、FR-MS-006、**Q1 核心**、SC-MS-003）。
- [ ] T036 [P] [US3] 撰寫 `tests/integration/test_ttl_lifecycle.py::test_removed_after_ttl_remove`：
  t=11.5 + 一輪 cleanup（手動 `await registry.cleanup_expired()` 或等待背景 task）→ `/objects/all` 不
  再包含此 id；任何查詢皆不可見（US3 Acceptance 2、FR-MS-006 末段、SC-MS-004）。
- [ ] T037 [P] [US3] 撰寫 `tests/integration/test_ttl_lifecycle.py::test_landed_visibility_window`：
  最後一筆 `status="LANDED"` → `[0, ttl_warn_s-1)` 秒預設查詢仍見 `status=="LANDED"`；
  `[ttl_warn_s, ttl_remove_s)` 轉 lost；超出 `ttl_remove_s` 消失；**全程 UDS 不呼叫 DELETE**
  （US3 Acceptance 3、FR-MS-014、SC-MS-009）。
- [ ] T038 [P] [US3] 撰寫 `tests/integration/test_ttl_lifecycle.py::test_update_resets_last_seen`：
  t=4 再 update 同 id → last_seen_at 重設；t=8 仍為 active（data-model.md §2 不變量）。
- [ ] T039 [P] [US3] 撰寫 `tests/integration/test_ttl_lifecycle.py::test_cleanup_period_bound`：
  背景 task `period_s=0.2`（測試覆寫），驗證從 `age_s > ttl_remove_s` 到 `_objects.pop` 的時間差 < `period_s
  + epsilon`（SC-MS-003 / SC-MS-004 精度上限）。

### 3.2 並發安全整合測試

**Target file**：`services/map-sim/tests/integration/test_concurrent_safety.py`。

- [ ] T040 [P] [US3] 撰寫 `tests/integration/test_concurrent_safety.py::test_concurrent_post_and_query`：
  以 `asyncio.gather` 併發發 100 筆 POST（5 drone_id 輪替）+ 50 筆 GET；所有 GET 回的 `objects[]` 每筆都
  有 8 + 3 個欄位齊全（不允許「半新半舊」混合）；`GET /objects/all` 的 `total` ≤ 唯一 drone_id 數（FR-MS-007、
  SC-MS-006）。
- [ ] T041 [P] [US3] 撰寫 `tests/integration/test_concurrent_safety.py::test_cleanup_does_not_corrupt_query`：
  併發 POST + 手動快速呼叫 `cleanup_expired()`（覆寫極短 TTL）→ GET 永不回傳已被 delete 的 id、
  也不 raise（US3 Acceptance 4、FR-MS-007、data-model.md §3 鎖語意）。

### 3.3 Unit tests

- [ ] T042 [P] 撰寫 `tests/unit/test_haversine.py`：對固定 10 組 `(lat1,lon1,lat2,lon2)`（含跨赤道、
  近極、短程），與 `geopy.distance.great_circle(..., radius=6371.0).meters` 交叉比對誤差 < 0.5%
  （SC-MS-005、research.md §1）。
- [ ] T043 [P] 撰寫 `tests/unit/test_drone_object.py`：測 `DroneObject.age_s(now)` / `is_lost(ttl_warn_s,
  now)`（邊界：`age_s == ttl_warn_s` 必為 `True`，`<` 必為 `False`）；測 `serialize` 輸出 `distance_m` 僅
  在帶 center 時存在、`timestamp` 以 `Z` 結尾、`status` 直接 echo（data-model.md §5）。
- [ ] T044 [P] 撰寫 `tests/unit/test_object_registry.py`：測 `update` 返回 `registered_at`；
  `query_radius` 過濾 + 排序 + include_lost 行為；`remove` 回傳 bool；`cleanup_expired` 回傳刪除數；
  `count`；以 `asyncio.gather` 併發呼叫驗證 lock 序列化（data-model.md §3）。

### 3.4 與 UDS 的端到端整合測試（必要覆蓋）

**Target file**：`services/map-sim/tests/integration/test_uds_push_end_to_end.py`。

- [ ] T045 [US1] 撰寫 `tests/integration/test_uds_push_end_to_end.py::test_uds_push_client_round_trip`
  —— 在同一 event loop 啟動 Map Sim aiohttp app（隨機 port / `aiohttp.test_utils.TestServer`），撰寫一個
  最小 UDS push client（async httpx 或 aiohttp.ClientSession）按 UDS `specs/001-uds/contracts/rest-api.md`
  §3.2 的 8 欄位 payload 連推 3 架 × 3 tick；之後呼叫 `GET /objects?lat=&lon=&radius_m=10000` →
  `count==3`、所有 drone 的 `status` 為原值、`is_lost=false`。**驗證 Map Sim 與 UDS 契約相容**（對應
  plan.md Summary 與 quickstart.md §4；本測試是 Map Sim 方的合約驗證，不實際 import `services/uds/`
  套件——以硬編碼 payload schema 重現，避免跨 service import 耦合）。

---

## Phase 4: Core Implementation（Models → Geo → Registry → Cleanup）

**目標**：讓 Phase 2/3 的單元測試與「不需要 HTTP 層」的 registry 測試由紅轉綠。順序內有依賴，
`[P]` 者可併行。

- [ ] T046 [P] 撰寫 `services/map-sim/src/map_sim/geo/haversine.py`：`haversine_m(lat1, lon1, lat2, lon2)
  -> float`，`R = 6_371_000.0`，以 `math.radians/sin/cos/atan2` 實作；純函式、無 side effect（research
  §1；與 `services/uds/src/uds/geo/wgs84.py` 常數一致，但獨立實作、不跨 service import）。→ 讓 T042 綠。
- [ ] T047 [P] 撰寫 `services/map-sim/src/map_sim/models/drone_object.py`：`@dataclass DroneObject`
  含 8 欄位 + `last_seen_at`；methods `age_s(now=None)`、`is_lost(ttl_warn_s, now=None)`；模組層級函式
  `serialize(obj, ttl_warn_s, now, *, center_lat=None, center_lon=None) -> dict`（依 data-model.md §5
  規格；`timestamp` 輸出以 `Z` 後綴；`is_lost` 明確輸出 true/false；帶 center 時多輸出 `distance_m`）。
  → 讓 T043 綠。
- [ ] T048 [P] 撰寫 `services/map-sim/src/map_sim/models/request.py`：pydantic v2 `UpdatePayload(BaseModel)`
  with `model_config = ConfigDict(extra="ignore")`；8 個必填欄位（`drone_id: str = Field(min_length=1)`、
  `status: str = Field(min_length=1)`、數值欄位為 float / `timestamp: datetime`）。**不**在此處做 lat/lon
  值域驗證（research §4；data-model.md §4.1）。
- [ ] T049 [P] 撰寫 `services/map-sim/src/map_sim/config.py`：`@dataclass(frozen=True) Settings(port: int
  = 8090, ttl_warn_s: float = 5.0, ttl_remove_s: float = 10.0, verbose: bool = False, cleanup_period_s:
  float = 2.0)`，`__post_init__` assert `ttl_remove_s >= ttl_warn_s > 0`（data-model.md §3、quickstart.md
  §2.2；`cleanup_period_s` 供測試覆寫為短週期）。
- [ ] T050 [P] 撰寫 `services/map-sim/src/map_sim/logging.py`：`setup_logging(verbose: bool)` 初始化
  structlog JSON renderer，event key 約定見 research §7；風格對齊 `services/uds/src/uds/logging.py`。
- [ ] T051 撰寫 `services/map-sim/src/map_sim/registry/object_registry.py`：`ObjectRegistry` 全實作
  （依 data-model.md §3）—— `__init__(ttl_warn_s, ttl_remove_s)`、`_lock = asyncio.Lock()`；`update` /
  `query_radius` / `get_all` / `remove` / `cleanup_expired` / `count`；**所有 public 方法皆以
  `async with self._lock` 入段；鎖內無任何 await 外部 I/O**（research §3 規則 1）。`query_radius`
  必須同時過濾 `age_s >= ttl_remove_s` 的暫留物件（data-model.md §3 註）。依賴 T046、T047。→ 讓 T044
  與 T040/T041 的 registry 層面綠。
- [ ] T052 撰寫 `services/map-sim/src/map_sim/cleanup/ttl_task.py`：
  `async def run_cleanup_loop(registry: ObjectRegistry, period_s: float, logger) -> None`：
  `while True: await asyncio.sleep(period_s); removed = await registry.cleanup_expired(); if removed:
  logger.info("ttl.cleanup", removed=removed)`；捕捉 `asyncio.CancelledError` 乾淨退出（research §2）。

---

## Phase 5: Interface — API Skeleton & Errors

- [ ] T053 撰寫 `services/map-sim/src/map_sim/api/errors.py`：
  (a) 穩定 `reason` 字串常數集合（`REASON_INVALID_JSON = "invalid json"`、
  `reason_missing_field(name)`、`reason_invalid_type(name)`、
  `reason_missing_param(name)`、`REASON_RADIUS_NON_POSITIVE = "radius_m must be > 0"`、
  `REASON_INVALID_COORDS = "invalid coordinates"`）；
  (b) `def error_response(reason: str, status: int = 400) -> web.Response` 輸出
  `{"status":"error","reason": reason}`（contracts §1.2 / §5）。
- [ ] T054 撰寫 `services/map-sim/src/map_sim/api/server.py`：
  `def build_app(settings: Settings) -> web.Application`；建 `ObjectRegistry`、掛 `app["registry"]` /
  `app["settings"]` / `app["started_at"]`；`on_startup` 啟動 `asyncio.create_task(run_cleanup_loop(...))`、
  `on_cleanup` cancel + await；註冊各 handler 路由（handler 實作於下階段）。依賴 T049 / T051 / T052 / T053。

---

## Phase 6: User Story 1 — `POST /objects/update` Handler（Priority: P1）🎯 MVP

**Goal**：完成 UDS → Map Sim 推送資料流，使 `tests/contract/test_update_contract.py` 全部綠燈，並讓
`tests/integration/test_uds_push_end_to_end.py` 有可用的入口。

**Independent Test**：啟動 `build_app`，以 `aiohttp.test_utils.TestClient` 連推 8 欄位 payload →
`GET /objects/all` 可見。

- [ ] T055 [US1] 撰寫 `services/map-sim/src/map_sim/api/handlers_update.py`：
  - `POST /objects/update`：`await request.json()` → `try UpdatePayload.model_validate(raw) except
    ValidationError` → 以自家 mapping 轉成穩定 `reason` 字串（不用 pydantic 預設訊息，研究 §4）：
    * `json.JSONDecodeError` → `invalid json`
    * 缺必填（type=="missing"）→ `missing required field: <loc>`
    * 空字串 / 型別錯 / `timestamp` 解析失敗 → `invalid type: <loc>`
  - 成功時 `registered_at = await app["registry"].update(**payload.model_dump(include=FIELDS_8))`；
    回 200 `{"status":"updated","drone_id":..., "registered_at": registered_at.isoformat().replace("+00:00","Z")}`。
  - **副作用隔離（FR-MS-015）**：所有 400 分支絕不呼叫 `registry.update`。
  - 寫 DEBUG log `update.ok` / WARNING log `update.rejected`（reason）。依賴 T048 / T051 / T053。
- [ ] T056 [US1] 於 `api/server.py` 註冊 `app.router.add_post("/objects/update", handlers_update.update)`。

**Checkpoint US1**：`pytest tests/contract/test_update_contract.py tests/integration/test_uds_push_end_to_end.py`
全綠；US1 MVP 可 demo（UDS 單向推送）。

---

## Phase 7: User Story 2 — `GET /objects` Handler（Priority: P1）

**Goal**：完成下游感測器資料查詢，使 `tests/contract/test_query_contract.py` 全部綠燈。

**Independent Test**：在 Phase 6 之後（registry 已可寫），預填數筆物件後以多組 query 驗證。

- [ ] T057 [US2] 撰寫 `services/map-sim/src/map_sim/api/handlers_query.py`：
  - `GET /objects`：**手動** parse query params（不用 pydantic，research §5）：
    * 缺 `lat` / `lon` / `radius_m` → `missing required parameter: <name>`
    * `float()` 失敗 → `invalid type: <name>`
    * `include_lost` case-insensitive 限定 `true/false`，其他 → `invalid type: include_lost`（未帶 →
      `False`）
    * `radius_m <= 0` → `"radius_m must be > 0"`
    * `lat ∉ [-90,90]` / `lon ∉ [-180,180]` → `"invalid coordinates"`
  - `pairs = await registry.query_radius(lat, lon, radius_m, include_lost)`
  - `now = datetime.now(timezone.utc)`；於鎖外 list comprehension 呼叫 `serialize(obj, ttl_warn_s, now,
    center_lat=lat, center_lon=lon)` 產生 `objects[]`；**`is_lost` 明確輸出 true/false**；**`status`
    直接 echo `obj.status`，絕不覆寫**（contracts §3.2.2.1 Q1）。
  - 回 `{"query": {...echo + timestamp...}, "count": len(objects), "objects": objects}`。DEBUG log
    `query.ok`，count / radius。
  - 依賴 T047 / T051 / T053。
- [ ] T058 [US2] 於 `api/server.py` 註冊 `app.router.add_get("/objects", handlers_query.query)`。

**Checkpoint US2**：`pytest tests/contract/test_query_contract.py` 全綠；EchoShield / Sentrycs 的
data source 可用。

---

## Phase 8: User Story 3 — TTL 背景清理 & 生命週期整合（Priority: P1）

**Goal**：讓背景 TTL task 實際運行並影響整體 app 行為，使 `tests/integration/test_ttl_lifecycle.py`
與 `tests/integration/test_concurrent_safety.py` 全部綠燈。

**Independent Test**：用 `freezegun` 推進時鐘，驗證 lost 轉場與 remove 時機；所有斷言打在 Phase 2 / 3
已寫好的測試上。

- [ ] T059 [US3] 於 `api/server.py` 的 `on_startup` 啟動 `asyncio.create_task(run_cleanup_loop(registry,
  settings.cleanup_period_s, logger))` 並保存於 `app["cleanup_task"]`；`on_cleanup` cancel + `await
  asyncio.shield` / suppress `CancelledError`（research §2）。
- [ ] T060 [US3] 在 `ObjectRegistry.query_radius` / `cleanup_expired` 的實作層面，針對「物件剛過
  `ttl_remove_s` 但背景 task 尚未觸發」的窗口，確保 `query_radius` 已先排除（data-model.md §3 註解；
  若 T051 已覆蓋則此為驗證 + 測試調整）。
- [ ] T061 [US3] 針對 `settings.cleanup_period_s` 增加 config 覆寫路徑：`build_app(settings)` 接受
  測試時的短週期（例如 0.05 s），避免真實 2 s 拖慢 CI（plan.md「週期可由 config 覆寫供測試」）。

**Checkpoint US3**：所有三個 user story 全綠；Map Sim 具完整 MVP 功能。

---

## Phase 9: Admin / Health Handlers（除錯端點 + FR-MS-010）

- [ ] T062 [P] 撰寫 `services/map-sim/src/map_sim/api/handlers_admin.py::health`：
  `GET /health` → `{"status":"ok","registered_objects": await registry.count(), "uptime_s": round(
  (now - app["started_at"]).total_seconds(), 1)}`（contracts §3.3）。
- [ ] T063 [P] 撰寫 `handlers_admin.py::objects_all`：
  `GET /objects/all` → 取 `all = await registry.get_all()`、`now = now()`；`is_lost_flags =
  [obj.is_lost(ttl_warn_s, now) for obj in all]`；`active = sum(not f)`、`lost = sum(f)`、`total = len(all)`；
  `objects[]` 以 `serialize(..., center_lat=None, center_lon=None)`（無 `distance_m`）；**status 保留
  原值**（contracts §4.1、FR-MS-008）。
- [ ] T064 [P] 撰寫 `handlers_admin.py::delete_drone`：
  `DELETE /objects/{drone_id}` → `removed = await registry.remove(drone_id)`；回 200
  `{"status":"removed" if removed else "not_found", "drone_id": drone_id}`（contracts §4.2、FR-MS-009；
  **注意：不存在也回 200，不回 404**）。
- [ ] T065 於 `api/server.py` 註冊三個 admin 路由。讓 `tests/contract/test_health_contract.py` 全綠。

---

## Phase 10: CLI 與進入點

- [ ] T066 撰寫 `services/map-sim/src/map_sim/cli.py`：argparse 僅接受 `--port`（default 8090）、
  `--ttl-warn-s`（default 5.0）、`--ttl-remove-s`（default 10.0）、`--verbose`；其他 flag 不接受
  （FR-MS-012）；組 `Settings` → `setup_logging(verbose)` → `web.run_app(build_app(settings),
  host="127.0.0.1", port=settings.port)`（FR-MS-013 綁 127.0.0.1）；啟動 log `server.started` 帶參數，
  結束 log `server.shutdown`。
- [ ] T067 撰寫 `services/map-sim/src/map_sim/__main__.py`：`from .cli import main; main()` 以支援
  `python -m map_sim`（plan.md §Project Structure）。

---

## Phase 11: Polish（Metrics / Logging / Edge Cases / Docs）

- [ ] T068 [P] Review 全部 handler 確認 logging event key 與 research §7 對齊：`update.ok` /
  `update.rejected` / `query.ok` / `query.rejected` / `ttl.cleanup` / `health.ok` / `server.started` /
  `server.shutdown`；update/query 為 DEBUG、4xx 為 WARNING、cleanup 有移除為 INFO。
- [ ] T069 [P] 撰寫 `services/map-sim/tests/integration/test_side_effect_isolation.py`
  —— 跨 story regression：對 POST / GET 每個 400 分支各測一次，之後 `await registry.count()` 與
  `/objects/all` 狀態與該 400 前完全相同（FR-MS-015、SC-MS-006 邊界）。
- [ ] T070 [P] 撰寫 `services/map-sim/tests/integration/test_ttl_precision.py`：
  以覆寫 `cleanup_period_s=0.05, ttl_warn_s=0.5, ttl_remove_s=1.0` 量測 warn-transition 與 remove-transition
  的實際延遲是否落在 SC-MS-003 / SC-MS-004 的 `[ttl, ttl+period]` 區間（取代「真實 2 s」降低 CI 時間）。
- [ ] T071 [P] 撰寫 `services/map-sim/tests/unit/test_errors.py`：驗證 `errors.py` 所有 `reason` 字串
  常數與 `contracts/rest-api.md §5` 速查表**逐字相等**（未來若 implementation 誤改字串，契約測試 +
  此測試雙層擋）。
- [ ] T072 [P] 執行 `quickstart.md §3` 的 curl 範例腳本化（`services/map-sim/scripts/smoke.sh` 或
  `tests/integration/test_quickstart_smoke.py`），驗證 §3.1 / §3.2 / §3.3 / §3.4 / §3.5 全部走得通。
- [ ] T073 [P] 更新 `services/map-sim/README.md`：加入 quickstart 摘要 + `pytest` / `ruff check src
  tests` / `black --check src tests` 指令（對齊 `services/uds/README.md` 風格）。
- [ ] T074 執行 `cd services/map-sim && ruff check src tests && black --check src tests && pytest`，全綠
  後視為 feature 完成。

---

## Dependencies & Execution Order

### Phase 依賴

- **Phase 1 Setup**：無依賴，可立即開始。
- **Phase 2 / 3 Tests（紅燈）**：依賴 Phase 1（才能 collect）；**必須在 Phase 4+ 之前寫完並確認失敗**。
- **Phase 4 Core**：T046 / T047 / T048 / T049 / T050 互不依賴，可全 `[P]`；T051 依 T046+T047；T052 依 T051。
- **Phase 5 API Skeleton**：T053 獨立；T054 依 T049 / T051 / T052 / T053。
- **Phase 6 US1**：依 Phase 4 / 5（T055 需 T048 / T051 / T053；T056 需 T054）。完成後 US1 MVP 可 demo。
- **Phase 7 US2**：依 Phase 4 / 5。與 Phase 6 互不干擾（不同 handler 檔），可並行開發。
- **Phase 8 US3**：依 Phase 5 (T054) 的 lifecycle hook；與 Phase 6 / 7 的 handler 無檔案衝突，可並行。
- **Phase 9 Admin / Health**：依 Phase 4 / 5；可與 Phase 6/7/8 並行（不同 handler 檔）。
- **Phase 10 CLI**：依 Phase 5 (T054)。
- **Phase 11 Polish**：依其他所有 Phase 完成。

### User Story 獨立性

三個 user story 皆 P1，且：

- **US1**（POST 接收）依 Phase 4 Core；完成 Phase 6 後可獨立 demo（UDS push 成功寫入）。
- **US2**（GET 查詢）依 Phase 4 Core；完成 Phase 7 後可獨立 demo（預填資料、curl 查詢）。
- **US3**（TTL 清理）依 Phase 4 Core + Phase 5 lifecycle；完成 Phase 8 後可獨立 demo（短 TTL + freezegun）。

三 story 在 Foundational（Phase 1–5）完成後可 **並行實作**（不同檔案）。

### Within each story

- 先紅（Phase 2 / 3 測試）→ 後綠（Phase 4–9 實作）。
- Models / geo 先於 registry；registry 先於 handler；handler 先於 route 註冊。

---

## Parallel Execution Examples

### Setup 併行

```bash
# T003 / T004 可在 T002 pyproject 就位後併行
Task: "寫 services/map-sim/README.md"
Task: "加 [tool.ruff] / [tool.black] 到 pyproject.toml"
```

### US1 契約測試併行（Phase 2.1）

```bash
Task: "test_update_happy_path"
Task: "test_update_overwrites_same_drone"
Task: "test_update_accepts_extra_fields"     # Q1 寬鬆 payload
Task: "test_update_missing_required_field"
Task: "test_update_invalid_type"
Task: "test_update_invalid_timestamp"
Task: "test_update_invalid_json"
Task: "test_update_landed_is_accepted"
Task: "test_update_400_does_not_mutate_registry"
```

### Core 模型與 geo 併行（Phase 4 前段）

```bash
Task: "geo/haversine.py"
Task: "models/drone_object.py"
Task: "models/request.py (UpdatePayload)"
Task: "config.py (Settings)"
Task: "logging.py (structlog)"
```

### 三個 handler 併行（Phase 6 / 7 / 9）

```bash
Task: "handlers_update.py (US1)"
Task: "handlers_query.py (US2)"
Task: "handlers_admin.py (health / objects_all / delete)"
# server.py 的 route 註冊集中一次收攏，避免 merge conflict
```

---

## Coverage Matrix

### Functional Requirements

| FR | Primary tasks |
|----|---------------|
| FR-MS-001 (8-field payload) | T006, T055 |
| FR-MS-002 (寬鬆 payload) | T008, T048, T055 |
| FR-MS-003 (GET /objects Haversine) | T015, T016, T042, T046, T051, T057 |
| FR-MS-004 (空結果 200) | T017, T018, T057 |
| FR-MS-005 (query 參數校驗) | T023, T024, T025, T026, T057 |
| FR-MS-006 (TTL / is_lost / status 不覆寫) | T019, T020, T021, T022, T035, T047, T051, T057 |
| FR-MS-007 (並發安全) | T040, T041, T044, T051 |
| FR-MS-008 (GET /objects/all totals) | T032, T063 |
| FR-MS-009 (DELETE 選填) | T033, T064 |
| FR-MS-010 (GET /health) | T030, T031, T062 |
| FR-MS-011 (容量 20 drones) | T044 (registry), T040 (併發 smoke) |
| FR-MS-012 (CLI 旗標) | T066 |
| FR-MS-013 (aiohttp 127.0.0.1:8090) | T054, T066 |
| FR-MS-014 (LANDED 收尾可見) | T013, T037 |
| FR-MS-015 (副作用隔離) | T009, T014, T055, T057, T069 |

### Success Criteria

| SC | Tasks |
|----|-------|
| SC-MS-001 吞吐 | T040 (load)、Phase 11 smoke |
| SC-MS-002 延遲 | 手動 bench（T072 smoke）+ T044/T051 鎖策略 |
| SC-MS-003 / SC-MS-004 TTL 精度 | T035, T036, T039, T070 |
| SC-MS-005 查詢正確性 | T042, T015 |
| SC-MS-006 並發 | T040, T041, T069 |
| SC-MS-007 容量 | T044 (smoke) |
| SC-MS-008 health 可用性 | T030, T031 |
| SC-MS-009 LANDED 窗口 | T013, T037 |

### Clarification Q1（`status` 不覆寫 + `is_lost` 獨立欄位）

> 所有以下任務內的**契約/整合斷言**必須寫死「`objects[].status` 絕不等於 `"lost"`」與「`is_lost` 為獨立
> 布林欄位、明確輸出 true/false、不省略」。

- 契約層：**T020** (`include_lost=true` 保留原 status + `is_lost=true`)、**T021** (`include_lost=false`
  時 `is_lost=false` 明確輸出)、**T032** (`/objects/all` 同樣保留原 status)。
- 整合層：**T035** (lost 窗口 status 原值)、**T037** (LANDED 轉 lost 期間)。
- 實作層：**T047**（`DroneObject.serialize` 不含 `"lost"` 邏輯）、**T051**（`query_radius` 純 filter
  不 mutate）、**T057** (`handlers_query`：echo `obj.status`)、**T063**（`handlers_admin.objects_all`
  同上）。
- 契約字串防守：**T071**（`reason` 常數字串比對）間接 + 程式碼中**絕不**出現字串常數 `"lost"` 賦值給
  `status` 欄位（review gate）。

### Edge Cases 覆蓋

| Edge case | Tasks |
|-----------|-------|
| 缺必填欄位的 POST | T009, T055 |
| 未知 `drone_id` 查詢 | T018, T017 |
| `radius_m = 0 / 負值` | T025, T057 |
| `radius_m` 極大值 | T027, T057 |
| 重複 `drone_id` 更新 | T007, T051 |
| 高頻並發 POST + GET | T040, T041, T051 |
| LANDED 後停推但 TTL 未到 | T037, T035 |
| `include_lost=true` 行為 | T020, T022 |
| 非法 `timestamp` | T011, T055 |
| 啟動時空 registry | T018, T030 |

---

## Implementation Strategy

### MVP（US1 Only）

1. Phase 1 Setup → Phase 2.1 US1 contract tests（紅）→ Phase 3.4 UDS round-trip（紅）
2. Phase 4 Core（models / geo / registry / cleanup 本體）
3. Phase 5 API skeleton + T053 errors
4. Phase 6 US1 handlers_update + route
5. 驗證 `tests/contract/test_update_contract.py` + `test_uds_push_end_to_end.py` 全綠 → **MVP Demo**：
   啟動 Map Sim、跑 UDS push client，`GET /objects/all` 看到物件。

### Incremental Delivery

1. **MVP（US1）** 後：加 Phase 7 US2 → `GET /objects` 端點可用，EchoShield/Sentrycs 可接入。
2. 加 Phase 8 US3 → TTL 清理到位，下游不再看到鬼影。
3. 加 Phase 9 admin + Phase 10 CLI → 可本機一鍵啟動 + 除錯端點齊備。
4. Phase 11 Polish → 契約字串、副作用隔離、performance smoke、quickstart 驗證、README。

### Parallel Team Strategy

- Phase 1 / 2 / 3 一人起手，其他人在測試紅燈後 pair review。
- Phase 4 Core 模型 / geo 可三人併行（T046 / T047 / T048）。
- Phase 6 / 7 / 9 handler 三檔可三人併行，server.py route 註冊集中合併（T056 / T058 / T065）。
- Phase 11 Polish 全 `[P]`。

---

## Notes

- `[P]` = 不同檔案、無寫入衝突；同檔內多個 test function 雖可 `[P]` 撰寫但建議同一 commit 提交。
- 契約 `reason` 字串以 `contracts/rest-api.md §5` 為唯一真相；**禁止**在 implementation 直接 echo
  `pydantic.ValidationError` 的訊息（research §4）。
- 所有 TTL 時序測試以 `freezegun` 驅動；`cleanup_period_s` 在測試中覆寫為 ≤ 0.1 s；生產預設 2 s。
- `status` 欄位 **MUST NEVER** 被 Map Sim 寫入 `"lost"` 字串 —— review 時以 `rg '"lost"' src/` 若出現在
  「寫入 status」的 code path 即視為 Q1 違規（唯一可接受的 `"lost"` 字串是 `/objects/all` response 中
  `lost` 這個 **count 欄位 key** 名稱）。
- 任務完成節奏：每完成一個 Phase 建議 commit 一次；測試由紅轉綠的 commit 與 implementation commit 可
  合併。
