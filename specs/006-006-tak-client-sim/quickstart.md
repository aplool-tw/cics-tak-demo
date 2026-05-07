# Quickstart: TAK Client Simulator

**Feature**: 006-006-tak-client-sim  
**Date**: 2026-04-29

---

## 前置需求

- Python 3.11+ （建議 3.12）
- `pip`（或 `pip3`）
- TAK Server 已在 `:18089` 執行（或使用下方 stub 進行本機測試）

---

## 1. 安裝（開發模式）

```bash
cd services/tak-client-sim
pip install -e ".[dev]" --break-system-packages
```

依賴清單（`pyproject.toml`）：

| 依賴 | 用途 |
|------|------|
| `pydantic>=2.6` | `ClientConfig` 驗證 |
| `structlog>=24.1` | JSON 日誌 |
| `pyyaml` | `--config` YAML 載入（選配） |
| `pytest>=8.0` | 測試框架 |
| `pytest-asyncio>=0.23` | asyncio 測試支援 |
| `freezegun>=1.4` | 時間 mock（重連 delay 測試） |
| `ruff>=0.4` | Lint |
| `black>=24.3` | 格式化 |

---

## 2. 基本啟動

### 2.1 PoC 模式（跳過 SSL 驗證）

```bash
# 連線至本機 TAK Server（PoC 模式，不驗證憑證）
python -m tak_client_sim --host localhost --port 8089 --no-ssl-verify
```

### 2.2 只顯示特定來源

```bash
# 只顯示 FUSED 來源的事件
python -m tak_client_sim --host tak-server --port 8089 --no-ssl-verify --filter FUSED
```

### 2.3 同時寫入 log 檔

```bash
python -m tak_client_sim \
  --host tak-server \
  --port 8089 \
  --no-ssl-verify \
  --filter ECHO \
  --log-file /tmp/tak-client.jsonl
```

### 2.4 使用 YAML 設定檔

```bash
# 建立設定檔
cat > tak-client-sim.yaml << 'EOF'
host: tak-server
port: 8089
use_ssl_verify: false
filter_prefix: null
log_file: /tmp/tak.jsonl
max_retries: 10
backoff_initial_s: 1.0
backoff_cap_s: 60.0
EOF

python -m tak_client_sim --config tak-client-sim.yaml

# CLI 參數優先於 YAML（覆寫 filter）
python -m tak_client_sim --config tak-client-sim.yaml --filter FUSED
```

### 2.5 設定最大重試次數

```bash
# 最多重試 5 次（預設 0 = 無限重試）
python -m tak_client_sim --host tak-server --port 8089 --no-ssl-verify --max-retries 5
```

---

## 3. Console 輸出格式

成功接收並解析 CoT 後，stdout 輸出一行：

```
[2026-04-29T11:00:00.123Z] [ECHO][GREY] ECHO-TRK-001  25.060000/121.565400  101.0m  12.5m/s  045°  delta_s=+11  Source: ECHOSHIELD | Speed: 12.5m/s | Alt: 101m
```

若 stale 比接收當下早 >30 秒，行首附加 `[STALE]`：

```
[STALE] [2026-04-29T11:00:00.123Z] [ECHO][GREY] ECHO-TRK-001  ...
```

---

## 4. 結構化日誌

所有 lifecycle events 輸出至 stderr（JSON 格式），`--log-file` 同步寫入檔案。

```bash
# 觀察 structlog JSON（stderr）
python -m tak_client_sim --no-ssl-verify 2>&1 | grep '"event"'

# 只保留 structlog，console 分流
python -m tak_client_sim --no-ssl-verify \
  > /tmp/console.txt \
  2> /tmp/events.jsonl
```

典型輸出：

```json
{"event": "tak_connected", "host": "tak-server", "port": 8089, "timestamp": "2026-04-29T11:00:00.000Z", "level": "info"}
{"event": "cot_received", "uid": "ECHO-TRK-001", "source": "ECHO", "color": "GREY", "type": "a-u-A-M-F-Q-r", "lat": 25.06, "lon": 121.5654, "hae": 101.0, "delta_s": 11, "speed": 12.5, "course": 45.0, "remarks": "Source: ECHOSHIELD | Speed: 12.5m/s | Alt: 101m", "filtered": false, "timestamp": "2026-04-29T11:00:00.123Z", "level": "info"}
{"event": "session_summary", "total_received": 42, "total_filtered": 0, "total_parse_errors": 0, "reconnect_count": 0, "per_source": {"ECHO": 42}, "timestamp": "2026-04-29T11:00:30.456Z", "level": "info"}
```

---

## 5. 優雅關閉

按 `Ctrl-C` 觸發 SIGINT，服務完成當前事件處理後：

1. 關閉 SSL socket
2. 列印統計摘要至 stdout：

```
=== Session Summary ===
Total received:    42
Total filtered:     0
Parse errors:       0
Oversized dropped:  0
Reconnect count:    0
Per source: ECHO=42
========================
```

3. 寫入 `session_summary` JSON 至 structlog
4. 以 exit code 0 結束

---

## 6. 本機測試（無 TAK Server）

### 6.1 啟動 TCP Stub Server

