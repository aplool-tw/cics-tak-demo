# Research: TAK Client Simulator

**Feature**: 006-006-tak-client-sim  
**Date**: 2026-04-29  
**Status**: Complete — 無 NEEDS CLARIFICATION 殘留

---

## 概述

所有技術選項均已由凍結契約（`tak-uplink.md`、`cot-xml.md`）、AGENTS.md 守則（G1–G7）、及同倉庫參考服務（`cot-gateway`、`echoshield-sim`）明確規範。本研究文件整理決策依據與替代方案評估，供實作與審查參考。

---

## Research 1: asyncio TCP+SSL Client（接收側）

### 決策

使用 `asyncio.open_connection(host, port, ssl=ssl_ctx)` 建立 TCP+SSL 連線，返回 `(StreamReader, StreamWriter)` pair。

### 理由

- Python 3.11+ stdlib asyncio 原生支援；無需額外依賴（G7）
- `StreamReader` 提供 `readuntil(separator, limit)` 直接對應 NDJSON framing
- 與 `cot-gateway` 的 `TakTransmitter` 對稱（參考 `services/cot-gateway/src/cot_gateway/tak/`）
- 無需 `aiohttp`（Gateway 用於 HTTP polling；本服務純 TCP）

### SSL Context 建立（PoC 消費端）

```python
import ssl

def build_ssl_context(use_ssl_verify: bool, ca_bundle: str | None = None) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if not use_ssl_verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    else:
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.check_hostname = True
        if ca_bundle:
            ctx.load_verify_locations(ca_bundle)
    return ctx
```

**關鍵差異**（vs Gateway）：
- Gateway 需載入 `gateway.p12`（送出端需要 client cert）→ 依賴 `cryptography`
- `tak-client-sim` 為純接收端，**不需要** client certificate → **不引入** `cryptography`（G7）
- PoC: `verify_mode=CERT_NONE + check_hostname=False`

### 替代方案評估

| 方案 | 評估 | 棄用原因 |
|------|------|----------|
| `asyncssh` | SSH library，非 TLS | 不適用 |
| `anyio` | 跨 backend 抽象 | 過度設計，PoC 不需要 |
| `trio` | 替代 async 框架 | 與既有 asyncio 生態不相容 |

---

## Research 2: Newline-delimited 分幀讀取

### 決策

使用 `asyncio.StreamReader.readuntil(b'\n', limit=65536)` 逐行讀取。

### 理由

- `readuntil` 的 `limit` 參數直接支援 FR-TCS-016（64 KB oversized 保護）：超限拋 `asyncio.LimitOverrunError`
- `readline()` 無 limit 參數，無法防止 oversized 攻擊
- NDJSON framing 已由 `cot-xml.md` §1 凍結：每筆 CoT XML 後接 `\n`（0x0A）

### 實作模式

```python
try:
    raw_bytes = await reader.readuntil(b'\n', limit=65536)
    raw = raw_bytes.decode('utf-8').strip()
except asyncio.LimitOverrunError:
    # 消耗剩餘直到 \n
    await reader.read(65536)
    log.warning("cot_oversized", bytes_seen=65536)
    stats.total_oversized += 1
    continue
except (asyncio.IncompleteReadError, ConnectionResetError):
    # 連線斷線 → 重連
    break
```

### TCP 分包處理

`StreamReader` 內部維護 buffer，`readuntil` 自動等待 `\n` 到達後再返回，天然處理 TCP 分包（FR-TCS-010）。

---

## Research 3: CoT XML 解析（標準庫 ElementTree）

### 決策

使用 `xml.etree.ElementTree.fromstring(raw_xml)` 解析。

### 理由

- AGENTS.md §3.2 明文禁用 `lxml`；G7 標準庫優先
- `fromstring()` 對無效 XML 拋 `ET.ParseError`，可 catch 對應 FR-TCS-017
- 效能：本服務 50+ UPS，ElementTree 足夠（lxml 優勢在 GB 級文件）

### 提取欄位

