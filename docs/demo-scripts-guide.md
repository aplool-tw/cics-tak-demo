# CICS TAK Demo — Demo Scripts 使用手冊

> 本文件介紹 `scripts/` 目錄下所有 demo 腳本的用途、操作步驟與常見情境。  
> 如需接上正式 TAK Server，請先閱讀 **§3 Remote TAK 設定向導** 章節。

---

## 目錄

1. [Demo 腳本一覽](#1-demo-腳本一覽)
2. [前置準備](#2-前置準備)
3. [Remote TAK 設定向導](#3-remote-tak-設定向導)
4. [各腳本詳細說明](#4-各腳本詳細說明)
   - [demo-1drone.sh](#demo-1dronesh)
   - [demo-3drone.sh](#demo-3dronesh)
   - [demo-1drone-remote-tak.sh](#demo-1drone-remote-taksh)
   - [demo-3drone-remote-tak.sh](#demo-3drone-remote-taksh)
   - [demo-cot-gateway-map.sh](#demo-cot-gateway-mapsh)
   - [demo-cot-gateway-map-3drones.sh](#demo-cot-gateway-map-3dronessh)
   - [demo-map-viewer.sh](#demo-map-viewersh)
   - [gen-certs.sh](#gen-certssh)
5. [Web Map Viewer 說明](#5-web-map-viewer-說明)
6. [常見問題 FAQ](#6-常見問題-faq)

---

## 1. Demo 腳本一覽

| 腳本 | 情境 | 需要 TAK Server | 服務數量 |
|------|------|----------------|----------|
| `demo-1drone.sh` | 單架無人機，純本地 | 否（使用內建 relay） | 7 |
| `demo-3drone.sh` | 三架無人機，純本地 | 否（使用內建 relay） | 7 |
| `demo-1drone-remote-tak.sh` | 單架無人機，可接外部 TAK | 可選（見 §3） | 6 或 7 |
| `demo-3drone-remote-tak.sh` | 三架無人機，可接外部 TAK | 可選（見 §3） | 6 或 7 |
| `demo-cot-gateway-map.sh` | CoT Gateway + 地圖（無 TAK）| 否 | 5 |
| `demo-cot-gateway-map-3drones.sh` | 三機版 CoT Gateway + 地圖 | 否 | 5 |
| `demo-map-viewer.sh` | 純地圖檢視（UDS + Map Sim） | 否 | 2 |
| `gen-certs.sh` | 產生自簽 PKI 憑證（工具） | — | — |

---

## 2. 前置準備

### 2.1 系統需求

- Python 3.11+（建議 3.12）
- Bash 5.x+（Linux / macOS）
- `curl`、`python3` 在 PATH 中

### 2.2 安裝 Python 套件（一次即可）

```bash
# 從 repo 根目錄執行
pip install -e "libs/tak-connection[dev]" --break-system-packages
for svc in uds map-sim echoshield-sim sentrycs-sim cot-gateway tak-client-sim; do
  pip install -e "services/${svc}[dev]" --break-system-packages
done
```

> **macOS / 受 PEP 668 限制的系統**：加上 `--break-system-packages`，  
> 或先建立虛擬環境：`python3 -m venv .venv && source .venv/bin/activate`

---

## 3. Remote TAK 設定向導

### 3.1 什麼是 Remote TAK 模式？

預設情況下，demo 腳本在本機啟動一個輕量 `tak-relay`（TCP relay），供 `tak-client-sim` 連接驗證——**不需要真實 TAK Server**。

若想將 CoT 推送到正式 TAK Server（如 TAK.gov FreeTAKServer、或自建 TAK Server），只需完成以下設定：

1. 執行設定向導生成 `config/remote-tak.yaml`
2. 把憑證放到 `config/certs/`
3. 改用 `demo-1drone-remote-tak.sh` 或 `demo-3drone-remote-tak.sh`

### 3.2 執行設定向導

```bash
bash scripts/setup-remote-tak.sh
```

向導會逐步詢問以下設定項目：

| 步驟 | 內容 |
|------|------|
| **步驟 1** | TAK Server 的 IP 或 hostname（不可填 127.0.0.1） |
| **步驟 2** | TCP port（預設 8089 for SSL，8087 for 明文） |
| **步驟 3** | 是否啟用 TLS/SSL？是否驗證伺服器憑證？ |
| **步驟 4** | 客戶端 P12 憑證路徑及密碼（Mutual TLS） |
| **步驟 5** | CA bundle PEM 路徑（若要驗證伺服器憑證） |
| **步驟 6** | 進階選項：XML宣告、重試次數、backoff、佇列大小 |

完成後，向導自動寫入 `config/remote-tak.yaml`。

### 3.3 驗證設定

```bash
bash scripts/setup-remote-tak.sh --check
```

輸出範例：
```
  ✓  host: '10.0.0.50'
  ✓  port: 8089
  ✓  use_ssl: True
  ✓  use_ssl_verify: False
  ✓  cert_file: 'config/certs/gateway.p12'  (found)
  ·  ca_bundle: null  (using system trust store)

  All checks passed ✓
```

### 3.4 範本檔案

`config/remote-tak.example.yaml` 是包含所有欄位說明的完整範本。你也可以手動複製並編輯：

```bash
cp config/remote-tak.example.yaml config/remote-tak.yaml
# 用編輯器修改 host、port、cert_file 等欄位
```

> **注意**：`config/remote-tak.yaml` 已被加入 `.gitignore`，不會提交到版本控制。  
> 它可能包含真實的 IP、憑證路徑或密碼，請妥善保管。

### 3.5 憑證準備

如果需要自簽 PKI（開發 / 測試用途）：

```bash
# 在 repo 根目錄執行
bash scripts/gen-certs.sh
# 產生的 gateway.p12 預設在 infra/certs/，需手動複製到 config/certs/
cp infra/certs/gateway.p12 config/certs/gateway.p12
cp infra/certs/truststore.pem config/certs/ca-bundle.pem  # 若需驗證
```

詳細選項見 [gen-certs.sh 說明](#gen-certssh)。

---

## 4. 各腳本詳細說明

---

### `demo-1drone.sh`

**用途**：啟動完整 7 服務管線，模擬單架無人機入侵，純本地模式（不需外部 TAK Server）。

**啟動的服務**：
```
map-sim → uds → echoshield-sim → sentrycs-sim → cot-gateway → tak-relay → tak-client-sim
```

**情境時間軸**：

| 時間 | 事件 |
|------|------|
| t = 9s | EchoShield 初次偵測到無人機（TRK-E01） |
| t = 43s | Sentrycs DETECTED（進入 2 km 警戒圈） |
| t = 71s | Sentrycs MITIGATING → UDS 接管無人機 |
| t = 110s | Sentrycs NEUTRALIZED → 無人機導向 Hold Point |

**使用方式**：

```bash
# 啟動（自動開啟 3 個瀏覽器分頁）
bash scripts/demo-1drone.sh

# 停止
bash scripts/demo-1drone.sh --stop
# 或直接按 Ctrl-C
```

**Web Map**：

| URL | 內容 |
|-----|------|
| `http://127.0.0.1:18090/map` | Map Sim — 原始無人機位置 |
| `http://127.0.0.1:18092/map` | CoT Gateway — 融合戰術地圖 |
| `http://127.0.0.1:18093/map` | TAK Client Sim — 接收到的 CoT XML（MIL-STD-2525C） |

---

### `demo-3drone.sh`

**用途**：啟動完整 7 服務管線，模擬三架無人機交錯入侵，純本地模式。

**情境時間軸（三架）**：

| 時間 | 事件 |
|------|------|
| t = 9s | TRK-E01 進入雷達範圍 |
| t = 27s | TRK-E03 進入雷達範圍 |
| t = 52s | TRK-E02 進入雷達範圍 |
| t = 71s | TRK-E01 MITIGATING |
| t = 127s | TRK-E03 MITIGATING |
| t = 140s | TRK-E02 MITIGATING |

**使用方式**：

```bash
bash scripts/demo-3drone.sh
bash scripts/demo-3drone.sh --stop
```

---

### `demo-1drone-remote-tak.sh`

**用途**：單架無人機情境，支援「本地模式」與「遠端 TAK Server 模式」自動切換。

**模式判斷**：
- `config/remote-tak.yaml` **不存在** → 本地模式（與 `demo-1drone.sh` 相同）
- `config/remote-tak.yaml` **存在且 host 不是 localhost** → 遠端模式（略過 tak-relay，直連外部 TAK）

**遠端模式流程**：

```bash
# 步驟一：設定遠端 TAK Server
bash scripts/setup-remote-tak.sh

# 步驟二：驗證設定正確
bash scripts/setup-remote-tak.sh --check

# 步驟三：確認憑證已放到正確位置
ls config/certs/gateway.p12     # 客戶端憑證（必要）
ls config/certs/ca-bundle.pem   # CA bundle（若 use_ssl_verify: true）

# 步驟四：啟動 demo
bash scripts/demo-1drone-remote-tak.sh

# 停止
bash scripts/demo-1drone-remote-tak.sh --stop
```

**注意事項**：
- 遠端模式下，`tak-client-sim` 會直接連到你的 TAK Server，Console 輸出不再出現在本地
- 如果 TAK Server 不可達，`cot-gateway` 會持續重試（指數退避，最多 `max_retries` 次）

---

### `demo-3drone-remote-tak.sh`

**用途**：三架無人機情境，支援遠端 TAK Server 模式（用法同上）。

```bash
bash scripts/demo-3drone-remote-tak.sh
bash scripts/demo-3drone-remote-tak.sh --stop
```

---

### `demo-cot-gateway-map.sh`

**用途**：僅啟動 CoT Gateway 相關的 5 個服務（不含 TAK relay / client），專注在融合地圖驗證。

**啟動的服務**：
```
map-sim → uds → echoshield-sim → sentrycs-sim → cot-gateway
```

適合：
- 只需要檢視 CoT Gateway 融合結果而不需 ATAK 的場合
- 開發/測試 CoT Gateway 邏輯

```bash
bash scripts/demo-cot-gateway-map.sh
# 開啟 http://127.0.0.1:18092/map

bash scripts/demo-cot-gateway-map.sh --stop
```

---

### `demo-cot-gateway-map-3drones.sh`

**用途**：三架無人機版的 CoT Gateway 地圖 demo（5 服務，無 TAK relay/client）。

```bash
bash scripts/demo-cot-gateway-map-3drones.sh
# 開啟 http://127.0.0.1:18092/map

bash scripts/demo-cot-gateway-map-3drones.sh --stop
```

---

### `demo-map-viewer.sh`

**用途**：最精簡的 demo：僅啟動 `map-sim` 和 `uds`（2 服務），驗證無人機位置推送與地圖顯示。

適合：
- 快速確認 Map Sim + UDS 管線是否正常
- 低資源環境只需看飛行軌跡

```bash
bash scripts/demo-map-viewer.sh
# 開啟 http://127.0.0.1:18090/map

bash scripts/demo-map-viewer.sh --stop
```

---

### `gen-certs.sh`

**用途**：產生開發/測試用自簽 PKI（CA + TAK Server 憑證 + CoT Gateway 客戶端 P12）。

**預設輸出**（`infra/certs/`）：

| 檔案 | 說明 |
|------|------|
| `ca.crt` | CA 憑證（公開） |
| `ca.key` | CA 私鑰（⚠ 妥善保管） |
| `takserver.crt/.key` | TAK Server 憑證/私鑰 |
| `gateway.crt/.key` | CoT Gateway 客戶端憑證/私鑰 |
| `gateway.p12` | CoT Gateway PKCS#12 bundle |
| `truststore.pem` | Trust store（CA 公開憑證） |

**使用方式**：

```bash
# 預設設定（localhost SAN）
bash scripts/gen-certs.sh

# 自訂 TAK Server hostname / IP（遠端部署）
bash scripts/gen-certs.sh --tak-host tak.lab.example.com --tak-ip 10.0.0.5

# 自訂 P12 密碼
bash scripts/gen-certs.sh --p12-password "mySecurePass123"

# 強制重新產生（覆蓋現有憑證）
bash scripts/gen-certs.sh --force

# 自訂輸出目錄
bash scripts/gen-certs.sh --output /path/to/certs
```

完成後將 `gateway.p12` 複製到 demo 憑證目錄：

```bash
cp infra/certs/gateway.p12 config/certs/gateway.p12
cp infra/certs/truststore.pem config/certs/ca-bundle.pem
```

---

## 5. Web Map Viewer 說明

所有 demo 腳本啟動完畢後，會自動開啟瀏覽器。如果未自動開啟，請手動訪問以下 URL：

| Web Map | URL | 說明 |
|---------|-----|------|
| **Map Sim** | `http://127.0.0.1:18090/map` | UDS 推送的原始無人機位置（每秒更新） |
| **CoT Gateway** | `http://127.0.0.1:18092/map` | EchoShield + Sentrycs 融合後的戰術感知地圖 |
| **TAK Client Sim** | `http://127.0.0.1:18093/map` | TAK relay 接收到的 CoT XML（MIL-STD-2525C 圖示） |

**圖示說明**（MIL-STD-2525C）：

| 圖示類型 | CoT type | 顏色 | 含義 |
|----------|----------|------|------|
| 🔴 旋轉菱形 + 箭頭 | `a-h-A-M-F-Q-r` | 紅色 | 融合敵對目標（EchoShield + Sentrycs 都有） |
| ⬜ 圓圈 + 十字 + 箭頭 | `a-u-A-M-F-Q-r` | 灰色 | 未知目標（單一感測器來源） |
| 淡化版本 | 任一 | 半透明 | Stale（資料已過期） |

---

## 6. 常見問題 FAQ

### Q: 執行腳本出現「port is already in use」？

某個 port 已被佔用。先停止前一個 demo：

```bash
bash scripts/demo-1drone.sh --stop
bash scripts/demo-3drone.sh --stop
bash scripts/demo-1drone-remote-tak.sh --stop
```

或手動查找並終止：

```bash
lsof -ti:18090,18092,18093,18080,17070,18089 | xargs kill -9 2>/dev/null || true
```

### Q: `xxx not installed` 錯誤？

需要先安裝依賴（見 [§2.2](#22-安裝-python-套件一次即可)）：

```bash
pip install -e "libs/tak-connection[dev]" --break-system-packages
for svc in uds map-sim echoshield-sim sentrycs-sim cot-gateway tak-client-sim; do
  pip install -e "services/${svc}[dev]" --break-system-packages
done
```

### Q: 遠端模式啟動，但 CoT Gateway 一直重連？

1. 確認 TAK Server IP/port 正確：`bash scripts/setup-remote-tak.sh --check`
2. 確認網路可達：`nc -zv <host> <port>`
3. 確認憑證存在且格式正確（`.p12` 檔案）
4. 查看 cot-gateway 日誌：`tail -f .dev-runtime/logs/demo-*/cot-gateway.log`

### Q: `config/remote-tak.yaml` 不小心設成 localhost，結果觸發本地模式？

編輯 `config/remote-tak.yaml` 修改 `host` 欄位，或重新執行向導：

```bash
bash scripts/setup-remote-tak.sh
```

### Q: 向導寫出的 `config/remote-tak.yaml` 會被 git commit 嗎？

不會。`config/remote-tak.yaml` 已加入 `.gitignore`，不會意外提交真實伺服器資訊。  
提交到版本控制的是 `config/remote-tak.example.yaml`（範本，含佔位 IP）。

### Q: 如何手動編輯 `config/remote-tak.yaml`？

直接用文字編輯器修改，或參考範本：

```bash
# 查看範本（所有欄位與說明）
cat config/remote-tak.example.yaml

# 或重新執行向導（會覆寫現有內容，確認後生效）
bash scripts/setup-remote-tak.sh
```

### Q: 如何同時觀察所有服務的日誌？

Demo 腳本會把日誌寫入 `.dev-runtime/logs/<session>/` 目錄：

```bash
# 找最新的 session 日誌目錄
ls -t .dev-runtime/logs/ | head -1

# 即時追蹤所有服務日誌（以最新 session 為例）
tail -f .dev-runtime/logs/$(ls -t .dev-runtime/logs/ | head -1)/*.log
```

---

*文件維護者：CICS TAK PoC 開發團隊 | 對應 feature：[016-tak-shared-connection](../dev-docs/016-tak-shared-connection.md)*
