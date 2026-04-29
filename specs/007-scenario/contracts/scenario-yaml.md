# Contract: UDS 劇本 YAML Schema

**Feature**: `007-e2e-scenarios`
**Version**: 1.0.0
**Status**: Draft
**Related spec**: `specs/007-scenario/spec.md` (FR-SCN-001～FR-SCN-020)
**Related data model**: `specs/007-scenario/data-model.md` §1

---

## 概述

UDS（Unmanned Detection Service）劇本 YAML 定義一組無人機的起始狀態、飛行路徑及時間軸事件。本 schema 為 `pydantic v2` 強型別設計，**extra="forbid"**（額外欄位即 fail-fast）。

檔案放置路徑：`services/uds/scenarios/<scenario_name>.yaml`

---

## 頂層結構

```yaml
scenario:          # <ScenarioBody>  必填
  name: ...
  description: ...
  update_hz: ...
  servers:
    command_api_port: ...
  drones:
    - ...
  timeline:
    - ...
```

---

## SchemaDetails

### `scenario` — ScenarioBody（必填）

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `name` | `string` | ✅ | — | 劇本識別名稱（建議 slug 格式，例 `e2e_single_drone_invasion`） |
| `description` | `string` | ✅ | — | 自然語言說明 |
| `update_hz` | `float` | ❌ | `10.0` | UDS 主迴圈更新率（Hz）；範圍 (0, 100] |
| `servers` | `ServersConfig` | ❌ | 見下 | 服務端口設定 |
| `drones` | `DroneProfile[]` | ✅ | — | 最少 1 架，無上限 |
| `timeline` | `TimelineEvent[]` | ✅ | — | 最少 1 個事件 |

**校驗規則**：`timeline` 中所有 `drone_id` 必須存在於 `drones` 陣列中。

---

### `scenario.servers` — ServersConfig

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `command_api_port` | `int` | ❌ | `8080` | UDS REST API 監聽端口；範圍 [1024, 65535] |

---

### `scenario.drones[]` — DroneProfile（必填項目）

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `drone_id` | `string` | ✅ | — | 系統唯一識別，與 sentrycs YAML `uid` 對應。格式建議 `TRK-XXXX` |
| `model` | `string` | ✅ | — | 無人機型號（傳遞給 Sentrycs `remarks`），例 `"DJI Mavic 3"` |
| `start_lat` | `float` | ✅ | — | 起點緯度，WGS-84 十進位度，精度 ≥ 6 位小數。範圍 [-90, 90] |
| `start_lon` | `float` | ✅ | — | 起點經度，WGS-84 十進位度，精度 ≥ 6 位小數。範圍 [-180, 180] |
| `start_alt_m` | `float` | ✅ | — | 起始高度（公尺 AGL）；≥ 0.0 |
| `speed_ms` | `float` | ✅ | — | 巡航速度（m/s）；範圍 (0, 100] |
| `heading_deg` | `float` | ✅ | — | 航向（真北 = 0°，順時針）；範圍 [0, 360) |
| `operator_bearing_deg` | `float` | ✅ | — | 操作員方位角（以無人機為中心，順時針）；範圍 [0, 360) |
| `operator_distance_m` | `float` | ✅ | — | 操作員距無人機距離（公尺）；> 0 |
| `waypoints` | `Waypoint[]` | ❌ | `[]` | 飛行路徑中繼點列表 |
| `landing_point` | `LandingPoint \| null` | ❌ | `null` | 接管後降落目標座標（HP 座標）；見 FR-SCN-009 |

---

### `scenario.drones[].waypoints[]` — Waypoint

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `lat` | `float` | ✅ | 緯度；WGS-84，精度 ≥ 6 位小數 |
| `lon` | `float` | ✅ | 經度；WGS-84，精度 ≥ 6 位小數 |
| `alt_m` | `float` | ✅ | 高度（公尺 AGL）；≥ 0 |

**YAML inline 格式**（單行可讀）：
```yaml
waypoints:
  - { lat: 24.725806, lon: 121.033750, alt_m: 150.0 }
```

---

### `scenario.drones[].landing_point` — LandingPoint

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `lat` | `float` | ✅ | — | 降落目標緯度 |
| `lon` | `float` | ✅ | — | 降落目標經度 |
| `alt_m` | `float` | ❌ | `0.0` | 降落目標高度（通常為 0） |
| `descent_speed_ms` | `float` | ❌ | `3.0` | 垂直降落速度（m/s）；> 0 |

---

### `scenario.timeline[]` — TimelineEvent

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `at_s` | `float` | ✅ | 觸發時間（場景計時器秒數）；≥ 0 |
| `action` | `string` | ✅ | 事件類型；目前唯一合法值：`"start_flying"` |
| `drone_id` | `string` | ✅ | 目標無人機 ID，必須存在於 `drones` 陣列 |

---

## 劇本一：e2e_single_drone_invasion 完整示例

