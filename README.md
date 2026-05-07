# CICS TAK PoC — Counter-UAS Tactical Awareness Demo

> 台灣反無人機 TAK 戰術感知 PoC：整合 EchoShield 4D 雷達與 Sentrycs C-UAS 射頻偵測，融合輸出 CoT 至 TAK Server / ATAK 顯示端。

[![tests](https://img.shields.io/badge/tests-659%20passing-brightgreen)]() [![python](https://img.shields.io/badge/python-3.11+-blue)]() [![status](https://img.shields.io/badge/PoC%20v1-complete-success)]()

---

## 1. 概覽

本專案以六個獨立 Python 服務模擬完整的反無人機戰術感知鏈路。所有感測器皆以 PoC 模擬器替代，方便在單機開發環境上端對端驗證融合與 CoT 推送邏輯。

```
┌─────────────────┐  POST /command/takeover   ┌───────────────────┐
│  Sentrycs Sim   │ ─────────────────────────▶│  Unified Drone    │
│  (RF C-UAS)     │ ◀── GET /objects ──┐      │  Simulator (UDS)  │
│  HTTP :7070     │                    │      │  REST :8080       │
└────────┬────────┘                    │      └─────────┬─────────┘
         │ 1 Hz HTTP poll              │                │ push 8 fields
         │                             ▼                ▼
         │                   ┌─────────────────────────────────┐
         │                   │     Map Simulator (Registry)    │
         │                   │  REST :8090 + Web Map :8090     │
         │                   └────────────────┬────────────────┘
         │                                    │ 10 Hz poll
         │                                    ▼
         │                          ┌──────────────────┐
         │                          │ EchoShield Sim   │
         │                          │ TCP NDJSON :9000 │
         │                          └─────────┬────────┘
         │                                    │
         ▼                                    ▼
┌─────────────────────────────────────────────────────────┐
│          CoT Gateway  (correlator + emitter)            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Echodyne     │  │  Track       │  │ MIL-STD-2525C│  │
│  │ Adapter      │─▶│  Correlator  │─▶│ XML Generator│  │
│  └──────────────┘  └──────────────┘  └──────┬───────┘  │
│  ┌──────────────┐         ▲          Web Map :8092 │    │
│  │ Sentrycs     │─────────┘                 │      │    │
│  │ Adapter      │                           ▼      │    │
│  └──────────────┘                  TCP :8089       │    │
└──────────────────────────────────────────┬──────────────┘
                                           │
                    ┌──────────────────────┴──────────────────┐
                    ▼                                         ▼
           ┌────────────────┐                   ┌─────────────────────────┐
           │   TAK Relay    │                   │     TAK Client Sim      │
           │ scripts/tak_   │──── CoT push ────▶│  console + Web Map      │
           │ relay.py :8089 │                   │  :8093  MIL-STD-2525C   │
           └────────────────┘                   └─────────────────────────┘
```

| 服務 | 路徑 | 角色 | 預設 Port |
|------|------|------|-----------|
| **UDS** (Unified Drone Simulator) | `services/uds/` | 無人機飛行模擬 + 接管閉環 | REST `:8080` |
| **Map Sim** | `services/map-sim/` | 物件狀態中央登錄表 + TTL；Web Map `:8090/objects` | REST `:8090` |
| **EchoShield Sim** | `services/echoshield-sim/` | 雷達 4D 模擬 + 噪點 | TCP NDJSON `:9000` |
| **Sentrycs Sim** | `services/sentrycs-sim/` | RF C-UAS 反制設備模擬 | HTTP JSON `:7070` |
| **CoT Gateway** | `services/cot-gateway/` | 雷達/RF 融合 + CoT XML 推送；**Web Map** `:8092/map` | → TAK `:8089` |
| **TAK Client Sim** | `services/tak-client-sim/` | CoT 接收驗證 + **Web Map** `:8093/map`（MIL-STD-2525C icons） | TCP `:8089` |

---

## 2. 快速開始

### 環境需求

- Python 3.11+（目前以 3.12 開發測試）
- Linux / macOS（bash 5.x+）
- 約 100 MB 磁碟空間（含 Python 依賴）

### 安裝依賴

每個服務有獨立 `pyproject.toml`，共享的 TAK 連線程式庫位於 `libs/tak-connection/`：

```bash
pip install -e "libs/tak-connection[dev]" --break-system-packages
for svc in uds map-sim echoshield-sim sentrycs-sim cot-gateway tak-client-sim; do
  pip install -e "services/${svc}[dev]" --break-system-packages
done
```

> macOS / 系統 Python 受 PEP 668 限制時請加 `--break-system-packages`，或先建立 `python3 -m venv .venv && source .venv/bin/activate`。

### Demo 一鍵啟動（推薦）

最快的方式是使用 demo 腳本，可自動啟動全部 7 個服務並開啟三個瀏覽器視窗：

```bash
# 安裝共享 TAK 連線庫與所有服務（一次即可）
pip install -e "libs/tak-connection[dev]" --break-system-packages
for svc in uds map-sim echoshield-sim sentrycs-sim cot-gateway tak-client-sim; do
  pip install -e "services/${svc}[dev]" --break-system-packages
done

# 單機無人機情境 demo（1 架無人機）
scripts/demo-1drone.sh

# 三機無人機情境 demo（3 架無人機）
scripts/demo-3drone.sh

# 停止所有服務
scripts/demo-1drone.sh --stop
scripts/demo-3drone.sh --stop
```

Demo 腳本會依序啟動 7 個服務（map-sim → uds → echoshield-sim → sentrycs-sim → cot-gateway → tak-relay → tak-client-sim），完成 health-check 後自動開啟三個 Web Map Viewer：

| Web Map | URL | 內容 |
|---------|-----|------|
| **Map Sim** | `http://127.0.0.1:8090/map` | 原始無人機位置（UDS 推送） |
| **CoT Gateway** | `http://127.0.0.1:8092/map` | EchoShield + Sentrycs 融合 CoT 戰術地圖 |
| **TAK Client Sim** | `http://127.0.0.1:8093/map` | TAK relay 收到的 CoT XML（MIL-STD-2525C 圖示） |

### Remote TAK Server

若要改接正式 TAK Server，不再需要設定 `TAK_HOST` / `TAK_PORT` / `TAK_USE_SSL` 環境變數：

1. 編輯 repo root 的 `config/remote-tak.yaml`
2. 將憑證放到 `config/certs/gateway.p12`（需要 CA 驗證時再加入 `config/certs/ca-bundle.pem`）
3. 執行 `scripts/demo-1drone-remote-tak.sh` 或 `scripts/demo-3drone-remote-tak.sh`

更完整的操作範例請見 [`specs/016-tak-shared-connection/quickstart.md`](specs/016-tak-shared-connection/quickstart.md)。

### 開發用多服務啟動

```bash
scripts/dev-launcher.sh                  # 啟動全部 6 個服務（預設 ports）
scripts/dev-launcher.sh --help           # 看完整選項
```

啟動後：
- 日誌輸出至 `.dev-runtime/logs/<service>.log`
- PID 寫入 `.dev-runtime/pids/<service>.pid`
- Ctrl-C 觸發優雅關閉（SIGTERM 5s 寬限 → SIGKILL）

### 部分啟動 / 自訂 port / 跨主機部署

```bash
# 只啟動 Map Sim 與 UDS
scripts/dev-launcher.sh --services map-sim,uds

# 自訂 port（例如 8080 已被佔用）
scripts/dev-launcher.sh --uds-port 18080 --map-sim-port 18090

# Gateway 連到遠端的 EchoShield 與 TAK Server
scripts/dev-launcher.sh --services cot-gateway \
  --gateway-echoshield-host 10.0.0.5 \
  --gateway-tak-host tak.example.com --gateway-tak-port 8089

# 啟用 TAK SSL 上傳（搭配 infra/tak-server 內建 stub 或正式 TAK Server）
scripts/gen-certs.sh                                   # 產生 PoC 自簽 PKI
( cd infra/tak-server && docker compose up -d )        # 啟動 stub
scripts/dev-launcher.sh --services cot-gateway \
  --tak-host localhost --tak-port 8089 --tak-use-ssl

# 完整跨服務 URL 覆寫
scripts/dev-launcher.sh \
  --uds-map-sim-url   http://map-host:8090 \
  --sentrycs-uds-url  http://uds-host:8080 \
  --echoshield-map-sim-url http://map-host:8090
```

### 端對端冒煙驗證

```bash
# 1. 啟動所有服務（另開一個終端機）
scripts/dev-launcher.sh

# 2. 確認 Map Sim 持續收到 UDS 推送
curl http://localhost:8090/objects

# 3. 確認 Sentrycs 偵測有資料
curl http://localhost:7070/detections

# 4. 觀察 EchoShield TCP feed
nc localhost 9000   # 每 100ms 一行 NDJSON

# 5. 觀察 Gateway 推送至 TAK（無 TAK 時 Gateway 會自動退避重試）
tail -f .dev-runtime/logs/cot-gateway.log
```

### E2E 情境驗證（不需要 ATAK）

Feature 007 提供兩個端對端模擬情境，用於驗證整條鏈路。搭配 `tak-client-sim` Web Map Viewer 即可在瀏覽器上觀察 CoT 推送結果（不需安裝 ATAK）。

```bash
# 推薦：使用 demo 腳本自動啟動並開啟 3 個 web map（見上方 Demo 一鍵啟動）
scripts/demo-1drone.sh    # 單機情境
scripts/demo-3drone.sh    # 三機情境

# 或手動指定情境 YAML：
# Scenario 1 — 單架無人機（TRK-E01，15 m/s，從正北 5 km 逼近）
scripts/dev-launcher.sh \
  --uds-scenario services/uds/scenarios/e2e_single_drone.yaml \
  --sentrycs-scenario services/sentrycs-sim/config/e2e_single_drone.yaml \
  --echoshield-config services/echoshield-sim/config/e2e_scenario.yaml

# Scenario 2 — 三架無人機（TRK-E0A/B/C，12 m/s，交錯 0/30/60 s 起飛）
scripts/dev-launcher.sh \
  --uds-scenario services/uds/scenarios/e2e_multi_drone.yaml \
  --sentrycs-scenario services/sentrycs-sim/config/e2e_multi_drone.yaml \
  --echoshield-config services/echoshield-sim/config/e2e_scenario.yaml

# 離線驗證 YAML 文件格式
python3 specs/007-scenario/scripts/validate_scenario.py \
  --uds   services/uds/scenarios/e2e_single_drone.yaml \
  --sntr  services/sentrycs-sim/config/e2e_single_drone.yaml \
  --echo  services/echoshield-sim/config/e2e_scenario.yaml

# 驗證 CoT XML 串流（從 tak-client-sim 導出後驗證）
python3 specs/007-scenario/scripts/validate_cot.py --file /tmp/cot_capture.ndjson
```

詳見 [`dev-docs/007-scenario.md`](dev-docs/007-scenario.md) 與 [`specs/007-scenario/quickstart.md`](specs/007-scenario/quickstart.md)。

---

### Web Map Viewers

所有三個 Web Map Viewer 使用 Leaflet.js，支援即時 CoT 追蹤、戰術圖示與互動式 popup：

| Map | URL | CoT 資料來源 | 圖示樣式 |
|-----|-----|-------------|---------|
| **Map Sim** | `http://127.0.0.1:8090/objects` | UDS 推送（原始位置） | 文字清單 |
| **CoT Gateway** | `http://127.0.0.1:8092/map` | EchoShield + Sentrycs 融合 | MIL-STD-2525C |
| **TAK Client Sim** | `http://127.0.0.1:8093/map` | TAK relay CoT XML | MIL-STD-2525C |

CoT 圖示對照：
- `a-h-*`（敵方／融合）→ 🔴 紅色旋轉菱形 + 方向箭頭
- `a-u-*`（未知／單源）→ ⬜ 灰色圓圈 + 對角十字 + 方向箭頭
- Stale → 淡化版本（opacity 0.45）

---

倉庫附帶輕量 TAK Server stub（asyncio TLS CoT collector），無需 TAK.gov 帳號即可端對端測試：

```bash
# 1. 產生 PoC 自簽 PKI（CA + 伺服器憑證 + Gateway p12）
scripts/gen-certs.sh

# 2. 啟動 stub（profile=stub 為預設）
( cd infra/tak-server && docker compose up -d )

# 3. Gateway 啟用 SSL 上傳
scripts/dev-launcher.sh --services cot-gateway \
  --tak-host localhost --tak-port 8089 --tak-use-ssl

# 4. 觀察 stub 收到的 CoT
docker compose -f infra/tak-server/docker-compose.yaml logs -f tak-server-stub
```

切換到正式 TAK Server：替換 `infra/certs/` 內的憑證（檔名相同），開啟 `docker-compose.yaml`
中註解的 `tak-server` / `tak-db` 服務並設定 `TAK_IMAGE`，詳見
[`docs/tak-server-deployment.md`](./docs/tak-server-deployment.md)。

---

## 3. 開發者指南

### 倉庫結構

```
cics-tak-demo/
├── README.md                 ← 本檔
├── AGENTS.md                 ← AI agent 開發守則
├── docs/system-docs/         ← 規格權威文件 v0.6（10 份）
├── specs/                    ← Speckit 各 feature artifacts
│   ├── 001-uds/              ← spec.md / plan.md / tasks.md / contracts/ ...
│   ├── 002-map-sim/
│   ├── 003-echoshield-sim/
│   ├── 004-sentrycs-sim/
│   ├── 005-cot-gateway/
│   ├── 006-006-tak-client-sim/
│   ├── 007-scenario/         ← E2E 情境 + scripts/validate_*.py
│   ├── 010-perimeter-defense/
│   ├── 011-cot-gw-perimeter/
│   ├── 012-track-update-fix/
│   └── 013-tak-client-sim-webmap/ ← Web Map Viewer + Demo Scripts
├── dev-docs/                 ← 各 feature 開發完成紀錄
│   ├── 001-uds.md
│   ├── 002-map-sim.md
│   ├── 003-echoshield-sim.md
│   ├── 004-sentrycs-sim.md
│   ├── 005-cot-gateway.md
│   ├── 006-tak-client-sim.md
│   ├── 007-scenario.md
│   ├── ...
│   └── 013-tak-client-sim-webmap.md
├── services/                 ← 六個獨立 Python 服務
│   ├── uds/
│   ├── map-sim/
│   ├── echoshield-sim/
│   │   └── config/           ← e2e_scenario.yaml / demo.yaml
│   ├── sentrycs-sim/
│   │   └── config/           ← e2e_single_drone.yaml / e2e_multi_drone.yaml / demo.yaml
│   ├── cot-gateway/
│   │   └── ...               ← Web Map Viewer :8092/map
│   └── tak-client-sim/
│       └── ...               ← CoT 接收 + console + Web Map :8093/map（MIL-STD-2525C）
├── scripts/
│   ├── dev-launcher.sh       ← 多服務啟動腳本（含 --echoshield-config）
│   ├── demo-1drone.sh        ← 單機無人機 demo（7 服務 + 3 browser tabs）
│   ├── demo-3drone.sh        ← 三機無人機 demo（7 服務 + 3 browser tabs）
│   ├── tak_relay.py          ← TAK plaintext TCP broadcast relay（demo 用）
│   └── gen-certs.sh          ← 自簽 PKI 產生工具
└── .specify/                 ← Speckit 工具與模板
```

每個 `services/<name>/` 統一布局：

```
services/<name>/
├── pyproject.toml
├── README.md
├── config/                   ← 預設 YAML（部分服務）
├── scripts/smoke.sh
├── src/<module>/
│   ├── __main__.py  cli.py  config.py  logging.py  loop.py
│   ├── models/    *.py
│   └── ...
└── tests/
    ├── contract/             ← wire 契約凍結測試
    ├── unit/
    └── integration/
```

### 跑測試

```bash
# 單一服務
( cd services/cot-gateway && python3 -m pytest -q )

# 全部服務
for svc in uds map-sim echoshield-sim sentrycs-sim cot-gateway tak-client-sim; do
  ( cd "services/${svc}" && python3 -m pytest -q ) || exit 1
done

# 情境驗證腳本
python3 -m pytest specs/007-scenario/scripts/ -q
```

當前測試總計：**659 pass**（服務 628 + 情境驗證 31）

| Service | Tests |
|---------|-------|
| UDS | 83 |
| Map Sim | 107 |
| EchoShield Sim | 74 |
| Sentrycs Sim | 117 |
| CoT Gateway | 149 |
| TAK Client Sim | 98 |
| 情境驗證腳本 | 31 |

### Lint

每個服務皆通過 `ruff` + `black --check`。

```bash
ruff check services/
black --check services/
```

---

## 4. 設計決策（凍結契約）

> 詳細決策見每個 feature 的 `dev-docs/00X-*.md`，以下僅列跨服務契約凍結點。

### 4.1 UDS → Map Sim push（8 欄位）

```json
{
  "drone_id": "TRK-001",
  "lat": 25.0345, "lon": 121.5670, "alt_m": 152.4,
  "speed_ms": 18.7, "heading_deg": 85.3,
  "status": "FLYING_NORMAL",
  "timestamp": "2026-04-28T01:42:41.123Z"
}
```

**不包含** `model` 與 `operator_lat/lon`（那是 Sentrycs 的職責）。

### 4.2 Map Sim GET /objects 回應

`status` 永遠保留原始 FlightState；TTL 過期狀態以獨立 `is_lost: bool` 表達，**不**覆寫 `status`。

### 4.3 UDS POST /command/takeover

```json
{ "drone_id": "TRK-001", "target_lat": 25.05, "target_lon": 121.57, "target_alt_m": 0.0 }
```

回應：200（成功）/ 400（參數錯誤）/ 404（drone 不存在）/ 409（已被接管，視為成功）。

### 4.4 EchoShield TCP feed（NDJSON）

`track_status ∈ {"Active", "Lost"}`；2 秒 grace window 內 drone_id 重現沿用 `track_id`。

### 4.5 Sentrycs HTTP /detections

每筆 14 欄位含 `model`、`operator_lat/lon`、`status ∈ {DETECTED, MITIGATING, NEUTRALIZED}`；NEUTRALIZED 保留 30s 後移除。

### 4.6 CoT Gateway uid 命名

- 融合成功：`FUSED-{sentrycs_drone_id}` → `a-h-A-M-F-Q-r`（紅色）
- 只有雷達：`ECHO-{radar_track_id}` → `a-u-A-M-F-Q-r`（灰色）
- 只有 RF：`SENTRYCS-{drone_id}` → `a-u-A-M-F-Q-r`（灰色）
- Source 切換：對舊 uid 發 `stale=now` 清場，對新 uid 發首筆

### 4.7 CoT stale 政策

- `Lost`：`stale = time`（立即老化）
- `NEUTRALIZED`：`stale = time + 30s`
- 其他：`stale = time + 11s`

---

## 5. 開發流程（Speckit）

每個 feature 完整跑過：

```
Specify → Clarify → Plan → Tasks → Analyze → Implement → Test → Docs → Merge
```

artifacts 落於 `specs/00X-*/`，開發紀錄落於 `dev-docs/00X-*.md`。
分支策略：`feature/00X-*` 自 `develop` 分出，以 `--no-ff` 合回 `develop` 保留歷史。

詳細守則見 [`AGENTS.md`](./AGENTS.md)。

---

## 6. 已知遺留 / 未來工作

- **TAK Server**：`infra/tak-server/` 提供 PoC stub（asyncio TLS CoT collector）+ 自簽 PKI；
  生產環境改用 TAK.gov 提供的官方 image，cert 檔名相容（見 [`docs/tak-server-deployment.md`](./docs/tak-server-deployment.md)）
- **多主機部署**：launcher 已支援跨主機 URL 覆寫與 TAK 憑證注入，但缺 k8s manifests
- **真實 TAK Server 整合測試**：目前僅以 PoC stub 驗證；待官方 image 在實驗環境上線後補齊
- **效能基線**：各服務 SC 已含 p95 < 100ms / 吞吐目標，但缺多服務聯合壓測
- **Constitution**：`.specify/memory/constitution.md` 仍為 placeholder，沿用 PoC 自律準則 G1–G7

---

## 7. 文件導引

- 規格權威：[`docs/system-docs/00-index.md`](docs/system-docs/00-index.md)
- 各 feature spec：[`specs/00X-*/spec.md`](specs/)
- 各 feature 開發紀錄：[`dev-docs/`](dev-docs/)
- E2E 情境快速入門：[`specs/007-scenario/quickstart.md`](specs/007-scenario/quickstart.md)
- AI agent 守則：[`AGENTS.md`](AGENTS.md)

---

## License

Internal PoC — proprietary. Distribution restricted to project stakeholders.
