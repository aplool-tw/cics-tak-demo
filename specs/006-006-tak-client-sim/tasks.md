---
description: "Task list for 006-006-tak-client-sim implementation"
feature: "TAK Client Simulator"
spec: "specs/006-006-tak-client-sim/spec.md"
plan: "specs/006-006-tak-client-sim/plan.md"
generated: "2026-04-29"
---

# Tasks: TAK Client Simulator

**Input**: `specs/006-006-tak-client-sim/`  
**Service Root**: `services/tak-client-sim/`  
**Approach**: G1 Test-First — 每個 Phase 先確認測試 FAIL，再寫實作

## Format

- `[P]` = 可並行（不同檔案、無未完成依賴）
- `[USn]` = 所屬 User Story（僅 User Story Phase 標示）
- 每個 Phase 先寫測試（確認 FAIL）→ 再實作 → 最後驗收

---

## Phase 1: Setup（專案骨架）

**目的**: 建立服務目錄結構與工具設定，所有後續任務的前提

- [X] T001 建立 `services/tak-client-sim/` 完整目錄樹：`src/tak_client_sim/`、`tests/contract/`、`tests/unit/`、`tests/integration/`、`scripts/`
- [X] T002 建立 `services/tak-client-sim/pyproject.toml`：`[project]`（`pydantic>=2.6`、`structlog>=24.1`、`pyyaml`）、`[project.optional-dependencies] dev`（`pytest>=8.0`、`pytest-asyncio>=0.23`、`freezegun>=1.4`、`ruff>=0.4`、`black>=24.3`）、`[tool.pytest.ini_options]`（`asyncio_mode = "auto"`）、`[tool.ruff]` line-length=120；`[project.scripts]` 留空（以 `python -m tak_client_sim` 執行）
- [X] T003 [P] 建立空白 `__init__.py`：`src/tak_client_sim/__init__.py`、`tests/__init__.py`、`tests/contract/__init__.py`、`tests/unit/__init__.py`、`tests/integration/__init__.py`

**Checkpoint**: `pip install -e ".[dev]"` 可執行，`pytest --collect-only` 不報錯

---

## Phase 2: Foundational（阻塞前提）

**目的**: 建立所有 User Story 共用的資料模型與測試 Fixtures — 未完成前任何 User Story 均無法啟動

⚠️ **CRITICAL**: 此 Phase 須全部完成才能進入任何 User Story Phase

- [X] T004 建立 `services/tak-client-sim/src/tak_client_sim/models.py`：`from __future__ import annotations`；`SourceLabel = Literal["ECHO","SENTRYCS","FUSED","UNKNOWN"]`；`ColorLabel = Literal["GREY","RED","UNKNOWN"]`；`@dataclass(frozen=True) class CotEvent`（欄位：`uid: str`/`cot_type: str`/`source: SourceLabel`/`color: ColorLabel`/`time: datetime`/`stale: datetime`/`delta_s: int`/`lat: float`/`lon: float`/`hae: float`/`speed: float`/`course: float`/`remarks: str`/`raw_xml: str`）；`@dataclass class ConnectionStats`（mutable，欄位：`total_received: int = 0`/`total_filtered: int = 0`/`total_parse_errors: int = 0`/`total_oversized: int = 0`/`reconnect_count: int = 0`/`per_source: Dict[str,int] = field(default_factory=dict)`/`per_uid: Dict[str,int] = field(default_factory=dict)`，方法：`record_event(event, filtered)`/`to_dict() -> dict`）
- [X] T005 [P] 建立 `services/tak-client-sim/tests/conftest.py`：定義 8 筆合規矩陣 CoT XML fixture（`@pytest.fixture`），涵蓋 `ECHO-TRK-001` Active（delta_s=11）/Lost（delta_s=0）、`SENTRYCS-DRN-001` DETECTED（delta_s=11）/MITIGATING（delta_s=11）/NEUTRALIZED（delta_s=30）、`FUSED-DRN-001` DETECTED（delta_s=11）/MITIGATING（delta_s=11）/NEUTRALIZED（delta_s=30）；每筆含完整 `<event>/<point>/<detail>/<track>/<remarks>` XML；`pytest_configure` 確認 `asyncio_mode="auto"`

