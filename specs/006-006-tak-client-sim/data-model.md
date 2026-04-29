# Data Model: TAK Client Simulator

**Feature**: 006-006-tak-client-sim  
**Date**: 2026-04-29  
**Spec Reference**: `specs/006-006-tak-client-sim/spec.md` §Key Entities

---

## 概述

本服務使用三個核心資料結構：

| 結構 | 型態 | 說明 |
|------|------|------|
| `CotEvent` | `dataclasses.dataclass(frozen=True)` | 一筆已解析的 CoT 事件（不可變） |
| `ClientConfig` | `pydantic.BaseModel` | 服務設定（不可變，來自 YAML/CLI） |
| `ConnectionStats` | `dataclasses.dataclass` | 執行時期統計（可變，程式退出前匯出） |

> **設計原則**：`CotEvent` 與 `ClientConfig` 均不可變（frozen）；`ConnectionStats` 可變（asyncio 單執行緒安全，無需 Lock）。

---

## 1. CotEvent

`services/tak-client-sim/src/tak_client_sim/models.py`

### 結構定義

```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

SourceLabel = Literal["ECHO", "SENTRYCS", "FUSED", "UNKNOWN"]
ColorLabel  = Literal["GREY", "RED", "UNKNOWN"]

@dataclass(frozen=True)
class CotEvent:
    # --- 身份識別 ---
    uid: str                    # 原始 UID（如 "ECHO-TRK-001"）
    cot_type: str               # CoT type（如 "a-u-A-M-F-Q-r"）

    # --- 推導標籤 ---
    source: SourceLabel         # UID 前綴推導；見 §1.1
    color: ColorLabel           # cot_type 前綴推導；見 §1.2

    # --- 時間 ---
    time: datetime              # UTC aware；ISO 8601 解析自 <event time>
    stale: datetime             # UTC aware；ISO 8601 解析自 <event stale>
    delta_s: int                # max(0, round((stale - time).total_seconds()))

    # --- 位置 ---
    lat: float                  # 緯度（度）；來自 <point lat>
    lon: float                  # 經度（度）；來自 <point lon>
    hae: float                  # 海拔高度（公尺）；來自 <point hae>

    # --- 動態 ---
    speed: float                # 速度（m/s）；來自 <track speed>
    course: float               # 方位角（度）；來自 <track course>

    # --- 可選補充 ---
    remarks: str                # <remarks> 文字；缺席時為空字串
    raw_xml: str                # 原始行字串（供除錯 / contract test 用）
```

### 1.1 Source 推導規則（FR-TCS-014）

| UID 前綴 | source |
|----------|--------|
| `ECHO-` | `"ECHO"` |
| `SENTRYCS-` | `"SENTRYCS"` |
| `FUSED-` | `"FUSED"` |
| 其他 | `"UNKNOWN"` |

```python
def _derive_source(uid: str) -> SourceLabel:
    if uid.startswith("ECHO-"):     return "ECHO"
    if uid.startswith("SENTRYCS-"): return "SENTRYCS"
    if uid.startswith("FUSED-"):    return "FUSED"
    return "UNKNOWN"
```

### 1.2 Color 推導規則（FR-TCS-015）

| cot_type 前綴 | color |
|---------------|-------|
| `a-u-` | `"GREY"` |
| `a-h-` | `"RED"` |
| 其他 | `"UNKNOWN"` |

```python
def _derive_color(cot_type: str) -> ColorLabel:
    if cot_type.startswith("a-u-"): return "GREY"
    if cot_type.startswith("a-h-"): return "RED"
    return "UNKNOWN"
```

### 1.3 delta_s 計算規則（FR-TCS-013）

```python
delta_s = max(0, round((stale_dt - time_dt).total_seconds()))
```

| stale 語意 | stale - time | delta_s |
|------------|--------------|---------|
| Lost（stale=time） | 0 s | 0 |
| 其他（Active / DETECTED / MITIGATING） | +11 s | 11 |
| NEUTRALIZED | +30 s | 30 |
| 異常（stale < time） | 負數 | 0（下限） |

### 1.4 驗證規則

