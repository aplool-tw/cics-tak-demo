# TAK Server 部署規格

---

| 欄位 | 內容 |
|------|------|
| **文件編號** | 05 |
| **版本** | v0.3 |
| **日期** | 2026-04-22（修訂：PoC 改本機 MacBook Pro 部署，移除 WinTAK）|
| **作者** | 系統架構小組 |
| **狀態** | 草稿 |

---

## 1. 基礎設施概覽

### 1.1 PoC 部署環境

**PoC 階段所有服務部署於一台 MacBook Pro 本機**，不使用任何雲端服務。

| 元件 | 執行方式 | 位置 |
|------|---------|------|
| TAK Server | Docker 容器（Docker Desktop for Mac）| MacBook Pro 本機 |
| PostgreSQL 15 | Docker 容器（docker-compose 管理）| MacBook Pro 本機 |
| CoT Gateway | Python 直接執行（或 Docker）| MacBook Pro 本機 |
| EchoShield Simulator | Python 直接執行 | MacBook Pro 本機 |
| Sentrycs Simulator | Python 直接執行 | MacBook Pro 本機 |
| ATAK 顯示端 | Android 裝置（平板/手機）| 與 MacBook 同一 Wi-Fi |

### 1.2 網路架構

```
MacBook Pro
├── localhost (127.0.0.1)
│   ├── EchoShield Simulator :9000
│   ├── CoT Gateway（TCP client）
│   ├── TAK Server Docker :8087 :8089 :8443 :8446
│   └── PostgreSQL Docker :5432
│
└── LAN IP（Wi-Fi，e.g. 192.168.1.100）
    └── ATAK 平板/手機透過此 IP 連接 TAK Server

# 查詢 MacBook LAN IP：
ipconfig getifaddr en0
```

> **重要**：ATAK Android 裝置必須與 MacBook 連接同一 Wi-Fi AP，並使用 MacBook 的 LAN IP（非 localhost）連線至 TAK Server。

### 1.3 前置需求

| 需求 | 版本 / 規格 | 確認指令 |
|------|-----------|---------|
| Docker Desktop for Mac | 4.x 以上 | `docker --version` |
| docker-compose | v2.x（Docker Desktop 內建）| `docker compose version` |
| macOS | Ventura / Sonoma / Sequoia | 系統資訊 |
| 可用 RAM | 至少 8 GB（建議 16 GB）| 活動監控 |
| 可用磁碟 | 至少 20 GB | `df -h` |

---

## 2. Docker Desktop for Mac 安裝與設定

### 2.1 安裝 Docker Desktop

```bash
# 方法一：官網下載 .dmg 安裝
# https://www.docker.com/products/docker-desktop/

# 方法二：Homebrew
brew install --cask docker

# 確認安裝
docker --version
docker compose version
```

### 2.2 Docker Desktop 資源配置

開啟 Docker Desktop → Settings → Resources：

| 項目 | 建議設定 | 原因 |
|------|---------|------|
| CPUs | 4 | TAK Server Java JVM 需要 |
| Memory | 6 GB | TAK Server(2GB) + PostgreSQL(512MB) + 系統 |
| Disk image size | 20 GB | Docker Image + 資料 |
| Enable VirtioFS | ✅ | macOS 高效能檔案共享 |

### 2.3 目錄結構建立

```bash
# 在專案目錄下建立（建議放在專案路徑）
mkdir -p ~/tak-poc/{certs,logs,data,backups}
cd ~/tak-poc

# 確認目錄
ls -la ~/tak-poc/
```

---

## 3. macOS 網路與防火牆設定

### 3.1 macOS 防火牆確認

PoC 環境中 TAK Server 僅在本機與 LAN 對外開放，不需要複雜的防火牆規則。

```bash
# 確認 macOS 防火牆狀態（可選，通常不需要關閉）
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate

# 若防火牆已啟用，Docker Desktop 會自動處理連線規則
# 無需手動開放 Port
```

### 3.2 Port 用途說明

