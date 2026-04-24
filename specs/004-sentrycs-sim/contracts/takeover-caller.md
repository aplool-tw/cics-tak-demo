# Contract: UDS Takeover Caller（Sentrycs 作為 HTTP Client）

本檔定義 Sentrycs Simulator 作為 **HTTP Client** 對 UDS `POST /command/takeover` 的**呼叫端契約**。
此契約**不**重複定義 UDS server 行為——server 契約 already frozen at
[`specs/001-uds/contracts/rest-api.md §1`](../../001-uds/contracts/rest-api.md)；本檔只鎖定 Sentrycs **會**與
**不會**送出什麼、**如何解讀** UDS 回應、以及**何時**送出。

`tests/contract/test_takeover_caller.py` 必須完整覆蓋 §2、§3、§4。

---

## 1. 端點與基本設定

- **目標端點**：`POST {uds_url}/command/takeover`，其中 `uds_url` 由 scenario YAML / CLI 提供，預設 `http://localhost:8080`。
- **Timeout**：scenario YAML `uds_timeout_s`，預設 `3.0` 秒（FR-SC-012）。逾時視為 `FAILED_TRANSPORT`。
- **Headers**：`Content-Type: application/json`。
- **Client**：共用一個 `aiohttp.ClientSession`，隨程序生命週期開關；關閉時須 `await session.close()`（FR-SC-025）。

---

## 2. Request 契約（Sentrycs 送什麼）

### 2.1 Body schema

對齊 UDS server 契約（`specs/001-uds/contracts/rest-api.md §1.1`）的**必填 4 欄位**。Sentrycs **MUST NOT**
送出 `descent_speed_ms`（採 UDS 預設 `3.0`），也**MUST NOT**送出任何未知欄位（UDS `extra = forbid`）。

| 欄位 | 型別 | 必填 | 值域 | Sentrycs 取值 |
| --- | --- | --- | --- | --- |
| `drone_id` | string | ✅ | 非空 | `DroneTrack.uid`（= Map Simulator 回傳之 `drone_id`）|
| `target_lat` | number | ✅ | `[-90, 90]` | `DroneTrack.lat`（最近一次 Map Sim 同步值）|
| `target_lon` | number | ✅ | `[-180, 180]` | `DroneTrack.lon` |
| `target_alt_m` | number | ✅ | `≥ 0` | 固定 `0.0`（地面降落；HAE 0）|

**範例**：

```json
{
  "drone_id": "TRK-001",
  "target_lat": 25.0584745,
  "target_lon": 121.5654089,
  "target_alt_m": 0.0
}
```

### 2.2 不送出欄位（negative contract）

以下欄位 Sentrycs **MUST NOT** 在 body 中出現（違反會被 UDS 以 400 `unknown field: <name>` 拒絕）：

- `descent_speed_ms`（採 UDS 預設）
- `model`（不屬於 UDS schema；model 是 Sentrycs 對外輸出用）
- `operator_lat` / `operator_lon` / `operator_bearing_deg` / `operator_distance_m`（與 UDS 無關）
- `detection_status` / `is_landed` / `velocity_ms` / `azimuth_deg` / `alt_m` / `timestamp` / `uid`（Sentrycs 內部名）
- 任何 debug 欄位

---

## 3. 觸發契約（Sentrycs 何時送）

### 3.1 觸發條件（全部同時滿足）

1. 該 `DroneTrack.status == DETECTED`；
2. 場景時鐘 `≥ DroneScenario.mitigating_at_s`；
3. `DroneTrack.takeover_sent == False`（每目標**恰一次**，FR-SC-010）。

### 3.2 Latch 規則

- 無論 UDS 回 `200` / `409` / `400` / `404`，在**收到 HTTP 回應後**立即 latch `takeover_sent = True`（絕不重送）。
- 僅 **`FAILED_TRANSPORT`**（connection error / timeout / 5xx）**不** latch；下一 tick 允許重試。此為 Edge
  Case「UDS 暫時不可達」的容錯，但 spec §Edge Cases 明言 400/404 屬請求本身不合理**不得**重送——兩者分離處理。

### 3.3 併發

- 多架無人機同時達到 `mitigating_at_s` 時，各自的 takeover 呼叫以**獨立 asyncio task** 併發發出（FR-SC-023）。
- 同一 `uid` 不得有 > 1 個 in-flight takeover 呼叫（由 `takeover_sent=True` 在**請求發出前**即 latch 保證；
  詳見 §5 實作守則）。

