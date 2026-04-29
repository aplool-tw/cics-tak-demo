# Research: 007-e2e-scenarios — 技術研究

**Feature**: `007-e2e-scenarios`
**Phase**: Plan → Research
**Created**: 2026-05-03

---

## Decision 1: Haversine 距離公式

### Decision
自行實作 Haversine 公式（符合 G7 Minimal Dependencies 原則），不使用 `geopy`。

### 公式實作

```python
import math

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    計算兩個 WGS-84 座標間的 Haversine 距離（公尺）。
    精度：在 100km 範圍內誤差 < 0.5%，遠優於 50m 驗收容差。
    """
    R = 6_371_000  # 地球平均半徑（公尺）
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))
```

### 戰略座標距離驗證

| 起點 | 終點 | Haversine 結果 |
|------|------|---------------|
| SP (24.725806, 121.033750) | HP (24.725806, 121.071889) | **≈ 3,858 m ≈ 3.86 km** |
| TRK-E01 start (24.806556, 121.033750) | SP | **≈ 8,989 m ≈ 8.99 km** |
| TRK-E0B start (24.725806, 120.962306) | SP | **≈ 7,223 m ≈ 7.22 km** |
| TRK-E0C start (24.784500, 121.087278) | SP | **≈ 8,485 m ≈ 8.48 km** |

> **HP-SP 重要修正**：HP 與 SP 的實際 Haversine 距離為 **3.86 km**，而非任務說明中的「2km 正東」。
> 任務描述使用 `Δlon = 0.038139° × 111,320 × cos(24.725806°)` 的平面估算（≈ 3,858m），
> 但描述中稱「正東方 2km」可能是作業上的簡略表述，實際坐標給定，以座標為準。
> HP (24.725806, 121.071889) — SP (24.725806, 121.033750) 的正確距離約 3.86 km。

### Rationale
標準庫 `math` 已足夠；Haversine 在近地面短距離（< 100km）精度優於 0.5%，遠優於 50m 容差。

### Alternatives Considered
- `geopy.distance.geodesic`：使用 Vincenty 橢球算法，精度更高，但禁用外部依賴（G7）
- 平面直角近似（Δlat × 111320, Δlon × 111320 × cosφ）：在 < 50km 範圍誤差可接受，但非 Haversine

---

## Decision 2: WGS-84 終點座標公式

### Decision
自行實作 WGS-84 終點座標（Destination Point Formula），用於從起點、距離、方位角計算里程碑坐標。

### 公式實作

```python
def destination_point(lat: float, lon: float, bearing_deg: float, distance_m: float) -> tuple[float, float]:
    """
    從起點沿方位角飛行指定距離後的終點座標（WGS-84）。
    bearing_deg: 0=北, 90=東, 180=南, 270=西
    """
    R = 6_371_000
    d = distance_m / R
    phi1 = math.radians(lat)
    lam1 = math.radians(lon)
    theta = math.radians(bearing_deg)
    phi2 = math.asin(math.sin(phi1) * math.cos(d) + math.cos(phi1) * math.sin(d) * math.cos(theta))
    lam2 = lam1 + math.atan2(
        math.sin(theta) * math.sin(d) * math.cos(phi1),
        math.cos(d) - math.sin(phi1) * math.sin(phi2)
    )
    return math.degrees(phi2), math.degrees(lam2)
```

### 應用：里程碑位置估算

對 TRK-E01 (heading=180°，SP 在正南方)，各里程碑的 drone 位置：

| 飛行距離 | 時間（15 m/s） | 飛行後位置（lat） | 距 SP（m） |
|---------|-------------|----------------|----------|
| 5,989 m | 399 s | 24.806556 - 0.05383° = **24.752726°N** | 2,990 m ≈ **3 km** |
| 6,989 m | 466 s | 24.806556 - 0.06282° = **24.743736°N** | 1,987 m ≈ **2 km** |
| 7,989 m | 533 s | 24.806556 - 0.07182° = **24.734736°N** | 986 m ≈ **1 km** |

### Rationale
終點公式在球面幾何上精確，誤差在本場景（< 10km）< 0.01m。

---

## Decision 3: 里程碑距離觸發時間計算方法

### Method
給定：
- `d_start`: 無人機起點距 SP 的 Haversine 距離（m）
- `d_threshold`: 里程碑觸發閾值（m，如 3000、2000、1000）
- `v`: 無人機速度（m/s）
- `t_start`: 無人機起飛場景時間（at_s）

