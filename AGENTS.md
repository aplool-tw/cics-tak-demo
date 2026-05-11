# AGENTS.md — AI Agent Development Guide

> 本文件供 AI 開發代理（Claude / Copilot / GPT 等）與人類開發者共同遵循。摘述本倉庫的架構守則、coding standards、與 Speckit 流程預期。**新進 agent 開工前請先完整閱讀本文件。**

---

## 1. 專案脈絡（Project Context）

本專案為 **台灣反無人機 TAK 戰術感知 PoC**。六個獨立 Python 服務組成端對端鏈路：

```
UDS ─push─▶ Map Sim ◀─poll─ EchoShield Sim ─NDJSON─▶ CoT Gateway ─CoT XML─▶ TAK ◀─TCP+SSL─ TAK Client Sim
                       ◀─poll─ Sentrycs Sim   ─HTTP─▶                              (驗證用，無 ATAK 需求)
                                    └─ POST /command/takeover ─▶ UDS
```

權威規格在 [`docs/system-docs/`](docs/system-docs/)（v0.6, 10 份文件）。任何契約變更**必須**先回頭更新規格文件再動程式碼。

---

## 2. 工作流程（Speckit Workflow）

所有 feature 開發走完整 Speckit 流程，**不可跳階段**：

```
Specify → Clarify → Plan → Tasks → Analyze → Implement → Test → Docs → Merge
```

| 階段 | 產出 | 落點 |
|------|------|------|
| Specify | `spec.md`（FR/SC/User Stories/Edge Cases） | `specs/<id>-<name>/` |
| Clarify | 整合至 `spec.md` 的 `## Clarifications` 區塊 | 同上 |
| Plan | `plan.md` `data-model.md` `research.md` `contracts/*.md` `quickstart.md` | 同上 |
| Tasks | `tasks.md`（TDD 順序、`[P]` 並行標記） | 同上 |
| Analyze | 跨檔一致性檢查；CRITICAL/HIGH 必須修正 | 同上 |
| Implement | 程式碼 + 測試 | `services/<name>/` |
| Test | 全部 pytest pass、ruff + black 乾淨 | — |
| Docs | `dev-docs/<id>-<name>.md` 開發紀錄 | `dev-docs/` |
| Merge | `git merge --no-ff feature/<id>-<name>` | `develop` 分支 |

### 提問規則

- Clarify 階段最多 5 題高影響問題；無模糊點則直接結案「無需 clarify」
- 使用 `ask_user` 工具，**不可**在純文字回應中提問
- 一次只問一個問題

### 分支策略

- 主幹：`develop`
- 功能分支：`feature/<feature-id>-<short-name>`（kebab-case，2–4 字）
- 雜務分支：`chore/<topic>`
- 合併：`git merge --no-ff`，**不**直接 push 到 origin（除非使用者明確要求）
- Commit trailer：`Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`

### Conventional commits

- `feat(NNN-name): ...` 新功能
- `fix(NNN-name): ...` bug 修正
- `docs(NNN-name): ...` 規格 / dev-docs / Speckit artifacts
- `chore: ...` 工具、設定、CI

---

## 3. 程式碼守則（Coding Standards）

### 3.1 PoC 自律準則 G1–G7

`.specify/memory/constitution.md` 仍為 placeholder。在憲章正式建立前，所有 feature 採以下自律準則：

| ID | 準則 | 強制性 |
|----|------|--------|
| **G1** | Test-First：所有 contract / unit / integration test 在實作前先寫，且**確認 FAIL** | MUST |
| **G2** | Contract Freeze：跨服務 wire 契約（JSON schema、HTTP API、TCP framing）一旦凍結即不得 breaking change | MUST |
| **G3** | Structured Logging：所有 log 必須是 `structlog` JSON，至少含 `timestamp/level/logger/event` 四欄 | MUST |
| **G4** | Observability：每個 lifecycle 事件、錯誤分支、重試動作須有對應 event 名稱（已寫入各 spec FR） | MUST |
| **G5** | Structural Symmetry：所有服務 `services/<name>/` 目錄結構一致（src/, tests/{contract,unit,integration}/, pyproject.toml, README.md, scripts/smoke.sh） | MUST |
| **G6** | No Persistence：PoC 服務皆為記憶體狀態；重啟即重置（除非 spec 明示） | MUST |
| **G7** | Minimal Dependencies：標準庫優先（如 `xml.etree.ElementTree`, `ssl`）；新增依賴須在 `research.md` 證明必要 | MUST |

