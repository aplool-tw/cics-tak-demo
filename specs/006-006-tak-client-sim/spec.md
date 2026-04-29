# Feature Specification: TAK Client Simulator

**Feature Branch**: `feature/006-tak-client-sim`  
**Created**: 2026-04-29  
**Status**: Draft  
**Feature Directory**: `specs/006-006-tak-client-sim/`

## Overview

TAK Client Simulator（`tak-client-sim`）是一個輕量 Python 服務，扮演真實 Android TAK（ATAK）客戶端的替代角色，用於端對端驗證整條 PoC 資料鏈：

```
EchoShield Sim → CoT Gateway → TAK Server :8089 → [TAK Client Sim]
Sentrycs Sim  ↗
```

服務以 TCP+SSL 連線至 TAK Server，持續接收 Newline-delimited CoT XML，將每筆事件解析後以人讀格式輸出至 console，並以結構化 JSON 日誌並行記錄。當 TAK Server 不可用時自動指數退避重連；收到 SIGINT/SIGTERM 後優雅關閉並列印統計摘要，讓 demo 操作員不需要實體 Android 裝置即可確認整條鏈路正常運作。

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — 端對端鏈路驗證 (Priority: P1)

Demo 操作員在不使用實體 ATAK 裝置的情況下，需要確認整條 PoC 鏈路（EchoShield Sim / Sentrycs Sim → CoT Gateway → TAK Server）確實有將 CoT 事件下發。操作員啟動 `tak-client-sim`，觀察 console 持續出現新的 CoT 事件行，即可確認上游各服務正常運作。

**Why this priority**：這是本服務存在的核心理由——取代真實 ATAK 進行驗收確認，直接影響 PoC demo 能否自驗。

**Independent Test**：使用 TAK Server stub（測試用 TCP 伺服器）發送 3 筆 CoT XML 行，驗證 `tak-client-sim` 的 console 輸出包含正確的 uid、type、lat/lon 數值。

**Acceptance Scenarios**:

1. **Given** TAK Server stub 已就緒並持續送出 CoT XML，**When** `tak-client-sim` 啟動並連線成功，**Then** 每筆 CoT 在 1 秒內出現於 console，格式為 `[time] uid type lat/lon speed remarks`
2. **Given** `tak-client-sim` 正在接收 CoT，**When** 連線被中斷後 TAK Server 重新上線，**Then** `tak-client-sim` 在指數退避後自動重連，不需要人工介入
3. **Given** 操作員按下 Ctrl-C，**When** SIGINT 送達，**Then** `tak-client-sim` 完成當前事件處理後優雅關閉，並於 console 列印接收筆數摘要

---

### User Story 2 — CoT 事件解析正確性驗證 (Priority: P1)

QA 工程師需要逐筆確認 CoT Gateway 產出的 CoT XML 欄位是否符合凍結契約（uid 前綴、type、stale delta 等）。`tak-client-sim` 的 console 輸出需同時顯示 source 標籤（ECHO/SENTRYCS/FUSED）、敵友顏色標籤（灰/紅）、以及 stale delta_s，讓工程師無需手動解析 XML 即可判斷正確性。

**Why this priority**：直接服務於合規矩陣驗證（8 場景），是 PoC 驗收的關鍵輸出。

**Independent Test**：提供預先製作的 CoT XML fixture（含 ECHO 灰、FUSED 紅、NEUTRALIZED stale+30s 三種），確認 console 輸出的 source 標籤、顏色標籤、delta_s 皆正確。

**Acceptance Scenarios**:

1. **Given** 收到 uid `ECHO-TRK-001` 的 CoT，**When** 解析完成，**Then** console 顯示 `[ECHO][GREY]` 標籤
2. **Given** 收到 uid `FUSED-DRN-001` 的 CoT（type `a-h-A-M-F-Q-r`），**When** 解析完成，**Then** console 顯示 `[FUSED][RED]` 標籤
3. **Given** 收到 stale 比 time 早 30 秒的 CoT（NEUTRALIZED），**When** 解析完成，**Then** console 顯示 `delta_s=+30`
4. **Given** 收到 stale 等於 time 的 CoT（Lost），**When** 解析完成，**Then** console 顯示 `delta_s=0`

---

### User Story 3 — 過濾特定來源事件 (Priority: P2)

