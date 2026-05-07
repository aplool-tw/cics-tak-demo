# Quickstart: CoT Gateway

本文件提供 CoT Gateway（Feature 005）的最短「跑起來 → 看到 ATAK 圖示 → 驗證失效恢復」路徑。
適用於開發者在本機以 Docker Compose 驗證 PoC。

---

## 0. 前置條件

- Docker + Docker Compose v2
- Python 3.11+（本機 IDE 跑 pytest 用；容器內已預裝）
- `config/certs/gateway.p12`（由 Feature 001 基礎設施提供；若無 → 見 §7 產生指引）
- 前置 features 已實作並可啟動：
  - `specs/001-uds/`（可選；Sentrycs takeover 下游，本 Feature 不直接依賴）
  - `specs/002-map-sim/`
  - `specs/003-echoshield-sim/`
  - `specs/004-sentrycs-sim/`
  - TAK Server container（Feature 001 基礎設施）

---

## 1. 安裝（local dev，不跑 container）

```bash
cd services/cot-gateway
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

---

## 2. 設定

編輯 `services/cot-gateway/config/gateway.yaml`（範例）：

```yaml
echoshield:
  host: echoshield-sim
  port: 9000
  reconnect_interval_s: 5.0
sentrycs:
  enabled: true
  host: sentrycs-sim
  port: 7070
  poll_interval_s: 1.0
  timeout_s: 2.0
correlator:
  distance_threshold_m: 50.0
  time_window_s: 3.0
  ttl_s: 10.0
tak_server:
  host: tak-server
  port: 8089
  use_ssl: true
  use_ssl_verify: false          # PoC
  cert_file: config/certs/gateway.p12
  cert_password: ""              # 或 ${TAK_P12_PASSWORD}
  max_retries: 5
  backoff_initial_s: 1.0
  backoff_cap_s: 60.0
  queue_maxsize: 500
logging:
  level: INFO
  json: true
```

---

## 3. 啟動全鏈（Docker Compose）

```bash
# 從專案 repo 根目錄
docker compose up -d tak-server map-sim uds echoshield-sim sentrycs-sim
docker compose up cot-gateway           # 前景執行看日誌；-d 背景
```

預期 Gateway 日誌（INFO）：

```
{"event": "echoshield_connected", "host": "echoshield-sim", "port": 9000, ...}
{"event": "sentrycs_poll", "count": 0, ...}
{"event": "tak_connected", "host": "tak-server", "port": 8089, ...}
{"event": "track_first_seen", "uid": "ECHO-TRK-001", ...}
{"event": "correlation_hit", "radar": "TRK-001", "rf": "DRN-001", "distance_m": 12.3, ...}
{"event": "source_switch", "old_uid": "ECHO-TRK-001", "new_uid": "FUSED-DRN-001", ...}
```

---

## 4. 驗證 User Story 1（雷達單源 → ATAK 灰色）

1. 在 ATAK client（或連到 TAK Server `:18089` 的 `ncat --ssl` sink）觀察：
   ```bash
   # 臨時以 openssl 作為 TCP+SSL sniffer 旁觀 TAK 上送（需先停掉真 Gateway 並以此假冒，僅 debug 用）
   openssl s_client -connect tak-server:18089 -cert gateway.crt -key gateway.key
   ```
2. 預期每 100 ms 左右出現一筆以 `\n` 分隔的 CoT XML，uid=`ECHO-TRK-001`、type=`a-u-A-M-F-Q-r`、
   `<point lat lon hae>` 數值貼近 EchoShield Simulator JSON。
3. ATAK 地圖上出現**灰色**未識別空中目標，位置隨時間平滑移動。

---

## 5. 驗證 User Story 2（融合 → ATAK 紅色 + source 切換）

1. 啟動 Sentrycs Simulator（若已啟動則無需動作）；場景 YAML 含 `drones[].detected_at_s` 時序。
2. 於 Sentrycs `detected_at_s` 到達時，Gateway 日誌應出現：
   ```
   {"event": "correlation_hit", ...}
   {"event": "source_switch", "old_uid": "ECHO-TRK-001", "new_uid": "FUSED-DRN-001", ...}
   ```
3. ATAK：灰色 `ECHO-TRK-001` 消失（收到 stale=now）→ 紅色 `FUSED-DRN-001` 出現於幾乎相同位置。
4. 進入 Sentrycs `NEUTRALIZED` 狀態時，CoT `<remarks>` 出現 `Status: NEUTRALIZED`，`stale = time + 30s`
   （ATAK 停留顯示更久）。

---

## 6. 驗證 User Story 3（斷線與 TTL 恢復）

### 6.1 EchoShield 斷線重連

```bash
docker compose stop echoshield-sim
sleep 5
docker compose start echoshield-sim
```

預期：
- Gateway 日誌 WARNING `echoshield_disconnected` + `echoshield_connected`（5 s 後）；
- 主程序**未退出**（`docker compose ps cot-gateway` 仍 Running）；
- Sentrycs 輪詢與 TAK 連線不受影響（日誌持續有 `sentrycs_poll` 事件）。

### 6.2 TAK 不可達（指數退避）

```bash
# iptables 阻斷（需 root；或用 toxiproxy 更乾淨）
docker compose pause tak-server
sleep 10
docker compose unpause tak-server
```

預期：
- Gateway 日誌出現 `tak_send_failed` + 5 次 `tak_reconnect` 退避嘗試；
- 恢復後 `tak_connected` 再次出現，後續 CoT 正常送達；
- 若超過 max_retries=5 仍失敗 → Gateway exit code != 0。

### 6.3 TTL 過期（雷達靜默 > 10 s）

於場景腳本中讓某 `track_id` 在 10 秒內不再更新（或手動 Ctrl-C 單飛機腳本），預期：
- 下一秒 TTL tick 產生 `ttl_expired` INFO 事件 + 對該 uid 發 `stale=time` CoT；
- ATAK 於下一個 refresh 週期（≤ 3 s）移除對應圖示。

### 6.4 SIGINT 優雅關閉

```bash
docker compose kill -s SIGINT cot-gateway
```

預期：
- Gateway 於 ≤ 3 s 內排空 `cot_queue` 並關閉連線；
- exit code 0。

---

## 7. 憑證產生（開發用自簽 p12）

若沒有 TAK Server 發放的 `gateway.p12`，可用 openssl 產臨時自簽：

```bash
openssl req -x509 -newkey rsa:4096 -keyout gateway.key -out gateway.crt \
  -days 30 -nodes -subj "/CN=cot-gateway"
