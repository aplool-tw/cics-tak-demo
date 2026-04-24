# Feature Specification: CoT Gateway

**Feature Branch**: `005-cot-gateway`
**Created**: 2026-04-24
**Status**: Draft
**Input**: User description: "CoT Gateway — 整合 EchoShield 雷達（TCP JSON :9000）與 Sentrycs C-UAS（HTTP :7070），以 50m 距離閾值融合航跡，產生 MIL-STD-2525C CoT XML，並透過 TCP SSL :8089 推送至 TAK Server，供 ATAK 顯示為敵對無人機圖示。"

---

## Clarifications

### Session 2026-04-24

- Q: EchoShield wire 的 `track_status` enum 設計（NEW/UPDATED/LOST vs Active/Lost）？ → A: wire 與 spec 全面改用 `track_status ∈ {Active, Lost}`，移除 NEW/UPDATED 概念；「是否首見」由 Gateway 自行以內部 uid 首見旗標管理，不再依賴 wire 欄位。
- Q: 三種情境（EchoShield 單源 / Sentrycs 單源 / 融合）的 CoT uid 命名規則？ → A: 以來源前綴區分，融合時採 Sentrycs drone_id 作主鍵：(1) 融合成功 → `FUSED-{sentrycs_drone_id}`（例 `FUSED-DRN-001`）；(2) 僅 EchoShield → `ECHO-{radar_track_id}`（例 `ECHO-TRK-001`）；(3) 僅 Sentrycs → `SENTRYCS-{drone_id}`（例 `SENTRYCS-DRN-001`）。採 Sentrycs drone_id 作融合主鍵的理由：Sentrycs 的識別（型號 / RF 指紋）語意最穩定，融合後以其為權威 id 更貼近作戰情境。source 切換時（如 `ECHO-TRK-001` 升級為 `FUSED-DRN-001`，或 FUSED 降級回單源），Gateway MUST 對舊 uid 推送一筆立即過期的 stale CoT（`stale = now`）讓 ATAK 清除舊圖示，再以新 uid 發送首筆 CoT。
- Q: CoT type 與狀態（DETECTED/MITIGATING/NEUTRALIZED/Lost）的對應規則？是否隨狀態切換 type？ → A: 同一 source 固定 CoT type，不因 `detection_status` 或 `track_status` 切換；狀態差異一律由 `<remarks>` 字串與 `stale` 屬性表達。Type 規則：`ECHOSHIELD` 與 `SENTRYCS` source → `a-u-A-M-F-Q-r`（Unknown，灰色）；`FUSED` source → `a-h-A-M-F-Q-r`（Hostile，紅色）。Stale 規則：Active / DETECTED / MITIGATING → `stale = time + 11s`（TTL=10s 加 1s 緩衝，避免 ATAK 搶在 TTL 清理前過期）；NEUTRALIZED → `stale = time + 30s`（對齊 Sentrycs 30s 保留期，保留較長顯示時間供操作員確認）；`track_status=Lost`（含 TTL 推導之 Lost）→ `stale = time`（與 `time` 相同時戳，令 ATAK 立即老化並移除圖示）。採此設計的理由：(1) CoT type 與 stale 雙軸分離使 Adapter/Generator 邏輯更單純；(2) ATAK 顏色由 type 決定、停留時間由 stale 決定、細節說明由 remarks 呈現，彼此正交；(3) 與 FR-GW-014 的「source 切換以舊 uid + stale=now 清場」機制一致。

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — 雷達單源端對端：EchoShield 偵測立即上 TAK (Priority: P1)

場景操作員啟動 EchoShield Simulator 與 CoT Gateway（Sentrycs 暫不啟用）。Gateway 的 EchodyneAdapter 連線到 `echoshield-sim:9000`，以 10 Hz 的頻率接收 newline-delimited JSON 航跡，每筆解析為統一 `Track` 物件（`source=ECHOSHIELD`）後，直接由 CotGenerator 產生 `a-u-A-M-F-Q-r`（Unknown，灰色）CoT XML，並經 TakTransmitter 透過 TCP SSL 推送到 TAK Server `:8089`。ATAK 客戶端在地圖上看到灰色未識別空中目標，位置持續更新。

**Why this priority**：這是整個系統「看得見任何東西」的最小可行路徑。沒有這條鏈路，Demo 無法在 ATAK 上顯示任何目標；而一旦這條路徑打通，即可單獨驗證 TCP JSON 解析、Track 建模、CoT XML 結構合法性、TAK Server SSL 憑證與 ATAK 顯示鏈路。Sentrycs 融合與失效處理都建立在這條骨幹之上。

**Independent Test**：僅啟動 EchoShield Simulator、TAK Server 與 Gateway（不啟動 Sentrycs）。以一架場景無人機飛行約 60 秒，觀察：
1. Gateway 日誌可見「Connected to echoshield-sim:9000」與持續的 Track 接收紀錄；
2. TAK Server CoT log（或 ATAK 客戶端）收到 uid 為 `ECHO-TRK-001`、type=`a-u-A-M-F-Q-r` 的事件，`<point>` 座標與 EchoShield JSON 一致；
3. 同一 `track_id` 持續以 `track_status=Active` 回報時，Gateway 以相同 uid 持續更新 CoT（首見/後續更新由 Gateway 內部 uid 旗標判斷，非來自 wire），ATAK 上的灰色圖示平滑移動。

