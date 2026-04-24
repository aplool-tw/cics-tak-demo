# Phase 0 Research — Map Simulator

本文件記錄 Map Sim 關鍵技術決策。格式：Decision / Rationale / Alternatives considered。

---

## 1. Haversine 圓形範圍查詢

**Decision**：以 WGS84 球面近似實作 `haversine_m(lat1, lon1, lat2, lon2) -> float`，地球半徑常數
`R = 6_371_000.0 m`；在 `ObjectRegistry.query_radius()` 內對所有物件逐一計算距離、以 `dist <= radius_m`
過濾、以 `dist` 為 key 升冪排序。

**Rationale**：
- PoC 感測器半徑為 4800 m（EchoShield）與 8000 m（Sentrycs），均遠小於 100 km；球面 Haversine 在
  100 km 內誤差 < 0.5%，滿足 SC-MS-005（`distance_m` 與 ground truth 差 < 0.5%）。
- 與 `services/uds/src/uds/geo/wgs84.py` 常數一致（R = 6_371_000.0），跨服務測試時 ground truth 對齊。
- N ≤ 20 的線性掃描 + 排序，單次 query 成本 O(N log N)，常數極小；單核每秒可處理數千次查詢，完全
  不需要 R-tree / geohash 空間索引（SC-MS-002 p95 < 20 ms 已有充裕餘裕）。
- Python stdlib `math` 即可，不增依賴；`geopy` 僅在 `tests/unit/test_haversine.py` 作交叉驗證使用，
  不列入 runtime 依賴。

**Alternatives considered**：
- **Vincenty / 橢球**：精度更高但 PoC 半徑下額外精度無意義，且需 `geographiclib` 或 `geopy` 作為 runtime
  依賴；拒絕。
- **R-tree（`rtree` / `shapely.STRtree`）空間索引**：對大 N 查詢加速，但 PoC N ≤ 20；索引維護成本反而
  高於線性掃描；拒絕。
- **Geohash bucket**：同上；且對「經 180° 子午線 / 極區」edge case 處理複雜；PoC 不值得；拒絕。
- **平面近似（local tangent plane）**：在單一感測器半徑內精度亦足，但查詢中心可能隨 feature 增多而變，
  切 tangent plane 需重算；Haversine 實作更直接且 self-contained；拒絕。

---

## 2. TTL 背景清理策略

**Decision**：使用**單一背景 task** `cleanup.ttl_task.run_cleanup_loop(registry, period_s=2.0)`，
由 aiohttp `app.on_startup` 以 `asyncio.create_task` 啟動、以 `app.on_cleanup` cancel；loop 內每輪：

```
while not cancelled:
    await asyncio.sleep(period_s)
    removed = await registry.cleanup_expired()    # 取得鎖、scan、delete age_s > ttl_remove_s
    if removed:
        logger.info("ttl.cleanup", removed=removed)
```

**Rationale**：
- 清理週期 `period_s = 2.0` 對齊 SC-MS-003 / SC-MS-004 定義的「TTL warn / remove 精度 ≤ ttl + 2 s」。
  若 period 更小（如 0.5 s），SC 可更緊但鎖爭用增加；2.0 s 對 5/10 s 的 TTL 而言誤差比例合理。
- 單一 task、不引入 scheduler 套件（`apscheduler`、`aiocron` 等）；降低依賴與啟停複雜度。
- 放在 `on_startup` / `on_cleanup` 生命週期 hook 中，避免在 handler 啟動 task 造成重複或 leak。
- `cleanup_expired()` 內部照常取 `asyncio.Lock`，與 update / query 互斥；單一 event loop 天然無
  race condition，不需 `threading.Lock`。
- **lazy check 於 query 時**：`query_radius` 以 `obj.age_s() > ttl_warn_s` 即時判斷 `is_lost`，不依賴
  背景 task 先標記；因此即使背景 task 暫時落後，查詢結果仍正確（只是「已到 warn 線但尚未到 remove」
  的物件仍在表中——這正是 `include_lost=true` 所需行為，無誤差）。
- `ttl_warn_s` 不主動「標記」任何 flag——它只是 query/serialize 時的判斷閾值；只有 `ttl_remove_s` 才
  會實際修改 dict。這保證並發讀寫正確性：warn 不影響 registry state。

**Alternatives considered**：
- **Per-object `call_later` timer**：每次 update 排程一個 `loop.call_later(ttl_remove_s, ...)`；優點是
  移除時機精確、無週期誤差。缺點是「每次 update 需 cancel 舊 timer、排新 timer」、timer 堆積成本高、
  與 `asyncio.Lock` 組合時需小心 reentry；對 PoC 量級不值得。拒絕。
- **同步於 query 內清理**：在 `query_radius` 順便刪除過期物件。缺點：`GET /objects/all` 呼叫頻率可能
  很低，過期物件不會被清理；且讓 GET 變成寫路徑，違反 CQRS-lite 邊界；拒絕。