- `uid`：非空字串（空 uid 視同解析失敗 → `cot_parse_error`）
- `cot_type`：非空字串（空 type 視同解析失敗 → `cot_parse_error`）
- `lat`：IEEE 754 float；範圍不驗證（依上游 cot-xml.md 保證）
- `time` / `stale`：UTC aware datetime；解析失敗時以 `datetime.now(timezone.utc)` 替代並 log warning
- `delta_s`：`≥ 0`（強制 max(0, ...)）

### 1.5 [STALE] 標記判斷

```python
def is_stale_at_receive(event: CotEvent, now: datetime) -> bool:
    """stale 時間早於接收當下超過 30 秒"""
    return (now - event.stale).total_seconds() > 30
```

此判斷在 `formatter.py` 中執行，`CotEvent` 本身不含 `received_at` 欄位（避免 frozen dataclass 難以測試）。

---

## 2. ClientConfig

`services/tak-client-sim/src/tak_client_sim/config.py`

### 結構定義

```python
from __future__ import annotations
from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional

class ClientConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # --- 連線 ---
    host: str = "tak-server"
    port: int = 8089
    use_ssl_verify: bool = False         # False = PoC CERT_NONE；True = 正式模式
    ca_bundle: Optional[str] = None      # CA bundle 路徑（use_ssl_verify=True 時有效）

    # --- 重連 ---
    max_retries: int = 0                 # 0 = 無限重試
    backoff_initial_s: float = 1.0
    backoff_cap_s: float = 60.0

    # --- 過濾 ---
    filter_prefix: Optional[str] = None  # 空字串視為 None（FR-TCS-022 edge case）

    # --- 輸出 ---
    log_file: Optional[str] = None       # structlog JSON 目標檔案路徑

    @field_validator("filter_prefix", mode="before")
    @classmethod
    def normalize_filter_prefix(cls, v: object) -> object:
        """空字串視為 None（Edge Case：--filter ""）"""
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError(f"port must be 1–65535, got {v}")
        return v

    @field_validator("max_retries")
    @classmethod
    def validate_max_retries(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"max_retries must be ≥ 0, got {v}")
        return v
```

### YAML 設定格式（snake_case）

```yaml
# tak-client-sim.yaml
host: tak-server
port: 8089
use_ssl_verify: false
ca_bundle: null
max_retries: 0
backoff_initial_s: 1.0
backoff_cap_s: 60.0
filter_prefix: null
log_file: null
```

### CLI 參數 → Config 欄位對應（FR-TCS-040）

| CLI 參數 | Config 欄位 | 預設值 |
|----------|-------------|--------|
| `--host` | `host` | `"tak-server"` |
| `--port` | `port` | `8089` |
| `--no-ssl-verify` | `use_ssl_verify=False`（flag） | `False`（PoC 預設） |
| `--filter PREFIX` | `filter_prefix` | `None` |
| `--log-file PATH` | `log_file` | `None` |
| `--max-retries N` | `max_retries` | `0` |
| `--config PATH` | YAML 載入來源 | N/A |

### 載入優先級

```
ClientConfig 預設值
    ↓ 被 YAML 檔案覆寫（若 --config 提供）
        ↓ 被 CLI 參數覆寫（FR-TCS-042）
```

```python
def load_config(args: argparse.Namespace) -> ClientConfig:
    base: dict = {}
    if args.config:
        import yaml
        with open(args.config) as f:
            base = yaml.safe_load(f) or {}
    # CLI 覆寫：僅套用非 None / 非預設的值
    if args.host is not None:        base["host"]          = args.host
    if args.port is not None:        base["port"]          = args.port
    if args.no_ssl_verify:           base["use_ssl_verify"] = False
    if args.filter is not None:      base["filter_prefix"] = args.filter
    if args.log_file is not None:    base["log_file"]       = args.log_file
    if args.max_retries is not None: base["max_retries"]    = args.max_retries
    try:
        return ClientConfig(**base)
    except ValidationError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(2)
```

### 驗證錯誤處理（FR-TCS-041）

- `extra="forbid"`：YAML 含多餘欄位 → `pydantic.ValidationError` → 顯示友善訊息 → `exit(2)`
- 欄位型別錯誤（如 `port: "abc"`）→ 同上

---