**Acceptance Scenarios**:

1. **Given** EchoShield Simulator 正以 10 Hz 廣播 `{"track_id":"TRK-001", "lat":25.0598, "lon":121.5654, "altitude_m":101.0, "track_status":"Active", "classification":"DRONE", ...}`，**When** Gateway 啟動並成功連上 `:9000`，**Then** 在 500ms 內 TAK Server 收到對應 `uid=ECHO-TRK-001`、`type=a-u-A-M-F-Q-r`、`<point lat="25.0598..." lon="121.5654..." hae="101.0">` 的 CoT XML。
2. **Given** 同一 `track_id` 持續以 `track_status=Active` 回報，**When** Gateway 連續處理 30 秒，**Then** TAK Server 收到的所有事件使用同一 uid `ECHO-TRK-001`，而非每筆都產生新 uid；且 `<event time>` 單調遞增、`<event stale>` = `time + 11s`（依 FR-GW-017 規則 (c)）。Gateway 以內部 uid 首見旗標判斷首次出現（用於日誌 INFO `track first seen`），不從 wire 欄位讀取。
3. **Given** EchoShield JSON 中 `altitude_m=100.8`，**When** CoT 生成，**Then** 輸出 `<point hae="100.8">`（完成 `altitude_m → alt_m → hae` 的命名對齊），且 `<track speed="{velocity_ms}" course="{azimuth_deg}">` 數值一致。
4. **Given** EchoShield 送出一筆 `"track_status":"Lost"` 事件，**When** Gateway 處理該筆，**Then** 對該 uid 發送最終 CoT（`track_status=Lost`、`stale = time` 立即過期）並從活躍表移除，使 ATAK 在下一個 refresh 週期即自動移除圖示，且後續不再為該 `track_id` 產生新事件。

---

### User Story 2 — 雷達 + RF 融合：以 50m 閾值關聯並升級為敵對目標 (Priority: P1)

場景操作員同時啟動 EchoShield Simulator、Sentrycs Simulator 與 Gateway。EchodyneAdapter 與 SentrycsAdapter（`sentrycs-sim:7070`，1 Hz 輪詢 `GET /detections`）各自把 Track 放入同一個內部 queue，由 source 欄位區分。TrackCorrelator 每次收到雷達 Track 時，對現有 Sentrycs Track 以 Haversine 距離 ≤ 50m 且時間差 ≤ 3s 尋找最近匹配；若成功，建立 `FUSED` Track（位置/速度 取雷達、型號/狀態 取 Sentrycs），uid 升級為 `FUSED-{sentrycs_drone_id}`（例 `FUSED-DRN-001`），同時對原本的 `ECHO-{radar_track_id}` 舊 uid 推送一筆立即過期的 stale CoT 讓 ATAK 清除舊圖示；CoT type 升級為 `a-h-A-M-F-Q-r`（Hostile，紅色，此後 FUSED 生命週期內固定）。當 Sentrycs 狀態在 `DETECTED / MITIGATING / NEUTRALIZED` 之間切換時，type 不變，改由 `<remarks>` 的 `Status:` 段與 `<event stale>`（NEUTRALIZED → +30s；其餘 → +11s；Lost → =time）表達狀態差異。

**Why this priority**：融合是本 Demo 的差異化價值——雷達只能畫出「有東西」，RF 才能補上「是哪一型、誰在操作、現在是否被制壓」。沒有這個故事，Demo 只是單純雷達顯示，失去 C-UAS 的敘事張力。與 Story 1 並列 P1，但實作必須在 Story 1 之後。

**Independent Test**：同時啟動兩個 Simulator 與 Gateway，以一架無人機跑完 `DETECTED → MITIGATING → NEUTRALIZED` 的完整劇情（約 40 秒）。驗證：
1. 未關聯前（或雷達先於 Sentrycs 啟動的幾秒）ATAK 顯示灰色 `ECHO-TRK-001`；
2. Sentrycs 首次 DETECTED 並與雷達關聯成功後 ≤ 1.5s 內，Gateway 對舊 `ECHO-TRK-001` 推送 `stale=now` 的最終 CoT（ATAK 清除灰色圖示），同時發送新的紅色 `FUSED-DRN-001` 首筆 CoT；
3. CoT `<remarks>` 隨 Sentrycs 狀態由 `Status: DETECTED → MITIGATING → NEUTRALIZED` 變化，且 `drone_model`（如 `DJI Mavic 3`）正確顯示；
4. NEUTRALIZED 狀態的 CoT `stale` = `time + 30s`（Active/DETECTED/MITIGATING 為 `time + 11s`、Lost 為 `time`），保留更長顯示時間。

**Acceptance Scenarios**:

1. **Given** Sentrycs 回報 `{"drone_id":"DRN-001", "lat":25.0330, "lon":121.5654, "status":"DETECTED", "model":"DJI Mavic 3", ...}`，EchoShield 同時在距離 < 50m、時間差 < 3s 的位置回報 `track_id="TRK-001"`，**When** TrackCorrelator 執行關聯，**Then** 產出 `source=FUSED`、`correlation_id=FUSED-DRN-001`、`radar_track_id=TRK-001`、`rf_track_id=DRN-001`、`drone_model="DJI Mavic 3"`、`detection_status="DETECTED"` 的 Track，且輸出 CoT `uid=FUSED-DRN-001`、`type=a-h-A-M-F-Q-r`、`<remarks>` 含 `Source: FUSED | Model: DJI Mavic 3 | Status: DETECTED`；同時對舊 uid `ECHO-TRK-001` 推送一筆 `stale=now` 的最終 CoT。
2. **Given** 已建立 FUSED Track，**When** Sentrycs 下一筆偵測 `status` 變為 `MITIGATING`，**Then** 下一個處理週期產出的 CoT `<remarks>` 中 `Status:` 更新為 `MITIGATING`，uid 與 type 保持不變（type 固定為 `a-h-A-M-F-Q-r`，顏色變化由 remarks 字串驅動）。
3. **Given** Sentrycs `status=NEUTRALIZED`，**When** CotGenerator 生成事件，**Then** `<event stale>` = `time + 30s`（而非基準 11s），`<remarks>` 含 `Status: NEUTRALIZED`，`type` 仍為 `a-h-A-M-F-Q-r`（不因狀態切換）。
4. **Given** 雷達與 Sentrycs 同時報告兩架無人機（雷達 `TRK-001`/`TRK-002`、RF `DRN-001`/`DRN-002`），彼此相距 > 200m，**When** TrackCorrelator 分別處理，**Then** 恰好產生兩筆獨立 FUSED Track（`FUSED-DRN-001`、`FUSED-DRN-002`），不會發生交叉關聯。
5. **Given** 雷達回報但 Sentrycs 尚未回報（或已離開 50m 視窗），**When** 處理該雷達 Track，**Then** 保持 `source=ECHOSHIELD`、`uid=ECHO-TRK-001`、`type=a-u-A-M-F-Q-r`（灰色），不會因「找不到 RF 匹配」而丟棄資料。
6. **Given** 兩個 Sentrycs Track 都在某雷達 Track 的 50m/3s 視窗內，**When** TrackCorrelator 尋找最佳匹配，**Then** 選擇「距離最小」的 Sentrycs Track 作為關聯對象，不允許一對多融合。

---

### User Story 3 — 上下游斷線與航跡過期時仍能自我恢復 (Priority: P2)

Demo 現場網路/服務不穩是常態：TAK Server 重啟、EchoShield Simulator 被 Ctrl-C、Sentrycs HTTP 回 5xx、或一架無人機飛出雷達覆蓋導致不再更新。Gateway 必須在這些情境下不中止主程序、不靜默丟資料，並在服務恢復後自動重新貼上 CoT，讓 ATAK 畫面自然回復。此故事涵蓋：EchodyneAdapter 斷線重連（固定 5s 間隔、無限重試）、SentrycsAdapter HTTP 失敗時不拖垮其他模組、TakTransmitter 指數退避重連（1s→60s，最多 5 次）、以及 TrackCorrelator 的 TTL 清理（>10s 未更新的航跡標記為 `Lost` 並推送最終 CoT，讓 ATAK 圖示消失）。

**Why this priority**：Story 1 + 2 已構成 Demo 的「快樂路徑」可交付最小版本，但 Demo 現場一次小斷線就可能讓整個畫面卡住不動；這個故事讓 Gateway 在 Demo 期間具備基本韌性與自我清潔能力。P2 是因為沒有它 Demo 可以跑，但遇到任何外部事件就得手動重啟，體驗非常脆弱。

**Independent Test**：在 Story 1/2 已通過的基礎上，執行以下三個干擾腳本並觀察 Gateway 不崩潰且能復原：
1. 場景中途 `docker stop echoshield-sim` 5 秒後再 `docker start`，Gateway 應在日誌中出現 `connection lost` 與重連成功紀錄，期間不退出程序，重連後新的 Track 能重新送上 TAK。
2. `iptables` 暫時阻斷 TAK Server `:8089` 連線 3 秒，觀察 TakTransmitter 的指數退避重連與 CoT queue 滿時的 WARNING 日誌（丟棄策略符合規格）。
3. 雷達失去某架無人機訊號 > 10s（模擬飛出範圍），觀察 Gateway 於下一個 TTL 掃描週期對該 uid 推送一筆 `track_status=Lost`、`stale = time` 的最終 CoT，ATAK 於下一個 refresh 週期即移除對應圖示。

**Acceptance Scenarios**:

