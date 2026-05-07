---
description: "Task list for EchoShield Simulator implementation (TDD: contract → unit → integration)"
---

# Tasks: EchoShield Simulator

**Feature**: `003-echoshield-sim`
**Input**: Design documents from `/specs/003-echoshield-sim/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/tcp-feed.md ✅, quickstart.md ✅

**Tests**: INCLUDED（使用者要求 TDD：contract → unit → integration 三層先行；符合 Plan G1 與 contracts/tcp-feed.md §6）。

**Organization**: Tasks 以 User Story 分組（US1 / US2 / US3）。Phase 2 之後可並行；同一 Phase 內標 **[P]** 的 task 可並行（不同檔案、無相互相依）。

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: 可並行（不同檔案、無相依）
- **[Story]**: `[US1]` / `[US2]` / `[US3]`，對應 spec.md User Story 1/2/3
- 每個 task 都包含「絕對/相對於 repo root 的檔案路徑」

## Path Conventions

所有路徑以 repo root 為基準；服務目錄為 `services/echoshield-sim/`，對齊 `services/map-sim/` 結構。

---

## Phase 1: Setup（Shared Infrastructure）

**Purpose**: 建立服務 scaffolding，與 `services/map-sim/` 嚴格對稱。

- [X] T001 Create service directory tree `services/echoshield-sim/{src/echoshield_sim,tests/{contract,integration,unit},scripts,config}` and empty `__init__.py` under `src/echoshield_sim/`, `src/echoshield_sim/models/`, `src/echoshield_sim/geo/`, `src/echoshield_sim/mapsim/`, `src/echoshield_sim/feed/`.
- [X] T002 Create `services/echoshield-sim/pyproject.toml` mirroring `services/map-sim/pyproject.toml`（setuptools backend、`[project].name = "echoshield-sim"`、`[project.scripts] echoshield-sim = "echoshield_sim.cli:main"`、runtime deps: `aiohttp>=3.9,pydantic>=2.6,structlog>=24.1,numpy>=1.26,pyyaml`；dev deps: `pytest>=8.0,pytest-asyncio>=0.23,freezegun>=1.4,ruff,black`；pytest `asyncio_mode=auto`）.
- [X] T003 [P] Create `services/echoshield-sim/README.md` pointing to `specs/003-echoshield-sim/quickstart.md` and summarising endpoints（Map Sim client → `:18090`、TCP feed → `:19000`）.
- [X] T004 [P] Create `services/echoshield-sim/scripts/smoke.sh` mirroring `services/map-sim/scripts/smoke.sh`（`nc localhost 9000` tail + `curl :18090/objects` sanity check）.
- [X] T005 [P] Create `services/echoshield-sim/config/local.yaml` from quickstart.md §1 template（sensor 24.0/121.0、`max_range_m: 4800`、`feed_port: 9000`、`noise_seed: null`（flat YAML key））.
- [X] T006 [P] Create `services/echoshield-sim/tests/conftest.py` with shared fixtures: `frozen_time`（freezegun at `2026-04-24T08:15:30.000Z`）、`noise_seed=42`、`aiohttp` stub Map Sim server factory（reuse pattern from `services/map-sim/tests/conftest.py` if present）.
- [X] T007 Install editable + dev：`cd services/echoshield-sim && pip install -e '.[dev]'`；verify `pytest -q` discovers zero tests cleanly and `ruff check src tests` passes.

**Checkpoint**: Scaffolding compiles and an empty pytest run succeeds.

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**: 所有 User Story 都依賴的共用模型、設定、日誌、CLI 骨架。**⚠️ 完成前禁止開 Story 實作**。

### Foundational Tests（TDD 先行）

- [X] T008 [P] Unit test `services/echoshield-sim/tests/unit/test_config.py`: 驗證 YAML 載入 + `extra="forbid"` + `frozen=True`；CLI `--seed 7` 覆寫 YAML `noise_seed: 42` → 最終 `noise_seed == 7`（spec §Clarifications）；非法值（`update_rate_hz=0`、`sensor_lat=91`）raise ValidationError.
- [X] T009 [P] Unit test `services/echoshield-sim/tests/unit/test_logging.py`: structlog JSON renderer 輸出含必要欄位（`event`、`level`、`timestamp`）；throttle helper 驗證「每秒最多 1 行」`map_sim_unavailable`（research.md R7）.
- [X] T010 [P] Contract test `services/echoshield-sim/tests/contract/test_radar_track_schema.py`: 讀入 `specs/003-echoshield-sim/contracts/tcp-feed.md` §3.1 JSON Schema（內嵌為字串常數或 fixture），以 `jsonschema` 驗證 example（§3.3）通過；故意破壞 `track_id` 格式應 fail（紅燈先行、Phase 3 前不實作 producer）.

### Foundational Implementation

- [X] T011 [P] Implement `services/echoshield-sim/src/echoshield_sim/config.py`: pydantic v2 `RadarConfig(BaseModel)` per data-model.md §1（所有欄位、validators、`ConfigDict(extra="forbid", frozen=True)`）；`load_config(path: str) -> RadarConfig`（`yaml.safe_load` + `model_validate`）.
- [X] T012 [P] Implement `services/echoshield-sim/src/echoshield_sim/logging.py`: `configure_logging(verbose: bool)` 安裝 structlog JSON renderer to stdout；`get_throttled_logger(logger, key, min_interval_s)` 實作 per-key 節流（research.md R7）.
- [X] T013 [P] Implement `services/echoshield-sim/src/echoshield_sim/models/track.py`: `RadarTrack` pydantic model 對應 contracts/tcp-feed.md §3.1（所有欄位、`additionalProperties=False` 等價的 `extra="forbid"`、pattern validators for `track_id`、`timestamp`、`track_status` enum、`classification` const）.
- [X] T014 Implement `services/echoshield-sim/src/echoshield_sim/cli.py`: argparse `--config`（必要）、`--verbose`、`--seed int`；load config → CLI `--seed` 覆寫 → `configure_logging` → call `loop.run(config)`（暫存 stub，Phase 3 接入）.
- [X] T015 Implement `services/echoshield-sim/src/echoshield_sim/__main__.py`: `from .cli import main; main()`，支援 `python -m echoshield_sim`.
- [X] T016 Green-light Foundational tests：run `pytest tests/unit/test_config.py tests/unit/test_logging.py tests/contract/test_radar_track_schema.py -q`，全部 PASS.

**Checkpoint**: Config/log/RadarTrack schema 就緒；Contract schema 已凍結。三個 User Story 可並行展開。

---

## Phase 3: User Story 1 — CoT Gateway 透過 TCP 接收 10 Hz 雷達航跡（Priority: P1）🎯 MVP

**Goal**: 啟動 `echoshield-sim` 後，TCP Client 連上 `:19000` 可收到合法 NDJSON 並於斷線 / 多連線下不影響其他 Client 或主迴圈。

**Independent Test**: `nc localhost 9000` + stub RadarTrack producer（餵 1 筆固定 track 每 100ms）→ Client 於 1.0s 內收到 ≥ 8 行合法 JSON；中途 `Ctrl-C` 一個 Client 不影響另一個（符合 spec US1 Acceptance 1–3 + SC-ES-007）.

### Tests for User Story 1（先寫、先失敗）⚠️

- [X] T017 [P] [US1] Contract test `services/echoshield-sim/tests/contract/test_tcp_framing.py`: 啟動 `FeedServer`、手動 `broadcast([radar_track_json_bytes])`，TCP 連線讀 1 行 → byte 末為 `0x0A`、行內無其他 `0x0A`、`json.loads` 成功、通過 RadarTrack JSON Schema（contracts §6 #1）.
- [X] T018 [P] [US1] Unit test `services/echoshield-sim/tests/unit/test_track_serialization.py`: RadarTrack → JSON line 為 compact（`separators=(",",":")`）、UTF-8、尾端單一 `\n`；欄位順序與小數位（lat/lon 7dp、alt 1dp、vel 2dp、az/el 2dp）符合 contracts/tcp-feed.md §3.2.
- [X] T019 [P] [US1] Integration test `services/echoshield-sim/tests/integration/test_multi_client.py`: 啟動 server + 餵 2 筆固定 track；3 個並發 asyncio TCP client 連線 2 秒 → 三者收到 bit-identical bytes（允許尾端差 ≤ 1 行）；斷開 client#2 後 client#1/#3 繼續收到後續 tick（FR-ES-013/014、SC-ES-007/008）.
- [X] T020 [P] [US1] Integration test `services/echoshield-sim/tests/integration/test_quiet_mode.py`: 餵空 track list 連續 5 秒 → TCP client `reader.read(1)` 超時（或讀到 0 bytes）；連線保持開啟不被關（FR-ES-011、SC-ES-011、contracts §6 #3）.

### Implementation for User Story 1

- [X] T021 [P] [US1] Implement `services/echoshield-sim/src/echoshield_sim/feed/tcp_server.py`: `FeedServer(host, port, logger)` with `asyncio.start_server`；`clients: set[StreamWriter]`；`async def broadcast(lines: list[bytes])` 對 snapshot iterate、`writer.write(line)` + `asyncio.gather(*[w.drain() for w in snapshot], return_exceptions=True)`；failure → `discard + log client_disconnected`；`async def start()/stop()`；handler on-connect log `client_connected` + add；on-EOF / exception → discard（research.md R3）.
- [X] T022 [US1] Implement serialization helper `services/echoshield-sim/src/echoshield_sim/models/track.py::RadarTrack.to_wire_bytes(self) -> bytes`: 回傳 `json.dumps(self.model_dump(), separators=(",",":")).encode("utf-8") + b"\n"`；lat/lon/alt/vel/az/el 於 `model_dump` 前已套 `round`（或於 builder 處理，避免重複 round）.
- [X] T023 [US1] Wire minimal `loop.py` stub producing a single fixed RadarTrack every 100ms for manual smoke：`services/echoshield-sim/src/echoshield_sim/loop.py::run(config)`（僅此 Phase，Phase 4/5 會擴充；以 `asyncio.TaskGroup` 管 FeedServer + tick task）.
- [X] T024 [US1] Run US1 tests green：`pytest tests/contract/test_tcp_framing.py tests/unit/test_track_serialization.py tests/integration/test_multi_client.py tests/integration/test_quiet_mode.py -q`；手動 smoke：`echoshield-sim --config config/local.yaml` + `nc localhost 9000` 觀察固定 track 輸出.

**Checkpoint**: US1 可獨立 demo——Gateway 可連線、收到 NDJSON、多 Client fan-out 正確、安靜模式正確。

---

## Phase 4: User Story 2 — 雷達範圍內物件查詢 + Track 生命週期（Priority: P1）

**Goal**: Simulator 以 10 Hz 向 Map Sim 查詢，處理 `drone_id → track_id` 穩定映射、2.0s grace window、Lost 事件一次性；Map Sim 不可用時不退出。

**Independent Test**: 啟動 aiohttp stub Map Sim → 餵固定 `objects[]` → TCP client 收到對應 `Active` 行；移除 object + 經 2s → 收到**恰一筆** `Lost`；停掉 stub → 進程不退、log 有節流 `map_sim_unavailable`；恢復 stub → 下一 tick 恢復廣播（spec US2 Acceptance 1–3 + Edge Cases + FR-ES-003/009/010/012）。

### Tests for User Story 2（先寫、先失敗）⚠️

- [X] T025 [P] [US2] Unit test `services/echoshield-sim/tests/unit/test_lifecycle.py`: `TrackRegistry` 狀態機 per data-model.md §4 所有 transition（`(none)→ACTIVE`、`ACTIVE→ACTIVE`、`ACTIVE→GRACE`、`GRACE→ACTIVE recover`、`GRACE→(none)` 發 Lost）；`track_id` 於 Active 期間恆定；Lost 後再出現分配**新** `track_id`；以 `monotonic_now` 參數化時間（非 `time.monotonic()`）.
- [X] T026 [P] [US2] Unit test `services/echoshield-sim/tests/unit/test_mapsim_client.py`: stub aiohttp server 回傳已知 `{count,objects}` → `MapSimClient.fetch(sensor_lat, sensor_lon, radius_m)` 回傳 `list[MapSimObject]`；URL query 精確為 `lat/lon/radius_m`（**不**含 `include_lost`）；忽略 `status`；`is_lost=true` 條目被過濾；`extra="ignore"` 容忍 `distance_m`、`model` 等欄位.
- [X] T027 [P] [US2] Contract test `services/echoshield-sim/tests/contract/test_bitexact_replay.py`: fixed `--seed 42` + `freezegun` 凍結時間 + 固定 Map Sim stub objects → 連跑 3 輪廣播，比對輸出 bytes 與 golden file；回歸保護（contracts §6 #2）.
- [X] T028 [P] [US2] Integration test `services/echoshield-sim/tests/integration/test_end_to_end.py`: 真正啟動 `loop.run(config)` + aiohttp stub Map Sim；TCP client 於 1s 內收 ≥ 8 行 Active；stub 回 `count=0` → 切靜默（US2 Acceptance 1–2 + SC-ES-001）.
- [X] T029 [P] [US2] Integration test `services/echoshield-sim/tests/integration/test_lifecycle_grace.py`:
  - 情境 A（抖動吸收）：drone 出現 1s → 消失 1.5s → 重現 → 沿用相同 `track_id`、無 Lost（FR-ES-010）.
  - 情境 B（Lost 發生）：drone 出現 → 持續消失 ≥ 2.0s → 恰一筆 `Lost` 於 grace 逾時後的下一 tick、不再出現後續行.
  - 情境 C（Lost 後再出現）：Lost 之後 drone 再出現 → 分配**新** `track_id`（FR-ES-009 + SC-ES-010）.
- [X] T030 [P] [US2] Integration test `services/echoshield-sim/tests/integration/test_mapsim_unavailable.py`: 三個變體——(i) stub server 未啟動（ConnectionRefused）、(ii) 回 `500`、(iii) 回應延遲 > 1.0s（timeout）。三者皆：主迴圈**不**退出、TCP client 保持連線、`map_sim_unavailable` log 每秒 ≤ 1 行；stub 恢復後 ≤ 200ms 恢復廣播（FR-ES-003、SC-ES-009）.

### Implementation for User Story 2

- [X] T031 [P] [US2] Implement `services/echoshield-sim/src/echoshield_sim/models/lifecycle.py`: `MapSimObject`（pydantic, `extra="ignore"`, 欄位 per data-model.md §2）、`TrackState`（dataclass per §3）、`TrackRegistry` 類別封裝狀態機：`update_from_tick(seen: list[MapSimObject], now_mono: float) -> tuple[list[TrackState_active], list[TrackState_lost]]`；`track_id = f"echo-{uuid4().hex[:8]}"`；Lost 後 pop 映射（data-model.md §4 transition 表）.
- [X] T032 [P] [US2] Implement `services/echoshield-sim/src/echoshield_sim/mapsim/client.py`: `MapSimClient(session: aiohttp.ClientSession, base_url: str, timeout_s=1.0)`；`async fetch(lat, lon, radius_m) -> list[MapSimObject]`；`ClientTimeout(total=timeout_s)`；`params={"lat":…,"lon":…,"radius_m":…}`（**不**送 `include_lost`）；失敗 raise `MapSimUnavailable`（含原因 enum）；filter out `is_lost=true`（FR-ES-012）.
- [X] T033 [US2] Expand `services/echoshield-sim/src/echoshield_sim/loop.py`:
  - 建立 `aiohttp.ClientSession` lifetime 綁 TaskGroup.
  - `tick_scheduler` 用 `loop.call_at(next_deadline, …)`（research.md R1）、單 `in_flight` flag；超時則 `tick_overrun` log.
  - 每 tick：`MapSimClient.fetch` → `TrackRegistry.update_from_tick` → 將 Active + 當輪 Lost 組成 `list[RadarTrack]`（**本階段**噪點與幾何由 placeholder 替代：lat/lon/alt/speed 直接帶入、`azimuth_deg=0`、`elevation_deg=0`）→ `FeedServer.broadcast`.
  - 無 track 時**不**寫任何 bytes（FR-ES-011）.
  - Map Sim 失敗 → throttled warn + 跳過該輪、主迴圈不退.
- [X] T034 [US2] Add structured log events per research.md R7：`map_sim_query{tick_id,latency_ms,count,status_code}`、`map_sim_unavailable{reason}`（throttled）、`track_lifecycle{drone_id,track_id,event}`、`tick_overrun{tick_id,reason}`、`client_connected/disconnected{remote_addr,client_count}`.
- [X] T035 [US2] Run US2 tests green：`pytest tests/unit/test_lifecycle.py tests/unit/test_mapsim_client.py tests/contract/test_bitexact_replay.py tests/integration/test_end_to_end.py tests/integration/test_lifecycle_grace.py tests/integration/test_mapsim_unavailable.py -q`.

**Checkpoint**: US1 + US2 協同可用——真正的 Map Sim → Simulator → TCP Client 端到端；lifecycle / Lost / 安靜模式 / 失敗回復皆驗證。

---

## Phase 5: User Story 3 — 雷達誤差模擬與幾何計算（Priority: P2）

**Goal**: 以 `(sensor_lat, sensor_lon, sensor_alt_m)` 為原點，對每個 target 套 Gaussian 噪點（位置 σ=5m、高度 σ=2m、速度 σ=0.5m/s clamp ≥0）並計算 azimuth/elevation；固定 seed 可 bit-exact 重現。

**Independent Test**: 固定 seed + 已知幾何 → azimuth/elevation ≤ 0.1°；水平距離 < 1m → elevation 退化 ±90°；10k 樣本 σ 統計 ∈ [4.0m, 6.0m]（spec US3 Acceptance 1–3 + SC-ES-004/005）。

### Tests for User Story 3（先寫、先失敗）⚠️

- [X] T036 [P] [US3] Unit test `services/echoshield-sim/tests/unit/test_bearing.py`:
  - 正北 1km 同高 → `azimuth_deg ≈ 0.0 ± 0.1`、`elevation_deg ≈ 0.0 ± 0.1`（US3 Acceptance 1）.
  - 正東 1km → `azimuth_deg ≈ 90.0 ± 0.1`.
  - 正上方 100m、水平 < 1m → `elevation_deg == +90.0`（無 NaN / ZeroDivisionError，FR-ES-020、US3 Acceptance 2）.
  - 正下方 → `elevation_deg == -90.0`.
  - azimuth 回傳範圍 `[0, 360)`.
- [X] T037 [P] [US3] Unit test `services/echoshield-sim/tests/unit/test_noise.py`:
  - 固定 seed 42：連續 10,000 次 `perturb_position` 的 lat 偏移 × 111320 → 樣本 σ ∈ [4.0, 6.0]（US3 Acceptance 3、SC-ES-004）.
  - `perturb_velocity` clamp：輸入 `0.0` + σ=0.5 → 所有樣本 ≥ 0（FR-ES-018）.
  - `perturb_altitude` σ ∈ [1.5, 2.5]（1k 樣本）.
  - 同一 seed 兩次建構 `NoiseGenerator` → 前 5 筆取樣 bit-identical.
- [X] T038 [P] [US3] Contract test update `services/echoshield-sim/tests/contract/test_bitexact_replay.py`: 開啟噪點 + 幾何後，重新生成 golden 並驗證固定 seed + freezegun 下 bit-identical（contracts §6 #2 的完整版）.

### Implementation for User Story 3

- [X] T039 [P] [US3] Implement `services/echoshield-sim/src/echoshield_sim/geo/bearing.py`:
  - `haversine_m(lat1, lon1, lat2, lon2) -> float`（R=6371000）.
  - `azimuth_deg(sensor_lat, sensor_lon, target_lat, target_lon) -> float`（大圓 bearing，`% 360`、round 2）.
  - `elevation_deg(sensor_lat, sensor_lon, sensor_alt_m, target_lat, target_lon, target_alt_m) -> float`（`atan2(Δalt, horiz)`；`horiz<1.0` 則依 Δalt 符號回 ±90；round 2）.
- [X] T040 [P] [US3] Implement `services/echoshield-sim/src/echoshield_sim/geo/noise.py`:
  - `NoiseGenerator(rng: np.random.Generator, pos_sigma_m: float, alt_sigma_m: float = 2.0, vel_sigma_ms: float)`.
  - `perturb_position(lat, lon) -> (lat', lon')`（`σ/111320` 近似，research.md R4）.
  - `perturb_altitude(alt_m) -> float`.
  - `perturb_velocity(speed_ms) -> max(0.0, speed_ms + N(0, σ))`.
  - Factory `make_noise(config: RadarConfig) -> NoiseGenerator` 實作 seed 優先序（CLI > YAML > None → OS 熵，research.md R4）.
- [X] T041 [US3] Integrate noise + geometry into `services/echoshield-sim/src/echoshield_sim/loop.py`: per-target 於建構 `RadarTrack` 前 pipeline：`perturb_position` → `perturb_altitude` → `perturb_velocity` → `azimuth_deg(sensor, noised_lat_lon)` → `elevation_deg(sensor, noised_lat_lon, noised_alt)` → rounding per contracts §3.2；替換 Phase 4 的 placeholder.
- [X] T042 [US3] Run US3 tests + regenerate golden for T038：`pytest tests/unit/test_bearing.py tests/unit/test_noise.py tests/contract/test_bitexact_replay.py -q`；手動執行 quickstart.md §4 兩 instance 同 seed diff 應為空.

**Checkpoint**: 三個 User Story 皆獨立可驗；端對端輸出含真實雷達誤差語義。

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T043 [P] Docs：更新 `services/echoshield-sim/README.md` 加入 structured log 欄位表 + Quickstart 連結；更新 `docs/system-docs/` 若有服務總覽表.
- [X] T044 [P] Performance harness `services/echoshield-sim/tests/integration/test_performance.py`: 50 次 tick 量測「查詢 → 廣播」p95 ≤ 10ms（SC-ES-002）；10s 量測 tick rate ∈ [9.0, 11.0] Hz（SC-ES-001）；20 個 target 不崩潰.
- [X] T045 [P] Long-run memory smoke `services/echoshield-sim/tests/integration/test_memory.py`: 跑 5 分鐘（或 3000 tick 的壓縮版），`tracemalloc` 峰值 < 100 MB 且 registry size 無單調成長（SC-ES-012）.
- [X] T046 Run `ruff check services/echoshield-sim && black --check services/echoshield-sim` 並修復告警.
- [X] T047 執行 `specs/003-echoshield-sim/quickstart.md` §2/§3/§4/§5/§6 全部步驟；於 README 標記「quickstart 已驗證 @ commit <sha>」.
- [X] T048 Final green-light：`cd services/echoshield-sim && pytest -q`（contract + unit + integration 全綠）.

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1（Setup）→ Phase 2（Foundational）→ Phase 3/4/5（可並行，若人力允許）→ Phase 6（Polish）.
- Phase 2 為所有 User Story 的 blocking prerequisite.

### Within Each User Story（TDD 強制順序）

1. Contract tests → 紅燈.
2. Unit tests → 紅燈.
3. Integration tests → 紅燈.
4. Implementation → 逐項轉綠.
5. 整 Story 全綠 checkpoint.

### 關鍵 Task 相依

- T011/T012/T013 → T014（cli 依 config/logging/models）.
- T021 + T022 → T023（loop stub 需要 server + serializer）.
- T031 + T032 → T033（loop 依 registry + mapsim client）.
- T039 + T040 → T041（loop 整合噪點與幾何）.
- T033（Phase 4 loop）→ T041（Phase 5 替換 placeholder）.
- 所有 integration tests（T019/T020/T028/T029/T030/T044/T045）依 `loop.run` 可啟動，故 integration 的「綠燈」落在對應 implementation task 之後；但**紅燈撰寫**可與 implementation 並行先行.

### Parallel Opportunities

- Setup：T003 / T004 / T005 / T006 四者可並行（不同檔案）.
- Foundational tests：T008 / T009 / T010 並行；implementation T011 / T012 / T013 並行（T014 依序）.
- US1 tests T017 / T018 / T019 / T020 並行；implementation T021 為主要；T022 在同檔（`models/track.py`）因此**不 [P]**.
- US2 tests T025 / T026 / T027 / T028 / T029 / T030 並行；implementation T031 / T032 並行，T033 / T034 / T035 序列.
- US3 tests T036 / T037 / T038 並行；implementation T039 / T040 並行，T041 序列.
- 人力允許時，Phase 3 / 4 / 5 可由三位工程師並行，但 US3 的幾何 / 噪點最終會注入 US2 的 loop（T041 改 T033），建議 US2 先到 T033，US3 從 T041 接手.
- Polish T043 / T044 / T045 並行.

---

## Parallel Example: Phase 2 Foundational

```bash
# 同時撰寫三支先行測試（紅燈）
Task: "T008 Unit test for RadarConfig in tests/unit/test_config.py"
Task: "T009 Unit test for structlog config in tests/unit/test_logging.py"
Task: "T010 Contract test for RadarTrack schema in tests/contract/test_radar_track_schema.py"

