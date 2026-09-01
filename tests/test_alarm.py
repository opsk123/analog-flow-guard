import unittest

from analog_flow_guard.alarm import LowFlowAlarm, MonitorStatus
from analog_flow_guard.config import AlarmConfig


class LowFlowAlarmTests(unittest.TestCase):
    def setUp(self):
        self.alarm = LowFlowAlarm(
            AlarmConfig(
                low_flow_threshold=10,
                hysteresis=5,
                trigger_duration_sec=1,
                detection_error_timeout_sec=1,
            )
        )

    def test_delay_and_hysteresis(self):
        self.assertEqual(self.alarm.update(9, 0).status, MonitorStatus.PENDING)
        self.assertEqual(self.alarm.update(9, 0.9).status, MonitorStatus.PENDING)
        self.assertTrue(self.alarm.update(9, 1.0).active)
        self.assertTrue(self.alarm.update(12, 2.0).active)
        self.assertFalse(self.alarm.update(15, 3.0).active)

    def test_detection_error_does_not_create_false_alarm(self):
        self.alarm.update(20, 0)
        self.assertEqual(self.alarm.update(None, 0.5).status, MonitorStatus.NORMAL)
        result = self.alarm.update(None, 1.0)
        self.assertEqual(result.status, MonitorStatus.DETECTION_ERROR)
        self.assertFalse(result.active)

    def test_detection_error_retains_existing_alarm(self):
        self.alarm.update(5, 0)
        self.alarm.update(5, 1)
        result = self.alarm.update(None, 2)
        self.assertEqual(result.status, MonitorStatus.DETECTION_ERROR)
        self.assertTrue(result.active)

    def test_mvp_threshold_requires_one_continuous_second(self):
        alarm = LowFlowAlarm(
            AlarmConfig(
                low_flow_threshold=0.15,
                hysteresis=0.1,
                trigger_duration_sec=1.0,
                detection_error_timeout_sec=1.0,
            )
        )

        self.assertEqual(alarm.update(0.15, 0.0).status, MonitorStatus.PENDING)
        self.assertEqual(alarm.update(0.15, 0.999).status, MonitorStatus.PENDING)
        self.assertEqual(alarm.update(0.16, 1.0).status, MonitorStatus.NORMAL)
        self.assertEqual(alarm.update(0.15, 2.0).status, MonitorStatus.PENDING)
        self.assertTrue(alarm.update(0.15, 3.0).active)
        self.assertTrue(alarm.update(0.249, 4.0).active)
        self.assertFalse(alarm.update(0.25, 5.0).active)


if __name__ == "__main__":
    unittest.main()