**Checkpoint**: `python -c "from tak_client_sim.models import CotEvent, ConnectionStats"` 無錯

---

## Phase 3: User Story 2 — CoT 事件解析正確性驗證（Priority: P1）

**目標**: QA 工程師能從 console 一眼確認 source 標籤（ECHO/SENTRYCS/FUSED）、顏色標籤（GREY/RED）、delta_s，無需手動解析 XML

**Independent Test**: 提供 3 種預製 fixture（ECHO GREY、FUSED RED、NEUTRALIZED delta_s=30），執行 `pytest tests/contract/ tests/unit/test_parser.py tests/unit/test_formatter.py`，全部 PASS

### 測試先行（確認 FAIL）

- [X] T006 [US2] 建立 `services/tak-client-sim/tests/contract/test_tak_downlink.py`：針對 conftest 8 個 CoT XML fixture 撰寫 `test_echo_active`/`test_echo_lost`/`test_sentrycs_detected`/`test_sentrycs_mitigating`/`test_sentrycs_neutralized`/`test_fused_detected`/`test_fused_mitigating`/`test_fused_neutralized`，每個斷言 `event.uid`/`event.source`/`event.color`/`event.delta_s`；附加 `test_stub_server_3_cot`（asyncio stub TCP server 發 3 筆 CoT，驗證解析結果含正確 uid/lat/lon）；**確認全部 FAIL（ImportError 或 AssertionError）**
- [X] T007 [P] [US2] 建立 `services/tak-client-sim/tests/unit/test_parser.py`：`test_parse_happy_path`（含 track/remarks 完整 CoT）、`test_missing_point_defaults_to_zero`、`test_missing_track_defaults_to_zero`、`test_missing_remarks_empty_string`、`test_invalid_xml_returns_none`（格式錯誤 XML → `None`）、`test_missing_uid_returns_none`（`<event type=...>` 無 uid 屬性 → `None`）、`test_missing_type_returns_none`（無 type 屬性 → `None`）、`test_stale_lt_time_delta_s_zero`（stale < time → delta_s=0）、`test_delta_s_rounds_to_int`；覆蓋 SC-TCS-008 四類錯誤情境（oversized 由 T008 覆蓋）；**確認全部 FAIL**
- [X] T008 [P] [US2] 在 `services/tak-client-sim/tests/unit/test_parser.py` 新增 oversized 處理測試（作為 `test_runner_cot_oversized_handling` 放於此檔案或建立 `tests/unit/test_runner_unit.py`）：mock asyncio `StreamReader` 拋出 `asyncio.LimitOverrunError`；斷言 `stats.total_oversized == 1`；驗證有 `cot_oversized` structlog warning（含 `bytes_seen` 欄位）；斷言迴圈繼續處理下一行（SC-TCS-008 第 4 類錯誤情境）；**確認 FAIL**
- [X] T009 [P] [US2] 建立 `services/tak-client-sim/tests/unit/test_formatter.py`：`test_format_event_normal`（驗證輸出含 `[ECHO][GREY]`/`{lat:.6f}/{lon:.6f}`/`delta_s=+11`/`remarks`）、`test_format_event_stale_prefix`（stale 比 now 早 35 秒 → 輸出以 `[STALE]` 開頭，freezegun mock now）、`test_format_event_no_stale_prefix`（stale 比 now 早 25 秒 → 無 `[STALE]`）、`test_format_delta_s_zero`（Lost 狀態 → `delta_s=+0`）、`test_is_stale_at_receive_true`/`test_is_stale_at_receive_false`；**確認全部 FAIL**

### 實作