- **多個背景 task 並行清理不同 shard**：對 PoC N ≤ 20 毫無必要；拒絕。

---

## 3. aiohttp 併發 read/write 模型 & 鎖策略

**Decision**：對 `ObjectRegistry` 採**單一全域 `asyncio.Lock`**（`self._lock`）；所有公開 async 方法
（`update` / `query_radius` / `get_all` / `remove` / `cleanup_expired`）進入時 `async with self._lock`。

**Rationale**：
- aiohttp handler 都是 coroutine，全部跑在同一個 event loop；在 Python asyncio 下，CPU-bound 的純
  Python code 在 `async with lock` 區段內執行時不會被其他 coroutine 搶佔（只有 `await` 才 yield）。
  因此：
  1. `update` 的 dict `__setitem__` 是同步操作、不含 `await`，本質上原子，但仍需鎖——原因是：它會與
     `cleanup_expired` 的 `for k in expired: del self._objects[k]` 共享字典，而 `cleanup_expired` 在迭代
     前呼叫 `.age_s()`（含 `datetime.now()`，同步）不會 yield；**只要所有方法都在鎖內、且鎖內無任何
     `await`**（rule 1），就等同 critical section 被序列化。鎖主要用於**語意正確性的宣告**與未來若
     鎖內引入 `await` 時的保障（例如改為 per-key lock 時）。
  2. `query_radius` 在鎖內遍歷 `_objects.values()` 算 Haversine、sort、return snapshot；由於不含 `await`，
     其他 coroutine 在此期間不會看到中間狀態，無髒讀。
- PoC 負載：update ≈ 100 req/s（10 架 × 10 Hz）、query ≈ 20 req/s（2 sensor × ~10 Hz）、cleanup
  0.5 Hz；鎖內工作 O(N) N ≤ 20、純 Python 無 I/O、耗時 < 1 ms；鎖爭用可忽略。
- **規則 1**（必須落在 implementation review）：`ObjectRegistry` 鎖內**不得** `await` 任何外部 I/O
  （檔案、網路、subprocess）；只允許純計算與 dict/dataclass 操作。否則鎖被持有跨 I/O 會破壞 SC-MS-002。
- **規則 2**：handler 的 `await request.json()`、`web.json_response()` 等 I/O 必須在鎖**外**完成；
  handler 先 parse 再 `await registry.update(...)`；registry 方法自己取鎖。

**Alternatives considered**：
- **Per-key `asyncio.Lock`（Dict[drone_id, Lock]）**：允許不同 `drone_id` 的 update 併行。缺點：
  (a) query/cleanup 仍需「鎖全部 key」才能一致 snapshot，退化為全域鎖；
  (b) N ≤ 20 下並行收益 ≈ 0，但多了 lock lifecycle 管理（何時 GC 鎖？）；
  (c) 測試覆蓋面上升。拒絕；保留作為「未來若 N >> 100 且 query 成為瓶頸」時的優化。
- **`asyncio.RLock`**：允許同一 task 重入；本設計 handler 不遞迴呼叫 registry method，不需要；拒絕。
- **讀寫鎖（`aiorwlock`）**：允許多 reader 並行、單 writer 獨佔。理論上可讓 query 併發；但 Python
  asyncio 單 loop 下「併發 reader」其實也要走同一 event loop、並無真正平行；且 query 在鎖內無 `await`，
  其他 coroutine 本來就拿不到時間片。引入外部依賴無收益；拒絕。
- **無鎖 + copy-on-write**：每次 update 建新 dict。更新頻率 100 Hz、每次複製 20 entries，成本小；但
  若 query 持有舊 snapshot 同時 cleanup 建新 snapshot，兩者對 `_objects` 的讀寫仍需 barrier；Python
  dict 無原生 atomic swap 保證（CPython 實作下 `self._objects = new_dict` 是單一 bytecode，但語言層
  面不保證）。不值得為了省一個 `asyncio.Lock` 採此路徑；拒絕。

---

## 4. Request schema 寬鬆化（pydantic `extra="ignore"`）

**Decision**：`POST /objects/update` request body 以 pydantic v2 `BaseModel` + `model_config =
ConfigDict(extra="ignore")` 定義 8 個必填欄位；額外欄位靜默忽略。解析失敗（缺必填、型別錯、非 JSON）
統一 catch 並回 `400` + 穩定 `reason` 字串。

**Rationale**：
- spec FR-MS-002 明確要求：body 包含 `model` / `operator_lat` / `operator_lon` 等 UDS 契約以外欄位時，
  Map Sim **MUST NOT** 回 400；這正是 pydantic `extra="ignore"` 的預期行為。
- 與 `services/uds/` 的 `TakeoverRequest`（`extra="forbid"`）形成有意的不對稱：UDS 作為**正式指令接收端**
  須嚴格，Map Sim 作為**內部多源資料 hub**須寬鬆，以容許未來感測器 / UDS 加欄位時不破壞 Map Sim。
