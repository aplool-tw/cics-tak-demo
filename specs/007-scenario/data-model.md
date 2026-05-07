# Data Model: 007-e2e-scenarios

**Feature**: `007-e2e-scenarios`
**Phase**: Plan → Data Model
**Created**: 2026-05-03

---

## 1. UDS 劇本 YAML — Pydantic Schema

### Pydantic v2 定義

```python
from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Optional


class WaypointModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lat: float = Field(..., ge=-90.0, le=90.0, description="緯度（WGS-84 十進位度）")
    lon: float = Field(..., ge=-180.0, le=180.0, description="經度（WGS-84 十進位度）")
    alt_m: float = Field(..., ge=0.0, description="高度（公尺 AGL）")


class LandingPointModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    alt_m: float = Field(0.0, ge=0.0)
    descent_speed_ms: float = Field(3.0, gt=0.0, description="降落速度（m/s）")


class DroneProfileModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    drone_id: str = Field(..., min_length=1, description="UDS 系統唯一識別（如 TRK-E01）")
    model: str = Field(..., description="無人機型號，用於 Sentrycs remarks")
    start_lat: float = Field(..., ge=-90.0, le=90.0)
    start_lon: float = Field(..., ge=-180.0, le=180.0)
    start_alt_m: float = Field(..., ge=0.0)
    speed_ms: float = Field(..., gt=0.0, le=100.0)
    heading_deg: float = Field(..., ge=0.0, lt=360.0)
    operator_bearing_deg: float = Field(..., ge=0.0, lt=360.0,
                                         description="操作員方位角（相對 drone）")
    operator_distance_m: float = Field(..., gt=0.0,
                                        description="操作員距無人機距離（公尺）")
    waypoints: list[WaypointModel] = Field(default_factory=list,
                                            min_length=0,
                                            description="飛行路徑中繼點（按序）")
    landing_point: Optional[LandingPointModel] = Field(None,
                                                        description="接管後降落目標（HP）")


class TimelineEventModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    at_s: float = Field(..., ge=0.0, description="場景計時器觸發時間（秒）")
    action: str = Field(..., description="事件類型，目前支援：start_flying")
    drone_id: str = Field(..., description="目標 drone_id，需在 drones 陣列中存在")


class ServersConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command_api_port: int = Field(8080, ge=1024, le=65535)


class ScenarioBodyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(..., description="劇本名稱（slug 格式，無空格）")
    description: str = Field(..., description="劇本描述")
    update_hz: float = Field(10.0, gt=0.0, le=100.0,
                              description="UDS 主迴圈更新率（Hz）")
    servers: ServersConfigModel = Field(default_factory=ServersConfigModel)
    drones: list[DroneProfileModel] = Field(..., min_length=1,
                                             description="劇本中的無人機列表")
    timeline: list[TimelineEventModel] = Field(..., min_length=1,
                                                description="時間軸事件列表")

    @model_validator(mode="after")
    def validate_timeline_drone_ids(self) -> "ScenarioBodyModel":
        """確認 timeline 中所有 drone_id 存在於 drones 陣列"""
        drone_ids = {d.drone_id for d in self.drones}
        for evt in self.timeline:
            if evt.drone_id not in drone_ids:
                raise ValueError(
                    f"Timeline event references unknown drone_id: {evt.drone_id!r}"
                )
        return self


class UDSScenarioConfig(BaseModel):
    """UDS 劇本 YAML 頂層結構"""
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario: ScenarioBodyModel
```

---

## 2. Sentrycs 設定 YAML — Pydantic Schema

