from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum

from .config import AlarmConfig


class MonitorStatus(str, Enum):
    NORMAL = "NORMAL"
    PENDING = "LOW FLOW PENDING"
    LOW_FLOW = "LOW FLOW"
    DETECTION_ERROR = "GAUGE DETECTION ERROR"


@dataclass(frozen=True)
class AlarmResult:
    status: MonitorStatus
    active: bool


class LowFlowAlarm:
    def __init__(self, config: AlarmConfig) -> None:
        self.config = config
        self.active = False
        self.low_since: float | None = None
        self.last_valid_at: float | None = None

    def update(self, flow: float | None, now: float | None = None) -> AlarmResult:
        now = time.monotonic() if now is None else now
        if flow is None:
            if self.last_valid_at is None or now - self.last_valid_at >= self.config.detection_error_timeout_sec:
                return AlarmResult(MonitorStatus.DETECTION_ERROR, self.active)
            return AlarmResult(MonitorStatus.LOW_FLOW if self.active else MonitorStatus.NORMAL, self.active)

        self.last_valid_at = now
        if self.active:
            if flow >= self.config.low_flow_threshold + self.config.hysteresis:
                self.active = False
                self.low_since = None
            return AlarmResult(MonitorStatus.LOW_FLOW if self.active else MonitorStatus.NORMAL, self.active)

        if flow <= self.config.low_flow_threshold:
            if self.low_since is None:
                self.low_since = now
            if now - self.low_since >= self.config.trigger_duration_sec:
                self.active = True
                return AlarmResult(MonitorStatus.LOW_FLOW, True)
            return AlarmResult(MonitorStatus.PENDING, False)

        self.low_since = None
        return AlarmResult(MonitorStatus.NORMAL, False)