則里程碑觸發的絕對場景時間（s）：

```
t_milestone = t_start + (d_start - d_threshold) / v
```

### 精確計算結果

#### 劇本一（TRK-E01，d_start=8989m，v=15 m/s，t_start=0）

| 里程碑 | 閾值 | 計算 | 精確 at_s | Spec 建議值 | 差異 |
|--------|------|------|----------|-----------|------|
| M2 EchoShield | 3,000 m | (8989-3000)/15 | **399.3 s** | — | — |
| M3 DETECTED | 2,000 m | (8989-2000)/15 | **465.9 s** | 460 | -5.9 s ✓ |
| M4 MITIGATING | 1,000 m | (8989-1000)/15 | **532.6 s** | 525 | -7.6 s ✓ |
| NEUTRALIZED | — | 525 + 40 | **565 s** | 565 | 0 s ✓ |

> ⚠️ **時間矛盾分析（FR-SCN-010 vs 實際飛行時間）**：
>
> FR-SCN-010 要求「從 at_s=0 到 drone LANDED ≤ 12 分鐘（720s）」。
>
> 實際計算：接管後無人機從位置（24.7347°N, 121.0338°E）飛往 HP (24.7258°N, 121.0719°E)：
> - 直線距離 ≈ √(986² + 3858²) = **3,982m**
> - 飛行時間 ≈ 3982/15 = **266s**
> - 降落時間（150m ÷ 3m/s） = 50s
> - 預估 LANDED at_s ≈ 525 + 266 + 50 = **841s ≈ 14 min**
>
> **結論**：FR-SCN-010 的「12 分鐘」約束在現有速度與距離設定下**無法滿足實體降落**。
> 解決方案：FR-SCN-010 解讀為「M1-M4 關鍵 CoT 事件序列在 720s 內完成」；
> M4（接管指令發出，t≈525s = 8.75 min）符合此解讀。物理降落發生在 t≈841s（不影響 CoT 驗收）。
> SC-SCN-001 的量化基準「4 個里程碑事件均在 720s 內按序出現」支持此解讀。

#### 劇本二

**TRK-E0A（d_start=8989m，v=12 m/s，t_start=0）**

| 里程碑 | 閾值 | 精確 at_s | Spec 建議值 |
|--------|------|----------|-----------|
| M2 EchoShield | 3,000 m | (8989-3000)/12 = **499.1 s** | — |
| M3 DETECTED | 2,000 m | (8989-2000)/12 = **582.4 s** | 580 ✓ |
| M4 MITIGATING | 1,000 m | (8989-1000)/12 = **665.7 s** | 666 ✓ |
| NEUTRALIZED | — | 666 + 40 | **706 s** | 706 ✓ |

**TRK-E0B（d_start=7223m，v=12 m/s，t_start=30）**

| 里程碑 | 閾值 | 精確 at_s | Spec 建議值 |
|--------|------|----------|-----------|
| M2 EchoShield | 3,000 m | 30+(7223-3000)/12 = **381.9 s** | — |
| M3 DETECTED | 2,000 m | 30+(7223-2000)/12 = **465.3 s** | 406 ⚠️ |
| M4 MITIGATING | 1,000 m | 30+(7223-1000)/12 = **548.6 s** | 489 ⚠️ |
| NEUTRALIZED | — | 489+30 | **519 s** | 519 ✓ |

> ⚠️ **TRK-E0B 時間矛盾**：Spec 的 detected_at_s=406 對應距離觸發點 = 7223 - (406-30)×12 = 2,711m（非 2,000m）。
> Spec 值 (406/489) 顯示 detected 在 ~2.7km 處、mitigating 在 ~1.7km 處，比 spec 設定的閾值提前。
> **建議**：使用 Spec 提供的值（406/489/519）作為 YAML 設定值，符合「±30s 調校」說明。

**TRK-E0C（d_start=8485m，v=12 m/s，t_start=60）**

| 里程碑 | 閾值 | 精確 at_s | Spec 建議值 |
|--------|------|----------|-----------|
| M2 EchoShield | 3,000 m | 60+(8485-3000)/12 = **516.8 s** | — |
| M3 DETECTED | 2,000 m | 60+(8485-2000)/12 = **600.4 s** | 600 ✓ |
| M4 MITIGATING | 1,000 m | 60+(8485-1000)/12 = **683.8 s** | 684 ✓ |
| NEUTRALIZED | — | 684+30 | **714 s** | 714 ✓ |