openssl pkcs12 -export -in gateway.crt -inkey gateway.key \
  -out services/cot-gateway/config/certs/gateway.p12 -passout pass:
```

搭配 `tak_server.use_ssl_verify: false`、`tak_server.cert_password: ""` 即可啟動。

---

## 8. 測試

```bash
cd services/cot-gateway
pytest                                       # 全部三層
pytest tests/contract                        # 僅契約
pytest tests/integration -k us1              # 僅 User Story 1
pytest tests/unit -k stale                   # 僅 stale 三段式
pytest --cov=cot_gateway --cov-report=term   # 覆蓋率
```

---

## 9. 觀測（structlog JSON）

Gateway 所有 INFO/WARNING/ERROR 事件皆輸出 JSON 至 stdout。關鍵 event 清單見 `plan.md` G3/G4；用
`jq` 過濾：

```bash
docker compose logs -f cot-gateway | jq 'select(.event == "source_switch")'
```

---

## 10. 常見問題

| 症狀 | 可能原因 | 處理 |
| --- | --- | --- |
| ATAK 看不到任何圖示 | TAK Server 未連接 / 憑證不對 | 查日誌 `tak_connected` 是否出現；檢查 `cert_file` 路徑與密碼 |
| 灰色圖示持續不變紅 | Sentrycs 未啟動 / 距離 > 50 m / 時間差 > 3 s | 查 `correlation_hit` 是否出現；對照 Sentrycs `/detections` 輸出 |
| ATAK 圖示一直殘留不消失 | TTL 未觸發（雷達持續送資料）或 stale 錯誤 | 查 `ttl_expired` 事件；停 EchoShield 觀察 ≤ 11 s 後是否消失 |
| `queue_full_drop` WARNING 頻繁 | TAK 連線塞住；下游消費跟不上 | 檢查 TAK Server 負載 / 網路；必要時調整 `queue_maxsize` |
| Gateway exit code 非 0 立即結束 | `cert_file` 不存在 / p12 密碼錯 / TAK 達 max_retries | 查最後一筆 ERROR 日誌；修正設定後重啟 |