| Port | 協定 | 用途 | 存取來源 |
|------|------|------|---------|
| 9000 | TCP | EchoShield Simulator JSON API | 本機（127.0.0.1）|
| 8087 | TCP | TAK Server 無 SSL（測試用）| 本機 |
| 8089 | TCP SSL | TAK Server 主線 CoT | 本機 + LAN Android 裝置 |
| 8443 | HTTPS | TAK Server Web Admin Console | 本機瀏覽器 |
| 8446 | HTTPS | PKI Auto-enrollment | 本機 + LAN Android 裝置 |
| 4242 | UDP | SA（作戰模式備用）| 本機 |
| 5432 | TCP | PostgreSQL（僅 Docker 內部）| Docker 內部網路 |

### 3.3 Android 裝置連線確認

```bash
# 查詢 MacBook Wi-Fi LAN IP
ipconfig getifaddr en0

# 確認 Android 裝置可達（在 MacBook 端執行）
# 先確認 Android 裝置 IP（在 Android 設定 > 關於 > IP 位址查看）
ping <Android-IP>

# 確認 TAK Server Port 可達（從 MacBook 本機測試）
nc -zv 127.0.0.1 8089
```

> **PoC 注意**：本 PoC 為 LAN 內部測試環境，不對外網開放。如需跨網段存取，請設定路由或使用同一 Wi-Fi AP。

---

## 4. Docker 安裝與 docker-compose 配置

### 4.1 TAK Server Docker Image

TAK Server 官方提供 Docker Image，需從 TAK.gov 申請並下載（需帳號）。下載後在 MacBook 本機載入：

```bash
# 解壓並載入 Image（在 MacBook 本機執行）
cd ~/tak-poc
unzip takserver-docker-*.zip
docker load -i takserver-*.tar.gz

# 確認 image 名稱
docker images | grep tak
```

### 4.2 docker-compose.yml

```yaml
# ~/tak-poc/docker-compose.yml
version: '3.8'

services:
  tak-server:
    image: takserver:latest
    container_name: takserver
    restart: unless-stopped
    ports:
      - "8087:8087"    # TCP 無 SSL（測試用）
      - "8089:8089"    # TCP SSL（主線）
      - "8443:8443"    # HTTPS Web Console
      - "8446:8446"    # HTTPS PKI Auto-enrollment
      - "4242:4242/udp" # UDP SA
    volumes:
      - ./certs:/opt/tak/certs:ro
      - ./logs:/opt/tak/logs
      - ./data:/opt/tak/data
      - ./CoreConfig.xml:/opt/tak/CoreConfig.xml:ro
    environment:
      - TAK_DB_HOST=postgres
      - TAK_DB_PORT=5432
      - TAK_DB_NAME=cot
      - TAK_DB_USER=martiuser
      - TAK_DB_PASSWORD=${DB_PASSWORD}
      - TAK_JAVA_OPTS=-Xmx2g -Xms512m
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - tak-network
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "5"

  postgres:
    image: postgres:15-alpine
    container_name: takserver-db
    restart: unless-stopped
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=cot
      - POSTGRES_USER=martiuser
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    networks:
      - tak-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U martiuser -d cot"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
    driver: local

networks:
  tak-network:
    driver: bridge
```

### 4.3 .env 設定檔

```bash
# ~/tak-poc/.env
# 請修改為強密碼
DB_PASSWORD=takserver_poc_2025
```

### 4.4 啟動指令

```bash
cd ~/tak-poc

# 啟動（背景執行）
docker-compose up -d

# 查看狀態
docker-compose ps

# 查看日誌
docker-compose logs -f tak-server

# 停止
docker-compose down

# 完整重置（含資料）
docker-compose down -v
```

---

## 5. PKI 憑證設置流程

### 5.1 進入 TAK Server Container

```bash
docker exec -it takserver /bin/bash
cd /opt/tak/certs/files
```

### 5.2 Step 1：建立根 CA

```bash
# 建立 TAK-POC-CA 根憑證
./makeRootCa.sh
# CA Name: TAK-POC-CA
# Password: atakatak（PoC 測試用）
# 產生：TAK-POC-CA.pem / .key / .jks
```

### 5.3 Step 2：建立 TAK Server 憑證

```bash
./makeCert.sh server takserver
# 密碼：atakatak
# 產生：takserver.p12, takserver.jks
```