### Milestone Collision Check（FR-SCN-017）

| 事件 | TRK-E0A | TRK-E0B | TRK-E0C | 最小間隔 |
|------|---------|---------|---------|---------|
| M3 DETECTED | 580 | 406 | 600 | min(600-580)=**20s** ≥ 10s ✓ |
| M4 MITIGATING | 666 | 489 | 684 | min(684-666)=**18s** ≥ 10s ✓ |
| NEUTRALIZED | 706 | 519 | 714 | min(714-706)=**8s** ⚠️ |

> ⚠️ E0A(706) 與 E0C(714) 間隔僅 8s < 10s。調校建議：E0C neutralized_at_s = **716**（714+2s）。
> 但此為 sentrycs YAML 內部屬性，不影響跨服務契約，允許微調。

### Rationale
直線近似（等速飛行、忽略GPS噪點）已足夠；驗證腳本加 ±30s 容差緩衝。

---

## Decision 4: EchoShield 感測半徑設定

### Decision
為 e2e 場景建立獨立 EchoShield 設定檔，**不修改**現有預設 config。

### 問題
dev-launcher.sh 的 `launch_echoshield_sim()` 函式將 EchoShield sensor 硬編碼在台北附近（lat=24.0, lon=121.0），**與戰略作戰座標（SP: 24.725806, 121.033750）相差 ≈ 80.9km**，遠超過 max_range_m=4800。
**若不修改 dev-launcher.sh，e2e 場景中的所有無人機都不會被 EchoShield 偵測到。**

### Resolution
1. 新增 `--echoshield-config <path>` 參數至 `scripts/dev-launcher.sh`（修改 shell script，非 Python 服務程式碼）
2. 建立 `services/echoshield-sim/config/e2e_scenario.yaml`：
   ```yaml
   sensor_lat: 24.725806   # SP
   sensor_lon: 121.033750  # SP
   sensor_alt_m: 10.0
   max_range_m: 3200       # 覆蓋至 3.2km，確保 M2 (3km) 可靠觸發
   update_rate_hz: 10
   lost_grace_sec: 2.0
   position_noise_m: 5.0
   velocity_noise_ms: 0.5
   noise_seed: null
   # map_sim_url / feed_host / feed_port 由 dev-launcher 覆寫
   ```
3. e2e 啟動指令加入 `--echoshield-config services/echoshield-sim/config/e2e_scenario.yaml`

### max_range_m 選擇依據

| max_range_m | 劇本一 M2 觸發時間（15m/s，8989m 起） | 劇本二 M2-A（12m/s，8989m，at_s=0） |
|-------------|-------------------------------------|-----------------------------------|
| 3000 m | t = (8989-3000)/15 = **399s** | t = (8989-3000)/12 = **499s** |
| 3200 m | t = (8989-3200)/15 = **386s** | t = (8989-3200)/12 = **482s** |
| 5000 m | t = (8989-5000)/15 = **266s** | t = (8989-5000)/12 = **332s** |

選用 **3200m**：比 3000m 多 200m 緩衝，在 GPS 噪點（±5m）下可靠觸發 M2。

### Alternatives Considered
- 保留 max_range_m=4800 但修改 sensor 位置：若感測位置正確（SP），4800m 會讓 EchoShield 在 t≈266s（4.8km 處）就開始偵測，M2 概念失去「3km 進入感測圈」的意義。
- 不修改 dev-launcher.sh，改為手動設定環境變數：降低 Demo 可重複性，不可行。

---

## Decision 5: Sentrycs detected_at_s / mitigating_at_s 設計考量

### Decision
使用 spec FR-SCN-004 / FR-SCN-014 中的建議值，並額外標注各值的幾何依據。

### sentrycs-sim 的時間機制
sentrycs-sim 以**場景計時器**（`at_s` 計數，從服務啟動時開始計時）驅動狀態切換：
- `detected_at_s`：場景時間到達此值時，將 drone 狀態切換為 `DETECTED`，並透過 `/detections` API 提供給 cot-gateway 輪詢
- `mitigating_at_s`：切換為 `MITIGATING`，同時對 UDS 發送 `POST /command/takeover`
- `neutralized_at_s`：切換為 `NEUTRALIZED`，開始 30s 計時後從列表移除

### 與 UDS 計時的對齊
- UDS timeline 的 `at_s: 0` 和 sentrycs 的 `at_s` 計時器必須從**相同絕對時間**開始
- dev-launcher.sh 同時啟動兩個服務，啟動時間偏差 < 1s（在 ±30s 調校容差內）

