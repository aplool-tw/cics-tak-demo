# Quickstart — Map Simulator

本文件涵蓋 Map Sim 的安裝、啟動、手動驗證（curl）、測試指令。對應 spec.md User Stories 的獨立測試
路徑。所有操作均假設工作目錄在 repo root。

---

## 1. 安裝

```bash
cd services/map-sim

# 建議 Python 3.11+ 的 virtualenv
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 正式依賴 + dev 工具
pip install -e ".[dev]"
```

預期安裝後可執行：
```bash
map-sim --help
# 或
python -m map_sim --help
```

---

## 2. 啟動

### 2.1 預設啟動（PoC 對齊）

```bash
# 綁 127.0.0.1:18090；ttl_warn_s=5.0；ttl_remove_s=10.0
map-sim
```

啟動後 log（structlog JSON）：
```json
{"event": "server.started", "port": 8090, "ttl_warn_s": 5.0, "ttl_remove_s": 10.0}
```

### 2.2 CLI 參數

```bash
map-sim \
  --port 8090 \
  --ttl-warn-s 5.0 \
  --ttl-remove-s 10.0 \
  --verbose
```

| 參數 | 預設 | 說明 |
|------|------|------|
| `--port` | `8090` | HTTP server 監聽 port（綁 `127.0.0.1`）|
| `--ttl-warn-s` | `5.0` | 物件逾此秒數未更新 → `is_lost=true`；預設查詢不回傳 |
| `--ttl-remove-s` | `10.0` | 物件逾此秒數未更新 → 從 registry 移除；必須 `>= ttl-warn-s` |
| `--verbose` | `false` | log level 切至 DEBUG（預設 INFO）|

短 TTL 測試（用於手動驗證 TTL 生命週期）：
```bash
map-sim --ttl-warn-s 1.0 --ttl-remove-s 2.0 --verbose
```

### 2.3 停止

`Ctrl+C`（SIGINT）；server 會在 aiohttp `on_cleanup` 中 cancel 背景 TTL task，乾淨退出。

---

## 3. 手動驗證（curl 範例）

假設 server 跑在 `http://127.0.0.1:18090`。

### 3.1 推送無人機狀態（User Story 1）

```bash
# (1) 合法 8 欄位 payload
curl -sS -X POST http://127.0.0.1:18090/objects/update \
  -H 'Content-Type: application/json' \
  -d '{
    "drone_id": "TRK-001",
    "lat": 25.0584745,
    "lon": 121.5654089,
    "alt_m": 100.8,
    "speed_ms": 15.1,
    "heading_deg": 180.2,
    "status": "FLYING_NORMAL",
    "timestamp": "2026-04-22T08:00:01.000Z"
  }'
# → 200 {"status":"updated","drone_id":"TRK-001","registered_at":"..."}

# (2) 多餘欄位（Sentrycs 專屬）— MUST 仍 200
curl -sS -X POST http://127.0.0.1:18090/objects/update \
  -H 'Content-Type: application/json' \
  -d '{
    "drone_id": "TRK-002",
    "lat": 25.0410, "lon": 121.5800, "alt_m": 150.0,
    "speed_ms": 18.0, "heading_deg": 270.0,
    "status": "FLYING_NORMAL",
    "timestamp": "2026-04-22T08:00:01.000Z",
    "model": "DJI Mavic 3",
    "operator_lat": 25.0310,
    "operator_lon": 121.5634
  }'
# → 200（額外欄位被靜默忽略）

# (3) 缺必填 — 400
curl -sS -X POST http://127.0.0.1:18090/objects/update \
  -H 'Content-Type: application/json' \
  -d '{"drone_id": "TRK-003", "lat": 25.0}'
# → 400 {"status":"error","reason":"missing required field: lon"}
```

### 3.2 地理範圍查詢（User Story 2）

```bash
# (1) Radar 半徑 4800 m 查詢
curl -sS 'http://127.0.0.1:18090/objects?lat=25.0330&lon=121.5654&radius_m=4800'
# → 200；objects[] 依 distance_m 升冪；各含 is_lost=false

# (2) Sentrycs 半徑 8000 m + include_lost
curl -sS 'http://127.0.0.1:18090/objects?lat=25.0330&lon=121.5654&radius_m=8000&include_lost=true'

# (3) 範圍內無物件 — 200 count=0
curl -sS 'http://127.0.0.1:18090/objects?lat=0&lon=0&radius_m=1000'
# → 200 {"query":{...},"count":0,"objects":[]}

# (4) 缺參數 — 400
curl -sS 'http://127.0.0.1:18090/objects?lat=25.0&lon=121.5'
# → 400 {"status":"error","reason":"missing required parameter: radius_m"}

# (5) radius_m = 0 — 400
curl -sS 'http://127.0.0.1:18090/objects?lat=25.0&lon=121.5&radius_m=0'
# → 400 {"status":"error","reason":"radius_m must be > 0"}
```

### 3.3 TTL 生命週期（User Story 3；建議使用短 TTL）