### 3.2 技術棧

- Python 3.11+（測試於 3.12）
- 必要依賴：`aiohttp`, `pydantic v2`, `structlog`, `PyYAML`
- 測試：`pytest`, `pytest-asyncio`, `freezegun`
- 額外：`numpy`（雷達噪點）、`cryptography`（p12→PEM 解析）
- **禁用**：`geopy`（自寫 Haversine / WGS84 destination formula）、`lxml`（用標準庫 ElementTree）

### 3.3 Python 風格

- `pydantic v2` model 設定 `model_config = ConfigDict(extra="forbid", frozen=True)`，YAML 多餘欄位即 fail-fast
- `from __future__ import annotations` 全檔啟用
- 結構化日誌：`logger.info("event_name", key1=v1, key2=v2)`，**禁用** f-string log
- ⚠️ Log format ≠ wire format：`cot-gateway` 與 `tak-client-sim` 輸出的 log 是 structlog JSON；TCP socket 傳輸的 bytes 是 CoT XML。兩者格式獨立，不可混淆。
- 不使用 `print()`（**例外**：`tak-client-sim` 的 `formatter.py#print_event()` 及 `connection.py` 為 FR-TCS-023 要求的 console 輸出，允許使用 `print()`）
- `asyncio.Lock` 內**禁止** await I/O
- 所有 wire JSON 經 pydantic 驗證；reject 時 log `invalid_wire_fields` 並繼續（不退出）
- 時間戳統一 ISO 8601 UTC 含毫秒：`2026-04-28T01:42:41.123Z`

### 3.4 Lint / Format

- `ruff check .` 必須乾淨（規則繼承各服務 `pyproject.toml`）
- `black --check src tests` 必須乾淨
- CI 等價指令：`ruff check . && black --check src tests && python3 -m pytest -q`

---

## 4. 跨服務契約（凍結點）

修改下列任一契約都會 break 既有服務測試。如必須變更，**先**更新 `docs/system-docs/` + 相關 `specs/00X-*/contracts/`，再動實作。

### UDS → Map Sim push（8 欄位）

`drone_id, lat, lon, alt_m, speed_ms, heading_deg, status, timestamp`。**禁用**其他欄位。

### Map Sim GET /objects 回應

`status` 永不被覆寫為 `"lost"`；用獨立 `is_lost: bool`。

### UDS POST /command/takeover

`{drone_id, target_lat, target_lon, target_alt_m}`；200 / 400 / 404 / 409；**409 視為成功**。

### EchoShield TCP :19000 NDJSON

`track_status ∈ {"Active", "Lost"}`（**不是** NEW/UPDATED/LOST）；
`track_id = drone_id`（例如 `TRK-E01`；**不含** `ECHO-` 前綴，前綴由 CoT Gateway 加）；
`latitude/longitude/altitude_m`（注意命名：底層 wire 用全名，內部模型用 `lat/lon/alt_m`，CoT XML 用 `lat/lon/hae`）。
2 秒 grace window 內 drone_id 重現沿用同一 `track_id`（= drone_id，行為不變）。

### Sentrycs HTTP :17070 /detections

14 欄位 item；status `DETECTED/MITIGATING/NEUTRALIZED`；NEUTRALIZED 保留 30s 後移除；`/health` 200 = ready 就緒。

### CoT XML（MIL-STD-2525C）

- type：`a-u-A-M-F-Q-r`（單源灰色）/ `a-h-A-M-F-Q-r`（融合敵對紅色）—— **不依狀態切換 type**
- stale：`Lost=time`、`NEUTRALIZED=time+30s`、其他 `time+11s`
- 狀態以 `<remarks>` 字串表達
- TAK uplink：TCP+SSL `:18089`，NDJSON framing（每筆 CoT 後接 `\n`）

詳見 [`specs/005-cot-gateway/contracts/cot-xml.md`](specs/005-cot-gateway/contracts/cot-xml.md)。

---

## 5. AI Agent 注意事項

### 5.1 工具偏好

- 探索程式碼：先用 `grep`/`glob`/`view`，再考慮 `task` agent
- 多檔讀取請**並行**呼叫 `view`（同一 response 內）
- 多 bash 步驟用 `&&` 串接，少開 round-trip
- 長指令掛 `mode=async detach=true`（servers/daemons）

