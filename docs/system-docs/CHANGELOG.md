# 文件修改日誌（CHANGELOG）

本日誌記錄 `docs/system-docs/` 所有規格文件的修改歷史。

---

## [v0.6] - 2026-04-23

### 修改
- **移除特定硬體型號指定**：將所有 "MacBook Pro" / "MacBook" 字眼替換為泛稱「展示環境主機」、「展示主機」、「本地 Docker 環境」等，PoC 不寫死特定機器型號
- **移除 PostgreSQL 強調**：資料庫選型屬細部設計，不在架構規格中指定；Docker Compose 範例的 postgres 服務改為注解，CoreConfig.xml 的 DB 連線改為通用範本
- 影響文件：`00-index.md`（v0.6）、`01-system-architecture.md`（v0.7）、`02-unified-drone-simulator-spec.md`（v0.3）、`06-cot-gateway-spec.md`（v0.5）、`07-tak-server-deployment-spec.md`（v0.4）、`08-api-icd.md`（v0.5）

---



### 新增
- `04-echoshield-simulator-spec.md`：EchoShield Simulator 完整開發規格（新增獨立文件），涵蓋：Map Simulator 查詢、雷達誤差模擬、方位角/仰角計算、EchoShield TCP JSON Feed 輸出（:9000）

### 修改
- **文件重新編號**：
  - `02-drone-simulator-spec.md` → `02-unified-drone-simulator-spec.md`
  - `02b-map-simulator-spec.md` → `03-map-simulator-spec.md`
  - `03-sentrycs-simulator-spec.md` → `05-sentrycs-simulator-spec.md`
  - `04-cot-gateway-spec.md` → `06-cot-gateway-spec.md`
  - `05-tak-server-deployment-spec.md` → `07-tak-server-deployment-spec.md`
  - `06-api-icd.md` → `08-api-icd.md`
- **日期欄位格式統一**：所有文件日期改為 `YYYY-MM-DD` 格式，移除行內修訂說明文字
- `00-index.md`：更新文件索引（新編號、新文件、閱讀順序）
- `CHANGELOG.md`：新增本日誌文件

---

## [v0.4] - 2026-04-23

### 架構精簡

#### 移除 SimulatedDroneAdapter
- **背景**：EchoShield Simulator 已可直接輸出 EchoShield JSON TCP Feed，不再需要 Gateway 內的橋接模組
- **變更**：EchodyneAdapter 直接連接 EchoShield Simulator TCP :9000；PoC 與生產模式共用同一 Adapter，差異僅在設定檔 `host`/`port`
- **影響文件**：`01-system-architecture.md`（v0.6）、`04-cot-gateway-spec.md`（v0.4）

#### 架構從四層改為三層
- **背景**：「通訊層」本質上只是協議清單，不具獨立職責
- **變更**：移除通訊層 subgraph，通訊協議（TCP / HTTP / SSL）直接標注在元件連線箭頭上
  - 三層架構：感測層（Sensor Layer）→ 指管層（C2 Layer）→ 顯示層（Display Layer）
- **影響文件**：`01-system-architecture.md`（v0.6）、`00-index.md`（v0.5）

---

## [v0.3] - 2026-04-23

### 新增

#### Map Simulator（地圖模擬器）
- **角色**：感測層物件狀態中央登錄表（Port :8090）
- **資料流**：Unified Drone Simulator 每秒 POST /objects/update → Map Simulator；EchoShield Simulator / Sentrycs Simulator 改從 Map Simulator GET /objects?radius_m=N 查詢偵測範圍內物件
- `03-map-simulator-spec.md`（原 `02b`）：Map Simulator 完整開發規格（v0.1）

### 修改
- `01-system-architecture.md`（v0.5）：感測層架構圖新增 Map Simulator；EchoShield Simulator 改為獨立元件；更新元件職責表
- `02-unified-drone-simulator-spec.md`（v0.2）：新增 UDS 每秒推送狀態至 Map Simulator；更新與感測器模擬器的互動說明
- `05-sentrycs-simulator-spec.md`（v0.4）：Sentrycs Simulator 改為向 Map Simulator 查詢偵測範圍物件，不再直接呼叫 UDS GET /status
- `00-index.md`（v0.4）：新增 Map Simulator 文件條目

---

## [v0.2] - 2026-04-23

### 架構重要修正

#### Sentrycs 資料路由變更
- **舊**：Sentrycs Simulator 直接 TCP SSL 推送 CoT XML → TAK Server（Native TAK Push）
- **新**：Sentrycs Simulator 提供 HTTP JSON Status API（Port :7070）→ CoT Gateway SentrycsAdapter 以 1 Hz 輪詢 → TrackCorrelator 融合 → TakTransmitter → TAK Server
- **理由**：統一路由讓 TrackCorrelator 可正確融合雷達位置（高精度）+ RF 型號/狀態（高識別度）；CoT type 邏輯集中在 CotGenerator 統一維護

#### 受影響文件
- `01-system-architecture.md`（v0.4）：架構圖、元件表、資料流、設計決策、PKI（移除 sentrycs.p12）
- `05-sentrycs-simulator-spec.md`（v0.3）：移除 TakSslPusher 與 CotXmlBuilder；新增 SentrycsStatusApiServer（aiohttp HTTP Server）
- `06-cot-gateway-spec.md`（v0.3）：新增 SentrycsAdapter 模組規格（HTTP Poll :7070 → Track 物件）
- `08-api-icd.md`（v0.4）：ICD-002 從「Sentrycs CoT XML Push」改為「Sentrycs JSON HTTP Feed」

---

## [v0.1] - 2026-04-22

### 初版建立

基於 PoC 技術規格書建立 7 份初版文件。

#### 核心設計決策
- **部署環境**：所有服務部署於 展示環境主機（Docker Desktop for Mac）；ATAK Android 裝置透過同一 Wi-Fi 網段連線（無 AWS EC2）
- **TAK 顯示端**：全為 ATAK Android（平板/手機）；無 WinTAK
- **無人機模擬**：單一 Unified Drone Simulator（Python asyncio + aiohttp）負責飛行引擎與接管閉環
- **接管閉環**：`POST /command/takeover` → 改變航線 → 飛往降落點 → 高度≤2m → LANDED → Sentrycs 推送 Neutralized
- **四層架構**（後改為三層）：感測層 → 通訊層 → 指管層 → 顯示層

#### 建立文件
- `00-index.md`：文件索引（v0.1）
- `01-system-architecture.md`：系統架構設計書（v0.1）
- `02-unified-drone-simulator-spec.md`（原 `02-drone-simulator-spec.md`）：統一無人機模擬器規格（v0.1）
- `05-sentrycs-simulator-spec.md`（原 `03`）：Sentrycs C-UAS 模擬器規格（v0.1）
- `06-cot-gateway-spec.md`（原 `04`）：CoT Gateway 中介軟體規格（v0.1）
- `07-tak-server-deployment-spec.md`（原 `05`）：TAK Server 展示主機 Docker 部署規格（v0.1）
- `08-api-icd.md`（原 `06`）：介面控制文件 ICD（v0.1）