1. **Given** EchoShield Simulator 在 Gateway 運行中被關閉，**When** EchodyneAdapter 偵測到 EOF / ConnectionResetError，**Then** 記錄 WARNING 日誌、等待 5 秒後嘗試重連，並持續無限次重試；Gateway 主程序不退出，SentrycsAdapter 與 TakTransmitter 仍正常運作。
2. **Given** TAK Server 暫時不可達，**When** TakTransmitter 嘗試送出 CoT，**Then** 觸發指數退避重連（1s → 2s → 4s → … 封頂 60s，最多 5 次嘗試），期間 CoT queue 若超過 500 筆則丟棄最舊/最新（依實作策略）並記錄 WARNING，重連成功後繼續消費 queue。
3. **Given** Sentrycs `GET /detections` 回傳 HTTP 5xx 或連線逾時，**When** SentrycsAdapter 下次輪詢，**Then** 該筆輪詢被跳過（不產生 Track），下一秒重試；EchoShield 資料流不受影響，Gateway 繼續處理雷達單源 CoT。
4. **Given** 某 uid 的雷達 Track 超過 10 秒未更新（TTL 超時），**When** 每秒的 TTL 清理任務執行，**Then** 將 `track_status` 標記為 `Lost`、推送一筆最終 CoT（`stale = time`，即立即過期），並從活躍航跡表移除，不再因殘留資料持續產生 CoT。
5. **Given** 收到 SIGINT / SIGTERM，**When** Gateway 開始優雅關閉，**Then** 停止接收新 Track、排空 CoT queue（或最多等待 3 秒）、關閉所有 TCP 連線後退出，退出碼為 0。

---

### Edge Cases

- **時鐘偏差**：EchoShield `timestamp` 與 Sentrycs `timestamp` 若來自不同主機，時差可能 > 3s 造成無法關聯；Gateway 以「本機收到訊息時間 `received_at`」輔助判斷，但關聯演算法仍以 sensor timestamp 為準（超出 3s 視為不匹配，記錄 DEBUG 日誌）。
- **id 命名空間分離**：EchoShield 使用雷達 `track_id`（如 `TRK-001`），Sentrycs 使用 RF `drone_id`（如 `DRN-001`），兩者屬不同命名空間且字串不同；Gateway 產生的 CoT uid 以前綴區分來源（`ECHO-*` / `SENTRYCS-*` / `FUSED-*`），融合時採 Sentrycs drone_id 作主鍵（`FUSED-{sentrycs_drone_id}`）。當一架無人機由單源升級為 FUSED 時，舊 uid（`ECHO-*` 或 `SENTRYCS-*`）與新 uid（`FUSED-*`）不同，Gateway MUST 對舊 uid 推送 `stale=now` 的最終 CoT 以清除 ATAK 舊圖示。
- **雷達丟一拍**：某一筆 EchoShield JSON 因網路亂序晚到 500ms，造成 `received_at` 在新資料之後；Gateway 僅以 `track_id` 更新字典，不做順序保證（ATAK 端本來就 tolerate 近似時間）。
- **JSON 欄位缺失或超範圍**：缺 `track_id` → 記錄 ERROR 跳過；`lat=999` → 記錄 WARNING 跳過；`track_status` 非 `{Active, Lost}` enum 值 → 記錄 WARNING 跳過；任何單筆錯誤都不應影響後續訊息處理。
- **Sentrycs 輸出空陣列**：IDLE 狀態 Sentrycs 回傳 `[]`，SentrycsAdapter 僅視為「沒有新 RF Track」不刪既有 rf_tracks（由 TTL 負責老化）。
- **CoT XML 字元逸出**：drone_model 或 remarks 中若出現 `<>&"'` 等字元，CoT XML 必須正確逸出；PoC 期間模型字串為白名單（`DJI Mavic 3` 等）可暫不逸出，但實作應預留。
- **TAK Server 拒絕憑證**：`gateway.p12` 過期或不匹配，TakTransmitter 啟動時在 `_connect_with_retry` 達到 max_retries 後拋出 ConnectionError，Gateway 應以非 0 exit code 終止並在日誌留下明確錯誤，而非無限重試遮蔽問題。
- **來源命名衝突**：EchoShield 使用 `Active/Lost`（生命週期存活標記），Sentrycs 使用 `DETECTED/MITIGATING/NEUTRALIZED`（RF 處置狀態）——Gateway 必須不混用；前者寫入 `Track.track_status`，後者寫入 `Track.detection_status`，兩個欄位語義獨立。`Active → Lost` 的轉變可由 wire 明示或由 Gateway TTL 推導。
- **首見旗標由 Gateway 管理**：wire 上不區分 NEW/UPDATED；Gateway 以內部 `seen_uids` 集合判斷某 uid 是否首次出現，用於 INFO 日誌與任何「首筆通知」副作用，Adapter 不再承擔此職責。
- **欄位命名對齊**：EchoShield JSON 的 `altitude_m`、Sentrycs 的 `alt_m`、CoT 的 `hae` 三者都是「高度（公尺，HAE）」但命名不同；Adapter 層負責統一為內部 `Track.alt_m`，CoT 生成時輸出 `hae`。

---

## Requirements *(mandatory)*

### Functional Requirements

**EchodyneAdapter（雷達輸入）**

