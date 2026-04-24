# Quickstart: EchoShield Simulator

**Feature**: `003-echoshield-sim`
**適用對象**：在本機（Linux / macOS）驗證 EchoShield Simulator 與 Map Sim 串接、確認 TCP JSON
Feed 格式正確的 PoC 開發者 / demo 操作者。

---

## 0. 前置條件

| 項目                   | 要求                                                                       |
| ---------------------- | -------------------------------------------------------------------------- |
| Python                 | 3.11+                                                                      |
| Map Simulator (`:8090`)| 已跑起來（`services/map-sim/`，參照 `specs/002-map-sim/quickstart.md`）     |
| UDS 上游（可選）       | 若要看到動態 track，最簡單是跑 `services/uds/scenarios/` 內任一情境        |
| 工具                   | `nc`（netcat）、`curl`、`jq`（方便觀察）                                   |

> 若只想驗證「靜默模式」與 connection lifecycle，**不需要**任何 UDS；Map Sim 空的也行，
> Simulator 會保持連線但不送 bytes。

---

## 1. 安裝與啟動

```bash
cd services/echoshield-sim
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
```

建立一個最小 config（e.g. `config/local.yaml`）：

```yaml
sensor_lat: 24.0
sensor_lon: 121.0
sensor_alt_m: 10.0
max_range_m: 4800
update_rate_hz: 10
lost_grace_sec: 2.0

position_noise_m: 5.0
velocity_noise_ms: 0.5

noise_seed: null   # 或填整數以求可重現（CLI --seed 會覆寫此值）

map_sim_url: http://localhost:8090
feed_host: 0.0.0.0
feed_port: 9000
```

啟動：

```bash
echoshield-sim --config config/local.yaml --verbose
# 或
python -m echoshield_sim --config config/local.yaml
```

預期 stdout（structlog JSON）：

```json
{"event":"startup","map_sim_url":"http://localhost:8090","feed":"0.0.0.0:9000","seed":null,"level":"info"}
{"event":"tcp_server_listening","host":"0.0.0.0","port":9000,"level":"info"}
{"event":"tick","tick_id":0,"latency_ms":3.1,"count":0,"level":"debug"}
```

---

## 2. 先看 TCP Feed（無需 Gateway）

開另一個終端：

```bash
nc localhost 9000
```

- **若 Map Sim 內無範圍內目標**：終端靜默（正常，FR-ES-011）。
- **若 Map Sim 內 ≥ 1 架無人機**：每 100ms 1 筆（多目標時每 100ms N 筆），JSON 行 + `\n`：

```json
{"track_id":"echo-1a2b3c4d","latitude":24.0008934,"longitude":121.0001205,"altitude_m":98.7,"velocity_ms":12.34,"azimuth_deg":3.21,"elevation_deg":5.07,"timestamp":"2026-04-24T08:15:30.123Z","track_status":"Active","classification":"UAV"}
```

用 `jq` 觀察：

```bash
nc localhost 9000 | jq -c '{id:.track_id, s:.track_status, az:.azimuth_deg, el:.elevation_deg}'
```

---

## 3. 手動灌資料（含 Lost 事件）

### 3a. 啟動 Map Sim（另一終端）
```bash
cd services/map-sim && python -m map_sim --config config/local.yaml
```

### 3b. 推一架無人機 → 看到 Active

```bash
curl -X POST http://localhost:8090/drones/DR-001 \
  -H 'Content-Type: application/json' \
  -d '{
    "drone_id":"DR-001","lat":24.002,"lon":121.0,"alt_m":100,
    "speed_ms":12,"heading_deg":0,"status":"FLYING_NORMAL",
    "timestamp":"2026-04-24T08:15:30Z"
  }'
```

在 `nc` 終端應立即開始每 100ms 收到 `track_status:"Active"` 的行，`track_id` 保持不變。

### 3c. 讓 Map Sim TTL 過期 → 看到 Lost