# 紅燈完成後，三支實作並行
Task: "T011 Implement config.py"
Task: "T012 Implement logging.py"
Task: "T013 Implement models/track.py"
```

## Parallel Example: User Story 2

```bash
# 先寫六支測試（紅燈）
Task: "T025 Unit test TrackRegistry in tests/unit/test_lifecycle.py"
Task: "T026 Unit test MapSimClient in tests/unit/test_mapsim_client.py"
Task: "T027 Contract bit-exact replay in tests/contract/test_bitexact_replay.py"
Task: "T028 Integration e2e in tests/integration/test_end_to_end.py"
Task: "T029 Integration lifecycle grace in tests/integration/test_lifecycle_grace.py"
Task: "T030 Integration mapsim unavailable in tests/integration/test_mapsim_unavailable.py"

# 實作（T031 / T032 並行；T033 合流）
Task: "T031 Implement models/lifecycle.py"
Task: "T032 Implement mapsim/client.py"
```

---

## Implementation Strategy

### MVP Scope（建議）

- Phase 1 → Phase 2 → **Phase 3 (US1)** → **Phase 4 (US2)** → Stop & Demo.
- 此時 Gateway 可收到穩定 10 Hz NDJSON、Lost 事件正確、Map Sim 故障不退；輸出為無噪點「真值」。足以驗證下游 Gateway / TAK 管線.

### Incremental Delivery

1. Setup + Foundational → 基礎就緒.
2. US1 → `nc` smoke pass → Demo #1.
3. US2 → 端對端 + Lost → Demo #2（建議對 Gateway 做第一次整合測試）.
4. US3 → 雷達級誤差 → Demo #3（可給 TrackCorrelator 測 50m 關聯閾值）.
5. Polish → 效能 / 記憶體 / docs → 交付.

### Parallel Team Strategy

- Dev A：Phase 3（US1, feed/tcp_server + serializer）.
- Dev B：Phase 4（US2, mapsim client + lifecycle + loop skeleton）.
- Dev C：Phase 5（US3, geo/bearing + geo/noise，mock 注入 loop）.
- Phase 4 T033 與 Phase 5 T041 需協調合併（約定 loop 的 `build_radar_track(target, sensor, noise, now)` 介面先行）.

---

## Summary

- **Total tasks**: 48
- **By phase**: Setup 7 / Foundational 9 / US1 8 / US2 11 / US3 7 / Polish 6
- **By story**: US1 = 8（T017–T024）｜US2 = 11（T025–T035）｜US3 = 7（T036–T042）
- **Parallelizable [P] tasks**: 27
- **Contract tests**: 3（T010, T017, T027/T038）— 凍結 `RadarTrack` schema + bit-exact replay
- **Unit tests**: 7（T008, T009, T018, T025, T026, T036, T037）
- **Integration tests**: 7（T019, T020, T028, T029, T030, T044, T045）
- **Independent test criteria**:
  - **US1**: `nc localhost 9000` 收到合法 NDJSON、3-client fan-out 一致、安靜模式保連線.
  - **US2**: stub Map Sim 驅動端到端；2s grace → 恰一筆 Lost；Map Sim 故障不退出且恢復廣播.
  - **US3**: 固定 seed/幾何 → az/el ≤ 0.1°；10k 樣本 σ ∈ [4, 6]m；`horiz<1m` → ±90°.
- **Suggested MVP**: Phase 1 + Phase 2 + Phase 3 (US1) + Phase 4 (US2).

## Notes

- [P] = 不同檔案、無相依；同檔案內多 task 不得並行.
- 每個 task 皆含絕對於 repo root 的檔案路徑（或 CLI 指令）.
- TDD：Contract → Unit → Integration，每層先紅再綠；完成一個 Task 後建議立即 commit.
- 嚴守 spec `track_status` 僅 `"Active"` / `"Lost"`（**禁**用 ICD-001 的 `NEW/UPDATED/LOST`，見 contracts §3.2）.
- `services/echoshield-sim/` 結構嚴格對稱 `services/map-sim/`；新增 runtime dep 僅 `numpy`.
