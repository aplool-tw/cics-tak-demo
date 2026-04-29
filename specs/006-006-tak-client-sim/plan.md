# Implementation Plan: TAK Client Simulator

**Branch**: `006-006-tak-client-sim` | **Date**: 2026-04-29 | **Spec**: [`specs/006-006-tak-client-sim/spec.md`](spec.md)  
**Input**: Feature specification from `specs/006-006-tak-client-sim/spec.md`

---

## Summary

`tak-client-sim` 是輕量 Python 服務，扮演被動 TAK 客戶端角色，以 `asyncio` TCP+SSL 連線至 TAK Server `:8089`，逐行讀取 Newline-delimited CoT XML，使用標準庫 `xml.etree.ElementTree` 解析並輸出人讀格式至 stdout，同時以 `structlog` JSON 並行記錄至 stderr/log-file。連線中斷時指數退避重連；收到 SIGINT/SIGTERM 後優雅關閉並列印 session_summary。無任何持久化（G6），替代實體 ATAK 裝置完成 PoC 端對端驗收。

---

## Technical Context

**Language/Version**: Python 3.11+（測試於 3.12）  
**Primary Dependencies**: `pydantic>=2.6`、`structlog>=24.1`、`pyyaml`（選配 `--config`）；stdlib `asyncio`、`ssl`、`xml.etree.ElementTree`  
**Storage**: N/A（G6 無持久化）  
**Testing**: `pytest>=8.0`、`pytest-asyncio>=0.23`、`freezegun>=1.4`  
**Target Platform**: Linux server（PoC 本機 / Docker）  
**Project Type**: CLI service（`python -m tak_client_sim`）  
**Performance Goals**: 每筆 CoT 接收→console 延遲 ≤ 100ms（SC-TCS-001）；50+ UPS 不積壓接收迴圈（SC-TCS-005）  
**Constraints**: 無外部 HTTP port；無 p12 憑證（消費端不需 client cert）；禁用 lxml / geopy；`asyncio.Lock` 內禁止 await I/O  
**Scale/Scope**: 單一 TAK Server 連線；記憶體內統計歸零；PoC 環境 50+ UPS 峰值

---

## Constitution Check

*依 AGENTS.md §3.1 PoC 自律準則 G1–G7 評估。constitution.md 仍為 placeholder，以守則代替。*

| 守則 | 評估 | 狀態 |
|------|------|------|
| **G1** Test-First | contract / unit / integration test 先寫確認 FAIL，再實作 | ✅ PASS |
| **G2** Contract Freeze | 下行接收契約 `tak-downlink.md` 凍結；不修改 `tak-uplink.md` | ✅ PASS |
| **G3** Structured Logging | 全程 `structlog` JSON；禁 f-string log；禁 `print()`（console formatter 除外） | ✅ PASS |
| **G4** Observability | 所有 lifecycle events 有對應 event name（FR-TCS-031~036） | ✅ PASS |
| **G5** Structural Symmetry | `services/tak-client-sim/src/tak_client_sim/`，`tests/{contract,unit,integration}/` | ✅ PASS |
| **G6** No Persistence | 統計記憶體內，重啟歸零 | ✅ PASS |
| **G7** Minimal Dependencies | 無 lxml/geopy；`cryptography` 不需引入（無 p12）；依賴精簡 | ✅ PASS |

**結論**：無守則違反，可直接進入 Phase 1 設計。

---

## Architecture

### 系統脈絡

```
CoT Gateway ──CoT XML NDJSON──▶ TAK Server :8089 ──TCP+SSL──▶ tak-client-sim
                                                                      │
                                                        stdout ──▶ console（human-readable）
                                                        stderr ──▶ structlog JSON
                                                        file   ──▶ --log-file out.jsonl（可選）
```

### 模組分解