- **FR-GW-001**: Gateway MUST 以 TCP Client 身份連線到設定檔指定的 EchoShield 端點（預設 `echoshield-sim:9000`），讀取以 `\n` (0x0A) 為分隔符的 UTF-8 newline-delimited JSON 串流。
- **FR-GW-002**: EchodyneAdapter MUST 對每筆 JSON 驗證必填欄位（`track_id`, `lat`, `lon`, `altitude_m`, `velocity_ms`, `azimuth_deg`, `elevation_deg`, `timestamp`, `track_status`, `classification`）與值域（lat ∈ [-90, 90]、lon ∈ [-180, 180]、`track_status ∈ {Active, Lost}`）；違反者記錄 WARNING/ERROR 並跳過單筆，不中止串流。Adapter MUST NOT 嘗試從 wire 判斷「首見 vs 後續更新」——該職責由 Gateway 主程序以內部 uid 首見旗標（如 `seen_uids: set[str]`）管理。
- **FR-GW-003**: EchodyneAdapter MUST 將合法 JSON 轉為內部 `Track(source=ECHOSHIELD)` 物件，其中 `alt_m` 取自 JSON `altitude_m`，`timestamp` 為 UTC aware datetime，並放入共用的 `track_queue`（容量 1000）。
- **FR-GW-004**: EchodyneAdapter MUST 在 TCP 連線失敗（ConnectionRefusedError/OSError/EOF）時記錄 WARNING、等待固定 5 秒後自動重連，採無限重試直到 Gateway 關閉；Gateway 主程序不因此退出。

**SentrycsAdapter（RF 輸入）**

- **FR-GW-005**: Gateway MUST 以 HTTP Client 身份每 1 秒一次（1 Hz）對設定檔指定端點（預設 `sentrycs-sim:7070`）執行 `GET /detections`，解析回傳的 JSON 陣列。
- **FR-GW-006**: SentrycsAdapter MUST 將每筆偵測轉為 `Track(source=SENTRYCS)` 物件，其中 `alt_m` 取自 JSON `alt_m`、`detection_status` 取自 `status`（`DETECTED`/`MITIGATING`/`NEUTRALIZED`）、`drone_model` 取自 `model`、`operator_lat/operator_lon` 隨附；並放入相同的 `track_queue`。
- **FR-GW-007**: SentrycsAdapter MUST 在 HTTP 錯誤（連線逾時、5xx、JSON 解析失敗）時記錄 WARNING 並跳過本次輪詢；下一個 1 Hz 週期正常重試，不影響 EchoShield 資料流。
- **FR-GW-008**: SentrycsAdapter MUST 在回傳為空陣列時視為「無新 RF 偵測」，不清除既有 `rf_tracks`（老化交由 TTL 處理）。

**TrackCorrelator（融合）**

- **FR-GW-009**: TrackCorrelator MUST 維護三個獨立字典：`radar_tracks`（ECHOSHIELD）、`rf_tracks`（SENTRYCS）、`fused_tracks`（FUSED），皆以 track id 為鍵。
- **FR-GW-010**: 每次收到 `source=ECHOSHIELD` 的 Track，TrackCorrelator MUST 以 Haversine 公式（地球半徑 6,371,000m）對所有 `track_status=Active` 的 RF Track 計算距離，並於「距離 ≤ 50m 且 `|radar.timestamp - rf.timestamp| ≤ 3s`」條件下選取距離最小者為匹配，禁止一對多匹配。
- **FR-GW-011**: 匹配成功時 TrackCorrelator MUST 產生 `Track(source=FUSED, track_id="FUSED-{rf_track_id}", correlation_id="FUSED-{rf_track_id}", radar_track_id, rf_track_id)`（`rf_track_id` = Sentrycs `drone_id`），其中位置 / 速度 / 方位 / 仰角 / 高度取自雷達，`classification` / `drone_model` / `detection_status` / `operator_*` 取自 RF。
- **FR-GW-012**: 未匹配時 TrackCorrelator MUST 回傳原始雷達 Track（`source=ECHOSHIELD`），不得丟棄。
- **FR-GW-013**: TrackCorrelator MUST 每 1 秒執行一次 TTL 清理：凡 `last_updated` 超過 10 秒的航跡，將 `track_status` 設為 `Lost`、由主程序據此推送最終 CoT，並由 `get_all_active_tracks`（回傳 `track_status=Active` 的航跡）排除；同時從 Gateway 的 `seen_uids` 首見旗標集合中移除該 uid，使其未來若重新出現可再次觸發「首見」語意。

**CotGenerator（CoT XML 產生）**