- [X] T010 [US2] 實作 `services/tak-client-sim/src/tak_client_sim/parser.py`：`from __future__ import annotations`；`parse_cot_xml(raw: str) -> CotEvent | None`（使用 `xml.etree.ElementTree.fromstring()`，`ET.ParseError` → `None`，uid/type 缺失 → `None`，`<point>/<track>/<remarks>` 缺席降級為 `0.0`/`""`，`datetime.fromisoformat()` 解析 time/stale，`delta_s = max(0, round((stale_dt - time_dt).total_seconds()))`）；`_derive_source(uid: str) -> SourceLabel`（`ECHO-`/`SENTRYCS-`/`FUSED-` 前綴比對）；`_derive_color(cot_type: str) -> ColorLabel`（`a-u-`/`a-h-` 前綴比對）；**禁用 lxml**
- [X] T011 [P] [US2] 實作 `services/tak-client-sim/src/tak_client_sim/formatter.py`：`from __future__ import annotations`；`is_stale_at_receive(event: CotEvent, now: datetime) -> bool`（`(now - event.stale).total_seconds() > 30`）；`format_event(event: CotEvent, now: datetime | None = None) -> str`（格式 `[{ISO8601Z}] [{SOURCE}][{COLOR}] {uid}  {lat:.6f}/{lon:.6f}  {hae:.1f}m  {speed:.1f}m/s  {course:03.0f}°  delta_s=+{delta_s}  {remarks}`，stale 時加前綴 `[STALE] `）；`print_event(event: CotEvent) -> None`（**唯一允許 `print()` 的函式**，輸出至 stdout）

### 驗收

- [X] T012 [US2] 執行 `pytest tests/contract/test_tak_downlink.py tests/unit/test_parser.py tests/unit/test_formatter.py -v`，確認 8 contract 場景 + parser happy/error path（含 4 類錯誤情境）+ formatter format/stale 全部 PASS

**Checkpoint**: `parse_cot_xml()` + `format_event()` 對合規矩陣 8 場景輸出正確（SC-TCS-002）

---

## Phase 4: User Story 1 — 端對端鏈路驗證（Priority: P1）🎯 MVP

**目標**: Demo 操作員啟動服務後，console 持續顯示 CoT 事件行；斷線後自動重連；Ctrl-C 優雅關閉並列印統計

**Independent Test**: asyncio stub TCP server 發 3 筆 CoT → `pytest tests/integration/test_runner.py::test_stub_3_cot` PASS，驗證 stdout 含正確 uid/lat/lon × 3 行、structlog stderr 含 3 筆 `cot_received` + 1 筆 `tak_connected`

### 測試先行（確認 FAIL）

- [X] T013 [US1] 建立 `services/tak-client-sim/tests/unit/test_config.py`：`test_default_config`（無參數 → 預設值）、`test_yaml_load_valid`（合法 YAML dict → ClientConfig）、`test_extra_field_raises_validation_error`（YAML 含多餘欄位 → `ValidationError`）、`test_cli_overrides_yaml`（CLI host/port 優先於 YAML）、`test_port_out_of_range`（port=0 → `ValidationError`）、`test_filter_prefix_empty_string_becomes_none`（`filter_prefix=""` → `None`）、`test_max_retries_negative_raises`（`max_retries=-1` → `ValidationError`）；**確認全部 FAIL**
- [X] T014 [P] [US1] 建立 `services/tak-client-sim/tests/integration/test_runner.py`：`test_stub_3_cot`（pytest-asyncio，建立 asyncio stub TCP server 送 3 筆合規 CoT XML，以 `capsys` capture stdout，斷言含 uid/lat/lon 正確值；驗證 structlog JSON 含 3 筆 `event=cot_received` + 1 筆 `event=tak_connected`）；`test_graceful_shutdown_prints_summary`（stub 送 2 筆 CoT 後關閉連線，驗證 session_summary console 輸出含 `total_received` 與正確計數）；**確認全部 FAIL**

### 實作