```python
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

def parse_cot_xml(raw: str) -> CotEvent | None:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None  # cot_parse_error 由呼叫側 log

    uid = root.get("uid")
    cot_type = root.get("type")
    if not uid or not cot_type:
        return None  # FR-TCS-018 缺少必要屬性

    time_str  = root.get("time", "")
    stale_str = root.get("stale", "")
    time_dt   = _parse_iso(time_str)
    stale_dt  = _parse_iso(stale_str)

    point = root.find("point")
    lat = float(point.get("lat", "0")) if point is not None else 0.0
    lon = float(point.get("lon", "0")) if point is not None else 0.0
    hae = float(point.get("hae", "0")) if point is not None else 0.0

    detail = root.find("detail")
    track  = detail.find("track")  if detail is not None else None
    speed  = float(track.get("speed",  "0")) if track  is not None else 0.0
    course = float(track.get("course", "0")) if track  is not None else 0.0
    remarks_el = detail.find("remarks") if detail is not None else None
    remarks = (remarks_el.text or "") if remarks_el is not None else ""

    delta_s = max(0, round((stale_dt - time_dt).total_seconds())) if time_dt and stale_dt else 0

    return CotEvent(
        uid=uid, cot_type=cot_type,
        source=_derive_source(uid), color=_derive_color(cot_type),
        time=time_dt, stale=stale_dt, delta_s=delta_s,
        lat=lat, lon=lon, hae=hae, speed=speed, course=course,
        remarks=remarks, raw_xml=raw,
    )
```

### 特殊處理

- **stale < time（異常）**：`max(0, ...)` 確保 delta_s ≥ 0（Edge Case FR-TCS-013）
- **ISO 8601 解析**：Python 3.11 `datetime.fromisoformat()` 支援 `Z` suffix；3.10 以下需手動替換
- **缺少 `<detail>/<point>`**：降級回 0 值，不崩潰

### 替代方案評估

| 方案 | 評估 | 棄用原因 |
|------|------|----------|
| `lxml` | 更快、XPath 更強 | AGENTS.md 明文禁用 |
| `minidom` | stdlib | API 較繁瑣，無明顯優勢 |
| SAX parser | 串流解析 | 對 ≤64KB 事件過度設計 |
| `xmltodict` | 第三方 | 額外依賴，G7 不合規 |

---

## Research 4: Source / Color 推導

### 決策

UID 前綴匹配：`ECHO-` / `SENTRYCS-` / `FUSED-`；type 前綴匹配：`a-u-` / `a-h-`。

### 實作

```python
def _derive_source(uid: str) -> str:
    if uid.startswith("ECHO-"):     return "ECHO"
    if uid.startswith("SENTRYCS-"): return "SENTRYCS"
    if uid.startswith("FUSED-"):    return "FUSED"
    return "UNKNOWN"

def _derive_color(cot_type: str) -> str:
    if cot_type.startswith("a-u-"): return "GREY"
    if cot_type.startswith("a-h-"): return "RED"
    return "UNKNOWN"
```

### 依據

- `cot-xml.md` §3 UID 規則：`ECHO-{id}`、`SENTRYCS-{id}`、`FUSED-{id}`
- `cot-xml.md` §4 Type 規則：`a-u-*`（Unknown/灰）、`a-h-*`（Hostile/紅）
- spec.md FR-TCS-014 / FR-TCS-015

---

## Research 5: structlog JSON 日誌

### 決策

使用 `structlog>=24.1`，設定 JSON renderer + timestamp processor。

### 理由

- 專案既有依賴（`cot-gateway` 已使用）
- G3 要求 structlog JSON；至少含 `timestamp/level/logger/event` 四欄
- 支援 `--log-file` 雙目標輸出（stderr + file）

### 設定模式

```python
import structlog
import logging
import sys

def configure_logging(log_file: str | None = None) -> None:
    processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.JSONRenderer(),
    ]

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, mode="a", encoding="utf-8"))

    logging.basicConfig(
        format="%(message)s",
        handlers=handlers,
        level=logging.INFO,
    )
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
```

### console 與 log 分離

| 輸出 | 目標 | 格式 |
|------|------|------|
| human-readable CoT 行 | `stdout`（`print()`） | `[TIME] [SRC][CLR] uid ...` |
| structlog events | `stderr` + optional file | JSON（每行一筆） |

### log-file 路徑不可寫

`--log-file` 設定時，啟動前先 `open(path, 'a')` 驗證寫入權限；失敗即 fail-fast（exit code 2）。

---

## Research 6: pydantic v2 ClientConfig

### 決策

`ClientConfig` 使用 `pydantic.BaseModel` + `ConfigDict(extra="forbid", frozen=True)`；YAML 載入後以 `ClientConfig(**yaml_dict)` 驗證。

### 理由

- AGENTS.md §3.3：pydantic v2 model 設定 `extra="forbid"`，YAML 多餘欄位即 fail-fast
- `frozen=True`：設定不可變，避免執行時意外修改
- CLI 參數優先：先載入 YAML → `model.model_copy(update={...})` 套用 CLI 覆寫