```python
class SentrycsDroneEntryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    uid: str = Field(..., description="對應 UDS 的 drone_id")
    model: str = Field(..., description="無人機型號（用於 remarks）")
    detected_at_s: float = Field(..., ge=0.0,
                                  description="場景時間到此值切換 DETECTED（秒）")
    mitigating_at_s: float = Field(..., ge=0.0,
                                    description="場景時間到此值切換 MITIGATING + 觸發 takeover（秒）")
    neutralized_at_s: float = Field(..., ge=0.0,
                                     description="場景時間到此值切換 NEUTRALIZED（秒）")
    operator_bearing_deg: float = Field(..., ge=0.0, lt=360.0,
                                         description="操作員方位角")
    operator_distance_m: float = Field(..., gt=0.0,
                                        description="操作員距離（公尺）")

    @model_validator(mode="after")
    def validate_time_ordering(self) -> "SentrycsDroneEntryModel":
        if not (self.detected_at_s < self.mitigating_at_s < self.neutralized_at_s):
            raise ValueError(
                "detected_at_s < mitigating_at_s < neutralized_at_s 必須成立"
            )
        return self


class SentrycsScenarioConfig(BaseModel):
    """Sentrycs 設定 YAML 頂層結構"""
    model_config = ConfigDict(extra="forbid", frozen=True)

    sensor_lat: float = Field(..., ge=-90.0, le=90.0)
    sensor_lon: float = Field(..., ge=-180.0, le=180.0)
    poll_interval_s: float = Field(0.5, gt=0.0)
    map_sim_url: str = Field("http://localhost:18090")
    uds_url: str = Field("http://localhost:18080")
    api_host: str = Field("0.0.0.0")
    api_port: int = Field(7070, ge=1024, le=65535)
    neutralized_hold_s: float = Field(30.0, gt=0.0)
    mitigating_disappear_grace_s: float = Field(10.0, ge=0.0)
    drones: list[SentrycsDroneEntryModel] = Field(..., min_length=1)
```

---

## 3. ValidationResult 資料結構

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class MilestoneStatus(Enum):
    PENDING = "PENDING"
    PASS = "PASS"
    FAIL = "FAIL"
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True)
class MilestoneCheck:
    """單一里程碑的驗證結果"""
    milestone_id: str               # 例："M1", "M2", "M3-A", "M3-B"
    drone_id: str                   # 例："TRK-E01", "TRK-E0A"
    description: str                # 人類可讀說明
    expected_at_s: float            # 預期觸發場景時間（秒）
    tolerance_s: float              # 容差（秒，預設 30.0）
    observed_at_s: Optional[float]  # 實際觀察到的場景時間（None = 未觀察到）
    status: MilestoneStatus         # PASS / FAIL / TIMEOUT
    detail: str = ""                # 失敗原因或額外說明

    @property
    def pass_or_fail(self) -> str:
        return f"[{self.status.value}] {self.milestone_id}: {self.description}"


@dataclass
class ValidationResult:
    """一次劇本驗證執行的完整結果"""
    scenario_name: str              # "single" | "multi"
    run_started_at: datetime        # 驗證腳本開始時間（UTC）
    run_completed_at: Optional[datetime] = None

    milestones: list[MilestoneCheck] = field(default_factory=list)

    # CoT 合規統計（validate_cot.py 填寫）
    total_cot_events: int = 0
    cot_type_violations: int = 0
    cot_stale_violations: int = 0
    missing_stale_clear: int = 0
    uid_cross_contamination: int = 0

    # 接管位置誤差
    takeover_landing_distances_m: dict[str, float] = field(default_factory=dict)
    # key: drone_id, value: Haversine distance to HP (m)

    @property
    def passed(self) -> bool:
        return all(m.status == MilestoneStatus.PASS for m in self.milestones)

    @property
    def total_milestones(self) -> int:
        return len(self.milestones)

    @property
    def passed_milestones(self) -> int:
        return sum(1 for m in self.milestones if m.status == MilestoneStatus.PASS)

    def summary_line(self) -> str:
        result = "PASS" if self.passed else "FAIL"
        return f"RESULT: {result} ({self.passed_milestones}/{self.total_milestones} milestones validated)"
