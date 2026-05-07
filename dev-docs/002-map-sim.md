# Feature 002 — Map Simulator 開發紀錄

| 欄位 | 內容 |
|------|------|
| Feature ID | 002 |
| 分支 | `002-map-sim` → `develop` |
| 日期 | 2026-04-24 |
| 狀態 | 已實作、測試通過（102/102） |

## 一、範圍

感測層的物件狀態中央登錄表。接收 UDS push、提供地理圓形查詢給 EchoShield / Sentrycs Sim、管理 TTL 過期。

實作位置：`services/map-sim/`。

## 二、Speckit 產出
- `specs/002-map-sim/{spec,plan,data-model,research,contracts/rest-api,quickstart,tasks}.md`
- 74 tasks 分 11 phases，全數完成

## 三、關鍵技術決策

1. **Q1 Clarification**：`GET /objects` 回應中 `status` 欄位**絕不**被覆寫為 `"lost"`，改用獨立布林 `is_lost` 表達 TTL 狀態（`last_seen_s ≥ ttl_warn_s`）。原始 FlightState 保留。
2. **併發**：單一全域 `asyncio.Lock` 保護 ObjectRegistry；鎖內禁止 await I/O。
3. **TTL**：warn 預設 5 s、remove 預設 10 s，CLI `--ttl-warn-s` / `--ttl-remove-s` 可覆寫；背景 task 週期 2 s。
4. **寬鬆 payload**：pydantic `extra="ignore"`，接受 UDS 8 欄位 + 未知欄位（model/operator_* 等）。
5. **副作用隔離（FR-MS-015）**：所有 400 分支在呼叫 `registry.update` 前 return；11 個 case 把關。
6. **query_radius 主動排除** `age_s ≥ ttl_remove_s`，覆蓋背景 cleanup 時差窗口。

## 四、檔案異動摘要

```
services/map-sim/
├── pyproject.toml, README.md, scripts/smoke.sh
├── src/map_sim/
│   ├── __main__.py, cli.py, config.py, logging.py
│   ├── geo/haversine.py            獨立實作 R=6_371_000
│   ├── models/drone_object.py      DroneObject + serialize()
│   ├── models/request.py           UpdatePayload (extra="ignore")
│   ├── registry/object_registry.py 全域 Lock
│   ├── cleanup/ttl_task.py         背景清理 task
│   └── api/{server,errors,handlers_update,handlers_query,handlers_admin}.py
└── tests/                          102 tests（contract 57、integration 22、unit 23）
```

## 五、Known Issues / Gotchas

1. **ruff / black 未在本環境實際執行**（T074 僅設定 pyproject.toml 規則）；測試完整覆蓋正確性，格式檢查可在獨立 venv 後補。
2. **pydantic v2 接受 naive datetime**（解析為 UTC），`test_update_invalid_timestamp` 用明顯壞格式測 400；`"not-a-timestamp"` 把關。
3. **獨立 haversine**：不跨 service import；與 UDS 的實作常數（R=6_371_000）一致，誤差 <0.5%。
4. **freezegun 測試時序**：`cleanup_period` 在測試中覆寫至 0.05 s 避免實際等待。

## 六、驗收指令

```bash
cd services/map-sim
pip install -e ".[dev]"
python3 -m pytest               # 102 passed (~3s)
python3 -m map_sim --port 18090  # 啟動 http://127.0.0.1:18090
```

## 七、下游介面契約（003 / 004 會呼叫）

**POST /objects/update**：接受 UDS 8 欄位 + 未知欄位（寬鬆）；回 200 `{status:"updated", drone_id, registered_at}`。

**GET /objects?lat=&lon=&radius_m=[&include_lost=false]**：回 `{query, count, objects:[...]}`；每物件含 `drone_id, lat, lon, alt_m, speed_ms, heading_deg, status, last_seen_s, distance_m, is_lost}`；`status` 為原始 FlightState，永不被覆寫；依 `distance_m` 升冪排序。

**GET /health**：回 `{status:"ok", uptime_s, object_count}`。

典型使用：
- EchoShield Sim：`GET /objects?lat=<radar_lat>&lon=<radar_lon>&radius_m=4800`
- Sentrycs Sim：`GET /objects?lat=<rf_lat>&lon=<rf_lon>&radius_m=8000`
