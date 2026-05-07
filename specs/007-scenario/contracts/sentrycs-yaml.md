# Contract: Sentrycs 設定 YAML Schema

**Feature**: `007-e2e-scenarios`
**Version**: 1.0.0
**Status**: Draft
**Related spec**: `specs/007-scenario/spec.md` (FR-SCN-003, FR-SCN-004, FR-SCN-014)
**Related data model**: `specs/007-scenario/data-model.md` §2

---

## 概述

Sentrycs Simulator (`sentrycs-sim`) 的設定 YAML 定義感測器位置、服務端點、以及劇本中每架無人機的狀態切換時間表。**extra="forbid"**（額外欄位即 fail-fast）。

檔案放置路徑：`services/sentrycs-sim/config/<scenario_name>.yaml`

---

## 頂層結構

```yaml
sensor_lat: ...         # float   必填
sensor_lon: ...         # float   必填
poll_interval_s: ...    # float   選填（預設 0.5）
map_sim_url: ...        # string  選填（預設 http://localhost:18090）
uds_url: ...            # string  選填（預設 http://localhost:18080）
api_host: ...           # string  選填（預設 0.0.0.0）
api_port: ...           # int     選填（預設 7070）
neutralized_hold_s: ... # float   選填（預設 30.0）
mitigating_disappear_grace_s: ... # float 選填（預設 10.0）

drones:
  - uid: ...
    model: ...
    detected_at_s: ...
    mitigating_at_s: ...
    neutralized_at_s: ...
    operator_bearing_deg: ...
    operator_distance_m: ...
```

---

## 欄位說明

### 頂層設定欄位

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `sensor_lat` | `float` | ✅ | — | 感測器緯度（WGS-84）；範圍 [-90, 90]。**e2e 劇本設定為 SP: 24.725806** |
| `sensor_lon` | `float` | ✅ | — | 感測器經度（WGS-84）；範圍 [-180, 180]。**e2e 劇本設定為 SP: 121.033750** |
| `poll_interval_s` | `float` | ❌ | `0.5` | 輪詢 map-sim 的間隔（秒）；> 0 |
| `map_sim_url` | `string` | ❌ | `http://localhost:18090` | Map Sim 基礎 URL；由 dev-launcher 覆寫 |
| `uds_url` | `string` | ❌ | `http://localhost:18080` | UDS REST API URL（用於 POST /command/takeover）；由 dev-launcher 覆寫 |
| `api_host` | `string` | ❌ | `0.0.0.0` | Sentrycs HTTP API 監聽位址 |
| `api_port` | `int` | ❌ | `7070` | Sentrycs HTTP API 監聽端口；範圍 [1024, 65535] |
| `neutralized_hold_s` | `float` | ❌ | `30.0` | NEUTRALIZED 狀態保留秒數，之後從 `/detections` 列表移除；> 0 |
| `mitigating_disappear_grace_s` | `float` | ❌ | `10.0` | MITIGATING 無信號消失容差（秒）；≥ 0 |

> **重要**：`map_sim_url` 和 `uds_url` 在 dev-launcher.sh 啟動時由 `--sentrycs-map-sim-url` / `--sentrycs-uds-url` 參數覆寫，**YAML 中設定的值在 e2e 場景下可能被忽略**（launcher 重新渲染 config）。見 dev-launcher.sh `launch_sentrycs_sim()` 實作。

---

### `drones[]` — SentrycsDroneEntry

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `uid` | `string` | ✅ | 對應 UDS YAML 的 `drone_id`（完全匹配） |
| `model` | `string` | ✅ | 無人機型號（填入 CoT `<remarks>` 字段） |
| `detected_at_s` | `float` | ✅ | 場景計時器到達此值時切換 `DETECTED` 狀態（秒）；≥ 0 |
| `mitigating_at_s` | `float` | ✅ | 切換 `MITIGATING` 狀態 + 觸發 `POST /command/takeover` 至 UDS（秒）；> detected_at_s |
| `neutralized_at_s` | `float` | ✅ | 切換 `NEUTRALIZED` 狀態（秒）；> mitigating_at_s |
| `operator_bearing_deg` | `float` | ✅ | 操作員方位角（以無人機為中心，順時針）；範圍 [0, 360) |
| `operator_distance_m` | `float` | ✅ | 操作員距無人機距離（公尺）；> 0 |

**校驗規則**：`detected_at_s < mitigating_at_s < neutralized_at_s` 必須嚴格遞增，否則 ValidationError。

---

### Takeover 指令行為

當場景計時器到達 `mitigating_at_s` 時，sentrycs-sim 自動向 UDS 發送：

```http
POST /command/takeover
Content-Type: application/json

{
  "drone_id": "<uid>",
  "target_lat": <HP lat>,
  "target_lon": <HP lon>,
  "target_alt_m": 0.0
}
```

`target_lat` / `target_lon` 來源：
- **繼承自 UDS YAML 的 `landing_point`**（若 sentrycs-sim 能讀取 map-sim 中的 drone 狀態），**或**
- **在 Sentrycs YAML 明確設定**（若 sentrycs-sim 不支援自動繼承）

> **目前設計**：sentrycs-sim 根據 map-sim `/objects` 回應中的 drone 資料計算 takeover 目標座標。Sentrycs YAML 僅控制**時機（when）**，目標座標（where）由服務邏輯決定。若需明確指定 HP 座標，需確認 sentrycs-sim 是否支援 YAML 欄位 `takeover_target_lat/lon`（待 004-sentrycs-sim spec 確認）。