### 5.4 Step 3：建立 CoT Gateway 客戶端憑證

```bash
./makeCert.sh client gateway
# 密碼：atakatak
# 產生：gateway.p12, gateway.jks
```

### 5.5 Step 4：建立 ATAK 客戶端憑證

```bash
# 建立平板和手機各一張憑證
./makeCert.sh client atak-tablet
./makeCert.sh client atak-phone
# 密碼：atakatak
# 產生：atak-tablet.p12, atak-phone.p12
```

### 5.6 Step 5：建立 Sentrycs Simulator 客戶端憑證

```bash
./makeCert.sh client sentrycs
# 密碼：atakatak
# 產生：sentrycs.p12
```

### 5.7 憑證複製至 MacBook 主機並分發

```bash
# 從 Container 複製至 MacBook（在 MacBook Terminal 執行）
docker cp takserver:/opt/tak/certs/files/ ~/tak-poc/certs/

# 查看產生的憑證
ls -la ~/tak-poc/certs/files/*.p12

# 憑證分發（所有服務都在同一台 MacBook，直接複製）
cp ~/tak-poc/certs/files/gateway.p12      ~/cot_gateway/certs/
cp ~/tak-poc/certs/files/truststore.p12   ~/cot_gateway/certs/
cp ~/tak-poc/certs/files/sentrycs.p12     ~/sentrycs_simulator/certs/
cp ~/tak-poc/certs/files/truststore.p12   ~/sentrycs_simulator/certs/

# ATAK 憑證傳送到 Android 裝置（USB / Wi-Fi 傳輸）
# 將 atak-tablet.p12 / atak-phone.p12 / truststore.p12 傳至 Android
```

### 5.8 truststore.pem 建立（供 Python ssl 使用）

```bash
# 在 MacBook Terminal 執行（需安裝 openssl：brew install openssl）
openssl pkcs12 -in ~/tak-poc/certs/files/truststore.p12 \
  -nokeys -cacerts -out ~/tak-poc/certs/files/truststore.pem \
  -passin pass:atakatak
```

---

## 6. TAK Server 初始配置

### 6.1 CoreConfig.xml 關鍵設定

TAK Server 的主設定檔位於 `/opt/tak/CoreConfig.xml`（Container 內）：

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Configuration>

  <!-- 資料庫連線 -->
  <repository enable="true">
    <connection url="jdbc:postgresql://postgres:5432/cot"
                username="martiuser"
                password="takserver_poc_2025"
                driver="org.postgresql.Driver"
                connectionPoolMinSize="5"
                connectionPoolMaxSize="50"/>
  </repository>

  <!-- 網路介面設定 -->
  <network>

    <!-- TCP 無 SSL（測試用）-->
    <input _name="tcp-8087" protocol="tcp" port="8087" auth="anonymous"/>

    <!-- TCP SSL（主線）-->
    <input _name="tcp-ssl-8089" protocol="tcp" port="8089" auth="x509"
           keystoreFile="/opt/tak/certs/files/takserver.jks"
           keystorePass="atakatak"
           truststoreFile="/opt/tak/certs/files/truststore.jks"
           truststorePass="atakatak"
           context="TLSv1.2"/>

    <!-- UDP SA（作戰模式備用）-->
    <input _name="udp-4242" protocol="udp" port="4242" auth="anonymous"/>

    <!-- HTTPS Web Console -->
    <connector port="8443" _name="https-8443"
               keystoreFile="/opt/tak/certs/files/takserver.jks"
               keystorePass="atakatak"
               truststoreFile="/opt/tak/certs/files/truststore.jks"
               truststorePass="atakatak"/>

    <!-- PKI Auto-enrollment -->
    <connector port="8446" _name="https-8446-pki"
               keystoreFile="/opt/tak/certs/files/takserver.jks"
               keystorePass="atakatak"
               truststoreFile="/opt/tak/certs/files/truststore.jks"
               truststorePass="atakatak"/>
  </network>

  <!-- 安全設定 -->
  <security>
    <tls keystore="JKS"
         keystoreFile="/opt/tak/certs/files/takserver.jks"
         keystorePass="atakatak"
         truststore="JKS"
         truststoreFile="/opt/tak/certs/files/truststore.jks"
         truststorePass="atakatak"
         context="TLSv1.2"
         keymanager="SunX509"/>
  </security>

