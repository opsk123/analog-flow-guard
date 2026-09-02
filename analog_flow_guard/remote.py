from __future__ import annotations

import json
import math
import os
import threading
import time
from datetime import datetime, timezone
from typing import Callable
from urllib.request import Request, urlopen

from .config import RemoteConfig


Payload = dict[str, str | float]
Sender = Callable[[str, str, Payload, float], None]


def post_flow_reading(url: str, token: str, payload: Payload, timeout: float) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-device-token": token,
        },
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        if not 200 <= response.status < 300:
            raise OSError(f"HTTP {response.status}")


class PeriodicFlowUploader:
    """Send the latest valid flow without blocking the camera/UI thread."""

    def __init__(
        self,
        config: RemoteConfig,
        *,
        sender: Sender = post_flow_reading,
        token_resolver: Callable[[str], str | None] = os.environ.get,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self._sender = sender
        self._token_resolver = token_resolver
        self._clock = clock
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._inflight = False
        self._closed = False
        self._last_success_at: float | None = None
        self._next_retry_at = 0.0
        self._pending_payload: Payload | None = None
        if not config.enabled:
            self._status = "사용 안 함"
        elif not token_resolver(config.token_env_var):
            self._status = f"환경변수 {config.token_env_var} 필요"
        else:
            self._status = "측정값 대기"

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    @property
    def inflight(self) -> bool:
        with self._lock:
            return self._inflight

    def observe(self, flow: float, measured_at: datetime | None = None) -> bool:
        if not self.config.enabled or not math.isfinite(flow) or flow < 0:
            return False

        measured_at = measured_at or datetime.now(timezone.utc)
        if measured_at.tzinfo is None:
            measured_at = measured_at.replace(tzinfo=timezone.utc)
        measured_at = measured_at.astimezone(timezone.utc)
        now = self._clock()

        with self._lock:
            if self._closed or self._inflight:
                return False
            if not self.config.function_url.strip():
                self._status = "함수 URL 필요"
                return False
            token = self._token_resolver(self.config.token_env_var)
            if not token:
                self._status = f"환경변수 {self.config.token_env_var} 필요"
                return False
            interval = max(1.0, float(self.config.upload_interval_sec))
            if self._last_success_at is not None:
                if now - self._last_success_at < interval:
                    return False
            if now < self._next_retry_at:
                return False

            if self._pending_payload is not None:
                payload = self._pending_payload
            else:
                # Use an interval-sized UTC bucket for the idempotency key.
                # This works for both the 60-second MVP demonstration and the
                # 3600-second production reporting interval.
                bucket_epoch = math.floor(measured_at.timestamp() / interval) * interval
                bucket = datetime.fromtimestamp(bucket_epoch, tz=timezone.utc)
                payload = {
                    "sample_id": f"{self.config.device_id}:{bucket.isoformat()}",
                    "device_id": self.config.device_id,
                    "flow_rate_lpm": round(float(flow), 3),
                    "measured_at": measured_at.isoformat(),
                }
            self._inflight = True
            self._status = "전송 중"
            self._thread = threading.Thread(
                target=self._upload,
                args=(token, payload),
                name="flow-web-uploader",
                daemon=True,
            )
            self._thread.start()
            return True

    def _upload(self, token: str, payload: Payload) -> None:
        try:
            self._sender(
                self.config.function_url.strip(),
                token,
                payload,
                self.config.request_timeout_sec,
            )
        except Exception as exc:
            with self._lock:
                self._pending_payload = payload
                self._next_retry_at = self._clock() + self.config.retry_interval_sec
                self._status = f"전송 실패: {str(exc)[:80]}"
                self._inflight = False
            return

        with self._lock:
            self._last_success_at = self._clock()
            self._next_retry_at = 0.0
            self._pending_payload = None
            self._status = "전송 완료"
            self._inflight = False

    def wait_for_idle(self, timeout: float = 2.0) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def close(self) -> None:
        with self._lock:
            self._closed = True
        self.wait_for_idle(0.2)


# Backward-compatible import for existing installations and tests.
HourlyFlowUploader = PeriodicFlowUploader