- **FR-GW-014**: CotGenerator MUST 依 Track.source 產生 uid：`ECHOSHIELD` → `ECHO-{radar_track_id}`（例 `ECHO-TRK-001`）；`SENTRYCS` → `SENTRYCS-{drone_id}`（例 `SENTRYCS-DRN-001`）；`FUSED` → `FUSED-{sentrycs_drone_id}`（例 `FUSED-DRN-001`）。同一實體在同一 source 的生命週期內 MUST 保持同一 uid。當 source 切換（如 `ECHOSHIELD → FUSED`、`SENTRYCS → FUSED`，或 FUSED 解除回單源）導致 uid 前綴或主鍵改變時，Gateway MUST 先對舊 uid 推送一筆立即過期（`stale = time`）的最終 CoT 讓 ATAK 清除舊圖示，再以新 uid 發送首筆 CoT；`seen_uids` 旗標隨舊 uid 一併移除。
- **FR-GW-015**: CotGenerator MUST 依 Track.source 產生 CoT type，且該 type 在同一 source 的生命週期內固定，不因 `detection_status`（DETECTED/MITIGATING/NEUTRALIZED）或 `track_status`（Active/Lost）切換而改變：`ECHOSHIELD` → `a-u-A-M-F-Q-r`（Unknown, Air — TAK 顯示灰色）；`SENTRYCS` → `a-u-A-M-F-Q-r`（Unknown, Air — TAK 顯示灰色，與雷達單源同色系，代表尚未融合確認）；`FUSED` → `a-h-A-M-F-Q-r`（Hostile — TAK 顯示紅色）。狀態變化（DETECTED→MITIGATING→NEUTRALIZED、Active→Lost）MUST 改由 `<remarks>` 字串（見 FR-GW-018）與 `<event stale>`（見 FR-GW-017）兩軸表達，禁止在 type 上編碼狀態。
- **FR-GW-016**: CotGenerator MUST 以 UTF-8 產生符合 CoT 2.0 的 XML 字串，內含 `<event version="2.0" uid type time start stale how="m-g">`、`<point lat lon hae ce="10.0" le="5.0"/>`、`<detail>` 含 `<contact callsign>`、`<remarks>`、`<track speed course/>`；`time/start` 為 Gateway 產生 CoT 當下的 UTC ISO 8601（毫秒精度）。`type` 依 FR-GW-015 由 source 決定並在該生命週期內固定；`stale` 依 FR-GW-017 由 `detection_status` / `track_status` 動態計算。
- **FR-GW-017**: CotGenerator MUST 依 Track 狀態計算 `<event stale>`（三段式）：(a) `track_status=Lost`（含 TTL 推導的 Lost）→ `stale = time`（與 `time` 相同時戳，令 ATAK 立即老化並移除圖示）；(b) `detection_status=NEUTRALIZED` → `stale = time + 30s`（對齊 Sentrycs 30s 保留期）；(c) 其他情況（Active / DETECTED / MITIGATING，含 ECHOSHIELD 單源 Active、SENTRYCS 單源 DETECTED/MITIGATING、FUSED DETECTED/MITIGATING）→ `stale = time + 11s`（TTL=10s 加 1s 緩衝，避免 ATAK 於 TTL 清理前先行過期）。規則 (a) 優先於 (b) 與 (c)；(b) 優先於 (c)。
- **FR-GW-018**: CotGenerator `<remarks>` MUST 依資料可用性組合為 `Source: {src} | Model: {drone_model?} | Status: {detection_status?} | Speed: {v:.1f}m/s | Alt: {alt:.0f}m`，缺欄位則該段省略。

**TakTransmitter（TAK Server 輸出）**

- **FR-GW-019**: TakTransmitter MUST 以 TCP SSL 連線至設定檔指定的 TAK Server（預設 `tak-server:8089`），使用 `gateway.p12` 客戶端憑證建立連線；PoC 模式允許 `verify_mode=CERT_NONE`（須以設定檔明示）。
- **FR-GW-020**: TakTransmitter MUST 以「CoT XML + `\n`」格式傳送（與 ICD-003 一致的 newline-delimited），不使用 length-prefix；每筆 CoT 經 `_cot_queue`（容量 500）非同步發送。
- **FR-GW-021**: TakTransmitter MUST 在連線錯誤時以指數退避重連（1s → 2s → 4s → … 封頂 60s），最多 `max_retries=5` 次；達上限後拋出 ConnectionError，Gateway 以非 0 exit code 終止並明確記錄。
- **FR-GW-022**: 當 `_cot_queue` 滿載（500）時，TakTransmitter MUST 記錄 WARNING 並丟棄新進訊息（drop-newest），不阻塞 CotGenerator 與主處理迴圈。

**GatewayMain（整合與運行）**

- **FR-GW-023**: Gateway MUST 以單一 YAML 設定檔（`config/gateway.yaml`）驅動所有端點、閾值、憑證路徑與日誌等級；關鍵欄位包含 `echoshield.{host,port,reconnect_interval_s}`、`sentrycs.{host,port,poll_interval_s,enabled}`、`correlator.{distance_threshold_m,time_window_s,ttl_s}`、`tak_server.{host,port,use_ssl,cert_file,cert_password,max_retries}`。
- **FR-GW-024**: Gateway MUST 使用 asyncio 事件迴圈，將 EchodyneAdapter、SentrycsAdapter、processing loop（消費 track_queue 執行 correlate + generate + enqueue_cot）、TTL loop、TakTransmitter send loop 作為獨立 coroutine 並行執行；任一 adapter 失敗不得使其他 coroutine 中止。
- **FR-GW-025**: Gateway MUST 在收到 SIGINT / SIGTERM 時執行優雅關閉：停止接收新 Track、盡量排空 CoT queue、關閉所有 TCP 連線、以 exit code 0 結束。
- **FR-GW-026**: Gateway MUST 以結構化日誌輸出關鍵事件（連線成功/失敗、Track 解析錯誤、融合成功、TTL 到期、TakTransmitter 重連、Queue 滿丟訊息），格式為 `%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s`，預設等級 INFO。