- pydantic 預設錯誤訊息（`ValidationError`）欄位名、格式可能隨版本漂移；為了契約 `reason` 字串穩定，
  **不**直接把 `ValidationError.errors()` 轉成 response；handler 捕獲後以自家的 `errors.py` 映射成
  固定字串集合（見 contracts/rest-api.md §3.2.2 表格）。

**Alternatives considered**：
- `extra="allow"`：保留額外欄位進 model。無用（Map Sim 不需要），反而讓 DroneObject 塞進非預期屬性；
  拒絕。
- `extra="forbid"`：直接違反 FR-MS-002；拒絕。
- **手動 parse**（不用 pydantic）：可行但要自行校驗每個欄位型別 / 值域，重複造輪子；拒絕。

---

## 5. Query 參數解析與 `radius_m > 0` 校驗

**Decision**：`GET /objects` 的 `lat` / `lon` / `radius_m` / `include_lost` 以 aiohttp `request.query.get()`
+ 手動 `float()` / `bool` 解析 + 明確 `reason` 字串回應。不使用 pydantic（query 層沒有 schema registry
的需求，且 pydantic 的錯誤字串漂移風險同 §4）。

錯誤分類：
- 缺任一必填（`lat` / `lon` / `radius_m`）→ `reason = "missing required parameter: <name>"`
- `float()` 失敗 → `reason = "invalid type: <name>"`
- `radius_m <= 0` → `reason = "radius_m must be > 0"`
- `lat ∉ [-90, 90]` 或 `lon ∉ [-180, 180]` → `reason = "invalid coordinates"`（對齊 UDS 風格）
- `include_lost` 預設 `false`；接受 `"true"` / `"false"`（case-insensitive）；其他值 →
  `reason = "invalid type: include_lost"`

**Rationale**：穩定 `reason` 字串是契約的一部份（FR-MS-005 要求明確指出錯誤參數名）；由 handler 層完全掌
控字串內容。

**Alternatives considered**：pydantic query schema（同 §4 理由）——拒絕。

---

## 6. 時鐘與 `last_seen_at`

**Decision**：`DroneObject.last_seen_at` 於 `ObjectRegistry.update()` 內以 `datetime.now(timezone.utc)`
設定，**完全忽略** request body 的 `timestamp` 欄位（後者原樣存入 `DroneObject.timestamp`，僅供下游查
詢時回傳，不參與 TTL 計算）。

**Rationale**：
- spec §5 Assumptions 明文：「`last_seen_at` 以 Map Sim 本地時鐘為準；避免 UDS 時鐘漂移影響 TTL」。
- UDS 在極端負載下可能 tick 抖動 ±10 ms 甚至更大；若以 UDS timestamp 當 TTL 基準，SC-MS-003 / SC-MS-004
  會因 UDS 的 jitter 而難以達成。
- 測試時 `freezegun` 可統一凍結 Map Sim 端時鐘，測試可重現。

**Alternatives considered**：
- **以 UDS timestamp 當 last_seen**：違反 spec，且引入跨服務時鐘同步問題；拒絕。
- **記兩套 timestamp 都用來判 TTL**（取較晚者）：不必要的複雜度；拒絕。

---

## 7. 日誌與可觀測性

**Decision**：採用與 `services/uds/` 同風格的 `structlog` JSON logger。事件名（event key）約定：
- `update.ok` / `update.rejected`（INFO / WARNING）
- `query.ok`（DEBUG；含 `count`、`radius_m`）
- `query.rejected`（WARNING；含 `reason`）
- `ttl.cleanup`（INFO；含 `removed`，僅在 `removed > 0` 時寫）
- `health.ok`（DEBUG）
- `server.started` / `server.shutdown`（INFO）

**Rationale**：統一 event key 讓跨服務 log aggregation（未來若要）更容易。DEBUG 級 log 預設不輸出，
需 `--verbose` 開啟，避免 100 req/s 下日誌量爆炸。

---

## 8. 依賴版本鎖定（與 UDS 對齊）

| 套件 | 版本約束 | 理由 |
|------|---------|------|
| `aiohttp` | `>= 3.9` | 與 uds 一致；`asyncio.timeout()` 整合穩定 |
| `pydantic` | `>= 2.6` | 與 uds 一致；`ConfigDict` API 穩定 |
| `structlog` | `>= 24.1` | 與 uds 一致 |
| `pytest` | `>= 8.0`（[dev]）| 與 uds 一致 |
| `pytest-asyncio` | `>= 0.23`（[dev]）| `asyncio_mode = "auto"` |
| `freezegun` | `>= 1.4`（[dev]）| TTL 時序測試 |
| `ruff` / `black` | `>= 0.4` / `>= 24.3`（[dev]）| 與 uds 一致 |

**不引入**：`redis`、`sqlalchemy`、`rtree`、`aiocron`、`geopy`（runtime；tests 可選）、`geographiclib`。

---

## 9. 待決事項

無。所有 NEEDS CLARIFICATION 已由 spec.md §Clarifications Q1 解決。
