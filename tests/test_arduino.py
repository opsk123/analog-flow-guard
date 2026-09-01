import sys
import types
import unittest
from unittest.mock import patch

from analog_flow_guard.arduino import ArduinoAlarmOutput
from analog_flow_guard.config import ArduinoConfig


class FakeSerial:
    def __init__(self, port, baudrate, timeout):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.is_open = True
        self.writes = []

    def write(self, data):
        self.writes.append(data)

    def close(self):
        self.is_open = False


class ArduinoAlarmOutputTests(unittest.TestCase):
    def test_disabled_output_does_not_connect(self):
        output = ArduinoAlarmOutput(ArduinoConfig(enabled=False))
        output.update(True, now=10)
        self.assertEqual(output.status, "DISABLED")
        self.assertIsNone(output.serial)

    def test_sends_normal_and_alarm_commands(self):
        fake_module = types.SimpleNamespace(Serial=FakeSerial)
        config = ArduinoConfig(
            enabled=True,
            port="COM6",
            reconnect_sec=0,
            heartbeat_sec=2,
            connection_settle_sec=0,
        )
        output = ArduinoAlarmOutput(config)
        with patch.dict(sys.modules, {"serial": fake_module}):
            output.update(False, now=10)
            output.update(True, now=11)
        self.assertEqual(output.serial.writes, [b"0\n", b"1\n"])
        self.assertEqual(output.status, "CONNECTED (COM6) TX=1 PROBLEM")

    def test_waits_for_usb_board_reset_before_first_command(self):
        fake_module = types.SimpleNamespace(Serial=FakeSerial)
        config = ArduinoConfig(enabled=True, port="COM7", reconnect_sec=0, connection_settle_sec=2)
        output = ArduinoAlarmOutput(config)
        with patch.dict(sys.modules, {"serial": fake_module}):
            output.update(True, now=10)
            self.assertEqual(output.serial.writes, [])
            output.update(True, now=11.9)
            self.assertEqual(output.serial.writes, [])
            output.update(True, now=12.0)
        self.assertEqual(output.serial.writes, [b"1\n"])


if __name__ == "__main__":
    unittest.main()
