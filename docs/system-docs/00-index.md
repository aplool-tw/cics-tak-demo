# 台灣反無人機 TAK 戰術感知 PoC — 文件索引

---

| 欄位 | 內容 |
|------|------|
| **版本** | v0.2 |
| **日期** | 2026-04-22 |
| **狀態** | 草稿 |

---

## 文件清單

| 編號 | 檔名 | 名稱 | 說明 | 狀態 |
|------|------|------|------|------|
| 00 | `00-index.md` | 文件索引 | 本文件，所有文件的入口與說明 | 草稿 |
| 01 | `01-system-architecture.md` | 系統架構文件 | 四層架構、資料流、技術棧、網路拓樸、安全設計、效能設計 | 草稿 |
| 02 | `02-drone-simulator-spec.md` | 統一無人機模擬器規格 | Unified Drone Simulator 的完整開發規格：EchoShield TCP Feed、Sentrycs REST Query/Command API、接管閉環設計、飛行狀態機 | 草稿 |
| 03 | `03-sentrycs-simulator-spec.md` | Sentrycs 模擬器規格 | Sentrycs C-UAS 模擬器開發規格，含狀態機、CoT XML 輸出、TAK SSL Push | 草稿 |
| 04 | `04-cot-gateway-spec.md` | CoT Gateway 規格 | CoT Gateway 所有模組的詳細規格，含 EchodyneAdapter、TrackCorrelator、CotGenerator、TakTransmitter | 草稿 |
| 05 | `05-tak-server-deployment-spec.md` | TAK Server 部署規格 | MacBook Pro 本機 Docker Desktop 部署步驟、PKI 憑證、ATAK 裝置連線設定 | 草稿 |
| 06 | `06-api-icd.md` | API 介面控制文件（ICD） | 所有系統介面的完整定義，含 JSON Schema、CoT XML 範例、端對端訊息流 | 草稿 |

---

## 專案概覽

### 背景

台灣面臨日益增長的無人機（UAS）威脅，需要一套能整合多感測器的戰術感知系統。本 PoC（Proof of Concept）專案旨在驗證將 EchoShield 4D 雷達與 Sentrycs C-UAS 射頻偵測系統整合至 TAK（Team Awareness Kit）生態系的可行性，讓前線指揮官能在 ATAK 介面上即時掌握無人機威脅態勢，並透過接管閉環實現對無人機的完整反制流程。

### 目標

1. **態勢共享**：雷達航跡與 RF 偵測結果即時顯示於 TAK 顯示端
2. **感測器融合**：EchoShield 雷達（位置精確）與 Sentrycs（型號識別）的航跡關聯
3. **端對端延遲驗證**：感測到顯示 ≤ 5 秒（容許上限 8 秒）
4. **MIL-STD-2525C 符合性**：CoT type 與戰術符號標準一致

### PoC 範圍

本 PoC 採用統一無人機模擬器替代真實硬體，所有服務部署於 MacBook Pro 本機：

- **統一無人機模擬器**：單一 Python 程式提供 EchoShield TCP Feed（:9000）與 Sentrycs REST API（:8080）
- **Sentrycs C-UAS 模擬器**：消費統一模擬器數據，實作接管閉環，直接推送 CoT XML 至 TAK Server
- **TAK Server**：部署於 MacBook Pro 本機 Docker Desktop
- **顯示端**：ATAK Android 裝置（平板/手機），與 MacBook 連接同一 Wi-Fi

**不在 PoC 範圍內**：
- 真實硬體整合（EchoShield 雷達、Sentrycs C-UAS）
- 作戰級別的資安加固
- 高可用/災難回復設計
- 超過 10 架無人機的大規模場景

---

## 四層架構摘要

```
感測層  →  通訊層  →  指管層  →  顯示層
```

| 層次 | 元件 |
|------|------|
| 感測層 | 統一無人機模擬器（EchoShield TCP Feed + Sentrycs REST API）、Sentrycs 模擬器 |
| 通訊層 | TCP SSL 8089（PoC）、UDP 4242（作戰模式）、REST HTTP 8080（內部指令）|
| 指管層 | CoT Gateway（Python）、TAK Server（MacBook Pro Docker Desktop）|
| 顯示層 | ATAK Android（平板/手機，同 Wi-Fi 網段）|

---

## 文件閱讀順序建議

### 新加入的開發人員

1. **`00-index.md`**（本文件）：了解整體文件結構
2. **`01-system-architecture.md`**：建立系統全貌認識
3. **`06-api-icd.md`**：了解所有介面格式
4. 再依分工閱讀：
   - 模擬器開發：`02-drone-simulator-spec.md`（Unified Drone Simulator）或 `03-sentrycs-simulator-spec.md`（Sentrycs Simulator）
   - Gateway 開發：`04-cot-gateway-spec.md`
   - 維運部署：`05-tak-server-deployment-spec.md`

### 系統架構師

1. `01-system-architecture.md`
2. `06-api-icd.md`
3. `04-cot-gateway-spec.md`

### DevOps / 維運人員

1. `01-system-architecture.md`（第 7–9 節）
2. `05-tak-server-deployment-spec.md`

### PoC 驗收評審

1. `00-index.md`
2. `01-system-architecture.md`（第 1–5 節）
3. `06-api-icd.md`（第 6 節：端對端訊息流）

---

## 驗收標準摘要

| 項目 | 指標 | 容許上限 |
|------|------|---------|
| V1–V10 圖標出現/切換/同步 | ≤ 5 秒 | 8 秒 |
| 雙感測器航跡關聯 | ≤ 5 秒 | — |
| 端對端整體延遲 | ≤ 5 秒 | — |