```
tak_client_sim/
├── __main__.py     CLI entrypoint → parse args → build ClientConfig → asyncio.run(runner.main())
├── config.py       ClientConfig（pydantic v2）+ YAML 載入 + CLI override 合併
├── models.py       CotEvent（frozen dataclass/pydantic）、ConnectionStats（mutable dataclass）
├── connection.py   TakConnection：asyncio.open_connection + SSL ctx + readuntil(\n) + 指數退避重連
├── parser.py       parse_cot_xml(raw: str) → CotEvent | None；source/color 推導；delta_s 計算
├── formatter.py    format_event(event: CotEvent) → str；[STALE] 標記；console print wrapper
└── runner.py       main coroutine：receive_loop + stats_loop + signal handler + graceful shutdown
```

### 資料流

```
TakConnection.read_line()
    ↓ raw bytes (一行 UTF-8)
parser.parse_cot_xml(raw)
    ↓ CotEvent | None（解析失敗則 log cot_parse_error 跳過）
runner.receive_loop
    ├── stats.total_received += 1
    ├── stats.per_source[source] += 1
    ├── structlog.info("cot_received", ..., filtered=bool)
    └── formatter.format_event(event) → print() to stdout（if not filtered）
```

### 重連序列

```
connect_with_retry():
    attempt = 0
    while True:
        try:
            open_connection(host, port, ssl=ctx)
            return  # 成功
        except (OSError, ssl.SSLError):
            attempt += 1
            if max_retries > 0 and attempt >= max_retries:
                log max_retries_exceeded → exit(1)
            delay = min(backoff_initial * 2**(attempt-1), backoff_cap)
            log reconnecting(attempt, delay)
            await asyncio.sleep(delay)
```

### 並行結構

```
asyncio.run(main())
  ├── receive_loop()      # 主迴圈：readuntil → parse → format → log
  ├── signal_handler()    # SIGINT/SIGTERM → set stop_event
  └── shutdown()          # stop_event set → flush → close → print summary → exit(0)
```

---

## Module Design Decisions

### Decision 1: `asyncio.StreamReader.readuntil(b'\n')` 而非 `readline()`

- **決策**：使用 `readuntil(b'\n', limit=65536)` 而非 `readline()`
- **理由**：`readuntil` 提供 `limit` 參數，超限拋 `LimitOverrunError`；可直接對應 FR-TCS-016（64 KB oversized 保護）
- **替代方案**：自實作 buffer + find → 複雜度更高，無明顯優勢

### Decision 2: `CotEvent` 使用 `dataclasses.dataclass(frozen=True)` 而非 pydantic

- **決策**：`CotEvent` 用 stdlib `dataclasses`；`ClientConfig` 用 pydantic v2
- **理由**：`CotEvent` 由內部解析產生，不需 pydantic 的 wire 驗證；dataclass frozen 效能更好（高頻路徑）；`ClientConfig` 來自外部 YAML/CLI，需 pydantic 的 extra-forbid 驗證
- **替代方案**：全用 pydantic → 解析熱路徑增加不必要開銷

### Decision 3: `ConnectionStats` 使用 `dataclasses.dataclass`（mutable）

- **決策**：`ConnectionStats` 為 mutable dataclass（非 frozen），在 `runner.py` 中單一實例共享
- **理由**：統計資料需在接收迴圈中頻繁更新；mutable 避免每次重建物件；因 asyncio 單執行緒不需 Lock
- **替代方案**：`asyncio.Queue` 匯總 → 過設計，PoC 不需要

### Decision 4: SSL Context（消費端，無 client cert）

- **決策**：`ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)` + PoC `CERT_NONE`；不使用 `cryptography`
- **理由**：`tak-client-sim` 為純接收端，無需 client certificate（不同於 Gateway 的 `gateway.p12`）；stdlib `ssl` 足夠
- **替代方案**：`trustme`（僅用於測試）

### Decision 5: `--filter` 實作於 `formatter.py` 而非 `connection.py`

