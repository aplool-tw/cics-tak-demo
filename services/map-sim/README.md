# Map Simulator (map-sim)

Anti-drone TAK PoC 的中介登錄服務：接收 UDS 推送的無人機狀態，對下游（EchoShield / Sentrycs）
以地理範圍查詢方式揭露。詳見：

- `specs/002-map-sim/spec.md`
- `specs/002-map-sim/plan.md`
- `specs/002-map-sim/contracts/rest-api.md`
- `specs/002-map-sim/quickstart.md`

## 端點摘要（預設 `http://127.0.0.1:8090`）

- `POST /objects/update` — UDS 推送 8 欄位 DroneObject
- `GET /objects?lat=&lon=&radius_m=[&include_lost=]` — 下游範圍查詢
- `GET /health` — liveness / readiness
- `GET /objects/all` — 除錯：所有登錄物件
- `DELETE /objects/{drone_id}` — 除錯：移除指定物件

## CLI

```bash
map-sim --port 8090 --ttl-warn-s 5.0 --ttl-remove-s 10.0 [--verbose]
```

| 參數 | 預設 | 說明 |
|------|------|------|
| `--port` | 8090 | HTTP server port（綁 127.0.0.1） |
| `--ttl-warn-s` | 5.0 | 超過此秒數未更新 → `is_lost=true` |
| `--ttl-remove-s` | 10.0 | 超過此秒數未更新 → 從 registry 移除 |
| `--verbose` | false | log level 切至 DEBUG |

## 開發

```bash
cd services/map-sim
pip install -e ".[dev]"
pytest
ruff check src tests
black --check src tests
```