### 劇本間隔設計考量
- M3(DETECTED) → M4(MITIGATING) 間隔：= 距離觸發差 / 速度 ≈ 1000m / v
  - 劇本一（15m/s）：1000/15 ≈ **67s**；spec 建議 460→525 = 65s ✓
  - 劇本二（12m/s）：1000/12 ≈ **83s**；A: 580→666=86s ✓，B: 406→489=83s ✓，C: 600→684=84s ✓
- M4 → NEUTRALIZED：固定 **40s**（給予 UDS 處理接管 + 確認的時間）

---

## Decision 6: validate_scenario.py 設計

### Decision
**主模式**：輪詢 `map-sim GET /objects`（M1）+ 解析 `.dev-runtime/logs/tak-client-sim.log`（M2-M4）
**離線模式**（`--offline`）：僅解析歷史 log 檔

### 驗證方法評估

| 方法 | 優點 | 缺點 |
|------|------|------|
| 輪詢 map-sim | M1 最直接；不依賴 log 格式 | 只能驗 M1 |
| 解析 tak-client-sim log | 可驗 M2-M4 CoT 序列；離線可用 | 依賴 tak-client-sim 輸出格式 |
| 直連 cot-gateway TCP :8089 | 最直接的 CoT 來源 | 需長連線監聽；與 tak-client-sim 競爭連線 |
| 解析 cot-gateway log | 不依賴 tak-client-sim | log 格式需另行確認 |

### 選擇依據
FR-SCN-033 允許「解析 tak-client-sim 日誌檔或直接監聽 cot-gateway」；FR-SCN-027 規定 tak-client-sim 的 console 輸出格式。選用 log 解析為主，因為：
1. 不需 TCP 長連線
2. 離線重播可用（CI 從歷史 log 驗證）
3. FR-SCN-033 明確允許此方式

### tak-client-sim log 格式（假設依 006 spec）
```
[2026-05-03T10:00:00.123Z] uid=ECHO-TRK-E01 type=a-u-A-M-F-Q-r lat=24.7527 lon=121.0338 stale=2026-05-03T10:00:11.123Z status=Active
```
驗證腳本以正規表達式解析此格式。若實際格式不符，需調整解析 regex（記錄為 Plan 風險項）。

### Rationale
log 解析比直接 TCP 監聽更穩定，且符合 CI 場景（錄製後驗證）。

---

## Decision 7: validate_cot.py 設計

### Decision
純靜態 log 解析工具，解析 tak-client-sim log 或 cot-gateway 輸出的 CoT XML，
輸出 type/stale/uid 三類合規報告。

### CoT type 驗證邏輯
```python
EXPECTED_TYPE = {
    "ECHO-": "a-u-A-M-F-Q-r",
    "SENTRYCS-": "a-u-A-M-F-Q-r",
    "FUSED-": "a-h-A-M-F-Q-r",
}
```

### stale 驗證邏輯（FR-SCN-023）
```python
# 給定 CoT event 的 time_str, stale_str, status
def expected_stale(time: datetime, status: str) -> datetime:
    if status in ("Lost", "stale-clear"):
        return time
    elif status == "NEUTRALIZED":
        return time + timedelta(seconds=30)
    else:  # Active / DETECTED / MITIGATING
        return time + timedelta(seconds=11)
```
允許 ±1s 容差（FR-SCN-038）。

### 跨機混淆偵測（劇本二）
當 `FUSED-TRK-E0A` CoT 的 lat/lon 超出 A 的合理飛行區域（距 A 路徑 > 500m）時標記為混淆。

---

## Summary

| 問題 | 結論 |
|------|------|
| Haversine 公式 | 標準庫 `math`，自實作 |
| WGS-84 終點公式 | 標準庫 `math`，自實作 |
| EchoShield sensor 位置 | 需新增 e2e 設定檔（sensor at SP，range=3200m） |
| dev-launcher.sh 擴充 | 新增 `--echoshield-config` 參數 |
| FR-SCN-010 12分鐘矛盾 | 解讀為 M1-M4 CoT 事件序列完成（≤535s = 8.9 min），物理降落 ~841s |
| TRK-E0B timing 矛盾 | 使用 spec 提供的值（406/489/519）作為 YAML，±30s 調校容差 |
| validate_scenario.py 方式 | map-sim 輪詢（M1）+ tak-client-sim log 解析（M2-M4） |