</Configuration>
```

### 6.2 建立 Mission Package for ATAK

```bash
# Mission Package = ATAK 連線設定包（.zip 格式）
# 包含：伺服器位址（MacBook LAN IP）、Port、客戶端憑證

# 在 TAK Server Web Console 建立：
# 瀏覽器開啟：https://localhost:8443/
# 1. 登入（預設帳號：admin）
# 2. 進入 Setup > Data Package
# 3. 建立 Enrollment Package：
#    - Server Address: <MacBook-LAN-IP>（如 192.168.1.100）
#    - Port: 8089
#    - 選擇 atak-tablet.p12 / atak-phone.p12 憑證
# 4. 下載 .zip 包
# 5. 透過 USB 或 AirDrop / 雲端分享傳送至 Android 裝置
```

---

## 7. ATAK Android 裝置連線設定

> **注意**：PoC 已移除 WinTAK，所有顯示端均為 Android ATAK 裝置（平板/手機）。

### 7.1 ATAK 共同前置準備

1. 確認 Android 裝置與 MacBook 連接**同一 Wi-Fi AP**
2. 確認 MacBook LAN IP（`ipconfig getifaddr en0`）
3. 準備憑證檔案：`atak-tablet.p12` / `atak-phone.p12` + `truststore.p12`

### 7.2 ATAK 指揮端（平板）

**方法一：Mission Package（推薦）**
1. 將 Mission Package (.zip) 以 USB 或雲端傳送至平板
2. 開啟 ATAK → Import → 選擇 .zip 檔
3. 自動完成設定並連線

**方法二：手動設定**
1. 將 `atak-tablet.p12` 傳送至平板（USB / 雲端）
2. ATAK → Settings → TAK Servers → 新增：
   - **Description**：TAK-POC-Server
   - **Server Address**：`<MacBook-LAN-IP>`（如 `192.168.1.100`）
   - **Port**：8089
   - **Protocol**：SSL
   - **Client Certificate**：atak-tablet.p12
   - **Password**：atakatak
   - **Trust Store**：truststore.p12
3. 點擊 Connect，確認狀態變綠色

### 7.3 ATAK（手機）

同 7.2 手動設定步驟，使用 `atak-phone.p12` 憑證，Server Address 相同。

### 7.4 連線確認

- ATAK 狀態列圖示變綠（Connected）
- 進入 ATAK 地圖，確認能看到其他裝置的 SA（情況感知）標記
- 稍後可確認 EchoShield / Sentrycs 模擬器產生的無人機圖標出現

---

## 8. 驗證程序

### 8.1 Docker 狀態確認

```bash
# 確認所有 Container 運行正常
docker-compose ps

# 預期輸出：
# NAME            STATUS
# takserver       Up (healthy)
# takserver-db    Up (healthy)
```

### 8.2 Port 開放確認

```bash
# 確認 Port 監聽
ss -tlnp | grep -E '8087|8089|8443|8446'

# 或
netstat -tlnp | grep -E '8087|8089|8443|8446'
```

### 8.3 TCP 連線測試（無 SSL）

```bash
# 測試 Port 8087 是否可達（本機執行）
nc -zv localhost 8087

# 或
curl -v telnet://localhost:8087
```

### 8.4 SSL 連線測試

```bash
# 測試 SSL 握手（本機執行，需先匯出 PEM）
openssl s_client -connect localhost:8089 \
  -cert ~/tak-poc/certs/files/gateway.pem \
  -key ~/tak-poc/certs/files/gateway.key \
  -CAfile ~/tak-poc/certs/files/truststore.pem \
  -no_ssl3 -no_tls1 -no_tls1_1