```yaml
scenario:
  name: "e2e_single_drone_invasion"
  description: "劇本一：TRK-E01 從北方 8.99km 處南向滲透 SP（24.725806, 121.033750），
    EchoShield 在 3km 偵測（t≈399s），Sentrycs DETECTED 在 2km（t≈460s），
    接管指令在 1km（t≈525s），目標 HP（24.725806, 121.071889）"
  update_hz: 10
  servers:
    command_api_port: 8080

  drones:
    - drone_id: "TRK-E01"
      model: "DJI Mavic 3"
      start_lat: 24.806556
      start_lon: 121.033750
      start_alt_m: 150.0
      speed_ms: 15.0
      heading_deg: 180.0
      operator_bearing_deg: 225
      operator_distance_m: 300
      waypoints:
        - { lat: 24.725806, lon: 121.033750, alt_m: 150.0 }  # SP（原始入侵終點）
      landing_point:
        lat: 24.725806      # HP 緯度（= SP 緯度）
        lon: 121.071889     # HP 經度（SP 正東方 ~3.86 km）
        alt_m: 0.0
        descent_speed_ms: 3.0

  timeline:
    - at_s: 0
      action: start_flying
      drone_id: "TRK-E01"
```

### 劇本一里程碑時間表

| 里程碑 | at_s（精確計算） | 說明 |
|--------|----------------|------|
| M1 | 0 | TRK-E01 起飛；map-sim 首次推送 |
| M2 | ≈ 386 | EchoShield 偵測（drone 進入 3200m 感測圈）；計算：(8989-3200)/15 = 385.9s |
| M3 | 460（spec 建議） | Sentrycs DETECTED（≈ 2km 觸發）|
| M4 | 525（spec 建議） | Sentrycs MITIGATING + 接管指令至 UDS |
| NEUTRALIZED | 565 | Sentrycs 標注 NEUTRALIZED |
| LANDED | ≈ 841 | UDS 無人機抵達 HP ±50m（估算） |

---

## 劇本二：e2e_multi_drone 完整示例

```yaml
scenario:
  name: "e2e_multi_drone_invasion"
  description: "劇本二：三架無人機（TRK-E0A 北→南、TRK-E0B 西→東、TRK-E0C 東北→西南）
    同時滲透 SP，各自在 1km 處接管，目標均為 HP（24.725806, 121.071889）"
  update_hz: 10
  servers:
    command_api_port: 8080

  drones:
    - drone_id: "TRK-E0A"
      model: "DJI Mavic 3"
      start_lat: 24.806556
      start_lon: 121.033750
      start_alt_m: 120.0
      speed_ms: 12.0
      heading_deg: 180.0
      operator_bearing_deg: 180
      operator_distance_m: 300
      waypoints:
        - { lat: 24.725806, lon: 121.033750, alt_m: 120.0 }  # SP
      landing_point:
        lat: 24.725806
        lon: 121.071889
        alt_m: 0.0
        descent_speed_ms: 3.0

    - drone_id: "TRK-E0B"
      model: "Autel EVO II"
      start_lat: 24.725806
      start_lon: 120.962306
      start_alt_m: 130.0
      speed_ms: 12.0
      heading_deg: 90.0
      operator_bearing_deg: 270
      operator_distance_m: 350
      waypoints:
        - { lat: 24.725806, lon: 121.033750, alt_m: 130.0 }  # SP
      landing_point:
        lat: 24.725806
        lon: 121.071889
        alt_m: 0.0
        descent_speed_ms: 3.0

    - drone_id: "TRK-E0C"
      model: "Skydio 2+"
      start_lat: 24.784500
      start_lon: 121.087278
      start_alt_m: 140.0
      speed_ms: 12.0
      heading_deg: 225.0
      operator_bearing_deg: 45
      operator_distance_m: 280
      waypoints:
        - { lat: 24.725806, lon: 121.033750, alt_m: 140.0 }  # SP
      landing_point:
        lat: 24.725806
        lon: 121.071889
        alt_m: 0.0
        descent_speed_ms: 3.0

  timeline:
    - { at_s: 0,  action: start_flying, drone_id: "TRK-E0A" }
    - { at_s: 30, action: start_flying, drone_id: "TRK-E0B" }
    - { at_s: 60, action: start_flying, drone_id: "TRK-E0C" }
```

### 劇本二里程碑時間表

| Drone | M1（at_s） | M2 EchoShield | M3 DETECTED | M4 MITIGATING | NEUTRALIZED |
|-------|-----------|--------------|-------------|--------------|------------|
| TRK-E0A | 0 | ≈ 499 | 580 | 666 | 706 |
| TRK-E0B | 30 | ≈ 382 | 406 | 489 | 519 |
| TRK-E0C | 60 | ≈ 517 | 600 | 684 | 716 |

> **注意 E0C neutralized_at_s = 716**（spec 原值 714，調整 +2s 使 E0A/E0C 間隔 ≥ 10s 符合 FR-SCN-017）

---

## 凍結契約點

下列欄位為跨服務 wire contract，**不得** breaking change：

| 欄位 | 凍結值 / 規則 |
|------|------------|
| `drone_id` | UDS push 到 map-sim 的 8 欄位之一 |
| `start_lat/lon/alt_m` | 決定 EchoShield 初始偵測時機 |
| `landing_point.lat/lon` | 決定 sentrycs takeover 的 `target_lat/lon` |
| `timeline[].action` | 目前白名單只有 `"start_flying"` |

---

## 錯誤處理

| 情況 | 行為 |
|------|------|
| 多餘欄位（extra keys） | pydantic `extra="forbid"` → ValidationError，服務拒絕啟動 |
| `timeline.drone_id` 不在 `drones` 中 | `model_validator` → ValidationError |
| `detected_at_s ≥ mitigating_at_s` | Sentrycs YAML validator → ValidationError |
| 座標超出 WGS-84 範圍 | pydantic `ge/le` constraint → ValidationError |