- **決策**：過濾邏輯在 formatter/runner 層，`structlog` 仍記錄全部事件（含 `filtered=true`）
- **理由**：FR-TCS-022/030 要求 console 不輸出但 log 仍記錄；接收層不感知過濾
- **替代方案**：connection 層過濾 → 無法滿足 log 全記錄需求

### Decision 6: `print()` 僅在 `formatter.py` 使用

- **決策**：`formatter.py` 的 `print_event()` 為唯一允許 `print()` 的位置
- **理由**：AGENTS.md §3.3 允許 CLI smoke 場景用 `print()`；console human-readable 輸出屬此類；其餘模組全禁
- **替代方案**：用 `sys.stdout.write()` → 語意等價，無優勢

---

## Project Structure

### Documentation (this feature)

```text
specs/006-006-tak-client-sim/
├── plan.md              ← 本文件
├── spec.md              ← 已完成
├── research.md          ← Phase 0 輸出
├── data-model.md        ← Phase 1 輸出
├── quickstart.md        ← Phase 1 輸出
├── contracts/
│   └── tak-downlink.md  ← Phase 1 輸出（下行接收契約）
└── tasks.md             ← /speckit.tasks 產出（未在本階段）
```

### Source Code

```text
services/tak-client-sim/
├── src/
│   └── tak_client_sim/
│       ├── __init__.py
│       ├── __main__.py          # CLI entry point（argparse + asyncio.run）
│       ├── config.py            # ClientConfig（pydantic v2）+ YAML loader
│       ├── models.py            # CotEvent（frozen dataclass）+ ConnectionStats（mutable dataclass）
│       ├── connection.py        # TakConnection：asyncio TCP+SSL + readuntil + reconnect backoff
│       ├── parser.py            # parse_cot_xml() → CotEvent | None；source/color/delta_s
│       ├── formatter.py         # format_event()；print_event()；[STALE] 標記
│       └── runner.py            # main()：receive_loop + signal_handler + graceful_shutdown
├── tests/
│   ├── contract/
│   │   └── test_tak_downlink.py # 凍結契約 8 場景 × CoT 接收正確性
│   ├── unit/
│   │   ├── test_parser.py       # parse happy path + oversized/invalid/missing uid/type
│   │   ├── test_formatter.py    # format + [STALE] + filter
│   │   └── test_config.py       # ClientConfig 驗證 + YAML load + CLI override
│   └── integration/
│       └── test_runner.py       # stub TAK Server → tak-client-sim 端對端流程
├── pyproject.toml
├── README.md
└── scripts/
    └── smoke.sh
```

**Structure Decision**: G5 對稱標準，與 `services/cot-gateway/` 一致。Python module `tak_client_sim`（底線），服務目錄 `tak-client-sim`（連字號）。

---

## Phase 0: Research

詳見 [`research.md`](research.md)。所有技術選項均已由凍結契約與既有參考服務確認，無 NEEDS CLARIFICATION 殘留。

**關鍵決策摘要**：

| 主題 | 決策 |
|------|------|
| TCP framing | `asyncio.StreamReader.readuntil(b'\n', limit=65536)` |
| XML 解析 | `xml.etree.ElementTree.fromstring()`（禁 lxml） |
| SSL（PoC） | `ssl.PROTOCOL_TLS_CLIENT` + `CERT_NONE + check_hostname=False` |
| 結構化日誌 | `structlog` JSON processor chain |
| 設定驗證 | `pydantic v2 ConfigDict(extra="forbid", frozen=True)` |
| 重連算法 | `min(1.0 * 2**(n-1), 60.0)` 秒，configurable max_retries |

---

## Phase 1: Design Artifacts

- [`data-model.md`](data-model.md) — `CotEvent`、`ClientConfig`、`ConnectionStats` 完整欄位定義  
- [`contracts/tak-downlink.md`](contracts/tak-downlink.md) — TAK Server 下行接收契約（與 `tak-uplink.md` 互補）  
- [`quickstart.md`](quickstart.md) — 本機開發快速啟動指南

---

## Complexity Tracking

無守則違反，本節略。
