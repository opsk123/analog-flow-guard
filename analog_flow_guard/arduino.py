from __future__ import annotations

import time
from typing import Any

from .config import ArduinoConfig


class ArduinoAlarmOutput:
    """Best-effort serial output; camera monitoring continues if Arduino is absent."""

    def __init__(self, config: ArduinoConfig) -> None:
        self.config = config
        self.serial: Any = None
        self.last_connect_attempt = 0.0
        self.last_send = 0.0
        self.last_state: bool | None = None
        self.error: str | None = None
        self.connected_at: float | None = None

    def _connect(self, now: float) -> bool:
        if not self.config.enabled:
            self.error = "Arduino output disabled"
            return False
        if self.serial is not None and getattr(self.serial, "is_open", False):
            return True
        if now - self.last_connect_attempt < self.config.reconnect_sec:
            return False
        self.last_connect_attempt = now
        try:
            import serial

            self.serial = serial.Serial(self.config.port, self.config.baudrate, timeout=0.2)
            self.error = None
            self.last_state = None
            self.connected_at = now
            return True
        except Exception as exc:  # hardware errors must not stop monitoring
            self.error = str(exc)
            self.serial = None
            return False

    @property
    def status(self) -> str:
        if not self.config.enabled:
            return "DISABLED"
        if self.serial is not None and getattr(self.serial, "is_open", False):
            command = "--" if self.last_state is None else ("1 PROBLEM" if self.last_state else "0 NORMAL")
            return f"CONNECTED ({self.config.port}) TX={command}"
        if self.error:
            return f"ERROR: {self.error}"
        return f"CONNECTING ({self.config.port})"

    def update(self, active: bool, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        if not self._connect(now):
            return
        if self.connected_at is not None and now - self.connected_at < self.config.connection_settle_sec:
            return
        if active == self.last_state and now - self.last_send < self.config.heartbeat_sec:
            return
        try:
            self.serial.write(b"1\n" if active else b"0\n")
            self.last_state = active
            self.last_send = now
            self.error = None
        except Exception as exc:
            self.error = str(exc)
            self.close()

    def close(self) -> None:
        if self.serial is not None:
            try:
                self.serial.close()
            except Exception:
                pass
        self.serial = None
        self.connected_at = None