- [X] T015 [US1] 實作 `services/tak-client-sim/src/tak_client_sim/config.py`：`from __future__ import annotations`；`ClientConfig(BaseModel)` + `ConfigDict(extra="forbid", frozen=True)`，全部欄位含預設值（`host="tak-server"`/`port=8089`/`use_ssl_verify=False`/`ca_bundle=None`/`max_retries=0`/`backoff_initial_s=1.0`/`backoff_cap_s=60.0`/`filter_prefix=None`/`log_file=None`）；`field_validator` for `filter_prefix`（空字串→None）、`port`（1-65535）、`max_retries`（≥0）；`load_config(args: argparse.Namespace) -> ClientConfig`（YAML load → CLI 覆寫 → `ClientConfig(**base)`，`ValidationError` → `print + sys.exit(2)`）；`validate_log_file_writable(path: str) -> None`（`open(path,"a")` 失敗 → `sys.exit(2)` + friendly message）
- [X] T016 [P] [US1] 實作 `services/tak-client-sim/src/tak_client_sim/connection.py`：`from __future__ import annotations`；`build_ssl_context(config: ClientConfig) -> ssl.SSLContext`（PoC: `CERT_NONE + check_hostname=False`，verify: `CERT_REQUIRED + check_hostname=True + load_verify_locations`）；`TakConnection` 類別含 `connect() -> tuple[asyncio.StreamReader, asyncio.StreamWriter]`（`asyncio.open_connection(host, port, ssl=ctx)`）和 `close(writer) -> None`（`writer.close() + await writer.wait_closed()`）；`connect_with_retry(config, stats, stop) -> tuple[StreamReader, StreamWriter]`（loop: attempt+=1 → `delay=min(backoff_initial_s*2**(attempt-1), backoff_cap_s)` → max_retries 檢查（`log max_retries_exceeded + sys.exit(1)`）→ `print(f"Reconnecting... (attempt {attempt}, delay {delay:.0f}s)")` → structlog `reconnecting(attempt, delay_s)` → `asyncio.sleep(delay)` → 重試；成功後 structlog `tak_reconnected(attempt)` + `stats.reconnect_count+=1` + attempt 歸 0）
- [X] T017 [US1] 實作 `services/tak-client-sim/src/tak_client_sim/runner.py`：`from __future__ import annotations`；`configure_logging(log_file: str | None) -> None`（structlog JSON processor chain：`add_log_level` / `add_logger_name` / `TimeStamper(fmt="iso", utc=True)` / `JSONRenderer()`；`logging.basicConfig` handlers 含 `StreamHandler(stderr)` + 可選 `FileHandler(log_file)`；**禁用 f-string log**）；`_is_filtered(event: CotEvent, filter_prefix: str | None) -> bool`（`filter_prefix` 為 None 或空字串時回傳 False，否則 `not event.uid.startswith(filter_prefix)`）；`receive_loop(reader, config, stats, stop) -> None`（`while not stop.is_set()`: `readuntil(b"\n", limit=65536)` → `LimitOverrunError`: `await reader.read(65536)` + log `cot_oversized(bytes_seen=65536)` + `stats.total_oversized+=1` + continue；`IncompleteReadError/ConnectionResetError/OSError`: log `tak_disconnected(error=...)` + raise；解碼/strip；`parse_cot_xml()` → None: log `cot_parse_error(raw_preview=raw[:200])` + `stats.total_parse_errors+=1` + continue；`_is_filtered()` → `stats.record_event(event, filtered)` → log `cot_received(..., filtered=bool)` → `if not filtered: print_event(event)`）；`_print_summary(stats) -> None`（console session summary block 輸出至 stdout）；`main(config: ClientConfig) -> None`（`stop=asyncio.Event()`；`loop.add_signal_handler` SIGINT/SIGTERM → `stop.set()`；`stats=ConnectionStats()`；外層 while: `(reader, writer) = await connect_with_retry(...)` → log `tak_connected(host, port)` → `try: await receive_loop(reader, config, stats, stop)` → `except: await conn.close(writer)` → `if stop.is_set(): break`；finally: `_print_summary(stats)` → log `session_summary(**stats.to_dict())` → `sys.exit(0)`）
- [X] T018 [US1] 實作 `services/tak-client-sim/src/tak_client_sim/__main__.py`：`from __future__ import annotations`；`argparse.ArgumentParser(description="TAK Client Simulator")` 含 `--host`/`--port`/`--no-ssl-verify`（store_true）/`--filter`/`--log-file`/`--max-retries`/`--config` 全部參數；`args = parser.parse_args()`；`config = load_config(args)`；若 `config.log_file`: `validate_log_file_writable(config.log_file)`；`configure_logging(config.log_file)`；`asyncio.run(main(config))`

### 驗收

- [X] T019 [US1] 執行 `pytest tests/unit/test_config.py tests/integration/test_runner.py::test_stub_3_cot tests/integration/test_runner.py::test_graceful_shutdown_prints_summary -v`，確認全部 PASS；手動確認 `python -m tak_client_sim --help` 顯示全部 CLI 參數

