"""UDS takeover request + response mapping."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TakeoverResult(str, Enum):
    ACCEPTED = "accepted"
    ALREADY_TAKEN_OVER = "already_taken_over"
    REJECTED_BAD_REQUEST = "rejected_bad_request"
    REJECTED_NOT_FOUND = "rejected_not_found"
    FAILED_TRANSPORT = "failed_transport"


class TakeoverRequest(BaseModel):
    """Exact 4-field body sent to UDS ``POST /command/takeover``."""

    model_config = ConfigDict(extra="forbid")

    drone_id: str = Field(..., min_length=1)
    target_lat: float = Field(..., ge=-90.0, le=90.0)
    target_lon: float = Field(..., ge=-180.0, le=180.0)
    target_alt_m: float = Field(default=0.0, ge=0.0)
    sent_at: datetime | None = Field(default=None, exclude=True)


# UDS HTTP status → TakeoverResult (takeover-caller.md §4)
def classify_http_status(status: int) -> TakeoverResult:
    if status == 200:
        return TakeoverResult.ACCEPTED
    if status == 409:
        return TakeoverResult.ALREADY_TAKEN_OVER
    if status == 400:
        return TakeoverResult.REJECTED_BAD_REQUEST
    if status == 404:
        return TakeoverResult.REJECTED_NOT_FOUND
    if 400 <= status < 500:
        # other 4xx: treat as unretryable bad request (latch, no retry)
        return TakeoverResult.REJECTED_BAD_REQUEST
    return TakeoverResult.FAILED_TRANSPORT


def result_latches(result: TakeoverResult) -> bool:
    """Whether ``takeover_sent`` should be latched to True after receiving this result."""
    return result in (
        TakeoverResult.ACCEPTED,
        TakeoverResult.ALREADY_TAKEN_OVER,
        TakeoverResult.REJECTED_BAD_REQUEST,
        TakeoverResult.REJECTED_NOT_FOUND,
    )


def result_transitions_to_mitigating(result: TakeoverResult) -> bool:
    return result in (TakeoverResult.ACCEPTED, TakeoverResult.ALREADY_TAKEN_OVER)
