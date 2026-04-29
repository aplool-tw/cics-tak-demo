from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Literal

SourceLabel = Literal["ECHO", "SENTRYCS", "FUSED", "UNKNOWN"]
ColorLabel = Literal["GREY", "RED", "UNKNOWN"]


@dataclasses.dataclass(frozen=True)
class CotEvent:
    uid: str
    cot_type: str
    source: SourceLabel
    color: ColorLabel
    time: datetime
    stale: datetime
    delta_s: int
    lat: float
    lon: float
    hae: float
    speed: float
    course: float
    remarks: str
    raw_xml: str


@dataclasses.dataclass
class ConnectionStats:
    total_received: int = 0
    total_filtered: int = 0
    total_parse_errors: int = 0
    total_oversized: int = 0
    reconnect_count: int = 0
    per_source: dict[str, int] = dataclasses.field(default_factory=dict)
    per_uid: dict[str, int] = dataclasses.field(default_factory=dict)

    def record_event(self, event: CotEvent, filtered: bool) -> None:
        self.total_received += 1
        if filtered:
            self.total_filtered += 1
        self.per_source[event.source] = self.per_source.get(event.source, 0) + 1
        self.per_uid[event.uid] = self.per_uid.get(event.uid, 0) + 1

    def to_dict(self) -> dict[str, object]:
        return {
            "total_received": self.total_received,
            "total_filtered": self.total_filtered,
            "total_parse_errors": self.total_parse_errors,
            "total_oversized": self.total_oversized,
            "reconnect_count": self.reconnect_count,
            "per_source": dict(self.per_source),
            "per_uid": dict(self.per_uid),
        }