**Checkpoint**: MVP 達成 — `python -m tak_client_sim --no-ssl-verify` 可連線 stub 並顯示 CoT；SC-TCS-001 端對端延遲 ≤ 100ms 可手動驗收

---

## Phase 5: User Story 3 — 過濾特定來源事件（Priority: P2）

**目標**: `--filter FUSED` 時，console 僅顯示 FUSED 開頭事件；structlog 仍記錄全部事件（含 `filtered=true`）

**Independent Test**: 混合 ECHO/SENTRYCS/FUSED CoT 串 + `--filter FUSED` → `pytest tests/integration/test_runner.py::test_filter_console_vs_log` PASS

### 測試先行（確認 FAIL）

- [X] T020 [US3] 在 `services/tak-client-sim/tests/unit/test_formatter.py` 新增 filter 測試區塊：`test_is_filtered_matching_prefix`（`filter_prefix="FUSED"`, uid=`FUSED-DRN-001` → `False`）、`test_is_filtered_non_matching`（uid=`ECHO-TRK-001` → `True`）、`test_is_filtered_none_prefix`（`filter_prefix=None` → `False`，永不過濾）、`test_is_filtered_empty_string_treated_as_none`（`filter_prefix=""` → `False`）；**確認新增測試 FAIL（runner._is_filtered 尚未可 import 或邏輯不符）**
- [X] T021 [P] [US3] 在 `services/tak-client-sim/tests/integration/test_runner.py` 新增 `test_filter_console_vs_log`：stub 發送 ECHO/SENTRYCS/FUSED 各 1 筆，`filter_prefix="FUSED"`，斷言 stdout 僅含 `FUSED-` 行（無 `ECHO-`/`SENTRYCS-`），structlog JSON 含 3 筆 `cot_received`（ECHO/SENTRYCS 含 `"filtered": true`，FUSED 含 `"filtered": false`）；**確認 FAIL**

### 實作

- [X] T022 [US3] 確認 `services/tak-client-sim/src/tak_client_sim/runner.py` 中 `_is_filtered()` 邏輯正確（`filter_prefix` None/空字串 → False；不匹配前綴 → True）；確認 `receive_loop()` 中 `filtered=True` 時跳過 `print_event()` 但仍執行 `stats.record_event()` 與 structlog `cot_received(filtered=True)`；如有不符，更新 `runner.py`

### 驗收

- [X] T023 [US3] 執行 `pytest tests/unit/test_formatter.py -k filter tests/integration/test_runner.py::test_filter_console_vs_log -v`，確認全部 PASS（SC-TCS-007）

**Checkpoint**: `--filter FUSED` 正確過濾 console 輸出，structlog log 仍完整（含 `filtered=true`）

---

## Phase 6: User Story 4 — 日誌檔持久化（Priority: P2）

**目標**: `--log-file <path>` 將 structlog JSON 同步寫入檔案；含全部事件（含 filtered=true）；最後一行為 `session_summary`；path 不可寫時啟動即 fail-fast exit(2)

**Independent Test**: `--log-file /tmp/tak-test.jsonl` + 5 筆 CoT + SIGINT → log 含 5 筆 `cot_received` + 1 筆 `session_summary`；`pytest tests/integration/test_runner.py -k log_file` PASS

### 測試先行（確認 FAIL）

- [X] T024 [US4] 在 `services/tak-client-sim/tests/integration/test_runner.py` 新增 3 個 log-file 測試：`test_log_file_receives_all_events`（`log_file=/tmp/tak-test-{uuid}.jsonl`，5 筆 CoT，讀回 log 斷言 5 筆 `event=cot_received` + 1 筆 `event=session_summary`）、`test_log_file_records_filtered_events`（`filter_prefix="FUSED" + log_file`，混合 CoT，log 含全部事件含 `filtered=true`）、`test_log_file_unwritable_exits_2`（`log_file="/nonexistent/path/file.jsonl"`，斷言在啟動時拋出 `SystemExit(2)`）；**確認全部 FAIL**

### 實作