## 3. ConnectionStats

`services/tak-client-sim/src/tak_client_sim/models.py`

### 結構定義

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict

@dataclass
class ConnectionStats:
    """執行時期統計（可變，asyncio 單執行緒安全）"""
    total_received:    int = 0
    total_filtered:    int = 0
    total_parse_errors: int = 0
    total_oversized:   int = 0
    reconnect_count:   int = 0
    per_source: Dict[str, int] = field(default_factory=dict)
    per_uid:    Dict[str, int] = field(default_factory=dict)

    def record_event(self, event: "CotEvent", filtered: bool) -> None:
        """成功解析的 CoT 事件記錄"""
        self.total_received += 1
        if filtered:
            self.total_filtered += 1
        self.per_source[event.source] = self.per_source.get(event.source, 0) + 1
        self.per_uid[event.uid]       = self.per_uid.get(event.uid, 0) + 1

    def to_dict(self) -> dict:
        """轉換為 structlog session_summary payload"""
        return {
            "total_received":     self.total_received,
            "total_filtered":     self.total_filtered,
            "total_parse_errors": self.total_parse_errors,
            "total_oversized":    self.total_oversized,
            "reconnect_count":    self.reconnect_count,
            "per_source":         dict(self.per_source),
            "per_uid":            dict(self.per_uid),
        }
```

### 欄位說明

| 欄位 | 型別 | 說明 |
|------|------|------|
| `total_received` | `int` | 成功解析的 CoT 總數（含 filtered） |
| `total_filtered` | `int` | 被 `--filter` 過濾、未輸出至 console 的筆數 |
| `total_parse_errors` | `int` | XML 解析失敗（invalid XML / missing uid / missing type）計數 |
| `total_oversized` | `int` | 超過 64 KB 的行被丟棄計數 |
| `reconnect_count` | `int` | 累計重連嘗試次數（成功連線後不歸零，保留全程統計） |
| `per_source` | `Dict[str, int]` | 各 source（ECHO/SENTRYCS/FUSED/UNKNOWN）的接收筆數 |
| `per_uid` | `Dict[str, int]` | 各 uid 的接收筆數 |

### session_summary 輸出範例（FR-TCS-035）

```json
{
  "event": "session_summary",
  "total_received": 42,
  "total_filtered": 10,
  "total_parse_errors": 1,
  "total_oversized": 0,
  "reconnect_count": 2,
  "per_source": {"ECHO": 20, "FUSED": 15, "SENTRYCS": 7},
  "per_uid": {"ECHO-TRK-001": 20, "FUSED-DRN-001": 15, "SENTRYCS-DRN-001": 7},
  "timestamp": "2026-04-29T11:00:00.123Z",
  "level": "info"
}
```

---

## 4. 結構間關係

```
CLI args ──────────────────────▶ ClientConfig (frozen)
YAML file ──────────────────────▶      │
                                        │
                                        ▼
TCP stream ──── raw bytes ──▶ parse_cot_xml() ──▶ CotEvent (frozen)
                                                          │
                                        ┌─────────────────┘
                                        │
                                        ▼
                              ConnectionStats.record_event()
                                        │
                              formatter.format_event() ──▶ stdout (human)
                              structlog.info("cot_received", ...) ──▶ stderr/file (JSON)
```

---

## 5. 狀態機（連線生命週期）

```
INIT
  │ asyncio.run(main())
  ▼
CONNECTING ──── 連線失敗 / 逾時 ──▶ BACKOFF ──── delay 後 ──▶ CONNECTING
  │                                    │
  │ 達 max_retries                      │
  ▼                                    │
EXIT(1)     ◀────────────────────────┘
  │
CONNECTED（連線成功）
  │ tak_connected log
  ▼
RECEIVING（receive_loop）
  │
  ├─── readuntil 成功 ──▶ parse → format → log → stats ──▶（迴圈頂部）
  │
  ├─── readuntil 失敗（Connection Reset / EOF）──▶ tak_disconnected log ──▶ BACKOFF
  │
  └─── stop.is_set() ──▶ SHUTTING_DOWN
              │
              ▼
          CLOSED（writer.close()）──▶ summary print ──▶ EXIT(0)
```
