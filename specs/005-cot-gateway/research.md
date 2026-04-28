# Phase 0 Research: CoT Gateway

本檔紀錄 `/speckit.plan` Phase 0 階段針對未決技術選項的調研與決策。所有 NEEDS CLARIFICATION 皆已於
`spec.md` 的 `Clarifications` 三輪問答中解決；本檔聚焦**實作層級**的選型與最佳實務。

---

## R1. CoT XML 函式庫選型

**Decision**: 採 Python 標準庫 `xml.etree.ElementTree`。

**Rationale**:

- CoT 2.0 的 event/point/detail 結構單層且欄位固定（見 `contracts/cot-xml.md`），`ElementTree` 足以
  產生合法 XML；手動控制屬性順序與毫秒 ISO 8601 字串反而比 lxml 更直觀。
- 守 G7「Dependency Minimalism」——不新增 C 編譯依賴。
- 單筆 CoT 序列化 < 1 ms（預量測），遠低於 SC-GW-002 的 5 ms 預算。

**Alternatives considered**:

- `lxml`：C extension，比 ElementTree 快 2–5×，但 PoC 吞吐 ~100 msg/s 根本觸不到瓶頸；新增編譯依賴
  違反 G7。
- 字串模板 / f-string 手拼：最快，但 drone_model / remarks 字元逸出需要自己處理，容易出 bug（Edge Case
  §6「CoT XML 字元逸出」）。

---

## R2. TAK Server TCP+SSL 與 gateway.p12 載入

**Decision**:

- 使用 stdlib `ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)` + `load_cert_chain(certfile=..., keyfile=..., password=...)`。
- 以 `cryptography.hazmat.primitives.serialization.pkcs12.load_key_and_certificates` 在啟動時將
  `gateway.p12` 解出 → 暫存 PEM（記憶體 BytesIO 或 tmpfile with 0600）→ 載入 SSLContext。
- PoC 期間 `context.check_hostname = False`、`context.verify_mode = ssl.CERT_NONE`（Assumptions §5
  明示允許；`config.tak_server.use_ssl_verify = false`）。
- 連線以 `asyncio.open_connection(host, port, ssl=context)`。

**Rationale**:

- stdlib `ssl` 原生支援 PEM；p12 不支援 → 必須先解成 PEM。`cryptography` 是 Python 生態解 p12 的事實
  標準，已被 `pyopenssl` / `trustme` 等依賴間接引入，本身也是純 Python + Rust wheel，PyPI 預編好，不
  增加編譯負擔。
- `CERT_NONE` 僅 PoC：Assumption 明文允許；正式部署以設定檔升級為 `CERT_REQUIRED` + 載入 TAK Server CA。
- `asyncio.open_connection(ssl=...)` 讓 reader/writer 與明文 TCP API 一致，方便 test_stub 以明文 TCP sink
  替代 SSL（降低測試 fixture 複雜度；見 `tests/conftest.py` `tak_stub`）。

**Alternatives considered**:

- 離線先用 `openssl pkcs12 -in gateway.p12 -out gateway.pem` 轉出 PEM，運行時只用 stdlib `ssl` 載入
  PEM：可完全免 `cryptography` 依賴；但部署流程多一步。**保留此選項**於 `config/certs/README.md`
  紀錄，讓使用者二選一（預設走 p12 自動解；若使用者提供 PEM，config 也支援直接載入）。
- `pyopenssl`：過時 API，官方推薦遷移至 `cryptography`。

---

## R3. Haversine 距離計算（50 m 關聯閾值）

**Decision**: 手寫於 `src/cot_gateway/correlate/haversine.py`：

```python
from math import radians, sin, cos, asin, sqrt
EARTH_R_M = 6_371_000.0

def haversine_m(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = radians(lat1), radians(lat2)
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(p1) * cos(p2) * sin(dlon / 2) ** 2
    return 2 * EARTH_R_M * asin(sqrt(a))
```

**Rationale**:

- FR-GW-010 明示地球半徑 6,371,000 m；`geopy` 預設 WGS84 ellipsoidal 距離（Vincenty / geodesic）與
  spec 不同，使用它反而不合規。