# 預期看到：
# SSL handshake has read ... bytes
# Verify return code: 0 (ok)
```

### 8.5 Web Console 存取

```bash
# MacBook 瀏覽器開啟（接受自簽憑證警告）
open https://localhost:8443/
# 預期看到 TAK Server 管理介面
```

### 8.6 健康檢查 Endpoint

```bash
# TAK Server REST API 健康確認
curl -k https://localhost:8443/api/version/config
# 預期回應：{"version": "...", "api": "..."}
```

### 8.7 端對端 CoT 測試

```bash
# 推送一筆測試 CoT（TCP 無 SSL，Port 8087，本機執行）
cat << 'EOF' | nc localhost 8087
<?xml version="1.0" encoding="UTF-8"?>
<event version="2.0" uid="TEST-PING-001" type="a-f-G" time="2025-07-10T08:00:00.000Z" start="2025-07-10T08:00:00.000Z" stale="2025-07-10T08:05:00.000Z" how="m-g">
  <point lat="25.0330" lon="121.5654" hae="0" ce="9999999" le="9999999"/>
  <detail><contact callsign="TEST-PING"/></detail>
</event>
EOF

# 確認 ATAK 畫面上出現 "TEST-PING" 圖標
```

---

## 9. 本機監控配置

### 9.1 Docker 容器狀態監控

```bash
# 即時資源用量（CPU / Memory / Network）
docker stats takserver takserver-db

# 查看容器狀態
docker compose -f ~/tak-poc/docker-compose.yml ps

# 查看最新日誌
docker compose -f ~/tak-poc/docker-compose.yml logs --tail 100 tak-server
docker compose -f ~/tak-poc/docker-compose.yml logs --tail 50 postgres
```

### 9.2 TAK Server 日誌監控

```bash
# 持續追蹤 TAK Server 日誌（即時）
docker compose -f ~/tak-poc/docker-compose.yml logs -f tak-server

# 查看特定關鍵字（如 ERROR）
docker logs takserver 2>&1 | grep -i "error\|exception\|warn" | tail -30
```

### 9.3 Port 狀態確認

```bash
# 確認 TAK Server Port 監聽中
lsof -i :8087 -i :8089 -i :8443 -i :8446

# 或
netstat -an | grep -E '8087|8089|8443|8446'
```

### 9.4 監控項目建議

| 指標 | 警戒值 | 確認方式 |
|------|-------|---------|
| Docker CPU 使用率 | > 80% | `docker stats` |
| Docker 記憶體使用 | > 5 GB | `docker stats` |
| 磁碟使用率 | > 80% | `df -h` |
| TAK Server 連線數 | 異常 | TAK Web Console → Status |
| CoT 延遲 | > 5 秒 | 觀察 ATAK 圖標更新速度 |

---

## 10. 備援切換程序

### 10.1 TAK Server 重啟步驟

```bash
cd ~/tak-poc

# 優雅重啟 TAK Server（保留資料庫）
docker compose restart tak-server

# 查看重啟後狀態
docker compose ps
docker compose logs --tail 50 tak-server
```

### 10.2 完整堆疊重啟

```bash
cd ~/tak-poc

# 停止所有 Container
docker compose down

# 等待 5 秒
sleep 5

# 重新啟動
docker compose up -d

# 確認健康
docker compose ps
```

### 10.3 資料庫備份

```bash
# 手動備份 PostgreSQL
docker exec takserver-db pg_dump -U martiuser cot \
  > ~/tak-poc/backups/cot_$(date +%Y%m%d_%H%M%S).sql

# 壓縮備份
gzip ~/tak-poc/backups/cot_$(date +%Y%m%d_%H%M%S).sql
```

### 10.4 資料庫還原

```bash
# 還原資料庫（替換備份檔名）
gunzip ~/tak-poc/backups/cot_20250710.sql.gz
docker exec -i takserver-db psql -U martiuser cot < ~/tak-poc/backups/cot_20250710.sql
```

### 10.5 Container 崩潰自動重啟

docker-compose.yml 中設定 `restart: unless-stopped`，Container 崩潰後會自動重啟。確認設定：

```bash
docker inspect takserver | grep -A 3 RestartPolicy
# 預期："Name": "unless-stopped"
```

### 10.6 PoC 完整重置（清除所有資料）

```bash
cd ~/tak-poc

# 停止並移除所有容器 + 資料 Volume
docker compose down -v

# 清除憑證（如需重新產生）
rm -rf ~/tak-poc/certs/files/*

# 重新啟動
docker compose up -d
```