Demo 操作員需要單獨觀察某一資料來源（例如只看融合結果 `FUSED-`），而不被其他來源的 console 輸出干擾。`tak-client-sim` 提供 `--filter` CLI 參數，讓操作員只顯示特定 UID 前綴的事件。

**Why this priority**：Demo 場景中多來源事件並行時，過濾能力讓驗證目標更聚焦；但不影響連線與接收功能本身。

**Independent Test**：啟動時加上 `--filter FUSED`，送入混合 ECHO/SENTRYCS/FUSED 的 CoT 串，確認 console 只出現 FUSED 開頭的行，但結構化日誌仍記錄全部事件。

**Acceptance Scenarios**:

1. **Given** `--filter FUSED` 已設定，**When** 接收到 `ECHO-TRK-001` 的 CoT，**Then** console **不**輸出該行，但 structlog JSON 仍記錄 `cot_received`（`filtered=true`）
2. **Given** `--filter FUSED` 已設定，**When** 接收到 `FUSED-DRN-001` 的 CoT，**Then** console 正常輸出該行
3. **Given** 無 `--filter` 參數，**When** 接收任何 CoT，**Then** console 輸出全部來源

---

### User Story 4 — 日誌檔持久化 (Priority: P2)

Demo 執行後，操作員或 CI 腳本需要能回顧完整的 CoT 事件記錄，包含所有欄位值（含被過濾的事件）。`tak-client-sim` 提供 `--log-file <path>` 選項，將 structlog JSON 日誌同步寫入指定檔案。

**Why this priority**：PoC 驗收需要留存證據；log-file 讓 smoke test 腳本能斷言事件是否有被接收。

**Independent Test**：以 `--log-file /tmp/tak-client.log` 啟動，送入 5 筆 CoT，Ctrl-C 後確認 log 檔含 5 筆 `cot_received` JSON 行及 1 筆 `session_summary` JSON 行。

**Acceptance Scenarios**:

1. **Given** `--log-file /tmp/tak.log` 已設定，**When** 接收 5 筆 CoT，**Then** log 檔包含 5 筆 `event=cot_received` JSON 行
2. **Given** `--log-file` 已設定且 `--filter FUSED` 同時生效，**When** 接收混合 CoT，**Then** log 檔記錄全部事件（含 `filtered=true` 欄位的非 FUSED 事件）
3. **Given** 程式優雅關閉，**When** session 結束，**Then** log 檔最後一行為 `event=session_summary`，含 `total_received`、per-uid breakdown

---

### User Story 5 — 自動重連韌性 (Priority: P2)

Demo 期間 TAK Server 可能因環境問題短暫不可用。`tak-client-sim` 需在重連成功後繼續接收，且重連嘗試記錄於 console 和 structlog，讓操作員能即時得知狀態。

**Why this priority**：PoC 環境不穩定，可靠的重連避免 demo 中斷需要人工重啟。

**Independent Test**：TAK stub 連線建立後主動斷線，確認 `tak-client-sim` 以指數退避序列（1s→2s→4s→…上限 60s）嘗試重連，重連成功後繼續接收新 CoT。

**Acceptance Scenarios**:

1. **Given** TAK Server 暫時不可用，**When** 連線被重置，**Then** `tak-client-sim` 在不超過 60 秒間隔的指數退避後嘗試重連，console 顯示 `Reconnecting... (attempt N)`
2. **Given** 重連嘗試超過設定上限（預設不設硬性上限，可配置），**When** 達上限，**Then** `tak-client-sim` 輸出錯誤摘要並以非零 exit code 退出
3. **Given** 重連成功，**When** TAK Server 再度可用，**Then** `tak-client-sim` 繼續正常接收且重連計數歸零

---

### Edge Cases

- **超長 CoT XML 行**：單行 CoT XML 超過 64 KB 時，服務丟棄該行並記錄 `cot_oversized` warning，繼續處理下一行，不崩潰
- **無效 XML**：收到格式錯誤的 XML（非法字元、未閉合標籤）時，服務記錄 `cot_parse_error` warning 並跳過，不崩潰
- **缺少必要屬性**：CoT `<event>` 缺少 `uid` 或 `type` 時，視同無效 XML 處理
- **連線中途收到半行**：TCP 分包導致 CoT XML 行被截斷時，服務等待 `\n` 完整後再解析，不提前輸出
- **stale 早於 time（異常）**：若 stale < time（理論上僅 Lost 的 stale=time），delta_s 顯示為 0 而非負值
- **大量高頻事件**：同時接收 50+ UPS（updates per second）時，console 輸出不阻塞接收迴圈
- **`--filter` 空字串**：若 `--filter ""` 被傳入，視為不過濾（等同未設定 `--filter`）
- **log-file 路徑不可寫**：若 `--log-file` 指定路徑無寫入權限，服務啟動時即 fail-fast 並提示錯誤，不靜默忽略
- **stale CoT（time 極舊）**：服務正常接收並輸出，於 console 額外顯示 `[STALE]` 標記（stale 時間早於接收當下超過 30 秒）