- 5 架航跡的兩兩距離計算在 < 0.1 ms（預量測），遠低於 SC-GW-002 的 1 ms 預算。
- 守 G7。

**Alternatives considered**:

- `geopy.distance.distance`：精確但與 spec 不同演算法；引入新依賴。
- `numpy` 向量化：過度工程，N=5 無意義。

---

## R4. Async 架構與 queue 容量

**Decision**: 5 個並行 coroutine + 2 個 `asyncio.Queue`：

```
echodyne_adapter ──►┐
                    ├──► track_queue (maxsize=1000) ──► process_loop ──► cot_queue (maxsize=500) ──► tak_sender
sentrycs_adapter ──►┘                                        ▲
                                                             │
                                                    ttl_loop (1 Hz)
```

- `process_loop`：消費 `track_queue` → TrackCorrelator.correlate → 偵測 source 切換 →（若切換）先 enqueue
  舊 uid `stale=time` 最終 CoT → CotGenerator.generate → enqueue `cot_queue`。
- `ttl_loop`：每 1 s 執行 `TrackCorrelator.update_ttl()`；對過期 uid enqueue `stale=time` 最終 CoT，從
  `seen_uids` 移除。
- `tak_sender`：消費 `cot_queue`，若連線未建立則阻塞於 `_connect_with_retry`；達 max_retries=5 後 raise
  `ConnectionError` 讓 Gateway 主程式以非 0 exit code 結束。
- `asyncio.Queue.put_nowait` + `QueueFull` → drop-newest + WARNING（FR-GW-022）。

**Rationale**:

- 單事件迴圈足以處理 ~100 msg/s，無需 thread pool 或多 process。
- queue 容量：`track_queue=1000`（雷達 10 Hz × 5 架 = 50 msg/s，20 s 緩衝）、`cot_queue=500`（FR-GW-022
  固定）；兩者相差 2×，避免 CotGenerator 下游倒灌。
- 5 coroutine 皆用 `asyncio.create_task`；Gateway 主程式以 `asyncio.gather(..., return_exceptions=True)`
  捕捉個別失敗（FR-GW-024 「任一 adapter 失敗不得使其他 coroutine 中止」）。

**Alternatives considered**:

- 合併 process_loop 與 tak_sender 為同一 coroutine：會讓 TAK 重連期間阻塞 correlator，違反 FR-GW-024。
- thread pool 加速 CoT XML 生成：SC-GW-002 已綽綽有餘，純屬過度工程。

---

## R5. source 切換雙訊息模式（FR-GW-014）的實作定位

**Decision**: 邏輯放於 `process_loop`（而非 CotGenerator 或 Correlator）。

- `cot/uid.py` 提供純函式 `uid_for(track) -> str`；process_loop 維護 `prev_uid_by_entity_key: dict[str, str]`
  （key = `radar_track_id` 或 `rf_track_id`，能跨 source 追蹤「同一實體」）。
- 當 `uid_for(track) != prev_uid_by_entity_key[entity_key]`：
  1. 以舊 uid 產一筆「stale=time 的最終 CoT」（用當下 track 座標即可，ATAK 只看 stale）→ enqueue。
  2. 更新 `prev_uid_by_entity_key[entity_key] = new_uid`；`seen_uids.discard(old_uid)`。
  3. 以新 uid 產首筆 CoT → enqueue；記錄 `source_switch` INFO 事件。

**Rationale**:

- Correlator 的職責是「關聯與否」，不該知道 CoT uid 前綴命名政策。
- CotGenerator 無跨 tick 記憶（純函式 `Track → str`）；保留其可測試性。
- process_loop 本就是狀態中樞（維護 `seen_uids`、enqueue CoT），最適合承擔此切換邏輯。

**Entity key 定義**：

- `ECHOSHIELD` Track → key = `radar:{radar_track_id}`；
- `SENTRYCS` Track → key = `rf:{rf_track_id}`；
- `FUSED` Track → key = **`rf:{rf_track_id}`**（與 SENTRYCS 同 key，讓 SENTRYCS↔FUSED 切換可被偵測為同一
  實體；ECHO↔FUSED 切換則跨 key，需額外處理：FUSED Track 同時保有 `radar_track_id` 與 `rf_track_id`，
  process_loop 檢查兩個 key，任一有舊 uid 則發 stale=now 最終 CoT）。

