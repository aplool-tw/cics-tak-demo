# 013 — CoT Gateway 地圖標記 & 接管指令 Bug 修復全紀錄

> **適用版本**：接續 `012-track-update-fix`（RC1–RC4 實作後）的後續除錯紀錄。  
> **目的**：完整記錄三個相互遮蔽的 Bug，分析共同的設計缺陷，以及未來預防措施。

---

## 問題背景

`012-track-update-fix` 實作了四個 RC（RC1–RC4）來修復地圖標記更新與 FUSED 融合顯示問題。部署後進行端對端 demo，觀察到以下症狀：

1. **EchoShield 標記在首次出現後 ~8 秒停止移動**，直到 Sentrycs 偵測後才有任何地圖變動
2. **FUSED 融合狀態從未出現**，或出現後無人機不轉向 Holding Point（HP），直接飛過 Strategic Point（SP）

事後分析確認這三個問題是**彼此遮蔽**的獨立 Bug，需依序診斷修復。

---

## Bug 1：EchoShield Tick Loop 崩潰（IEEE-754 rounding）

### 症狀

- ECHO 標記出現於 t=9s，約 t=17s 停止移動
- 地圖顯示完全凍結，但 HTTP `/info` endpoint 仍正常回應
- 一開始誤判為「loop hung」而非「loop crashed」

### 診斷過程

1. 在 `broadcast()` 加入細粒度診斷 log，發現 `broadcast_enter` 之後無任何後續 log
2. 移除 `await asyncio.sleep(0)` 排除 `CancelledError` 注入假說，問題仍在
3. 在 `run_forever()` 加入 `try/except` 後，終於在 log 中看到：

```json
{
  "event": "run_forever_exception",
  "error": "azimuth_deg: Input should be less than 360 [input_value=360.0]"
}
```

### 根本原因

`geo/bearing.py` 的 azimuth 計算邏輯：

```python
# ❌ 錯誤（guard 在 round() 之前執行）
brg = math.degrees(math.atan2(y, x)) % 360.0
if brg >= 360.0:
    brg = 0.0
return round(brg, 2)   # round(359.995, 2) → 360.0 ← 繞過 guard！
```

Python 的 `round(359.995, 2)` 在 IEEE-754 雙精度浮點數下回傳 `360.0`。Guard 已執行過，無法再攔截。`360.0` 進入 `RadarTrack` pydantic model（`azimuth_deg: float = Field(..., lt=360.0)`）觸發 `ValidationError`，整個 tick coroutine 因未捕獲例外而終止。

aiohttp HTTP server 是獨立的 asyncio task，所以 `/info` 仍然回應，造成「看起來 loop 還活著」的假象。

### 修復

**`services/echoshield-sim/src/echoshield_sim/geo/bearing.py`**
```python
# ✅ 修正：round() 先執行，再 guard
brg = math.degrees(math.atan2(y, x)) % 360.0
brg = round(brg, 2)
if brg >= 360.0:
    brg = 0.0
return brg
```

**`services/echoshield-sim/src/echoshield_sim/loop.py`**
- `run_one_tick()` 加入 `except Exception as exc: self._log.error("tick_error", ...)` — 單一 tick 例外不再殺死整個 loop
- `run_forever()` 加入 `try/except CancelledError/Exception` 結構化 ERROR log，確保任何崩潰都可觀察

**`services/echoshield-sim/src/echoshield_sim/feed/tcp_server.py`**
- 移除 `broadcast()` 中的 `await asyncio.sleep(0)`（保留 `async def` 相容性），消除 `CancelledError` 注入可能

---

## Bug 2：FUSED 未出現（RC1–RC4 功能修復）

> 此問題由 `012-track-update-fix` 的 RC1–RC4 修復，詳見 `dev-docs/012-track-update-fix.md`。以下為快速摘要。

### 症狀

Sentrycs 偵測到後，地圖上不出現 FUSED 狀態；EchoShield 和 Sentrycs 各自的點也沒有同時顯示。

### 根本原因（四項）

| RC | 問題 | 修復 |
|----|------|------|
| RC1 | `refreshTracks()` 每次 `clearLayers()` 重繪，marker 閃爍且位置凍結 | 改為 `droneMarkers[uid]` uid-keyed 增量更新，`setLatLng()` in-place |
| RC2 | `detect_source_switch()` 只回傳第一個舊 uid，多餘的舊 track 殘留 | 改回傳 `list[str]` 全部舊 uid，`_emit_for_track` 逐一 stale-emit + remove |
| RC3 | `/tracks` API 缺少 `uid` 欄位，前端無穩定身份鍵值 | `TrackStore._serialize()` 加入 `"uid"` 欄位（additive，不破壞 G2 凍結契約） |
| RC4 | `_within_match()` naive/aware datetime 相減拋出 `TypeError` | 本地 normalize UTC 再相減，不修改原始物件 |