- [X] T025 [US4] 確認 `services/tak-client-sim/src/tak_client_sim/runner.py` `configure_logging()` 中 `FileHandler(log_file)` 正確加入 handlers；確認 `config.py` `validate_log_file_writable()` 對不可寫路徑呼叫 `sys.exit(2)`；確認 `main()` finally 區塊的 `log.info("session_summary", ...)` 在 FileHandler 存在時也寫入 log 檔；如有缺漏，更新 `runner.py` / `config.py`

### 驗收

- [X] T026 [US4] 執行 `pytest tests/integration/test_runner.py -k log_file -v`，確認 3 個 log-file 測試全部 PASS（SC-TCS-007 log 完整記錄）

**Checkpoint**: `--log-file` 功能完整，log 可供 CI smoke assertion 使用

---

## Phase 7: User Story 5 — 自動重連韌性（Priority: P2）

**目標**: TAK Server 短暫不可用時，服務以指數退避（1→2→4→…→60s）自動重連；重連成功後繼續接收；達 `max_retries` 上限時 exit(1)；console 顯示重連訊息

**Independent Test**: stub 連線建立後主動斷線 → `pytest tests/unit/test_connection.py tests/integration/test_runner.py::test_reconnect_resumes` PASS

### 測試先行（確認 FAIL）

- [X] T027 [US5] 建立 `services/tak-client-sim/tests/unit/test_connection.py`：`test_backoff_sequence`（monkeypatch `asyncio.sleep`，模擬 7 次連線失敗，斷言 sleep 被以 `[1,2,4,8,16,32,60]` 依序呼叫）、`test_max_retries_exceeded_exits_1`（`max_retries=3`，3 次失敗後斷言 `SystemExit(1)`）、`test_reconnect_count_increments`（2 次失敗後成功，`stats.reconnect_count == 2`）、`test_attempt_resets_on_success`（成功後 attempt 歸 0，再次斷線時 delay 從 1s 重新開始）、`test_build_ssl_context_poc_mode`（`use_ssl_verify=False` → `ctx.verify_mode == ssl.CERT_NONE`）、`test_build_ssl_context_verify_mode`（`use_ssl_verify=True` → `ctx.verify_mode == ssl.CERT_REQUIRED`）；**確認全部 FAIL**
- [X] T028 [P] [US5] 在 `services/tak-client-sim/tests/integration/test_runner.py` 新增 `test_reconnect_resumes`：stub 送 1 筆 CoT → 主動斷線 → 重啟 stub → 送第 2 筆 CoT；斷言 stdout 含 2 筆 CoT 行；structlog 含 `reconnecting` + `tak_reconnected` 事件；console stderr/stdout 含 `Reconnecting...` 字串；**確認 FAIL**

### 實作

- [X] T029 [US5] 確認 `services/tak-client-sim/src/tak_client_sim/connection.py` `connect_with_retry()` 符合規格：`delay=min(backoff_initial_s*2**(attempt-1), backoff_cap_s)` 公式、`max_retries>0 and attempt>=max_retries` → log `max_retries_exceeded` → `sys.exit(1)`、成功後 `attempt` 歸 0 且 `stats.reconnect_count+=1`、console `print(f"Reconnecting... (attempt {attempt}, delay {delay:.0f}s)")`、structlog `reconnecting(attempt=, delay_s=)` + `tak_reconnected(attempt=)`；如有缺漏，更新 `connection.py`

### 驗收

- [X] T030 [US5] 執行 `pytest tests/unit/test_connection.py tests/integration/test_runner.py::test_reconnect_resumes -v`，確認全部 PASS（SC-TCS-003 2 個退避週期內重連）

**Checkpoint**: 重連韌性完整，PoC demo 不需人工重啟（SC-TCS-003）

---

## Phase 8: Polish & Cross-Cutting

**目的**: 文件、smoke test、效能/關閉時限測試、全套測試驗收、lint 合規

