# Implementation Plan: CoT Gateway

**Branch**: `005-cot-gateway` | **Date**: 2026-04-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/005-cot-gateway/spec.md`

## Summary

CoT Gateway 是 PoC 的融合與出站樞紐：以 asyncio 單進程同時 (a) 作為 TCP client 連線 EchoShield
Simulator `:9000`，逐行消費 newline-delimited JSON 航跡（10 Hz）；(b) 作為 HTTP client 以 1 Hz 輪詢
Sentrycs Simulator `:7070` 的 `GET /detections`；(c) 在記憶體內以 Haversine 距離 ≤ 50 m 且時間差 ≤ 3 s
的規則將雷達與 RF 航跡關聯為 `FUSED` Track（並以 Sentrycs `drone_id` 為融合主鍵）；(d) 依 Track
source 與狀態產生 MIL-STD-2525C / CoT 2.0 XML（`a-u-A-M-F-Q-r` 未識別灰色、`a-h-A-M-F-Q-r` 敵對紅色；
stale 三段式 0 s / 30 s / 11 s）；(e) 最後以 TCP SSL + gateway.p12（PoC `CERT_NONE`）推送至
TAK Server `:8089`，供 ATAK 顯示。Gateway 另負責 TTL 10 s 的航跡老化（下發 `stale=time` 最終 CoT）、
source 切換時以「舊 uid stale=now + 新 uid 首筆」的雙訊息交接，以及所有上下游斷線的韌性（無限重試雷達、
指數退避 1→60 s 最多 5 次 TAK、每秒補嘗試 Sentrycs）。

**技術取向**：async-first 單進程 asyncio；標準庫 `asyncio`（雷達 TCP client、TAK TCP+SSL client、所有
coroutine 協調）、`aiohttp`（僅 HTTP client，用於輪詢 Sentrycs）、`ssl`（標準庫載入 gateway.p12）、
`xml.etree.ElementTree`（CoT XML 組裝，免引入 lxml）、`pydantic v2`（`GatewayConfig` YAML + `Track`
dataclass 驗證）、`structlog`（結構化日誌）。測試 `pytest + pytest-asyncio + freezegun`（凍結 CoT `time`
/`stale` 毫秒精度）。服務目錄 `services/cot-gateway/`（hyphen，對齊 `services/echoshield-sim/` /
`services/sentrycs-sim/` / `services/map-sim/` / `services/uds/`），Python module 名 `cot_gateway`。

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**:

- runtime：
  - `asyncio`（stdlib；主事件迴圈、5 個並行 coroutine：echodyne_adapter / sentrycs_adapter / process_loop /
    ttl_loop / tak_sender；signal handler）
  - `aiohttp>=3.9`（**僅 HTTP client**；輪詢 Sentrycs `GET /detections`；不起 HTTP server——Gateway 不對外
    開 HTTP 埠）
  - `ssl`（stdlib；載入 `gateway.p12` 客戶端憑證，PoC 以 `verify_mode=CERT_NONE` 連 TAK `:8089`）
  - `xml.etree.ElementTree`（stdlib；CoT XML 組裝 — 手動控制 `time` / `stale` ISO 8601 毫秒格式與屬性順序；
    避免 lxml 依賴）
  - `pydantic>=2.6`（`GatewayConfig` YAML schema + `Track` 內部資料類；`extra="forbid"`）
  - `structlog>=24.1`（JSON 結構化日誌；格式對齊 FR-GW-026）
  - `pyyaml`（載入 `config/gateway.yaml`）
  - `cryptography`（stdlib 不足；讀 `gateway.p12` → PEM 暫存 → `SSLContext.load_cert_chain`；或使用
    `ssl.SSLContext.load_cert_chain` 搭配預先轉出的 PEM，見 research.md §4）
- dev：
  - `pytest>=8.0`、`pytest-asyncio>=0.23`（`asyncio_mode=auto`）
  - `freezegun>=1.4`（凍結 `datetime.now(timezone.utc)` → 斷言 CoT `time` / `stale` 毫秒字串）
  - `aiohttp`（test stub server，mock Sentrycs :7070）
  - `pytest`-based 自建 TCP stub（mock EchoShield :9000 newline-delimited JSON feeder；mock TAK :8089 SSL
    接收端以明文 TCP 取代便於斷言）
  - `ruff>=0.4`、`black>=24.3`

**Storage**: N/A。純 in-memory：`radar_tracks: dict[str, Track]`、`rf_tracks: dict[str, Track]`、
`fused_tracks: dict[str, Track]`、`seen_uids: set[str]`（Gateway 主程序管理的「首見」旗標，FR-GW-002 /
FR-GW-013 / FR-GW-014 交叉引用）；程序重啟 = 狀態全失。

**Testing**: pytest，目錄 `tests/{contract,integration,unit}/`，與 `services/sentrycs-sim/tests/` 三層布局
同構。

**Target Platform**: Linux server（單主機 PoC；與 EchoShield Sim / Sentrycs Sim / TAK Server 同
Docker Compose 網路）。

**Project Type**: single service / CLI（`python -m cot_gateway --config config/gateway.yaml`，無對外 HTTP
管理介面）。

**Performance Goals**:

- 端對端延遲 p95 < 100 ms、p99 < 200 ms（EchoShield `received_at` → TAK TCP socket `write`；SC-GW-001）。
- 單筆 CoT XML 生成 < 5 ms；5 航跡關聯計算 < 1 ms（SC-GW-002）。
- 穩態 ≥ 100 msg/s；`track_queue` / `cot_queue` 平均深度 < 10（SC-GW-003）。
- 記憶體 30 min 成長 < 50 MB（SC-GW-011）。

**Constraints**:

- CoT type 與 source 綁定且生命週期固定（FR-GW-015）；狀態差異僅由 `<remarks>` + `stale` 表達（FR-GW-017 /
  018），禁止在 type 上編碼狀態。
- uid 前綴切換（ECHO / SENTRYCS / FUSED 之間）MUST 以雙訊息模式處理：舊 uid 先發 `stale=time` 最終 CoT，再以新
  uid 發首筆（FR-GW-014）；`seen_uids` 同步移除舊 uid。
- TrackCorrelator 禁一對多匹配；多候選時取距離最小（FR-GW-010、Acceptance Scenario US2-6）。
- TAK queue 滿 500 drop-newest（FR-GW-022）；TAK 連線達 `max_retries=5` 後 exit code ≠ 0（FR-GW-021、Edge
  Case「TAK 憑證拒絕」）。
- EchoShield 斷線無限重試 5 s（FR-GW-004）；Sentrycs 錯誤 skip 當次輪詢（FR-GW-007），兩者彼此隔離不互相中止。
- 所有時間戳一律 UTC aware；CoT `time`/`start` 以 Gateway 產 CoT 當下時間（`datetime.now(timezone.utc)`）
  為準，sensor `timestamp` 僅用於關聯時間窗（Assumptions §6）。

**Scale/Scope**:

- PoC ≤ 5 架並行航跡（雷達 10 Hz + RF 1 Hz = ~55 msg/s 穩態）；≤ 20 架仍不崩潰。
- 單主機單進程；無水平擴展；不開管理埠。

## Constitution Check

> `.specify/memory/constitution.md` 尚未初始化（仍為 template placeholder）。本 plan 沿用
> `003-echoshield-sim` / `004-sentrycs-sim` 已建立的 **PoC 自律準則**作為替代檢核門檻；當專案憲章正式建立後，
> 本節 **MUST** 重新評估。

**Gate: PoC Self-Discipline（取代正式 Constitution Check）**

| 準則 | 檢核 | 狀態 |
| --- | --- | --- |
| G1. 測試先行（Test-First） | contract（CoT XML schema、Echodyne wire parser、Sentrycs poller、TAK uplink 四份契約凍結）、integration（US1 雷達單源端對端 / US2 融合升級 + source 切換雙訊息 / US3 斷線重連 + TTL / SIGINT 優雅關閉）、unit（Haversine、TTL 清理、stale 三段式、remarks 組裝、uid 前綴切換）三層先寫 | PASS |
| G2. 契約凍結（Contract Freeze） | 對上游 EchoShield = `contracts/echodyne-wire.md`（reuse `specs/003-echoshield-sim/contracts/` wire schema）；對上游 Sentrycs = `contracts/sentrycs-poller.md`（引用 `specs/004-sentrycs-sim/contracts/http-status-api.md`，不得漂移）；對下游 TAK = `contracts/tak-uplink.md`；對外輸出 = `contracts/cot-xml.md`（CoT 2.0 schema） | PASS |
| G3. 結構化日誌（Structured Logging） | 全程 structlog JSON；INFO 含 `track_first_seen` / `correlation_hit` / `source_switch` / `ttl_expired` / `tak_connected` / `tak_reconnect`；WARNING 含 `queue_full_drop` / `sentrycs_poll_failed` / `echoshield_disconnected`；ERROR 含 `tak_max_retries_exceeded` / `invalid_wire_fields` | PASS |
| G4. 可觀測性（Observability） | 關鍵 event：`echoshield_connected`、`track_parsed`、`sentrycs_poll`、`correlate_hit/miss`、`ttl_expired`、`cot_generated`、`tak_send`、`queue_full_drop`、`source_switch`、`shutdown` | PASS |
| G5. 結構對稱（Layout Symmetry） | `services/cot-gateway/src/cot_gateway/` 嚴格對齊 `services/sentrycs-sim/src/sentrycs_sim/`（`cli.py` / `config.py` / `logging.py` / `__main__.py` + 次級 package `models/`、`echoshield/`、`sentrycs/`、`correlate/`、`cot/`、`tak/`、`loop.py`）；tests 三層與 `services/sentrycs-sim/tests/` 同構 | PASS |
| G6. 無新存儲（No Persistence） | 不引入 DB / 檔案；航跡字典與 queue 純 in-memory；重啟即失效；TTL 控成長 | PASS |
| G7. 依賴最小化（Dependency Minimalism） | runtime 僅 `aiohttp`（HTTP client 輪詢 Sentrycs）+ `pydantic` + `structlog` + `pyyaml`；CoT XML 用 stdlib `xml.etree.ElementTree`（不引入 lxml）；Haversine 手寫（~10 行，不引入 geopy）；SSL 用 stdlib `ssl`；p12 解析以 `cryptography` 一次性讀取為 PEM（若已離線轉出 `.pem`/`.key` 則可完全免該依賴） | PASS |

**Pre-Phase-0 Gate**: ✅ PASS。無違反，不需 Complexity Tracking。

**Post-Phase-1 Gate**（§Phase 1 完成後重評）: ✅ PASS。設計仍滿足 G1–G7；特別確認：

- `contracts/` 4 份檔案（1 對外 CoT XML + 3 對上/下游 caller），皆指向既有或本服務 wire schema，無重複定義
  （G2）；
- `data-model.md` 所有實體皆為 in-memory runtime 物件（G6）；`Track` dataclass 為唯一跨模組流通型別；
- `quickstart.md` 以 `docker compose up` + `python -m cot_gateway` + `curl`（驗證 Sentrycs 來源）+ `openssl
  s_client` / `ncat --ssl`（旁觀 TAK uplink）為主，未引入額外工具鏈（G4）；
- 確認不引入 lxml / geopy / FastAPI / uvicorn（G7）。

## Project Structure

### Documentation (this feature)

```text
specs/005-cot-gateway/
├── spec.md                    # 既存 /speckit.specify + /speckit.clarify 產物
├── plan.md                    # 本檔
├── research.md                # Phase 0 產物
├── data-model.md              # Phase 1 產物
├── quickstart.md              # Phase 1 產物
├── contracts/
│   ├── cot-xml.md             # 對外：CoT 2.0 XML schema（event/point/detail/remarks/track）+ uid/type/stale 政策
│   ├── echodyne-wire.md       # 上游 caller：EchoShield TCP newline-delimited JSON（reuse 003 contract）
│   ├── sentrycs-poller.md     # 上游 caller：Sentrycs HTTP GET /detections 輪詢（reuse 004 contract）
│   └── tak-uplink.md          # 下游 caller：TAK Server :8089 TCP+SSL + newline-delimited CoT XML
├── checklists/                # 既有 /speckit.checklist 產物（若有）
└── tasks.md                   # Phase 2 產物（/speckit.tasks 產生，非本命令）
```

### Source Code (repository root)

```text
services/cot-gateway/
├── pyproject.toml                        # 對齊 sentrycs-sim / echoshield-sim 樣式（setuptools、ruff、black、pytest-asyncio）
├── README.md
├── scripts/
│   └── smoke.sh                          # 對齊 services/sentrycs-sim/scripts/smoke.sh
├── config/
│   ├── gateway.yaml                      # 範例設定：echoshield/sentrycs/correlator/tak_server 四段
│   └── certs/
│       ├── gateway.p12                   # PoC 客戶端憑證（gitignore；範例由 docker compose 提供）
│       └── README.md                     # 如何產生/替換憑證
├── src/
│   └── cot_gateway/
│       ├── __init__.py
│       ├── __main__.py                   # python -m cot_gateway
│       ├── cli.py                        # argparse：--config、--verbose
│       ├── config.py                     # pydantic Settings：GatewayConfig YAML loader + fail-fast 校驗（port 範圍、ttl>0、p12 存在）
│       ├── logging.py                    # structlog JSON configurator；格式符合 FR-GW-026
│       ├── models/
│       │   ├── __init__.py
│       │   └── track.py                  # UnifiedTrack dataclass（source/track_id/lat/lon/alt_m/... 見 data-model §1）+ TrackSource Enum
│       ├── echoshield/
│       │   ├── __init__.py
│       │   └── adapter.py                # EchodyneAdapter：asyncio TCP client、逐行 JSON、欄位驗證、無限重試 5s、enqueue track_queue
│       ├── sentrycs/
│       │   ├── __init__.py
│       │   └── adapter.py                # SentrycsAdapter：aiohttp client、1Hz 輪詢、HTTP 錯誤 skip、enqueue track_queue
│       ├── correlate/
│       │   ├── __init__.py
│       │   ├── haversine.py              # 手寫 Haversine（地球半徑 6,371,000m）
│       │   └── correlator.py             # TrackCorrelator：radar_tracks / rf_tracks / fused_tracks 三字典、correlate(track)、update_ttl()
│       ├── cot/
│       │   ├── __init__.py
│       │   ├── uid.py                    # Track.source + ids → uid；source 切換偵測（回傳 old_uid, new_uid）
│       │   ├── stale.py                  # 三段式 stale 計算（Lost=0s / NEUTRALIZED=30s / 其他=11s）
│       │   └── generator.py              # CotGenerator.generate(track) → str；xml.etree.ElementTree 組裝；毫秒精度 ISO 8601
│       ├── tak/
│       │   ├── __init__.py
│       │   ├── ssl_context.py            # 載入 gateway.p12 → SSLContext（PoC CERT_NONE）
│       │   └── transmitter.py            # TakTransmitter：TCP+SSL、_cot_queue(500)、指數退避 1→60s 最多 5 次、queue 滿 drop-newest、達上限 raise
│       └── loop.py                       # GatewayMain：組裝 5 個 coroutine、track_queue / cot_queue、TTL 1Hz tick、signal handler、優雅關閉（≤3s）
└── tests/
    ├── __init__.py
    ├── conftest.py                       # 共用 fixture：echoshield_stub（TCP feeder）、sentrycs_stub（aiohttp test server）、tak_stub（TCP sink，替代 SSL 以簡化斷言）、frozen_clock、sample_tracks
    ├── contract/
    │   ├── test_cot_xml_schema.py        # 對 contracts/cot-xml.md：event/point/detail 必備屬性、type/stale/uid 規則對 8 類場景 100% 合規（SC-GW-009、SC-GW-012）
    │   ├── test_echodyne_wire.py         # 對 contracts/echodyne-wire.md：必填 10 欄、值域、track_status enum {Active,Lost}、非法 → WARNING skip
    │   ├── test_sentrycs_poller.py       # 對 contracts/sentrycs-poller.md：空陣列保留 rf_tracks、5xx skip、1Hz tick
    │   └── test_tak_uplink.py            # 對 contracts/tak-uplink.md：newline-delimited、queue 滿 drop-newest、指數退避序列 1/2/4/8/16 封頂 60s
    ├── integration/
    │   ├── test_us1_radar_only_e2e.py    # US1：EchoShield Sim → Gateway → TAK stub；uid=ECHO-TRK-001、type=a-u-A-M-F-Q-r、hae=altitude_m
    │   ├── test_us2_fusion_upgrade.py    # US2：50m/3s 內融合；source_switch 雙訊息（舊 ECHO-* stale=now + 新 FUSED-DRN-001 首筆）；remarks 隨 DETECTED→MITIGATING→NEUTRALIZED 變；stale=30s for NEUTRALIZED
    │   ├── test_us2_no_cross_match.py    # >200m 不交叉關聯；多候選取距離最小；禁一對多
    │   ├── test_us3_echoshield_reconnect.py  # 斷線 5s → 5s 後重連；主程序不退出；Sentrycs 與 TAK 不受影響
    │   ├── test_us3_tak_exp_backoff.py   # TAK 不可達 → 1/2/4/8/16 退避；queue 滿 drop-newest WARNING；5 次後 exit code≠0
    │   ├── test_us3_ttl_expiry.py        # 雷達 >10s 未更新 → 下秒 tick 推送 stale=time 最終 CoT、從 seen_uids 移除
    │   └── test_graceful_shutdown.py     # SIGINT/SIGTERM → 停接收 → 排空 cot_queue（≤3s）→ exit code 0
    └── unit/
        ├── test_haversine.py             # 台北 ↔ 台北 50m 邊界；跨經度；極區輸入
        ├── test_correlator_ttl.py        # TTL 10s 邊界、seen_uids 同步移除、track_status 轉 Lost
        ├── test_correlator_match.py      # 50m / 3s 四象限；多候選取最小；time_window 超出跳過
        ├── test_uid_source_switch.py     # ECHO→FUSED、SENTRYCS→FUSED、FUSED→ECHO 三種切換的 (old_uid, new_uid) 正確性
        ├── test_stale_policy.py          # 三段式 stale（Lost 優先於 NEUTRALIZED 優先於其他）；毫秒精度 `stale - time` == {0, 30_000, 11_000} ms
        ├── test_cot_generator.py         # remarks 組合（缺欄位省略）、XML 屬性順序/逸出、ISO 8601 毫秒、freezegun 凍結 time
        ├── test_config_fail_fast.py      # 非法 port / ttl<=0 / p12 不存在 → 啟動即拋
        └── test_logging.py               # structlog 事件 key 齊全（含 FR-GW-026 的 event 名單）