### Key Entities

- **EchodyneClient**：EchodyneAdapter 內的 asyncio TCP client，職責為維持與 EchoShield Simulator（或真實硬體）的長連線、逐行解析 JSON、在斷線時無限重試；不保留歷史航跡，僅轉發 Track 至 `track_queue`。
- **SentrycsClient**：SentrycsAdapter 內的 aiohttp HTTP client，職責為以固定 1 Hz 輪詢 `GET /detections`、解析陣列、轉為 `Track(source=SENTRYCS)`；對 HTTP 失敗 tolerant，不做本地狀態機（狀態由 Sentrycs Simulator 決定）。
- **UnifiedTrack**：跨模組流通的唯一航跡物件（`Track` dataclass，見 ICD-004）；欄位涵蓋識別（track_id, source）、位置動態（lat, lon, alt_m, velocity_ms, azimuth_deg, elevation_deg）、時間（timestamp, received_at, last_updated）、狀態（track_status, classification, detection_status）、融合關聯（correlation_id, radar_track_id, rf_track_id）、操控者（operator_lat, operator_lon）與選填模型（drone_model）。UnifiedTrack → CoT uid 的對應規則（FR-GW-014）：
  - `source=ECHOSHIELD` → `ECHO-{radar_track_id}`（例 `ECHO-TRK-001`）
  - `source=SENTRYCS` → `SENTRYCS-{rf_track_id}`（例 `SENTRYCS-DRN-001`，其中 `rf_track_id` = Sentrycs `drone_id`）
  - `source=FUSED` → `FUSED-{rf_track_id}`（例 `FUSED-DRN-001`，以 Sentrycs drone_id 為融合主鍵）
- **Correlator**：`TrackCorrelator` 實例，擁有三本字典（radar/rf/fused）與三個參數（`distance_threshold_m=50`, `time_window_s=3`, `ttl_s=10`），提供 `correlate(track)`（回傳原始或 FUSED Track）、`add_rf_track(track)`、`update_ttl()` 三個公開方法。
- **CotEvent**：由 CotGenerator 從 UnifiedTrack 產生的 CoT 2.0 XML 字串（`<event>...</event>`），在系統內以字串形式傳遞至 TakTransmitter；其 uid / type / stale / remarks 均由 UnifiedTrack 的 source 與 detection_status 決定。
- **TakConnection**：TakTransmitter 管理的 TCP SSL 長連線（asyncio StreamReader/Writer 對），附帶 `_cot_queue`（容量 500）、指數退避重連狀態機、以及 gateway.p12 載入的 SSL Context；所有出站 CoT 皆經此連線以 newline-delimited 方式傳送。

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-GW-001**：從 EchoShield JSON 到達 Gateway（`received_at`）至對應 CoT 送出到 TAK Server TCP socket 的端對端處理延遲 p95 < 100ms、p99 < 200ms（以 5 架無人機、10 Hz 更新頻率的壓力測試量測）。
- **SC-GW-002**：單筆 Track 的 CoT XML 生成時間 < 5ms；TrackCorrelator 關聯計算在 5 架活躍航跡下 < 1ms（`time.perf_counter` 量測）。
- **SC-GW-003**：在 5 架無人機同時飛行、EchoShield 10 Hz、Sentrycs 1 Hz 的情境下，Gateway 穩態吞吐 ≥ 100 msg/s，且 `track_queue` / `cot_queue` 平均深度 < 10（不出現持續堆積）。
- **SC-GW-004**：以一架無人機在 50m 關聯視窗內運動 60 秒，雷達 + RF 的融合命中率 ≥ 95%（命中定義：該週期產出 `source=FUSED` 的 CoT）；兩架相距 > 200m 的無人機在 60 秒測試中交叉關聯次數 = 0。
- **SC-GW-005**：Demo 期間 TAK Server 對單一 uid 的 CoT 更新頻率穩定 ≥ 5 Hz（對應雷達 10 Hz 的至少 50% 處理率），ATAK 上的圖示移動視覺連續無卡頓。
- **SC-GW-006**：EchoShield Simulator 被停機 5 秒再恢復的測試中，Gateway 不退出、不拋未捕捉例外，重連後 10 秒內重新產出該無人機 CoT。
- **SC-GW-007**：TAK Server `:8089` 不可達 30 秒的測試中，TakTransmitter 完成至少 1 次指數退避序列並在服務恢復後繼續送出 CoT；期間 Gateway 主程序未終止。
- **SC-GW-008**：TTL 清理的準確性——凡雷達 Track 超過 10 秒未更新，Gateway 在下一個秒級 tick（最晚 11 秒內）對其 uid 發送一筆 `track_status=Lost`、`stale = time` 的最終 CoT，ATAK 於下一個 refresh 週期（≤ 3s）內移除對應圖示。
- **SC-GW-009**：CoT XML 格式合法性——針對 100 筆任意場景產出的 CoT，以 XML schema 驗證（`<event>` 必備屬性齊全、`<point>` 數值在值域內）通過率 100%；uid 唯一性：同一無人機在同一 source 的生命週期內只出現一個 uid（前綴 `ECHO-*` / `SENTRYCS-*` / `FUSED-*` 其一），source 切換時舊 uid 先收到 `stale=now` 的最終 CoT 後才出現新 uid，不會同時存在兩個 uid 指向同一實體。
- **SC-GW-010**：對於非法輸入（缺欄位、超範圍、非 JSON 文本）的魯棒性——Gateway 在連續注入 1,000 筆異常資料後仍正常處理合法資料，且異常筆數全數有 WARNING/ERROR 日誌、不產生對應 CoT。
- **SC-GW-011**：CoT Gateway 程序記憶體佔用在連續運行 30 分鐘（5 架無人機、10 Hz）下成長 < 50MB（字典與 queue 受 TTL 控制，無明顯洩漏）。
- **SC-GW-012**：CoT type 與 stale 政策合規——對 100 筆涵蓋 `ECHOSHIELD-Active`、`SENTRYCS-DETECTED`、`SENTRYCS-MITIGATING`、`SENTRYCS-NEUTRALIZED`、`FUSED-DETECTED`、`FUSED-MITIGATING`、`FUSED-NEUTRALIZED`、`Lost`（含 TTL 推導）共 8 類場景的 CoT 事件，驗證：(1) `type` 100% 與 FR-GW-015 表對應（ECHO/SENTRYCS=`a-u-A-M-F-Q-r`、FUSED=`a-h-A-M-F-Q-r`，不因狀態切換）；(2) `stale - time` 100% 與 FR-GW-017 對應（Lost=0s、NEUTRALIZED=30s、其餘=11s，誤差 ≤ 1ms）。