```bash
# Python 一行建立 stub（發送假 CoT 並接受連線）
python3 - << 'EOF'
import asyncio, ssl

COT_SAMPLES = [
    '<event version="2.0" uid="ECHO-TRK-001" type="a-u-A-M-F-Q-r" time="2026-04-29T11:00:00.000Z" start="2026-04-29T11:00:00.000Z" stale="2026-04-29T11:00:11.000Z" how="m-g"><point lat="25.06" lon="121.5654" hae="101.0" ce="10.0" le="5.0"/><detail><contact callsign="ECHO-TRK-001"/><remarks>Source: ECHOSHIELD | Speed: 12.5m/s | Alt: 101m</remarks><track speed="12.5" course="45.0"/></detail></event>',
    '<event version="2.0" uid="FUSED-DRN-001" type="a-h-A-M-F-Q-r" time="2026-04-29T11:00:01.000Z" start="2026-04-29T11:00:01.000Z" stale="2026-04-29T11:00:12.000Z" how="m-g"><point lat="25.06" lon="121.5655" hae="95.0" ce="10.0" le="5.0"/><detail><contact callsign="FUSED-DRN-001"/><remarks>Source: FUSED | Status: DETECTED | Speed: 3.2m/s | Alt: 95m</remarks><track speed="3.2" course="180.0"/></detail></event>',
]

async def handle(reader, writer):
    for cot in COT_SAMPLES:
        writer.write((cot + "\n").encode())
        await writer.drain()
        await asyncio.sleep(1)
    writer.close()

async def main():
    server = await asyncio.start_server(handle, "127.0.0.1", 8089)
    print("Stub server on :18089 (no SSL)")
    async with server:
        await server.serve_forever()

asyncio.run(main())
EOF
```

### 6.2 連線至 Stub

```bash
# 另開 terminal（stub 無 SSL）
python -m tak_client_sim --host 127.0.0.1 --port 8089 --no-ssl-verify
```

---

## 7. 執行測試

### 7.1 全部測試

```bash
cd services/tak-client-sim
python -m pytest -q
```

### 7.2 只跑 contract test（8 場景）

```bash
python -m pytest tests/contract/ -v
```

### 7.3 只跑 unit test

```bash
python -m pytest tests/unit/ -v
```

### 7.4 只跑 integration test

```bash
python -m pytest tests/integration/ -v
```

---

## 8. Lint 與格式化

```bash
cd services/tak-client-sim

# Lint 檢查
ruff check .

# 格式化檢查
black --check src tests

# 自動格式化
black src tests

# CI 等價指令（須全部通過才能進 Merge）
ruff check . && black --check src tests && python -m pytest -q
```

---

## 9. Smoke Test

```bash
# 啟動 stub 後執行 smoke test
bash scripts/smoke.sh
```

`smoke.sh` 步驟：
1. 在背景啟動 stub TCP server
2. 啟動 `tak-client-sim --log-file /tmp/smoke.jsonl --no-ssl-verify`（背景）
3. 等待 5 秒
4. 發送 SIGINT
5. 檢查 `/tmp/smoke.jsonl` 含 ≥2 筆 `cot_received` 與 1 筆 `session_summary`
6. 印出 PASS / FAIL

---

## 10. 常見問題

### Q: 連線失敗時如何調試？

```bash
# 查看 structlog 中的 reconnecting / tak_disconnected 事件
python -m tak_client_sim --no-ssl-verify 2>&1 | python -m json.tool
```

### Q: 如何確認 --filter 生效？

```bash
# console 應只顯示 FUSED；stderr 含全部（含 filtered=true）
python -m tak_client_sim --no-ssl-verify --filter FUSED 2>&1 | grep '"filtered":true'
```

### Q: log-file 路徑無寫入權限？

服務啟動時即 fail-fast（exit code 2）：

```
Config error: log_file path '/root/tak.jsonl' is not writable
```

### Q: YAML 設定有多餘欄位？

```
Config error: 1 validation error for ClientConfig
extra_field
  Extra inputs are not permitted [type=extra_forbidden, ...]
```

---

## 11. 目錄結構

```
services/tak-client-sim/
├── src/
│   └── tak_client_sim/
│       ├── __init__.py
│       ├── __main__.py       # python -m tak_client_sim 入口
│       ├── config.py         # ClientConfig (pydantic v2) + YAML/CLI 載入
│       ├── models.py         # CotEvent (frozen dataclass) + ConnectionStats
│       ├── connection.py     # TakConnection: TCP+SSL + readuntil + 重連
│       ├── parser.py         # parse_cot_xml() → CotEvent | None
│       ├── formatter.py      # format_event() + print_event()
│       └── runner.py         # main(): receive_loop + signal + shutdown
├── tests/
│   ├── contract/
│   │   └── test_tak_downlink.py   # 8 場景契約測試
│   ├── unit/
│   │   ├── test_parser.py
│   │   ├── test_formatter.py
│   │   └── test_config.py
│   └── integration/
│       └── test_runner.py         # 端對端流程測試
├── pyproject.toml
├── README.md
└── scripts/
    └── smoke.sh
```
