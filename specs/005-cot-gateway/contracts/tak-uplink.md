# Contract: TAK Server Uplink（Gateway 下游送出端）

本契約定義 CoT Gateway 的 `TakTransmitter` 如何將 CoT XML 以 TCP+SSL 推送至 TAK Server `:8089`。

---

## 1. Transport

| 項目 | 值 |
| --- | --- |
| 協議 | TCP + TLS（SSL）單向；Gateway → TAK Server（無反向訊息需消費） |
| 端點 | 設定檔 `tak_server.host:port`，預設 `tak-server:8089` |
| 框架 | Newline-delimited CoT XML；UTF-8；每筆後接 `\n` (0x0A)；**無** length-prefix（FR-GW-020） |
| 客戶端憑證 | `tak_server.cert_file`（預設 `gateway.p12`）；密碼來自 `tak_server.cert_password` 或環境變數 |
| 憑證驗證 | PoC：`verify_mode=CERT_NONE`、`check_hostname=False`（設定檔 `use_ssl_verify=false`）；正式部署應 `true` + 載入 TAK CA |
| 重連策略 | 指數退避 1 s → 2 s → 4 s → 8 s → 16 s → 32 s（封頂 60 s），**最多 `max_retries=5` 次**（FR-GW-021） |
| 達上限 | `raise ConnectionError("TAK max retries exceeded")`，Gateway 以 exit code != 0 終止 |
| Queue | `_cot_queue: asyncio.Queue[str]`，maxsize=500（FR-GW-022） |
| Queue 滿策略 | **drop-newest**（新進訊息 `put_nowait` 失敗 → 丟棄 + WARNING） |

---

## 2. 送出流程

```python
async def run(self):
    await self._connect_with_retry()          # 阻塞直到成功或 exit
    while not self._stop.is_set():
        cot_xml: str = await self._cot_queue.get()
        payload: bytes = cot_xml.encode("utf-8") + b"\n"
        try:
            self._writer.write(payload)
            await self._writer.drain()
        except (ConnectionResetError, BrokenPipeError, ssl.SSLError) as e:
            self._log.warning("tak_send_failed", error=str(e))
            # 將 payload 放回 queue 頭（best-effort）以免丟；若 queue 滿則真丟
            self._requeue_or_drop(cot_xml)
            await self._connect_with_retry()
```

**enqueue（其他 coroutine 呼叫）**：

```python
def enqueue(self, cot_xml: str) -> None:
    try:
        self._cot_queue.put_nowait(cot_xml)
    except asyncio.QueueFull:
        self._log.warning("queue_full_drop", uid=_peek_uid(cot_xml))
        # 不阻塞呼叫者；新進 CoT 直接丟棄（drop-newest）
```

---

## 3. 指數退避演算法（FR-GW-021）

```
attempt   delay_s
  1        1
  2        2
  3        4
  4        8
  5       16
  6+      封頂 60（但 max_retries=5，實際不會進到此）
```

- `_retry_count` 在每次成功連線後歸 0；
- `_retry_count >= max_retries` 時 raise `ConnectionError`；
- 公式：`delay = min(backoff_initial_s * 2**(attempt-1), backoff_cap_s)`。

---

## 4. SSL Context 載入

```python
def build_ssl_context(cfg: TakServerConfig) -> ssl.SSLContext:
    from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption, BestAvailableEncryption
    from pathlib import Path
    import tempfile

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = cfg.use_ssl_verify
    ctx.verify_mode = ssl.CERT_REQUIRED if cfg.use_ssl_verify else ssl.CERT_NONE

    p12_bytes = Path(cfg.cert_file).read_bytes()
    pwd = cfg.cert_password.encode() if cfg.cert_password else None
    key, cert, chain = pkcs12.load_key_and_certificates(p12_bytes, pwd)

    # 寫入一次性 0600 檔（SSLContext 需要檔案路徑；記憶體 API Python 3.11 仍不支援）
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as cf, \
         tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as kf:
        cf.write(cert.public_bytes(Encoding.PEM))
        if chain:
            for c in chain:
                cf.write(c.public_bytes(Encoding.PEM))
        kf.write(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
        cert_path, key_path = cf.name, kf.name

    ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
    # os.chmod(key_path, 0o600) 同步套用
    return ctx
```

**Alternative**：若使用者離線 `openssl pkcs12 -in gateway.p12 -out gateway.pem -nodes`，config 可改指向
`.pem`/`.key`，SSL context 直接 `load_cert_chain`，免 `cryptography` 依賴。

---

## 5. Queue 滿語意（FR-GW-022 — drop-newest）

當 `_cot_queue` 已達 500：

- **不**阻塞 CotGenerator 與 process_loop；
- **新進**訊息被丟棄（drop-newest），非丟棄最舊；
- 每次丟棄記錄一筆 WARNING `queue_full_drop`，含被丟棄事件的 uid（best-effort 解析）。

**設計理由**：Demo 情境 queue 滿代表 TAK 連線持續異常；drop-newest 讓已排隊的事件（較可能是 Lost /
stale=now 的清場事件）優先送出，避免 ATAK 殘留舊圖示。

---

## 6. Graceful Shutdown（FR-GW-025）

1. Gateway 收到 SIGINT/SIGTERM → 設置 `_stop` 事件；
2. 停止從 `_cot_queue` 以外輸入（adapter coroutines cancelled）；
3. TakTransmitter 排空 `_cot_queue`，最多等 **3 秒**；
4. `writer.close()` + `await writer.wait_closed()`；
5. Gateway 以 exit code 0 結束。

若 3 秒內未排空，剩餘事件一律丟棄 + 單筆 INFO 日誌記錄丟棄數量。

---

## 7. Contract test 覆蓋（`tests/contract/test_tak_uplink.py`）

1. ✅ TAK stub 正常 → 產 3 筆 CoT → stub 收到 3 行，每行以 `\n` 結束、皆為合法 XML。
2. ✅ SSL 握手成功（`trustme` 自簽 CA + `use_ssl_verify=true` 測試路徑）。
3. ✅ TAK stub 拒絕連線 → 觀察 delay 序列 1/2/4/8/16 s（用 freezegun + `asyncio.sleep` mock 驗證；實際
   不等時）；5 次後 raise `ConnectionError`。
4. ✅ 連線建立後中途斷線 → Transmitter 進入重連序列；重連成功後新 CoT 能送達。
5. ✅ Queue 滿（enqueue 501 筆）→ 第 501 筆被丟棄 + WARNING `queue_full_drop`；前 500 筆正常消費。
6. ✅ Graceful shutdown：排隊 10 筆、SIGINT → 3 s 內清空並關閉 writer。
7. ✅ Source 切換雙訊息：enqueue 舊 uid `stale=time` + 新 uid 首筆 → stub 收到兩行，uid 前綴不同、順序
   正確（舊先、新後）。