---

## Bug 3：接管後無人機飛過 SP（PerimeterGuard drone_id 命名空間錯誤）

### 症狀

修復 Bug 1 & 2 後，完整飛行路徑首次可觀察。發現無人機飛過 SP 才停下，而非在 1 km 前轉向 HP。

### 診斷

查閱 UDS log，發現：

```json
{
  "reason": "drone_id not found",
  "drone_id": "FUSED-TRK-E01",
  "event": "takeover.rejected"
}
```

此 log 以每秒 10 次頻率重複出現——`PerimeterGuard` 每 tick 重試，但 UDS 永遠回 HTTP 400（`drone_id not found`），guard 的 idempotency latch（只在 200/409 才設）從未設置。

### 根本原因：跨層 ID 命名空間混用

本系統中同一無人機有三種 ID 表達：

| 層級 | 格式 | 範例 |
|------|------|------|
| UDS 原始 drone_id | 無前綴 | `TRK-E01` |
| CoT Gateway 內部 uid | 有 source 前綴 | `FUSED-TRK-E01` |
| CoT XML TAK uid | 有 source 前綴 | `FUSED-TRK-E01` |

`guard.py` 在建構 UDS takeover payload 時使用了 CoT Gateway 的內部 `track.track_id`（帶前綴），而 UDS 從未註冊過帶前綴的 ID：

```python
# ❌ 錯誤：CoT uid 當作 UDS drone_id
payload = {"drone_id": track.track_id, ...}   # "FUSED-TRK-E01"

# ✅ 修正：使用原始 UDS drone_id
payload = {"drone_id": track.rf_track_id, ...} # "TRK-E01"
```

### 為何之前未被發現

- Bug 1（EchoShield crash）在 t≈17s 就凍結整個 ECHO tick loop，無法觀察到完整飛行路徑
- 換言之：**Bug 1 遮蔽了 Bug 3**；修完 Bug 1 才看到 Bug 3
- 測試 T018 中 FUSED track 的 `track_id == rf_track_id`（同一值），沒有觸發差異，無法偵測此 bug

### 修復

**`services/cot-gateway/src/cot_gateway/perimeter/guard.py`**
```python
# Use rf_track_id (the raw UDS drone_id) rather than the prefixed
# track_id that UDS never registered.
payload = {
    "drone_id": track.rf_track_id,
    ...
}
```

**新增 Regression Test T018b** (`test_perimeter_guard.py`)：
```python
# 使用真實場景中 track_id ≠ rf_track_id 的 FUSED track
track = UnifiedTrack(
    track_id="FUSED-TRK-E01",   # CoT uid
    rf_track_id="TRK-E01",       # UDS drone_id
    ...
)
# 驗證 payload drone_id 為 rf_track_id，不是 track_id
assert payload["drone_id"] == "TRK-E01"
```

---

## 跨層 ID 使用規範

以下表格作為後續開發的固定參考：

| 目標服務 | 應使用的欄位 | Source 條件 |
|---------|------------|------------|
| **UDS** `/command/takeover` | `track.rf_track_id` | SENTRYCS、FUSED |
| **UDS** `/command/takeover` | `track.radar_track_id` | ECHOSHIELD（若未來支援）|
| **Sentrycs sim** 配對 | `track.rf_track_id` | SENTRYCS、FUSED |
| **EchoShield sim** 配對 | `track.radar_track_id` | ECHOSHIELD、FUSED |
| **TAK CoT XML** `uid` 欄位 | `uid(track)` via `cot/uid.py` | 所有 source |
| **前端 `/tracks` API** key | `track_store` uid（= `uid(track)`）| 所有 source |

> **規則**：凡是與 CoT Gateway 以外的服務通訊，禁用 `track.track_id`。`track_id` 是 CoT Gateway 內部邏輯欄位，不應洩漏為跨服務 ID。

---

## 設計缺陷總結與預防措施

### 共同設計缺陷

三個 Bug 均有一個共同根源：**隱性的「層級邊界」**——

1. `azimuth_deg` 的值域約束（`[0, 360)`）在 model 層有文件，但計算函式缺乏 round-then-guard 的標準實踐
2. `track_id` 欄位同時承擔「CoT uid」和「跨服務參考 ID」兩個角色，沒有 type-level 或文件層區分
3. 測試中使用了不代表真實場景的簡化值（`track_id == rf_track_id`），沒有觸發真正的差異