---

## 4. Response 解讀契約（Sentrycs 如何反應）

| UDS HTTP Status | `TakeoverResult` | 狀態機動作 | `takeover_sent` latch | 重送？ |
| --- | --- | --- | --- | --- |
| `200` | `ACCEPTED` | `DETECTED → MITIGATING` | `True` | ❌ |
| `409` | `ALREADY_TAKEN_OVER` | `DETECTED → MITIGATING`（視同成功，FR-SC-011 / SC-SC-008）| `True` | ❌ |
| `400` | `REJECTED_BAD_REQUEST` | 保留 `DETECTED` | `True`（鎖死，不重送）| ❌ |
| `404` | `REJECTED_NOT_FOUND` | 保留 `DETECTED` | `True`（鎖死，不重送）| ❌ |
| timeout (`uds_timeout_s` 超時) | `FAILED_TRANSPORT` | 保留 `DETECTED` | `False` | ✅（下一 tick）|
| `5xx` | `FAILED_TRANSPORT` | 保留 `DETECTED` | `False` | ✅（下一 tick）|
| connection refused / DNS error | `FAILED_TRANSPORT` | 保留 `DETECTED` | `False` | ✅（下一 tick）|
| 其他 `2xx`（理論上不會發生）| `FAILED_TRANSPORT` | 保留 `DETECTED` | `False` | ✅ + WARN log |
| 其他 `4xx`（410 / 422 等）| `REJECTED_BAD_REQUEST` | 保留 `DETECTED` | `True` | ❌ |

**Response body 解讀**：Sentrycs **不**依賴 UDS 回應 body 的具體欄位值（`status` / `new_state` /
`estimated_landing_s` 等），**只**讀 HTTP status code。body 若解析失敗 → WARN log 但不影響狀態機決策。

---

## 5. 實作守則（normative，契約測試驗證）

1. **Pre-send latch**：呼叫 `aiohttp.ClientSession.post(...)` **前**以 CAS 或簡單檢查
   `if track.takeover_sent: return`；**發出後**不論結果再一次 latch。避免 race：同一目標絕不併發兩個 in-flight。
2. **timeout 僅限 HTTP 層**：不要再額外包一層 asyncio.wait_for；aiohttp `ClientTimeout(total=uds_timeout_s)` 即可。
3. **Logging**：
   - 發送前：1 筆 `takeover_request` event，欄位 `uid, drone_id, target_lat, target_lon, target_alt_m`。
   - 收到回應（或 transport 失敗）：1 筆 `takeover_response` event，欄位 `uid, http_status, result, latency_ms`；
     `FAILED_TRANSPORT` 時 `http_status` 可為 `null`，再加 `error` 欄位。
4. **No retry loop inside single tick**：每個 tick 最多 1 次嘗試；下個 tick 若仍滿足 §3.1 且未 latch 才會再試。
5. **Graceful shutdown**：收到 SIGINT/SIGTERM 時 in-flight takeover 允許完成或被 cancel（視 timeout），
   但**不得**在 shutdown 階段新發出 takeover（FR-SC-025、SC-SC-012）。

---

## 6. 契約測試覆蓋矩陣

| 測試 | 對應本檔節 | 對應 spec 驗收 |
| --- | --- | --- |
| `test_takeover_body_exact_4_fields` | §2.1, §2.2 | FR-SC-003 |
| `test_takeover_drone_id_is_uid` | §2.1 | FR-SC-003 |
| `test_takeover_target_alt_m_is_zero` | §2.1 | FR-SC-003 |
| `test_takeover_sent_once_per_drone` | §3.2, §5.1 | FR-SC-010 |
| `test_takeover_200_transitions_to_mitigating` | §4 | FR-SC-003 |
| `test_takeover_409_transitions_to_mitigating` | §4 | FR-SC-011、SC-SC-008 |
| `test_takeover_400_stays_detected_no_retry` | §4 | Edge Cases、FR-SC-011 |
| `test_takeover_404_stays_detected_no_retry` | §4 | Edge Cases、FR-SC-011 |
| `test_takeover_timeout_retries_next_tick` | §4, §5.4 | FR-SC-012 |
| `test_takeover_no_body_parsing_required` | §4 末段 | — |
| `test_takeover_no_in_flight_dup` | §3.3, §5.1 | FR-SC-010 |