---

## Requirements *(mandatory)*

### Functional Requirements

#### 連線管理

- **FR-TCS-001**: 服務 MUST 以 asyncio TCP+SSL 連線至 TAK Server，端點由設定檔驅動（預設 `tak-server:8089`）
- **FR-TCS-002**: 服務 MUST 支援 PoC 模式（`use_ssl_verify=false`）：`verify_mode=CERT_NONE`、`check_hostname=False`，無需客戶端憑證
- **FR-TCS-003**: 服務 MUST 支援正式憑證模式（`use_ssl_verify=true`）：可從設定檔指定 CA bundle 路徑
- **FR-TCS-004**: 服務 MUST 在連線失敗或連線中斷時執行指數退避重連，初始延遲 1s，倍增至上限 60s
- **FR-TCS-005**: 設定檔 MUST 提供 `max_retries` 選項（預設 0 = 無限重試），達上限時以 exit code 1 終止，並記錄 `max_retries_exceeded` 事件
- **FR-TCS-006**: 每次重連嘗試 MUST 在 console 輸出 `Reconnecting... (attempt N, delay Xs)` 並記錄 structlog `reconnecting` 事件

#### CoT 接收與解析

- **FR-TCS-010**: 服務 MUST 以 Newline-delimited（`\n`）方式分幀讀取 CoT XML，不使用 length-prefix
- **FR-TCS-011**: 服務 MUST 以標準庫 `xml.etree.ElementTree` 解析 CoT XML，**禁用** lxml
- **FR-TCS-012**: 服務 MUST 從每筆 CoT XML 提取以下欄位：`uid`、`type`、`time`、`stale`、`lat`、`lon`、`hae`、`speed`（`<track speed>`）、`course`（`<track course>`）、`remarks`（`<remarks>` 文字）
- **FR-TCS-013**: 服務 MUST 計算 `delta_s = stale - time`（秒，整數四捨五入），用於 stale 正確性驗證
- **FR-TCS-014**: 服務 MUST 從 UID 前綴推導 `source`：`ECHO-` → `ECHO`；`SENTRYCS-` → `SENTRYCS`；`FUSED-` → `FUSED`；其餘 → `UNKNOWN`
- **FR-TCS-015**: 服務 MUST 從 CoT `type` 推導顏色標籤：`a-u-*` → `GREY`；`a-h-*` → `RED`；其餘 → `UNKNOWN`
- **FR-TCS-016**: 單行 CoT XML 超過 64 KB 時，MUST 丟棄並記錄 `cot_oversized` warning，服務繼續運行
- **FR-TCS-017**: XML 解析失敗時，MUST 記錄 `cot_parse_error` warning（含原始行前 200 字元），服務繼續運行
- **FR-TCS-018**: `<event>` 缺少 `uid` 或 `type` 屬性時，視同解析失敗處理（FR-TCS-017）

#### Console 輸出

- **FR-TCS-020**: 每筆 CoT 事件 MUST 在 console 輸出單行格式（`stdout`）：
  ```
  [TIME] [SOURCE][COLOR] uid  lat/lon  hae  speed  course  delta_s=N  remarks
  ```
  範例：
  ```
  [2026-04-24T12:34:56.789Z] [ECHO][GREY] ECHO-TRK-001  25.059800/121.565400  101.0m  12.5m/s  045°  delta_s=+11  Source: ECHOSHIELD | Speed: 12.5m/s | Alt: 101m
  ```
- **FR-TCS-021**: 若收到事件的 stale 時間早於當前時刻超過 30 秒，MUST 在行首附加 `[STALE]` 標記
- **FR-TCS-022**: `--filter <PREFIX>` 參數生效時，uid 不以指定前綴開頭的事件 MUST 不輸出至 console（但仍記錄至 structlog）
- **FR-TCS-023**: console 輸出使用 `print()`（CLI smoke 場景允許）；**禁止**在核心解析（parser.py）與連線邏輯（connection.py）中使用 `print()`，**例外**：`connection.py` 的 `connect_with_retry()` 允許以 `print()` 輸出重連進度訊息（`Reconnecting...`），因其為面向操作員的即時 console 提示

