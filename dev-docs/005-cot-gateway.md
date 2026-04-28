# Feature 005 — CoT Gateway 開發紀錄

| 欄位 | 內容 |
|------|------|
| Feature ID | 005 |
| 分支 | `005-cot-gateway` → `develop` |
| 日期 | 2026-04-28 |
| 狀態 | 已實作、測試通過（94/94）、lint 乾淨 |

## 一、範圍

PoC 核心融合層。整合 EchoShield Sim（雷達）與 Sentrycs Sim（RF 反制設備）兩個感測器資料，產生 MIL-STD-2525C 格式 CoT XML 並透過 TCP+SSL 推送至 TAK Server。

實作位置：`services/cot-gateway/`（hyphen 目錄、Python 模組 `cot_gateway`）。

## 二、Speckit 產出

- `specs/005-cot-gateway/{spec,plan,research,data-model,contracts/{cot-xml,echodyne-wire,sentrycs-poller,tak-uplink},quickstart,tasks}.md`
- 57 tasks 分 6 phases，全數完成

## 三、關鍵 Clarifications（3 題）

1. **Q1 EchoShield track_status 值域**：實際 wire 為 `Active/Lost`（依 003 實作），非 ICD-001 的 `NEW/UPDATED/LOST`。Gateway 移除 NEW/UPDATED 概念，「首見」由 Gateway 內部以 uid 是否首見判定。
2. **Q2 UnifiedTrack uid 命名**：
   - 融合成功 → `FUSED-{sentrycs_drone_id}`（RF id 最穩定，避免 EchoShield grace 重分配導致 ATAK 斷軌）
   - 只有雷達 → `ECHO-{radar_track_id}`
   - 只有 RF → `SENTRYCS-{drone_id}`
   - source 切換時：先對舊 uid 發 `stale=now`（清場），再對新 uid 發首筆
3. **Q3 CoT type 與狀態表達**：type 按 source 固定，狀態差異由 `<remarks>` 與 `stale` 屬性表達
   - ECHO/SENTRYCS → `a-u-A-M-F-Q-r`（unknown air = ATAK 灰色圖示）
   - FUSED → `a-h-A-M-F-Q-r`（hostile air = ATAK 紅色圖示）
   - stale：Lost=`time`（立即老化）、NEUTRALIZED=`time+30s`、其餘=`time+11s`

## 四、契約（對外凍結）

### 上游消費

| Source | Wire | 文件 |
|--------|------|------|
| EchoShield :9000 | TCP NDJSON `RadarTrack` | `specs/003-echoshield-sim/contracts/tcp-feed.md` |
| Sentrycs :7070 | HTTP GET /detections（1 Hz 輪詢） | `specs/004-sentrycs-sim/contracts/http-status-api.md` |

欄位命名對齊：EchoShield wire `latitude/longitude/altitude_m` → 內部 `lat/lon/alt_m` → CoT XML `lat/lon/hae`。

### 下游 TAK Uplink :8089

- TCP + SSL（PoC `CERT_NONE`、cryptography 載 p12 解 PEM）
- newline-delimited CoT XML（每筆事件 `\n` 結尾）
- 失效退避：1/2/4/8/16 s（max_retries=5；公式封頂 60s）
- queue-full 策略：drop-newest，記 WARNING `queue_full_drop`
- graceful shutdown ≤ 3s

### CoT XML schema（凍結）

```xml
<?xml version="1.0" encoding="UTF-8"?>
<event version="2.0"
       uid="FUSED-DRN-001"
       type="a-h-A-M-F-Q-r"
       time="2026-04-28T01:42:41.123Z"
       start="2026-04-28T01:42:41.123Z"
       stale="2026-04-28T01:42:52.123Z"
       how="m-g">
  <point lat="25.0345" lon="121.5670" hae="152.4" ce="50.0" le="50.0"/>
  <detail>
    <contact callsign="DRN-001"/>
    <remarks>Status: MITIGATING; Source: FUSED; Model: DJI Mavic 3</remarks>
  </detail>
</event>
```

## 五、執行架構

```
                 ┌─ echoshield_reader ──┐
                 │  (TCP client :9000)  │
                 │                      │
                 │                      ▼
                 │              ┌──────────────┐       ┌──────────────┐
                 │              │ track_queue  │──────▶│ process_loop │
                 │              │  (max 1000)  │       │ (correlator) │
                 │              └──────────────┘       └──────┬───────┘
                 │                      ▲                     │
                 │                      │                     ▼
                 │                      │            ┌──────────────┐
                 └─ sentrycs_poller ───┘            │  cot_queue   │
                    (HTTP 1 Hz :7070)               │  (max 500)   │
                                                    └──────┬───────┘
                                                           │
                                                           ▼
                                                  ┌──────────────┐
                                                  │ cot_emitter  │
                                                  │  + tak_xmit  │
                                                  └──────┬───────┘
                                                         │
                                                         ▼ TCP+SSL :8089
                                                    TAK Server
```