```bash
# 在另一 terminal 啟動 map-sim --ttl-warn-s 1 --ttl-remove-s 2 --verbose

# t=0：推送 TRK-099
curl -sS -X POST http://127.0.0.1:18090/objects/update \
  -H 'Content-Type: application/json' \
  -d '{"drone_id":"TRK-099","lat":25.0,"lon":121.5,"alt_m":100,"speed_ms":10,
       "heading_deg":0,"status":"FLYING_NORMAL","timestamp":"2026-04-22T08:00:00Z"}'

# t≈0.5s：仍 active
curl -sS 'http://127.0.0.1:18090/objects/all' | jq
# → {"total":1,"active":1,"lost":0,...}

# t≈1.5s：is_lost=true，預設查詢看不到
sleep 1
curl -sS 'http://127.0.0.1:18090/objects?lat=25.0&lon=121.5&radius_m=5000' | jq
# → count=0
curl -sS 'http://127.0.0.1:18090/objects?lat=25.0&lon=121.5&radius_m=5000&include_lost=true' | jq
# → count=1；objects[0].status="FLYING_NORMAL"（原值未覆寫）；is_lost=true

# t≈3s：已從 registry 移除（cleanup 週期 2 s）
sleep 2
curl -sS 'http://127.0.0.1:18090/objects/all' | jq
# → {"total":0,...}
```

### 3.4 健康檢查

```bash
curl -sS http://127.0.0.1:18090/health | jq
# → {"status":"ok","registered_objects":N,"uptime_s":123.4}
```

### 3.5 手動移除（除錯）

```bash
curl -sS -X DELETE http://127.0.0.1:18090/objects/TRK-001
# → 200 {"status":"removed","drone_id":"TRK-001"}（或 "not_found"）
```

---

## 4. 與 UDS 端到端整合

建議啟動順序（對齊 spec §6 與 `03-map-simulator-spec.md` §6.2）：

```bash
# Terminal 1: Map Sim 先啟動
cd services/map-sim && map-sim --port 8090

# Terminal 2: UDS 啟動並指向 Map Sim
cd services/uds && uds \
  --scenario scenarios/single_drone_invasion.yaml \
  --map-sim-url http://127.0.0.1:18090

# Terminal 3: 以 curl 查詢（模擬 EchoShield / Sentrycs）
watch -n 1 'curl -sS "http://127.0.0.1:18090/objects?lat=25.0330&lon=121.5654&radius_m=4800" | jq .count'
```

預期：UDS 每 100 ms 對每架 drone 推一筆；Map Sim 的 `GET /objects/all` 的 `total` 應等於 UDS 場景中
`flight_state != IDLE` 的 drone 數。

---

## 5. 測試指令

### 5.1 全部測試

```bash
cd services/map-sim
pytest
```

`pytest.ini_options` 預設 `asyncio_mode = "auto"`，無需在測試函式前加 `@pytest.mark.asyncio`。

### 5.2 分類執行

```bash
# 契約測試（三個正式端點）
pytest tests/contract/ -v

# 整合測試（TTL 時序、併發安全）
pytest tests/integration/ -v

# 單元測試（Haversine、DroneObject、ObjectRegistry）
pytest tests/unit/ -v

# 單一測試
pytest tests/contract/test_update_contract.py::test_accepts_extra_sentrycs_fields -v
```

### 5.3 TTL 時序測試（freezegun）

TTL 測試使用 `freezegun` 推進虛擬時鐘，**不**依賴 `asyncio.sleep`；CI 可穩定重現。範例（示意）：

```python
# tests/integration/test_ttl_lifecycle.py（示意）
from freezegun import freeze_time

async def test_is_lost_after_warn_ttl(registry):
    with freeze_time("2026-04-22T08:00:00Z") as frozen:
        await registry.update("TRK-001", ...)       # t=0
        frozen.tick(6.0)                            # t=6s (> ttl_warn_s=5)
        results = await registry.query_radius(..., include_lost=True)
        assert len(results) == 1
        obj, _ = results[0]
        assert obj.status == "FLYING_NORMAL"        # 原值未覆寫
        assert obj.is_lost(registry.ttl_warn_s) is True
```

### 5.4 Lint / Format（與 uds 對齊）

```bash
ruff check src tests
black --check src tests
```

### 5.5 Success Criteria 對應

| Success Criterion | 驗證位置 |
|-------------------|---------|
| SC-MS-001 (吞吐) | `tests/integration/test_concurrent_safety.py`（100 req/s × 10s）|
| SC-MS-002 (延遲) | 手動 benchmark（`wrk` / `ab`）|
| SC-MS-003 / SC-MS-004 (TTL 精度) | `tests/integration/test_ttl_lifecycle.py` |
| SC-MS-005 (查詢正確性) | `tests/unit/test_haversine.py` + `tests/contract/test_query_contract.py` |
| SC-MS-006 (併發安全) | `tests/integration/test_concurrent_safety.py` |
| SC-MS-009 (LANDED 可見性) | `tests/integration/test_ttl_lifecycle.py`（`status="LANDED"` 情境）|

---

## 6. 故障排除

| 現象 | 可能原因 | 檢查 |
|------|---------|------|
| `POST /objects/update` 一直回 `missing required field: <name>` | request body 拼錯欄位名 | 檢查是否為 8 欄位名稱（`speed_ms` 而非 `velocity_ms`；見 `specs/001-uds/contracts/rest-api.md` §3.2 註）|
| `GET /objects` 回 `count=0` 但 `/objects/all` 有物件 | 物件 `is_lost=true` 而未帶 `include_lost=true` | 確認 `last_seen_s`；或檢查 `radius_m` 是否太小 |
| 啟動即 crash `ttl_remove_s must be >= ttl_warn_s > 0` | CLI 參數順序錯 | 確認 `--ttl-warn-s <= --ttl-remove-s` |
| `aiohttp` Port 被佔用 | 已有 Map Sim 在跑或其他服務佔用 8090 | `lsof -i :18090`；或 `--port 8091` |