---

## Assumptions

- 所有服務部署於同一台展示主機（Docker Compose），Gateway 以 `echoshield-sim` / `sentrycs-sim` / `tak-server` 等主機名互相連線；跨主機部署不在本 Feature 範圍內。
- EchoShield Simulator 與 Sentrycs Simulator 對「同一架無人機」使用**不同命名空間的 id**：EchoShield 發 `track_id=TRK-00x`、Sentrycs 發 `drone_id=DRN-00x`；Gateway 關聯演算法 **只**依 Haversine 距離 + 時間窗，不依賴 id 字串匹配。兩個 Simulator 的場景腳本以「相同尾碼」約定（例如 `TRK-001` ↔ `DRN-001` 為同一架）僅供人工讀日誌時快速對照，非程式依據。
- uid 主鍵：融合時採 Sentrycs `drone_id`（`FUSED-{sentrycs_drone_id}`）而非雷達 `track_id`，因為 Sentrycs 具備型號確認與 RF 指紋，語意最穩定，融合後以其為權威 id 更貼近作戰情境；代價是單源 → FUSED 升級時 uid 會整個改變（`ECHO-TRK-001` → `FUSED-DRN-001`），Gateway 以「舊 uid 發 stale、新 uid 發首筆」的雙訊息切換模式處理 ATAK 視覺過渡。
- CoT type 選用 `a-u-A-M-F-Q-r`（未識別灰色）與 `a-h-A-M-F-Q-r`（敵對紅色）；是否升級至 `-q-r`（真正 quadrotor 子類）或改用 `a-h-A-M-F-Q`（不含 rotary 後綴）由 08-api-icd.md 權威定義，實作以該文件為準。
- uid 主鍵採 Sentrycs `drone_id`（`FUSED-{sentrycs_drone_id}`）的具體副作用：ATAK 上在 RF 首次關聯成功的瞬間會看到舊灰色目標消失、新紅色目標出現於幾乎相同位置，使用者體驗為「識別升級」而非「目標跳動」，屬預期行為。
- PoC 模式下 TAK Server SSL 使用 `verify_mode=CERT_NONE` 暫時停用伺服器憑證驗證，僅載入 `gateway.p12` 客戶端憑證；正式部署時本 Feature 之外另以設定檔升級為完整驗證。
- 所有對外時間一律使用 UTC；`datetime.now(timezone.utc)` 為 Gateway 產生 CoT 的時間基準，sensor `timestamp` 僅用於關聯時間窗比對，不作為 CoT `time` 屬性。
- Python 3.11+、asyncio 為基礎；相依套件 `aiohttp`, `PyYAML` 必要，`geopy` / `structlog` 為可選輔助。
- 本 Feature 聚焦「Gateway 本體」，不負責啟動/停止 Simulator 與 TAK Server（由 Docker Compose 統籌）；也不提供對外管理/監控介面（不開 HTTP 埠）。
- Sentrycs Simulator（Feature 004）已實作並符合 08-api-icd.md §3；EchoShield Simulator（Feature 003）已實作並符合 08-api-icd.md §2；TAK Server（Feature 001 基礎設施）已可在 `:8089` 接受 TCP SSL CoT。