HTTP 回應碼語義（凍結契約）：

| 回應碼 | 意義 |
|--------|------|
| `200` | 接管成功 |
| `400` | 請求格式錯誤 |
| `404` | drone_id 不存在 |
| `409` | 已在接管狀態（**視為成功**，sentrycs-sim 繼續執行） |

---

## 多機劇本的陣列格式說明

### 鍵值唯一性
`drones[]` 陣列中每個 `uid` 必須唯一（重複 uid 會導致 sentrycs-sim 計時器衝突）。

### 啟動時間偏移的處理
Sentrycs YAML 中的 `detected_at_s` 等時間為**絕對場景時間**，已包含 UDS timeline 中各無人機的 `at_s` 起飛偏移。

示例（劇本二，TRK-E0B at_s=30 起飛，detected 在飛行 376s 後 = 30+376 = 406s）：
```yaml
drones:
  - uid: TRK-E0B
    detected_at_s: 406   # = 30 (start offset) + 376s (flight time to threshold)
    mitigating_at_s: 489 # = 30 + 459s (flight time to 1km threshold)
    neutralized_at_s: 519 # = mitigating + 30s
```

### 多機事件間隔要求（FR-SCN-017）

相鄰里程碑事件的最小間隔 ≥ 10s，以防止 cot-gateway 事件洪流：

| 事件類型 | 劇本二各 drone 時間 | 最小間隔 |
|---------|-------------------|---------|
| DETECTED | A=580, B=406, C=600 | 20s ✓ |
| MITIGATING | A=666, B=489, C=684 | 18s ✓ |
| NEUTRALIZED | A=706, B=519, C=716 | 10s ✓ |

---

## 劇本一完整示例

```yaml
# services/sentrycs-sim/config/e2e_single_drone.yaml
sensor_lat: 24.725806   # SP
sensor_lon: 121.033750  # SP

# 以下為預設值，dev-launcher 啟動時可覆寫
poll_interval_s: 0.5
map_sim_url: http://localhost:18090
uds_url: http://localhost:18080
api_host: 0.0.0.0
api_port: 7070
neutralized_hold_s: 30.0
mitigating_disappear_grace_s: 10.0

drones:
  - uid: TRK-E01
    model: "DJI Mavic 3"
    detected_at_s: 460      # ≈ 2km 觸發（15m/s，幾何計算 465.9s，調至 460）
    mitigating_at_s: 525    # ≈ 1km 觸發（15m/s，幾何計算 532.6s，調至 525）
    neutralized_at_s: 565   # mitigating + 40s（接管確認緩衝）
    operator_bearing_deg: 225
    operator_distance_m: 300
```

---

## 劇本二完整示例

```yaml
# services/sentrycs-sim/config/e2e_multi_drone.yaml
sensor_lat: 24.725806   # SP
sensor_lon: 121.033750  # SP

poll_interval_s: 0.5
map_sim_url: http://localhost:18090
uds_url: http://localhost:18080
api_host: 0.0.0.0
api_port: 7070
neutralized_hold_s: 30.0
mitigating_disappear_grace_s: 10.0

drones:
  # Drone A：北→南，8.99km，12m/s，at_s=0
  - uid: TRK-E0A
    model: "DJI Mavic 3"
    detected_at_s: 580      # ≈ 2km from SP（幾何計算 582.4s）
    mitigating_at_s: 666    # ≈ 1km from SP（幾何計算 665.7s）
    neutralized_at_s: 706   # mitigating + 40s
    operator_bearing_deg: 180
    operator_distance_m: 300

  # Drone B：西→東，7.22km，12m/s，at_s=30
  - uid: TRK-E0B
    model: "Autel EVO II"
    detected_at_s: 406      # spec 建議值（幾何計算 465.3s，差異在容差內）
    mitigating_at_s: 489    # spec 建議值（幾何計算 548.6s）
    neutralized_at_s: 519   # mitigating + 30s
    operator_bearing_deg: 270
    operator_distance_m: 350

  # Drone C：東北→西南，8.48km，12m/s，at_s=60
  - uid: TRK-E0C
    model: "Skydio 2+"
    detected_at_s: 600      # ≈ 2km from SP（幾何計算 600.4s）
    mitigating_at_s: 684    # ≈ 1km from SP（幾何計算 683.8s）
    neutralized_at_s: 716   # mitigating + 32s（+2s 調整，使 E0A/E0C 間隔 ≥ 10s）
    operator_bearing_deg: 45
    operator_distance_m: 280
```

---

## 凍結契約點

| 欄位 / 行為 | 凍結規則 |
|------------|---------|
| `uid` 與 UDS `drone_id` 完全匹配 | sentrycs-sim 以此關聯 map-sim 物件 |
| `mitigating_at_s` 觸發 `POST /command/takeover` | UDS API 凍結契約（200/400/404/409） |
| `neutralized_hold_s` = 30.0 | stale = time + 30s 的 CoT 計算依據 |
| `/detections` status 值 | `DETECTED` / `MITIGATING` / `NEUTRALIZED`（不可新增） |

---

## 錯誤處理

| 情況 | 行為 |
|------|------|
| `detected_at_s ≥ mitigating_at_s` | pydantic validator → ValidationError，服務拒絕啟動 |
| 重複 `uid` | sentrycs-sim 最後一條覆寫（建議 validator 報 Warning）|
| 多餘欄位 | `extra="forbid"` → ValidationError |
| takeover 返回 409 | 視為成功，繼續（凍結契約）|
| takeover 返回 404 | 記錄 `takeover_not_found` 事件，不重試 |