#### 結構化日誌

- **FR-TCS-030**: 每筆成功解析的 CoT MUST 以 structlog JSON 記錄 `cot_received` 事件，欄位：`uid`、`source`、`color`、`type`、`time`、`stale`、`delta_s`、`lat`、`lon`、`hae`、`speed`、`course`、`remarks`、`filtered`（bool）
- **FR-TCS-031**: 服務啟動成功連線後 MUST 記錄 `tak_connected` 事件（含 host、port）
- **FR-TCS-032**: 連線斷線時 MUST 記錄 `tak_disconnected` 事件（含 error 訊息）
- **FR-TCS-033**: 每次重連嘗試 MUST 記錄 `reconnecting` 事件（含 attempt、delay_s）
- **FR-TCS-034**: 重連成功後 MUST 記錄 `tak_reconnected` 事件
- **FR-TCS-035**: 程式優雅關閉時 MUST 記錄 `session_summary` 事件（含 `total_received`、`total_filtered`、`total_parse_errors`、`per_source` breakdown、`per_uid` breakdown）
- **FR-TCS-036**: `--log-file <path>` 參數生效時，structlog JSON 日誌 MUST 同步寫入指定檔案（同時輸出至 stderr 可選）；console human-readable 輸出仍寫至 stdout

#### CLI 介面

- **FR-TCS-040**: 服務 MUST 提供以下 CLI 參數：
  | 參數 | 預設值 | 說明 |
  |------|--------|------|
  | `--host` | `tak-server` | TAK Server 主機名稱或 IP |
  | `--port` | `8089` | TAK Server 連接埠 |
  | `--no-ssl-verify` | （不設定，依 config 預設 `use_ssl_verify=false`） | PoC 模式，跳過 SSL 憑證驗證（旗標存在即 `use_ssl_verify=False`） |
  | `--filter` | （不設定） | 僅顯示符合此 UID 前綴的事件 |
  | `--log-file` | （不設定） | structlog JSON 寫入目標檔案路徑 |
  | `--max-retries` | `0`（無限） | 最多重連次數，0 為無限 |
  | `--config` | （不設定） | YAML 設定檔路徑（CLI 參數優先） |
- **FR-TCS-041**: `--config` YAML 設定檔 MUST 以 pydantic v2 驗證，多餘欄位即 fail-fast，設定不合法時顯示友善錯誤並以 exit code 2 退出
- **FR-TCS-042**: CLI 參數優先於 YAML 設定檔中同名設定

#### Graceful Shutdown

- **FR-TCS-050**: 服務 MUST 攔截 SIGINT 與 SIGTERM 訊號
- **FR-TCS-051**: 收到訊號後 MUST 停止接受新資料、完成當前行的解析與輸出，再關閉 SSL socket
- **FR-TCS-052**: 關閉前 MUST 在 console 列印統計摘要（總接收筆數、各 source 筆數、解析錯誤數），並記錄 `session_summary` 至 structlog
- **FR-TCS-053**: 正常關閉以 exit code 0 退出；達最大重連上限以 exit code 1 退出；設定檔錯誤以 exit code 2 退出

#### 服務結構

- **FR-TCS-060**: 服務 MUST 放置於 `services/tak-client-sim/`，Python module 名稱 `tak_client_sim`
- **FR-TCS-061**: 目錄結構 MUST 遵循 G5 對稱標準：`src/tak_client_sim/`、`tests/{contract,unit,integration}/`、`pyproject.toml`、`README.md`、`scripts/smoke.sh`
- **FR-TCS-062**: 服務 MUST 無持久化（G6）：重啟統計歸零
- **FR-TCS-063**: 服務 MUST 優先使用標準庫（G7）；依賴清單：`pydantic>=2.6`、`structlog>=24.1`、`pyyaml`（選配 `--config`）；無 `aiohttp`、`cryptography`（client 不需 p12 解析）、`lxml`

---

### Key Entities