### 5.2 子代理（Speckit Sub-agents）

對應的 sub-agents 已在 `.specify/agents/` 註冊：

- `speckit.specify` — 寫 spec.md
- `speckit.clarify` — 提問並整合
- `speckit.plan` — 產出 plan + research + data-model + contracts + quickstart
- `speckit.tasks` — TDD 順序的 tasks.md
- `speckit.analyze` — 跨檔一致性
- `speckit.implement` — 依 tasks 實作（**不**改規格）

呼叫 sub-agent 時**必須**提供完整 context（檔案路徑、前一階段結論、技術約束）。

### 5.3 禁止事項

- ❌ 不可手動跳過 Specify / Plan / Tasks 階段直接寫程式
- ❌ 不可在 Implement 階段修改 spec.md / plan.md（如發現問題回到對應階段）
- ❌ 不可 push 到 origin 除非使用者明確要求
- ❌ 不可改 wire 契約（4 節各項）而不更新對應 spec/contracts 文件
- ❌ 不可寫 `print()` 或非結構化 log 到 production 程式碼
- ❌ 不可引入 G7 禁用依賴（geopy / lxml）

### 5.4 必做事項

- ✅ 每個 feature 完成後寫 `dev-docs/00X-*.md`
- ✅ 每階段以 conventional commits 格式提交
- ✅ commit 訊息必含 `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer
- ✅ 合併用 `--no-ff` 保留 feature 分支歷史
- ✅ 全部 pytest pass + ruff + black 乾淨**才能**進 Merge 階段

---

## 6. 常見指令

```bash
# 啟動全部服務開發環境
scripts/dev-launcher.sh

# 部分啟動 + 自訂 port
scripts/dev-launcher.sh --services map-sim,uds --uds-port 18080

# E2E 情境一（單機）
scripts/dev-launcher.sh \
  --uds-scenario services/uds/scenarios/e2e_single_drone.yaml \
  --sentrycs-scenario services/sentrycs-sim/config/e2e_single_drone.yaml \
  --echoshield-config services/echoshield-sim/config/e2e_scenario.yaml

# 跑單一服務測試
( cd services/cot-gateway && python3 -m pytest -q )

# 跑全部服務測試
for svc in uds map-sim echoshield-sim sentrycs-sim cot-gateway tak-client-sim; do
  ( cd "services/${svc}" && python3 -m pytest -q ) || exit 1
done

# 跑情境驗證腳本
python3 -m pytest specs/007-scenario/scripts/ -q

# 離線驗證 YAML 場景文件
python3 specs/007-scenario/scripts/validate_scenario.py \
  --uds   services/uds/scenarios/e2e_single_drone.yaml \
  --sntr  services/sentrycs-sim/config/e2e_single_drone.yaml \
  --echo  services/echoshield-sim/config/e2e_scenario.yaml

# Lint 檢查單一服務
( cd services/cot-gateway && ruff check . && black --check src tests )

# 安裝（需 --break-system-packages；libs/tak-connection 必須先裝）
pip install -e libs/tak-connection --break-system-packages
pip install -e "services/cot-gateway[dev]" --break-system-packages
pip install -e "services/tak-client-sim[dev]" --break-system-packages
```

---

## 7. 文件導引

- 系統規格：[`docs/system-docs/00-index.md`](docs/system-docs/00-index.md)
- Speckit artifacts（每 feature 完整保留）：[`specs/`](specs/)
- 開發紀錄（人類友善摘要）：[`dev-docs/`](dev-docs/)
- 啟動腳本：[`scripts/dev-launcher.sh`](scripts/dev-launcher.sh)
- README（高層概覽）：[`README.md`](README.md)

---

## 8. 變更本文件

`AGENTS.md` 是活的文件。當下列任一情況發生時請更新：

1. 新增/移除一個服務或重大模組
2. 凍結契約有重大調整（先更新 docs/system-docs/）
3. 引入新的標準庫使用模式或工具偏好
4. 發現某個 AI agent 反覆犯的錯誤，需要明文禁止
5. 升級 Python 主版本或關鍵依賴

更新後請以 `chore: update AGENTS.md` 提交，並在 PR 描述標明變更摘要。
