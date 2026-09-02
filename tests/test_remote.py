import unittest
from datetime import datetime, timezone

from analog_flow_guard.config import RemoteConfig
from analog_flow_guard.remote import PeriodicFlowUploader


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class RemoteFlowUploaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.calls = []
        self.config = RemoteConfig(
            enabled=True,
            function_url="https://example.supabase.co/functions/v1/ingest-flow",
            device_id="FLOW-01",
            upload_interval_sec=3600,
            retry_interval_sec=300,
        )

    def make_uploader(self, sender=None, token="secret") -> PeriodicFlowUploader:
        if sender is None:
            sender = lambda *args: self.calls.append(args)
        return PeriodicFlowUploader(
            self.config,
            sender=sender,
            token_resolver=lambda _name: token,
            clock=self.clock,
        )

    def test_sends_immediately_then_once_per_interval(self) -> None:
        uploader = self.make_uploader()
        measured = datetime(2026, 8, 31, 6, 23, tzinfo=timezone.utc)

        self.assertTrue(uploader.observe(0.2222, measured))
        uploader.wait_for_idle()
        self.assertEqual(len(self.calls), 1)
        payload = self.calls[0][2]
        self.assertEqual(payload["sample_id"], "FLOW-01:2026-08-31T06:00:00+00:00")
        self.assertEqual(payload["flow_rate_lpm"], 0.222)

        self.clock.value = 3599
        self.assertFalse(uploader.observe(0.21, measured))
        self.clock.value = 3600
        self.assertTrue(uploader.observe(0.21, measured))
        uploader.wait_for_idle()
        self.assertEqual(len(self.calls), 2)

    def test_minute_demo_uses_minute_idempotency_bucket(self) -> None:
        self.config.upload_interval_sec = 60
        uploader = self.make_uploader()
        measured = datetime(2026, 8, 31, 6, 23, 47, tzinfo=timezone.utc)

        self.assertTrue(uploader.observe(0.222, measured))
        uploader.wait_for_idle()
        self.assertEqual(
            self.calls[0][2]["sample_id"],
            "FLOW-01:2026-08-31T06:23:00+00:00",
        )

    def test_failure_retries_after_retry_interval(self) -> None:
        attempts = []

        def failing_sender(*args):
            attempts.append(args)
            raise OSError("offline")

        uploader = self.make_uploader(sender=failing_sender)
        first_time = datetime(2026, 8, 31, 6, 59, tzinfo=timezone.utc)
        retry_time = datetime(2026, 8, 31, 7, 4, tzinfo=timezone.utc)
        self.assertTrue(uploader.observe(0.2, first_time))
        uploader.wait_for_idle()
        self.assertIn("전송 실패", uploader.status)

        self.clock.value = 299
        self.assertFalse(uploader.observe(0.3, retry_time))
        self.clock.value = 300
        self.assertTrue(uploader.observe(0.3, retry_time))
        uploader.wait_for_idle()
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0][2], attempts[1][2])
        self.assertEqual(attempts[1][2]["sample_id"], "FLOW-01:2026-08-31T06:00:00+00:00")

    def test_missing_token_does_not_start_request(self) -> None:
        uploader = self.make_uploader(token="")
        self.assertIn("FLOW_DEVICE_TOKEN", uploader.status)
        self.assertFalse(uploader.observe(0.2))
        self.assertIn("FLOW_DEVICE_TOKEN", uploader.status)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