- **`CotEvent`**：代表一筆已解析的 CoT 事件，包含：`uid`（str）、`source`（ECHO/SENTRYCS/FUSED/UNKNOWN）、`color`（GREY/RED/UNKNOWN）、`cot_type`（str）、`time`（datetime UTC）、`stale`（datetime UTC）、`delta_s`（int，stale-time 秒數）、`lat`（float）、`lon`（float）、`hae`（float）、`speed`（float）、`course`（float）、`remarks`（str）、`raw_xml`（str，原始行，供除錯）

- **`ClientConfig`**：服務設定，由 pydantic v2 驗證，包含：`host`（str）、`port`（int）、`use_ssl_verify`（bool，預設 False）、`ca_bundle`（Optional[str]，SSL verify 時用）、`max_retries`（int，0=無限）、`backoff_initial_s`（float，預設 1.0）、`backoff_cap_s`（float，預設 60.0）、`filter_prefix`（Optional[str]）、`log_file`（Optional[str]）

- **`ConnectionStats`**：執行時期統計（記憶體內），包含：`total_received`（int）、`total_filtered`（int）、`total_parse_errors`（int）、`total_oversized`（int）、`reconnect_count`（int）、`per_source`（Dict[str, int]）、`per_uid`（Dict[str, int]）；程式退出前匯出為 `session_summary` JSON 事件

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-TCS-001**: 在 TAK Server stub 正常情況下，每筆 CoT XML 從接收至出現於 console 的延遲 ≤ 100ms（本機環境）
- **SC-TCS-002**: 服務能正確解析並輸出合規矩陣中 8 種場景（見凍結契約 `specs/005-cot-gateway/contracts/cot-xml.md` §7）的全部 CoT，正確率 100%（source 標籤、顏色標籤、delta_s 均正確）
- **SC-TCS-003**: 在連線中斷後，服務能於 TAK Server 重上線的 2 個退避週期內自動重連，不需人工介入
- **SC-TCS-004**: 接收到格式錯誤的 CoT XML 時，服務不崩潰，能繼續處理後續正常 CoT，整體可用性不受單筆壞資料影響
- **SC-TCS-005**: 持續接收 50+ 筆/秒的 CoT 時，console 輸出與 structlog 寫入不造成接收迴圈積壓（無事件被靜默丟棄，除非明確使用 `--filter`）
- **SC-TCS-006**: 程式在收到 SIGINT 後 3 秒內完成關閉並輸出統計摘要
- **SC-TCS-007**: `--filter PREFIX` 過濾功能確保 console 僅顯示符合前綴的事件，但 structlog log-file 仍記錄全部事件（含 `filtered=true` 標記）
- **SC-TCS-008**: contract test 覆蓋凍結契約的全部 8 場景，unit test 覆蓋解析邏輯的 happy path 與 4 類錯誤情境（oversized、invalid XML、missing uid、missing type），integration test 驗證端對端流程（stub TAK Server → tak-client-sim console 輸出）

---

## Assumptions

- **TAK Server 為純下行**：本服務角色為被動接收端，不向 TAK Server 發送任何 CoT 或確認訊息（與凍結契約 `tak-uplink.md` §1「無反向訊息需消費」一致）
- **無客戶端憑證需求**：PoC 環境 `use_ssl_verify=false`，無需 .p12 憑證；正式部署可提供 CA bundle 路徑但不需 client cert（本服務為消費端）
- **單一 TAK Server 連線**：本服務一次只連接一個 TAK Server 端點，不支援多端點同時接收
- **CoT framing 為 Newline-delimited**：依凍結契約，每筆 CoT XML 後接 `\n`，服務以此分幀，不處理 length-prefix 格式
- **不需要重播或持久化**：服務僅做即時顯示與日誌，不保存 CoT 歷史資料（G6）
- **console 彩色輸出為選配**：規格以文字標籤（`[RED]`、`[GREY]`）表達顏色，實際 ANSI 色碼為實作時決定（不影響功能驗收）
- **`--config` YAML 格式對稱 `ClientConfig`**：YAML key 命名採 snake_case，與其他服務（cot-gateway）慣例一致
- **不依賴 Docker/docker-compose 啟動**：服務可直接 `python -m tak_client_sim` 執行，也可在 `scripts/dev-launcher.sh` 中被調用

---

## Clarifications

**無需 clarify**：本功能的所有技術選擇均已由凍結契約（`tak-uplink.md`、`cot-xml.md`）、AGENTS.md 守則（G1–G7）、以及同倉庫參考服務（`cot-gateway`）明確規範，無模糊點。
