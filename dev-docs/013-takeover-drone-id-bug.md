# 013 — CoT Gateway PerimeterGuard Takeover drone_id Bug

## 問題描述

**症狀**：執行 demo 時，無人機飛過 Strategic Point（SP）才停下來，而非在 1 km 前轉向 Holding Point（HP）。  
**預期行為**：無人機進入 SP 防禦半徑 1000 m 時，CoT Gateway 向 UDS 發送 takeover 指令，無人機應立即轉向 HP。

---

## 根本原因分析

### 系統 ID 命名空間不一致

本系統中，同一架無人機在不同服務層有**三種不同的 ID 表達方式**：

| 層級 | ID 格式 | 範例 |
|------|---------|------|
| UDS（無人機控制）| 原始 drone_id | `TRK-E01` |
| CoT Gateway 內部 track | 有 source 前綴的 uid | `ECHO-TRK-E01` / `SENTRYCS-TRK-E01` / `FUSED-TRK-E01` |
| CoT XML (TAK 端) | uid 欄位 | `FUSED-TRK-E01` |

`PerimeterGuard._issue_takeover()` 在建構 POST `/command/takeover` 的 payload 時，使用了 CoT Gateway 的內部 `track.track_id`（已有 source 前綴），而非 UDS 原始的 drone_id。

```python
# ❌ 錯誤的原始實作
payload = {
    "drone_id": track.track_id,   # "FUSED-TRK-E01" ← UDS 不認識
    ...
}

# ✅ 修正後
payload = {
    "drone_id": track.rf_track_id,  # "TRK-E01" ← UDS 的原始 drone_id
    ...
}
```

### 觀察到的日誌證據

```json
{
  "reason": "drone_id not found",
  "drone_id": "FUSED-TRK-E01",
  "event": "takeover.rejected",
  "level": "info"
}
```

此日誌以每秒 10 次的頻率重複出現（guard 每 tick 重試，因為 HTTP 400 不會設置 idempotency latch）。

### 為何之前未被發現

1. **被其他 bug 遮蔽**：在 `012-track-update-fix` 之前，EchoShield tick loop 在 t≈17s 就因 `azimuth_deg=360.0` 崩潰，無人機標記完全凍結，觀察者看不到後續的完整飛行路徑。修復 EchoShield crash 後，才能觀察到完整飛行路徑，進而暴露此 bug。
2. **測試覆蓋不足**：現有的 T018 測試 (`test_fused_mitigating_inside_radius_fires`) 建構 FUSED track 時使用 `track_id == rf_track_id`（同一值），因此沒有觸發差異。真實場景中 `track_id = "FUSED-TRK-E01"` 而 `rf_track_id = "TRK-E01"` 是不同的值。

---

## 修復內容

**檔案**：`services/cot-gateway/src/cot_gateway/perimeter/guard.py`

```python
# guard.py line 90-95
# Use rf_track_id (the raw UDS drone_id) rather than the prefixed
# track_id ("FUSED-TRK-E01", "SENTRYCS-TRK-E01") that UDS never registered.
payload = {
    "drone_id": track.rf_track_id,
    "target_lat": self._holding_lat,
    ...
}
```

`rf_track_id` 是 `UnifiedTrack` 模型中儲存 Sentrycs/map-sim 原始 ID 的欄位，對 SENTRYCS 和 FUSED source 都等同於 UDS 的 `drone_id`。

**測試**：新增 T018b (`test_fused_takeover_payload_uses_rf_track_id`) — 直接驗證 payload `drone_id` 欄位為 `rf_track_id` 的值，而非帶前綴的 `track_id`。

---

## 設計缺陷分析

### 問題根源：跨層 ID 轉換缺乏明確契約

CoT Gateway 引入 source 前綴是為了讓 TAK client 區分同一目標的不同感測器 tracks。然而此前綴為 **CoT Gateway 層的內部邏輯**，不應洩漏到與 UDS 溝通的介面。

問題在於：
1. `UnifiedTrack.track_id` 同時承擔了兩個角色：CoT uid 和「跨服務參考 ID」
2. `guard.py` 在撰寫時沒有意識到 `track_id` 已帶前綴，誤用為 UDS 的 drone_id
3. 沒有任何 type-level 或文件層面的機制提醒開發者「這個欄位不能直接傳給 UDS」

---

## 預防措施與開發建議

### 1. 跨服務 ID 使用原則（立即可執行）

**規則**：凡是需要將 CoT Gateway 的 track 對應到另一個服務（UDS、Sentrycs、EchoShield），必須使用對應的 raw ID 欄位，不得使用 `track_id`：

| 目標服務 | 應使用的欄位 |
|---------|------------|
| UDS | `rf_track_id`（SENTRYCS / FUSED）或 `radar_track_id`（ECHOSHIELD）|
| Sentrycs | `rf_track_id` |
| EchoShield | `radar_track_id` |
| TAK CoT XML | `track_id`（via `uid()` function）|

### 2. 測試策略：跨層 ID 不等值覆蓋

任何涉及跨服務 ID 傳遞的測試，必須使用**不同值**的 `track_id` 和 raw ID 欄位：

```python
# ❌ 危險（不會觸發差異）
UnifiedTrack(track_id="TRK-001", rf_track_id="TRK-001", ...)

# ✅ 正確（模擬真實場景）
UnifiedTrack(
    track_id="FUSED-TRK-E01",   # CoT uid（帶前綴）
    rf_track_id="TRK-E01",       # 原始 UDS drone_id（無前綴）
    ...
)
```

### 3. Code Review Checklist（PerimeterGuard / UDS 整合相關）

在 Review 任何涉及「CoT Gateway → UDS」通訊的程式碼時，需檢查：

- [ ] payload 的 `drone_id` 欄位是否使用 `rf_track_id` 或 `radar_track_id`？
- [ ] 是否有用 `track.track_id` 直接傳給外部服務？（如有，幾乎必定是 bug）
- [ ] 測試中的 FUSED/SENTRYCS track 是否有讓 `track_id != rf_track_id`？

### 4. 長期：考慮 ID 型別化

若後續有更多跨服務整合，可考慮用 `NewType` 或獨立 dataclass 區分「CoT uid」和「外部服務 ID」，讓 Python type checker 在編譯期攔截誤用：

```python
CotUid = NewType("CotUid", str)        # "FUSED-TRK-E01"
UdsDroneId = NewType("UdsDroneId", str) # "TRK-E01"

# guard.py 的函式簽名即可要求正確型別
def _issue_takeover(..., drone_id: UdsDroneId) -> None: ...
```

---

## 相關檔案

| 檔案 | 說明 |
|------|------|
| `services/cot-gateway/src/cot_gateway/perimeter/guard.py` | 修正 `drone_id: track.rf_track_id` |
| `services/cot-gateway/tests/unit/test_perimeter_guard.py` | 新增 T018b regression test |
| `dev-docs/012-track-update-fix.md` | 前一個 bug（EchoShield crash），是本 bug 被遮蔽的原因 |

---

## 時間線

| 事件 | 說明 |
|------|------|
| `012-track-update-fix` 修復後 | 完整飛行路徑首次可觀察，發現無人機飛過 SP |
| UDS 日誌分析 | 發現 `takeover.rejected: drone_id not found: FUSED-TRK-E01`，每 tick 重試 |
| 根本原因確認 | `guard.py` 使用 `track.track_id`（帶前綴）而非 `rf_track_id` |
| 修復 + 測試 | 單行修改 + 新增 T018b，148 tests pass |