停止對 DR-001 的 push，等到 Map Sim TTL 將其從 `/objects` 回應中移除；
Simulator 於其後 **`lost_grace_sec` (2.0s) 過後的下一輪** 廣播：

```json
{"track_id":"echo-1a2b3c4d","...","track_status":"Lost","classification":"UAV"}
```

之後該 `track_id` 完全消失（不再出現任何行）。若該 drone_id 再次被推回 Map Sim，Simulator
會分配**新**的 `track_id`。

### 3d. 抖動測試（Grace Window 吸收）

若 DR-001 在 Map Sim 中消失 < 2s 後重新出現，`nc` 終端應觀察到：
- 消失期間：無 DR-001 的行（靜默，**不**會看到 Lost）。
- 重新出現：**沿用相同 track_id** 繼續 Active 行。

---

## 4. 可重現噪點（Demo / Debug）

兩個終端啟動兩個 Simulator instance（不同 port 避開衝突），**相同 seed + 相同時間 + 相同 Map Sim
輸入** 應輸出 bit-identical JSON：

```bash
# Instance A
echoshield-sim --config config/local.yaml --seed 42

# Instance B（改 feed_port、其他相同；或 diff 同一份輸出）
echoshield-sim --config config/localB.yaml --seed 42
```

CLI `--seed` 優先於 YAML `noise_seed`（spec §Clarifications）。

---

## 5. 多 Client Fan-out

```bash
# Terminal 1
nc localhost 9000 > /tmp/c1.ndjson

# Terminal 2
nc localhost 9000 > /tmp/c2.ndjson

# 等 5s 後 Ctrl-C 兩者：
diff /tmp/c1.ndjson /tmp/c2.ndjson
# 預期：空 diff（兩 Client 收到完全相同 bytes，允許最後一行 buffering 差 ≤ 1 行）
```

---

## 6. Map Sim 暫時不可用

```bash
# 在 Simulator 運行時：
pkill -f "map_sim"   # 或 iptables DROP :8090

# Simulator 不崩潰、不關連線；log 會看到（每秒最多 1 行）：
# {"event":"map_sim_unavailable","reason":"ConnectionRefusedError","level":"warning"}

# 重新啟動 Map Sim：
cd services/map-sim && python -m map_sim --config config/local.yaml

# Simulator 於下一 tick（≤100ms）恢復廣播。
```

---

## 7. 測試

```bash
cd services/echoshield-sim
pytest -q                              # 全部
pytest tests/contract -q               # TCP JSON schema 凍結
pytest tests/integration -q            # 端對端：Map Sim stub + TCP client
pytest tests/unit -q                   # geo / noise / lifecycle 等單元
pytest -q -k "lifecycle_grace"         # grace window 2s 行為
```

固定 seed + freezegun 的契約測試應為 bit-identical 重現。

---

## 8. 故障排除

| 症狀                                           | 可能原因                          | 處理                                                                 |
| ---------------------------------------------- | --------------------------------- | -------------------------------------------------------------------- |
| `nc localhost 9000` 連得上但完全沒資料         | Map Sim 回應 `count=0`（正常）    | 先 `curl http://localhost:8090/objects?lat=24&lon=121&radius_m=4800` 確認 |
| log 連續出現 `map_sim_unavailable`             | Map Sim 沒起 / 埠不通             | 啟動 Map Sim 或 `curl` 自檢 :8090                                     |
| JSON 行含 `"track_status":"Lost"` 卻一直不清除 | （不會發生）Lost 後 drone_id 再出現 | Lost 會分配**新** track_id，不是同一個                                 |
| `nc` 收到的 JSON 行有多行縮排                  | 不符合契約                         | 本契約固定為 compact + `\n`，應回報 bug                                |
| 多 Client 收到不同行數（差 > 1）               | 中間有 Client 被 drain 失敗踢出   | 檢查 log `client_disconnected` + 該 Client 的 socket 設定             |
