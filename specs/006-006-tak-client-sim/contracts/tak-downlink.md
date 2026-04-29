# Contract: TAK Server Downlink（tak-client-sim 接收端）

本契約定義 `tak-client-sim` 如何從 TAK Server `:8089` 接收 CoT XML 下行流。  
與上行契約 `specs/005-cot-gateway/contracts/tak-uplink.md` 互補：上行由 CoT Gateway 送出，本契約描述接收側語意。

---

## 1. Transport

| 項目 | 值 |
|------|-----|
| 協議 | TCP + TLS（SSL）單向；TAK Server → tak-client-sim（純接收，無反向訊息） |
| 端點 | 設定檔 `host:port`，預設 `tak-server:8089` |
| 框架 | Newline-delimited CoT XML；UTF-8；每筆後接 `\n`（0x0A）；**無** length-prefix |
| 客戶端憑證 | **不需要**（接收端無需 client cert；PoC 環境為 `CERT_NONE`） |
| 憑證驗證（PoC） | `verify_mode=CERT_NONE`、`check_hostname=False`（`use_ssl_verify=false`） |
| 憑證驗證（正式） | `verify_mode=CERT_REQUIRED`、`check_hostname=True`；可指定 `ca_bundle` 路徑 |
| 讀取方法 | `asyncio.StreamReader.readuntil(b'\n', limit=65536)` |
| 行長上限 | 64 KB（65536 bytes）；超限丟棄並記錄 `cot_oversized` warning |
| 重連策略 | 指數退避：`delay = min(1.0 × 2^(n-1), 60.0)` 秒 |
| 達 max_retries | `log max_retries_exceeded → sys.exit(1)` |

---

## 2. 接收流程

```python
async def receive_loop(
    reader: asyncio.StreamReader,
    config: ClientConfig,
    stats: ConnectionStats,
    stop: asyncio.Event,
) -> None:
    while not stop.is_set():
        try:
            raw_bytes = await reader.readuntil(b'\n', limit=65536)
        except asyncio.LimitOverrunError:
            await reader.read(65536)           # 排空剩餘
            log.warning("cot_oversized")
            stats.total_oversized += 1
            continue
        except (asyncio.IncompleteReadError, ConnectionResetError, OSError):
            log.warning("tak_disconnected", error=...)
            raise                              # 由外層重連邏輯處理

        raw = raw_bytes.decode("utf-8", errors="replace").strip()
        if not raw:
            continue

        event = parse_cot_xml(raw)
        if event is None:
            log.warning("cot_parse_error", raw_preview=raw[:200])
            stats.total_parse_errors += 1
            continue

        filtered = _is_filtered(event, config.filter_prefix)
        stats.record_event(event, filtered)

        log.info("cot_received",
                 uid=event.uid, source=event.source, color=event.color,
                 type=event.cot_type, lat=event.lat, lon=event.lon,
                 hae=event.hae, delta_s=event.delta_s,
                 speed=event.speed, course=event.course,
                 remarks=event.remarks, filtered=filtered)

        if not filtered:
            print_event(event)
```

---

## 3. 指數退避重連算法（FR-TCS-004 / FR-TCS-005 / FR-TCS-006）

```
attempt   delay_s
  1         1
  2         2
  3         4
  4         8
  5        16
  6        32
  7+       60（封頂）
```

公式：`delay = min(backoff_initial_s × 2^(attempt-1), backoff_cap_s)`

- 每次成功連線後 `attempt` 歸 0，`reconnect_count` 累計
- `max_retries=0`：無限重試
- `max_retries>0 且 attempt >= max_retries`：log `max_retries_exceeded` → `sys.exit(1)`

---

## 4. SSL Context 建立（接收端無 client cert）

```python
import ssl

def build_ssl_context(config: ClientConfig) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if not config.use_ssl_verify:
        # PoC 模式：跳過憑證驗證
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    else:
        # 正式模式：驗證 server 憑證
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.check_hostname = True
        if config.ca_bundle:
            ctx.load_verify_locations(cafile=config.ca_bundle)
    return ctx
```

**與 Gateway 的差異**：

| 項目 | cot-gateway TakTransmitter | tak-client-sim TakConnection |
|------|---------------------------|------------------------------|
| 方向 | 送出（上行） | 接收（下行） |
| client cert | 需要（`gateway.p12`）→ 依賴 `cryptography` | **不需要** |
| `cryptography` 依賴 | 是 | **否** |
| SSL 上下文 | `load_cert_chain(cert, key)` | 純 client verify 設定 |

---

## 5. CoT XML 接收語意

本服務接收 CoT Gateway 產出的 CoT 2.0 XML（完整格式見 `specs/005-cot-gateway/contracts/cot-xml.md`）。以下整理接收側關注點：

### 5.1 必要屬性（接收側驗證）

| 屬性 | 位置 | 缺席處理 |
|------|------|----------|
| `uid` | `<event uid>` | 視同解析失敗（`cot_parse_error`） |
| `type` | `<event type>` | 視同解析失敗（`cot_parse_error`） |
| `time` | `<event time>` | 以 `datetime.now(UTC)` 替代 + warning |
| `stale` | `<event stale>` | 以 `datetime.now(UTC)` 替代 + warning |

### 5.2 可選屬性（缺席時降級回預設值）