**Alternatives considered**:

- 以 `(source, track_id)` 作 key：ECHO→FUSED 時 key 變，偵測不到切換。
- 以座標相近度反查舊 uid：脆弱，違背既有設計精神（Correlator 已負責座標關聯）。

---

## R6. 毫秒精度 ISO 8601 與 freezegun 相容性

**Decision**: 使用 `datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")`。

- 範例：`"2026-04-24T12:34:56.789Z"`。
- `stale` 計算：`(now + timedelta(seconds=N)).isoformat(timespec="milliseconds").replace("+00:00","Z")`。

**Rationale**:

- CoT 2.0 schema 要求 `time`/`start`/`stale` 為 ISO 8601 UTC 字串；毫秒精度足以讓 SC-GW-012「`stale -
  time` 誤差 ≤ 1 ms」可驗證。
- freezegun 凍結 `datetime.now(tz)` 後，`isoformat` 輸出穩定可斷言；避免 `strftime` 手拼。

**Gotcha**:

- `datetime.isoformat` 對 UTC tz 輸出 `+00:00`；CoT 慣用 `Z`。以 `.replace("+00:00","Z")` 處理。
- freezegun 需 `tz_offset=0` 或 `tick=False`（依 test 情境決定）；`unit/test_cot_generator.py` 以
  `@freeze_time("2026-04-24T12:34:56.789Z")` 精確控制。

---

## R7. 測試 fixture：EchoShield / Sentrycs / TAK stubs

**Decision**:

- **echoshield_stub**：asyncio TCP server fixture，接受單一連線後從 `scripts/data/*.ndjson` 逐行
  `writer.write(line + b"\n")`；支援 `drop_after_n` 參數模擬中斷（US3）。
- **sentrycs_stub**：`aiohttp.test_utils.TestServer`，`GET /detections` 回傳可由 test 動態注入的 JSON
  陣列；支援 `fail_rate` 模擬 5xx。
- **tak_stub**：asyncio TCP server fixture，**不使用 SSL**（配合 Gateway 的 `use_ssl=false` 測試模式）；
  紀錄所有收到的 newline-delimited 行至 `list[str]` 供斷言。`use_ssl` 為 `GatewayConfig.tak_server` 的欄位，
  contract test 會單獨用 SSL context 驗證握手成功。

**Rationale**:

- 降低 integration test 的 SSL 複雜度；SSL 握手本身於 contract test (`test_tak_uplink.py`) 獨立驗證，
  用 `trustme` 產生一次性自簽憑證；其餘 integration test 一律走明文 TCP sink。
- 與 `services/sentrycs-sim/tests/conftest.py` 的 `map_sim_stub` / `uds_stub` 樣式一致，降低貢獻者認知
  負擔（G5 Layout Symmetry）。

---

## R8. GatewayConfig YAML 結構（FR-GW-023）

**Decision**:

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
  use_ssl_verify: false          # PoC；正式部署應為 true
  cert_file: config/certs/gateway.p12
  cert_password: "${TAK_P12_PASSWORD}"  # 讀環境變數；未設則嘗試空密碼
  max_retries: 5
  backoff_initial_s: 1.0
  backoff_cap_s: 60.0
  queue_maxsize: 500
logging:
  level: INFO
  json: true
```

**Rationale**:

- 四段式（echoshield / sentrycs / correlator / tak_server）完全對應 spec Key Entities；`logging` 段對齊
  `004-sentrycs-sim/config/local.yaml` 樣式。
- `cert_password` 支援 `${ENV_VAR}` 展開，避免明文寫密碼入 YAML；`config.py` 於 pydantic validator 解析。
- `use_ssl_verify` 預設 `false`（PoC），明示提醒使用者正式部署需改 `true`。

---

## 結論

Phase 0 所有決策皆守 G7（依賴最小化）：runtime 新增依賴僅 `aiohttp` + `pydantic` + `structlog` + `pyyaml`
+ `cryptography`（p12 解碼唯一理由；若使用者離線轉 PEM 則可完全省略）；CoT XML、Haversine、SSL、XML
皆用 stdlib。無 NEEDS CLARIFICATION 殘留，可進入 Phase 1。