- [X] T031 [P] 建立 `services/tak-client-sim/README.md`：安裝（`pip install -e ".[dev]"`）、基本啟動（PoC mode / filter / log-file / YAML config / max-retries）、console 輸出格式（含 `[STALE]` 範例）、structlog JSON 格式範例、優雅關閉輸出範例、測試指令（`pytest -q` / `pytest tests/contract/` / `pytest tests/unit/` / `pytest tests/integration/`）、lint 指令（`ruff check . && black --check src tests`）
- [X] T032 [P] 建立 `services/tak-client-sim/scripts/smoke.sh`：①後台啟動 asyncio Python stub TCP server（發送 ECHO + FUSED 各 1 筆，loop 3 次）；②後台啟動 `python -m tak_client_sim --host 127.0.0.1 --port 8089 --no-ssl-verify --log-file /tmp/smoke-tak.jsonl`；③等待 5 秒；④發送 SIGINT；⑤等待 2 秒；⑥`grep -c '"event":"cot_received"' /tmp/smoke-tak.jsonl` 斷言 ≥ 2；⑦`grep -c '"event":"session_summary"' /tmp/smoke-tak.jsonl` 斷言 = 1；⑧全通 → `echo SMOKE PASS`，任一失敗 → `echo SMOKE FAIL; exit 1`
- [X] T033 [P] 在 `services/tak-client-sim/tests/integration/test_runner.py` 新增效能與關閉時限測試：`test_50_ups_no_backlog`（asyncio 並行發送 50 筆合規 CoT，`asyncio.timeout(5.0)` 等待消費完畢，斷言 `stats.total_received == 50` 且 `stats.total_parse_errors == 0`；驗證 SC-TCS-005）；`test_shutdown_within_3s`（`time.monotonic()` 量測從 `stop.set()` 到 `main()` 返回的耗時 ≤ 3.0 秒；驗證 SC-TCS-006）；先確認 FAIL，再執行驗收
- [X] T034 執行 `cd services/tak-client-sim && ruff check src/ tests/` 並修正全部 lint 錯誤；執行 `black src/ tests/` 自動格式化；確認 `ruff check . && black --check src tests` 零輸出
- [X] T035 執行 `cd services/tak-client-sim && python -m pytest -q`，確認全部測試 PASS（contract × 8 場景 + unit test_parser/test_formatter/test_config/test_connection + integration test_runner 含全部子測試含效能測試）；輸出通過測試總數
- [X] T036 [P] 驗證 FR-TCS-063 合規：確認 `pyproject.toml` 無 `lxml`/`aiohttp`/`cryptography` 依賴；執行 `grep -r "import lxml\|from lxml\|import aiohttp\|from cryptography" services/tak-client-sim/src/` → 無輸出

---

## Dependencies & Execution Order

### Phase 依賴

```
Phase 1: Setup
    └── Phase 2: Foundational（依賴 Phase 1）
            ├── Phase 3: US2 CoT 解析（依賴 Phase 2）← 先做，因 parser 是 US1 前提
            │       └── Phase 4: US1 端對端（依賴 Phase 2 + Phase 3 parser/formatter）
            │               ├── Phase 5: US3 過濾（依賴 Phase 4 runner.py 骨架）
            │               ├── Phase 6: US4 日誌持久化（依賴 Phase 4 configure_logging()）
            │               └── Phase 7: US5 自動重連（依賴 Phase 4 connection.py 骨架）
            └── Phase 8: Polish（依賴 Phase 3–7 全部完成）
```

### User Story 依賴

| Story | Priority | 依賴 Phase | 可並行 |
|-------|----------|-----------|--------|
| US2 CoT 解析 | P1 | Foundational（Phase 2） | 無跨 Story 依賴 |
| US1 端對端 | P1 | Foundational + **US2 parser/formatter** | 依賴 US2 |
| US3 過濾 | P2 | US1 runner.py 骨架存在 | US3 / US4 / US5 可三人並行 |
| US4 日誌持久化 | P2 | US1 configure_logging() 骨架存在 | US3 / US4 / US5 可三人並行 |
| US5 自動重連 | P2 | US1 connection.py 骨架存在 | US3 / US4 / US5 可三人並行 |

### US3 / US4 / US5 並行策略

Phase 4（US1）完成後，US3、US4、US5 **可由三人並行執行**：