```

---

## 4. 劇本一里程碑定義（預定義 MilestoneCheck 集合）

```python
SCENARIO_SINGLE_MILESTONES: list[dict] = [
    {
        "milestone_id": "M1",
        "drone_id": "TRK-E01",
        "description": "TRK-E01 appears in map-sim within 60s of start",
        "expected_at_s": 10.0,
        "tolerance_s": 60.0,
    },
    {
        "milestone_id": "M2",
        "drone_id": "TRK-E01",
        "description": "ECHO-TRK-E01 CoT (a-u-A-M-F-Q-r) observed in TAK feed",
        "expected_at_s": 386.0,
        "tolerance_s": 60.0,
    },
    {
        "milestone_id": "M3",
        "drone_id": "TRK-E01",
        "description": "FUSED-TRK-E01 CoT (a-h-A-M-F-Q-r) after stale-clear of ECHO-TRK-E01",
        "expected_at_s": 460.0,
        "tolerance_s": 60.0,
    },
    {
        "milestone_id": "M4",
        "drone_id": "TRK-E01",
        "description": "MITIGATING_TAKEOVER: FUSED-TRK-E01 heading HP",
        "expected_at_s": 525.0,
        "tolerance_s": 60.0,
    },
    {
        "milestone_id": "LANDED",
        "drone_id": "TRK-E01",
        "description": "TRK-E01 final position within 50m of HP",
        "expected_at_s": 841.0,
        "tolerance_s": 120.0,
    },
]
```

---

## 5. CoT 合規事件模型

```python
@dataclass(frozen=True)
class CotEvent:
    """解析後的 CoT 事件（從 tak-client-sim log 提取）"""
    uid: str              # 完整 uid，如 ECHO-TRK-E01, FUSED-TRK-E01
    cot_type: str         # 如 a-u-A-M-F-Q-r
    lat: float
    lon: float
    time: datetime        # CoT <event time=...>
    stale: datetime       # CoT <event stale=...>
    status: str           # detection_status 或 track_status

    @property
    def uid_prefix(self) -> str:
        """返回 ECHO/SENTRYCS/FUSED/UNKNOWN"""
        for prefix in ("ECHO-", "SENTRYCS-", "FUSED-"):
            if self.uid.startswith(prefix):
                return prefix.rstrip("-")
        return "UNKNOWN"

    @property
    def stale_delta_s(self) -> float:
        """stale - time（秒）"""
        return (self.stale - self.time).total_seconds()

    @property
    def is_stale_clear(self) -> bool:
        """stale ≤ time（清場事件）"""
        return self.stale_delta_s <= 0.0
```

---

## 6. 欄位對應表（UDS YAML ↔ Sentrycs YAML ↔ CoT XML）

| 概念 | UDS YAML | Sentrycs YAML | CoT XML |
|------|---------|--------------|---------|
| 無人機識別 | `drones[].drone_id` | `drones[].uid` | `uid` 屬性的後半段 |
| EchoShield CoT uid | — | — | `ECHO-{drone_id}` |
| Sentrycs CoT uid | — | — | `SENTRYCS-{uid}` |
| 融合 CoT uid | — | — | `FUSED-{uid}` |
| EchoShield CoT type | — | — | `a-u-A-M-F-Q-r` |
| 融合 CoT type | — | — | `a-h-A-M-F-Q-r` |
| 接管目標緯度 | `landing_point.lat` | *(繼承 UDS)* | 不反映在 CoT type |
| 接管目標經度 | `landing_point.lon` | *(繼承 UDS)* | 不反映在 CoT type |
| 操作員方位 | `operator_bearing_deg` | `operator_bearing_deg` | `<remarks>` 中 |
| DETECTED 時間 | — | `detected_at_s` | stale = time + 11s |
| NEUTRALIZED 時間 | — | `neutralized_at_s` | stale = time + 30s |

---

## 7. HoldingPoint / StrategicPoint 常數

```python
# 全系統固定常數（spec §5 Key Entities）
SP_LAT = 24.725806  # Strategic Point 緯度
SP_LON = 121.033750  # Strategic Point 經度
HP_LAT = 24.725806  # Holding Point 緯度（與 SP 同緯度）
HP_LON = 121.071889  # Holding Point 經度（SP 正東方 ~3.86 km）

# HP-SP 距離（Haversine）
HP_SP_DISTANCE_M = 3858.0  # ≈ 3.86 km
```