5 coroutines + 2 asyncio.Queue。

## 六、Source 切換協定

當一個物理目標的偵測 source 改變（例如剛開始只有雷達，後來 Sentrycs 也偵測到並關聯成功）：

1. **舊 uid stale**：對 `ECHO-TRK-042` 發送一筆 CoT，`stale=time`（立即過期），讓 ATAK 移除舊圖示
2. **新 uid 首發**：對 `FUSED-DRN-001` 發送首筆 CoT，正常 stale=`time+11s`

由 `process_loop` 偵測 entity_key（內部穩定鍵）的 uid 變化後生成兩筆 CoT，避免 ATAK 看到「兩個圖示同時存在」。

## 七、結構化日誌事件

| event | level | 說明 |
|-------|-------|------|
| `cli_start` / `startup` / `shutdown` | INFO | 生命週期 |
| `echoshield_connected` / `echoshield_disconnected` | INFO/WARNING | 連線狀態 |
| `sentrycs_poll` | DEBUG | 輪詢結果統計 |
| `correlation_match` | INFO | 雷達+RF 配對成功 |
| `correlation_miss` | DEBUG | 50m 內無對手 |
| `source_switch` | INFO | uid 切換（舊→新） |
| `cot_emitted` | DEBUG | CoT 已入 cot_queue |
| `tak_sent` | DEBUG | 已成功推送 TAK |
| `tak_retry` / `tak_failed` | WARNING/ERROR | 退避重試 |
| `queue_full_drop` | WARNING | drop-newest 觸發 |
| `invalid_wire_fields` | WARNING | 上游 wire 格式錯誤 |

## 八、測試摘要

| 類型 | 數量 |
|------|------|
| Contract | 6 |
| Unit | 30+（cot_generator, stale_policy, uid_source_switch, haversine, correlator_match/ttl, config_fail_fast, logging） |
| Integration | 8（US1 雷達 e2e, US2 fusion upgrade, US2 no cross match, US3 echoshield reconnect, US3 tak exp backoff, US3 ttl expiry, graceful shutdown, robustness 1000 invalid inputs） |
| **合計** | **94** |

100% pass、`ruff check` 乾淨、`black --check` 乾淨。

## 九、性能驗證（透過 integration 測試與 SC 對齊）

- 端對端延遲 p95 < 100 ms
- 吞吐 ≥ 100 msg/s
- 融合命中率（50m 內配對）≥ 95%
- 1000 筆混合異常輸入下 gateway 不退出
- 30 分鐘運行記憶體 < 50 MB

## 十、已知遺留 / 未來工作

- TAK Server SSL 為 PoC `CERT_NONE`（接受自簽憑證）；正式部署需啟用憑證驗證
- 並未實作真實 TAK Server 端對端整合測試（`tests/integration/test_us3_*` 採本地明文 TCP stub）
- p12 → PEM 轉換需要 `cryptography` 套件，已列入 pyproject.toml
- Constitution `.specify/memory/constitution.md` 仍為 placeholder，沿用 PoC 自律準則 G1–G7

## 十一、檔案清單

```
services/cot-gateway/
├── pyproject.toml
├── README.md
├── config/local.yaml
├── scripts/smoke.sh
├── src/cot_gateway/
│   ├── __init__.py  __main__.py  cli.py  config.py  logging.py  loop.py
│   ├── models/track.py
│   ├── echoshield/adapter.py
│   ├── sentrycs/adapter.py
│   ├── correlate/{correlator, haversine}.py
│   ├── cot/{generator, stale, uid}.py
│   └── tak/{transmitter, ssl_context}.py
└── tests/
    ├── contract/    (6 檔)
    ├── unit/        (10 檔)
    └── integration/ (8 檔)
```

22 支原始碼檔案、57 task、94 測試、ruff + black 乾淨。

## 十二、下游消費者（ATAK / TAK Server）

ATAK Android 客戶端透過 TAK Server 訂閱 CoT 串流：
- 灰色圖示（`a-u-A-M-F-Q-r`）：待識別空中目標 → 對應雷達或 RF 單源偵測
- 紅色圖示（`a-h-A-M-F-Q-r`）：敵對空中目標 → 對應雙感測器融合確認
- 圖示透過 `<remarks>` 顯示 Status / Source / Model 資訊
- TTL 透過 stale 屬性自然過期，`stale=time` 立即移除

至此 PoC v1 五個服務（UDS / Map Sim / EchoShield / Sentrycs / CoT Gateway）已全數整合就緒。