### 預防措施

#### 1. 守衛邊界測試原則

凡是有數值範圍限制的計算（`azimuth_deg`、`lat`、`lon` 等），測試必須覆蓋：
- 邊界值（0.0、359.99、360.0）
- 邊界值經過 `round()` 後的結果（`round(359.995, 2)` = `360.0`）

#### 2. 跨服務 ID 測試不等值原則

任何涉及跨服務 ID 傳遞的測試，構造 FUSED/SENTRYCS track 時**必須使用不同的 `track_id` 和 raw ID**：

```python
# ❌ 危險（無法觸發差異）
UnifiedTrack(track_id="TRK-001", rf_track_id="TRK-001", ...)

# ✅ 正確（模擬真實場景）
UnifiedTrack(
    track_id="FUSED-TRK-E01",   # CoT uid（帶前綴）
    rf_track_id="TRK-E01",       # 原始 UDS drone_id（無前綴）
    ...
)
```

#### 3. Code Review Checklist（跨服務整合相關）

- [ ] 傳給 UDS 的 `drone_id` 是否為 `rf_track_id` / `radar_track_id`？
- [ ] 是否有將帶前綴的 `track.track_id` 直接傳給外部服務？（幾乎必定是 bug）
- [ ] 測試中 FUSED/SENTRYCS track 是否有 `track_id ≠ rf_track_id`？
- [ ] 數值範圍計算是否先 `round()` 再 guard？

#### 4. 長期：異常容錯層（Defensive Tick Loop）

EchoShield 的修復已在 `run_one_tick()` 加入 per-tick exception catch。**所有服務的 tick loop 都應遵循相同模式**：

```python
async def run_one_tick(self) -> None:
    try:
        await self._do_tick()
    except asyncio.CancelledError:
        raise  # 讓取消機制正常傳播
    except Exception as exc:
        self._log.error("tick_error", error=repr(exc))
        # 繼續下一 tick，單次錯誤不殺死整個 loop
```

#### 5. 長期：ID 型別化（可選）

若後續跨服務整合增多，可用 `NewType` 讓 type checker 在編譯期攔截誤用：

```python
CotUid = NewType("CotUid", str)         # "FUSED-TRK-E01"
UdsDroneId = NewType("UdsDroneId", str) # "TRK-E01"
```

---

## 驗證結果

| 項目 | 結果 |
|------|------|
| echoshield-sim 74 tests | ✅ pass |
| cot-gateway 148+1 tests（含 T018b）| ✅ pass |
| ruff + black | ✅ clean |
| 完整 125s demo | ECHO t=9–43s 持續移動 → FUSED t≈44s → 接管 t≈71s → 轉向 HP ✓ |

---

## 修改檔案摘要

### Bug 1 修改（EchoShield）
| 檔案 | 說明 |
|------|------|
| `services/echoshield-sim/src/echoshield_sim/geo/bearing.py` | `round()` 移至 guard 之前 |
| `services/echoshield-sim/src/echoshield_sim/loop.py` | per-tick exception catch + run_forever 結構化 log |
| `services/echoshield-sim/src/echoshield_sim/feed/tcp_server.py` | 移除 `await asyncio.sleep(0)` |

### Bug 2 修改（RC1–RC4，CoT Gateway）
| 檔案 | 說明 |
|------|------|
| `services/cot-gateway/src/cot_gateway/web/track_store.py` | uid 欄位加入序列化 |
| `services/cot-gateway/src/cot_gateway/web/server.py` | refreshTracks() uid-keyed 增量更新 |
| `services/cot-gateway/src/cot_gateway/cot/uid.py` | source_switch 回傳 `list[str]` |
| `services/cot-gateway/src/cot_gateway/loop.py` | 逐一 stale-emit + remove 舊 uid |
| `services/cot-gateway/src/cot_gateway/correlate/correlator.py` | datetime UTC normalize |

### Bug 3 修改（PerimeterGuard）
| 檔案 | 說明 |
|------|------|
| `services/cot-gateway/src/cot_gateway/perimeter/guard.py` | `drone_id: track.rf_track_id` |
| `services/cot-gateway/tests/unit/test_perimeter_guard.py` | 新增 T018b regression test |

### Speckit Artifacts
- `specs/012-track-update-fix/`（spec、plan、tasks、contracts 等）

---

## 參考
- `dev-docs/012-track-update-fix.md` — RC1–RC4 實作紀錄
- `services/cot-gateway/src/cot_gateway/perimeter/guard.py` — PerimeterGuard 修正
- `services/echoshield-sim/src/echoshield_sim/geo/bearing.py` — azimuth round fix