```bash
# Developer A (US3):
pytest tests/unit/test_formatter.py -k filter
pytest tests/integration/test_runner.py::test_filter_console_vs_log

# Developer B (US4):
pytest tests/integration/test_runner.py -k log_file

# Developer C (US5):
pytest tests/unit/test_connection.py
pytest tests/integration/test_runner.py::test_reconnect_resumes
```

---

## Parallel Execution Examples

### Phase 2（Foundational 內部並行）

```bash
# T004 和 T005 可同時啟動（不同檔案）
Task T004: src/tak_client_sim/models.py（CotEvent + ConnectionStats）
Task T005: tests/conftest.py（8 CoT XML fixtures）
```

### Phase 3（US2 測試並行撰寫）

```bash
# T006、T007、T008、T009 可全部同時啟動（不同檔案）
Task T006: tests/contract/test_tak_downlink.py（8 contract 場景）
Task T007: tests/unit/test_parser.py（happy + error paths）
Task T008: tests/unit/test_parser.py 或 test_runner_unit.py（oversized handling）
Task T009: tests/unit/test_formatter.py（format + STALE + stale_at_receive）
```

### Phase 4（US1 實作內部並行）

```bash
# T015 和 T016 可同時啟動（不同檔案，均只依賴 models.py）
Task T015: src/tak_client_sim/config.py
Task T016: src/tak_client_sim/connection.py
# T017 (runner.py) 依賴 T015 + T016 完成
# T018 (__main__.py) 依賴 T017 完成
```

### Phase 8（Polish 並行）

```bash
# T031、T032、T033、T036 可全部同時啟動（不同 concern）
Task T031: README.md
Task T032: scripts/smoke.sh
Task T033: tests/integration/test_runner.py（效能測試新增）
Task T036: FR-TCS-063 依賴合規驗證
```

---

## Implementation Strategy

### MVP（US1 + US2，可獨立 Demo）

1. 完成 Phase 1（Setup）
2. 完成 Phase 2（Foundational）
3. 完成 Phase 3（US2 — parser + formatter）
4. 完成 Phase 4（US1 — config + connection + runner + CLI）
5. **STOP & VALIDATE**: `python -m tak_client_sim --no-ssl-verify` + TAK stub → console 顯示 CoT
6. Demo 可執行：操作員不需要實體 ATAK 裝置即可確認鏈路（FR-TCS-060 核心目標）

### 完整交付（US1–US5）

1. MVP 驗收後，繼續 Phase 5/6/7（可三人並行）
2. Phase 8 Polish
3. `bash scripts/smoke.sh` → `SMOKE PASS`
4. `python -m pytest -q` → 全部通過

### 合規矩陣對應（SC-TCS-002 / SC-TCS-008）

所有 8 個合規矩陣場景由 contract test（T006）覆蓋；4 類錯誤情境由 T007/T008 覆蓋：

| 場景 | Task | 驗證點 |
|------|------|--------|
| ECHO Active | T006 `test_echo_active` | source=ECHO, color=GREY, delta_s=11 |
| ECHO Lost | T006 `test_echo_lost` | source=ECHO, color=GREY, delta_s=0 |
| SENTRYCS DETECTED | T006 `test_sentrycs_detected` | source=SENTRYCS, color=GREY, delta_s=11 |
| SENTRYCS MITIGATING | T006 `test_sentrycs_mitigating` | source=SENTRYCS, color=GREY, delta_s=11 |
| SENTRYCS NEUTRALIZED | T006 `test_sentrycs_neutralized` | source=SENTRYCS, color=GREY, delta_s=30 |
| FUSED DETECTED | T006 `test_fused_detected` | source=FUSED, color=RED, delta_s=11 |
| FUSED MITIGATING | T006 `test_fused_mitigating` | source=FUSED, color=RED, delta_s=11 |
| FUSED NEUTRALIZED | T006 `test_fused_neutralized` | source=FUSED, color=RED, delta_s=30 |
| Oversized（>64KB） | T008 `test_cot_oversized_handling` | stats.total_oversized=1, cot_oversized log, 繼續運行 |
| Invalid XML | T007 `test_invalid_xml_returns_none` | returns None, cot_parse_error |
| Missing uid | T007 `test_missing_uid_returns_none` | returns None |
| Missing type | T007 `test_missing_type_returns_none` | returns None |