### YAML 對稱格式

```yaml
host: tak-server
port: 8089
use_ssl_verify: false
ca_bundle: null
max_retries: 0
backoff_initial_s: 1.0
backoff_cap_s: 60.0
filter_prefix: null
log_file: null
```

### exit code 對應

| 情境 | exit code |
|------|-----------|
| 正常關閉 | 0 |
| max_retries 達上限 | 1 |
| 設定檔錯誤（pydantic ValidationError / YAML parse error） | 2 |

---

## Research 7: 指數退避重連算法

### 決策

公式 `delay = min(backoff_initial_s * 2^(attempt-1), backoff_cap_s)`，`max_retries=0` 代表無限重試。

### 序列（預設 initial=1.0, cap=60.0）

| attempt | delay(s) |
|---------|----------|
| 1 | 1 |
| 2 | 2 |
| 3 | 4 |
| 4 | 8 |
| 5 | 16 |
| 6 | 32 |
| 7+ | 60（上限） |

### 與 Gateway 的差異

| 項目 | cot-gateway TakTransmitter | tak-client-sim |
|------|---------------------------|----------------|
| max_retries 預設 | 5 | 0（無限） |
| 需要重連的觸發 | 送出失敗 | 讀取失敗（接收端） |
| 重連後行為 | 繼續送出 queue 中的 CoT | 繼續讀取 stream |

### asyncio.sleep mock（測試用）

```python
# tests 中以 freezegun + monkeypatch 驗證 delay 序列
# 不實際等待，僅斷言 sleep 被以正確 delay 值呼叫
```

---

## Research 8: Graceful Shutdown

### 決策

使用 `asyncio` 的 signal handler + `asyncio.Event` 協調關閉。

### 實作模式

```python
import asyncio, signal

async def main(config: ClientConfig) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    stats = ConnectionStats()
    conn  = TakConnection(config)

    try:
        await receive_loop(conn, config, stats, stop)
    finally:
        _print_summary(stats)
        log.info("session_summary", **stats.to_dict())
```

### 關閉流程

1. Signal 到達 → `stop.set()`
2. `receive_loop` 在下一次迴圈頂部檢查 `stop.is_set()` → break
3. 完成當前行解析與輸出（FR-TCS-051）
4. `conn.close()` → `writer.close() + await writer.wait_closed()`
5. `_print_summary()` 至 stdout（FR-TCS-052）
6. `log.info("session_summary", ...)` → structlog（FR-TCS-035）
7. `sys.exit(0)`

### SC-TCS-006 合規

3 秒內關閉：每次 `readuntil` 有 limit=65536，最壞情況等待一行讀完（＜100ms），無阻塞操作。

---

## Research 9: 測試策略

### Contract Test（`tests/contract/test_tak_downlink.py`）

覆蓋凍結契約 8 場景（`cot-xml.md` §7）：

| 場景 | 驗證點 |
|------|--------|
| 1 ECHO Active | source=ECHO, color=GREY, delta_s=11 |
| 2 ECHO Lost | source=ECHO, color=GREY, delta_s=0 |
| 3 SENTRYCS DETECTED | source=SENTRYCS, color=GREY, delta_s=11 |
| 4 SENTRYCS MITIGATING | source=SENTRYCS, color=GREY, delta_s=11 |
| 5 SENTRYCS NEUTRALIZED | source=SENTRYCS, color=GREY, delta_s=30 |
| 6 FUSED DETECTED | source=FUSED, color=RED, delta_s=11 |
| 7 FUSED MITIGATING | source=FUSED, color=RED, delta_s=11 |
| 8 FUSED NEUTRALIZED | source=FUSED, color=RED, delta_s=30 |

### Unit Test

- `test_parser.py`：happy path × 8 場景；oversized（LimitOverrunError）；invalid XML；missing uid；missing type；stale < time → delta_s=0
- `test_formatter.py`：格式正確性；`[STALE]` 標記（stale 比 now 早 >30s）；filter 邏輯（console 不輸出但 filtered=True）
- `test_config.py`：合法 YAML；多餘欄位 ValidationError；CLI 覆寫優先

### Integration Test（`tests/integration/test_runner.py`）

使用 `asyncio` stub TCP server，發送 3 筆 CoT XML → 驗證 console capture 包含正確 uid/type/lat/lon；驗證 structlog 輸出含 3 筆 `cot_received`；驗證重連序列（stub 中途斷線）。

---

## 結論

無 NEEDS CLARIFICATION。所有技術選項均由現有規格與參考服務確認，可直接進入 Phase 1 設計。