```

**Structure Decision**: 採「single service 單包」布局，與 `services/sentrycs-sim/`、`services/echoshield-sim/`
完全同構（hyphen 目錄名、底線 Python 模組名、`src/<module>/` + `tests/{contract,integration,unit}/`）。
次級 package 以「上游 adapter / 核心 correlator / CoT 產生 / 下游 transmitter」四層切分，每層單一職責，
便於 G2 契約凍結與 G1 測試先行。不採 Web 應用或多專案布局，因為 Gateway 不對外開 HTTP 埠（僅 TCP client
+ HTTP client + TCP SSL client），也不需要 frontend。

## Phase 0: Outline & Research — 已產出

詳見 [`research.md`](./research.md)。主要決策（摘要）：

1. **CoT XML 函式庫選型** → `xml.etree.ElementTree`（stdlib），放棄 lxml。
2. **SSL / p12 載入** → `cryptography.hazmat` 讀 p12 一次性轉 PEM，注入 `SSLContext.load_cert_chain`；
   PoC `verify_mode=CERT_NONE`。
3. **Haversine 實作** → 手寫 ~10 行，不依賴 geopy。
4. **Async 架構** → 5 coroutine + 2 queue（`track_queue` 1000、`cot_queue` 500）；單 processing loop。
5. **source 切換雙訊息** → `cot/uid.py` 回傳 `(old_uid, new_uid)`，process_loop 在 enqueue 新 CoT 前先
   enqueue 舊 uid 的 `stale=time` 最終 CoT。
6. **freezegun + 毫秒 ISO 8601** → `datetime.now(timezone.utc).isoformat(timespec="milliseconds")` 於凍結
   時鐘下穩定。

所有 NEEDS CLARIFICATION 皆已於 spec.md `Clarifications` 三輪問答中解決；本 plan 無殘留未決項。

## Phase 1: Design & Contracts — 已產出

- [`data-model.md`](./data-model.md)：`UnifiedTrack` dataclass、`TrackSource` Enum、三字典 registry、
  `seen_uids` 首見旗標、`CotEvent`（str）、`TakConnection` 狀態機，以及「source 切換 → (old_uid, new_uid)
  雙訊息」的 runtime 狀態轉移表。
- [`contracts/cot-xml.md`](./contracts/cot-xml.md)：CoT 2.0 XML schema，含 `uid` / `type` / `stale` 對 8
  類場景的合規表（SC-GW-012）。
- [`contracts/echodyne-wire.md`](./contracts/echodyne-wire.md)：上游 EchoShield TCP JSON 契約（引用
  `specs/003-echoshield-sim/contracts/` 為權威，僅新增 Gateway 側「首見旗標由 Gateway 管理」的消費規則）。
- [`contracts/sentrycs-poller.md`](./contracts/sentrycs-poller.md)：上游 Sentrycs HTTP 輪詢契約（引用
  `specs/004-sentrycs-sim/contracts/http-status-api.md`；Gateway 側僅定義輪詢頻率、錯誤處理、欄位對應）。
- [`contracts/tak-uplink.md`](./contracts/tak-uplink.md)：下游 TAK Server `:8089` TCP+SSL +
  newline-delimited CoT 契約，含指數退避、queue 滿策略、憑證載入。
- [`quickstart.md`](./quickstart.md)：Docker Compose 拉起 4 服務 → `python -m cot_gateway` → `openssl
  s_client` 驗證 TAK 出站 → ATAK 截圖斷言；含三種失效演練腳本（US3）。

**Agent context update**：已將 `.github/copilot-instructions.md` 的 `<!-- SPECKIT START -->` 區塊指向本
plan（`specs/005-cot-gateway/plan.md`）。

## Complexity Tracking

*(空 — Constitution Check 無違反)*