| 屬性 | 位置 | 缺席預設 |
|------|------|----------|
| `lat` / `lon` / `hae` | `<point>` | `0.0` |
| `speed` | `<track speed>` | `0.0` |
| `course` | `<track course>` | `0.0` |
| remarks | `<remarks>` text | `""` |

### 5.3 Source / Color 推導（接收側語意）

詳見 `data-model.md` §1.1 / §1.2。

### 5.4 delta_s 語意解讀

| delta_s | 語意推導 |
|---------|---------|
| `0` | `stale = time`（Lost 狀態） |
| `11` | 一般 Active / DETECTED / MITIGATING |
| `30` | NEUTRALIZED（保留 30 s） |
| 其他 | 未知狀態或上游異常 |

接收側**不以 delta_s 反推狀態**；僅顯示數值供操作員參考（remarks 含完整狀態字串）。

---

## 6. Graceful Shutdown

1. SIGINT/SIGTERM 到達 → `stop.set()`
2. `receive_loop` 在當前 `readuntil` 返回後於迴圈頂部偵測 `stop.is_set()` → break
3. 完成當前行解析與 console 輸出
4. `writer.close()` + `await writer.wait_closed()`
5. console 列印統計摘要（stdout）
6. `log.info("session_summary", ...)` → structlog
7. `sys.exit(0)`（FR-TCS-053）

---

## 7. Structlog 事件表

| event | 觸發時機 | 必要欄位 |
|-------|----------|---------|
| `tak_connected` | 連線成功後 | `host`, `port` |
| `tak_disconnected` | 連線中斷 | `error` |
| `reconnecting` | 每次重連嘗試前 | `attempt`, `delay_s` |
| `tak_reconnected` | 重連成功後 | `attempt` |
| `max_retries_exceeded` | 達重連上限 | `max_retries` |
| `cot_received` | 成功解析 CoT | `uid`, `source`, `color`, `type`, `lat`, `lon`, `hae`, `delta_s`, `speed`, `course`, `remarks`, `filtered` |
| `cot_parse_error` | XML 解析失敗 | `raw_preview`（前 200 字元） |
| `cot_oversized` | 行超過 64 KB | `bytes_seen` |
| `session_summary` | 優雅關閉時 | `total_received`, `total_filtered`, `total_parse_errors`, `total_oversized`, `reconnect_count`, `per_source`, `per_uid` |

---

## 8. Contract Test 覆蓋（`tests/contract/test_tak_downlink.py`）

測試以 `cot-xml.md` §7 合規矩陣 8 場景為 fixture，驗證接收側解析正確性：

| # | 測試名稱 | 驗證點 |
|---|----------|--------|
| 1 | `test_echo_active` | uid=`ECHO-TRK-001`, source=`ECHO`, color=`GREY`, delta_s=11 |
| 2 | `test_echo_lost` | uid=`ECHO-TRK-001`, source=`ECHO`, color=`GREY`, delta_s=0 |
| 3 | `test_sentrycs_detected` | uid=`SENTRYCS-DRN-001`, source=`SENTRYCS`, color=`GREY`, delta_s=11 |
| 4 | `test_sentrycs_mitigating` | uid=`SENTRYCS-DRN-001`, source=`SENTRYCS`, color=`GREY`, delta_s=11 |
| 5 | `test_sentrycs_neutralized` | uid=`SENTRYCS-DRN-001`, source=`SENTRYCS`, color=`GREY`, delta_s=30 |
| 6 | `test_fused_detected` | uid=`FUSED-DRN-001`, source=`FUSED`, color=`RED`, delta_s=11 |
| 7 | `test_fused_mitigating` | uid=`FUSED-DRN-001`, source=`FUSED`, color=`RED`, delta_s=11 |
| 8 | `test_fused_neutralized` | uid=`FUSED-DRN-001`, source=`FUSED`, color=`RED`, delta_s=30 |

附加 contract test：
- `test_stub_server_3_cot` — stub TCP server 發 3 筆 CoT，驗證 console 輸出含正確 uid/lat/lon
- `test_reconnect_sequence` — stub 中途斷線，驗證重連 delay 序列（freezegun mock）
- `test_filter_console_vs_log` — `--filter FUSED` 時，console 僅含 FUSED 行，structlog 含全部（`filtered=true`）

---

## 9. Console 輸出格式（FR-TCS-020 / FR-TCS-021）

```
[{ISO8601Z}] [{SOURCE}][{COLOR}] {uid}  {lat}/{lon}  {hae}m  {speed}m/s  {course:03.0f}°  delta_s=+{delta_s}  {remarks}
```

附加 `[STALE]` 標記（FR-TCS-021）：

```
[STALE] [2026-04-29T11:00:00.123Z] [ECHO][GREY] ECHO-TRK-001  25.060000/121.565400  101.0m  12.5m/s  045°  delta_s=+11  Source: ECHOSHIELD | Speed: 12.5m/s | Alt: 101m
```

條件：`(datetime.now(UTC) - event.stale).total_seconds() > 30`

---

## 10. Exit Code 契約（FR-TCS-053）

| 情境 | exit code |
|------|-----------|
| SIGINT/SIGTERM 優雅關閉 | `0` |
| `max_retries` 達上限 | `1` |
| 設定檔錯誤（ValidationError / YAML parse error） | `2` |
| log-file 路徑不可寫（fail-fast） | `2` |
