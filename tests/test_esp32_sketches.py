import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Esp32SketchTests(unittest.TestCase):
    def setUp(self):
        self.sender = (
            ROOT / "esp32" / "esp32_1_pc_led_sender" / "esp32_1_pc_led_sender.ino"
        ).read_text(encoding="utf-8")
        self.receiver = (
            ROOT / "esp32" / "esp32_2_battery_display" / "esp32_2_battery_display.ino"
        ).read_text(encoding="utf-8")

    def test_receiver_displays_low_gas_on_1602_lcd_without_led_or_buzzer(self):
        receiver = self.receiver
        config = (ROOT / "esp32" / "esp32_2_battery_display" / "config.h").read_text(encoding="utf-8")
        self.assertIn("LCD_SDA_PIN", config)
        self.assertIn("LCD_SCL_PIN", config)
        self.assertIn("LCD_I2C_ADDRESS = 0x3F", config)
        self.assertIn("LiquidCrystal_I2C", receiver)
        self.assertIn('writeLine(0, "GAS STATUS")', receiver)
        self.assertIn('writeLine(1, "LOW")', receiver)
        self.assertNotIn("ALARM_LED_PIN", config)
        self.assertNotIn("BUZZER_PIN", config)
        self.assertNotIn("setAlarmOutputs", receiver)

    def test_sender_and_receiver_use_same_radio_channel(self):
        sender = (ROOT / "esp32" / "esp32_1_pc_led_sender" / "config.h").read_text(encoding="utf-8")
        receiver = (ROOT / "esp32" / "esp32_2_battery_display" / "config.h").read_text(encoding="utf-8")
        expected = "constexpr uint8_t ESPNOW_CHANNEL = 6;"
        self.assertIn(expected, sender)
        self.assertIn(expected, receiver)

    def test_sender_and_receiver_use_identical_protocol(self):
        sender = (ROOT / "esp32" / "esp32_1_pc_led_sender" / "protocol.h").read_text(encoding="utf-8")
        receiver = (ROOT / "esp32" / "esp32_2_battery_display" / "protocol.h").read_text(encoding="utf-8")
        self.assertEqual(sender, receiver)

    def test_problem_state_is_steady_and_links_fail_safe(self):
        self.assertIn("PC_COMMAND_TIMEOUT_MS", self.sender)
        self.assertIn("DeviceState::Problem", self.sender)
        self.assertIn("RADIO_TIMEOUT_MS", self.receiver)
        self.assertIn("DisplayState::RadioLinkError", self.receiver)
        self.assertIn("DisplayState::GasLow", self.receiver)
        self.assertIn("DeviceState::PcLinkError", self.receiver)
        self.assertNotIn("ALARM_BLINK_INTERVAL_MS", self.receiver)
        self.assertNotIn("lastAlarmToggleMs", self.receiver)

    def test_sender_uses_steady_normal_and_problem_leds(self):
        self.assertIn("digitalWrite(GREEN_LED_PIN, HIGH);", self.sender)
        self.assertIn("digitalWrite(RED_LED_PIN, HIGH);", self.sender)
        self.assertNotIn("updateProblemBlink", self.sender)

    def test_sender_uses_same_baudrate_as_python_default(self):
        config = (ROOT / "analog_flow_guard" / "config.py").read_text(encoding="utf-8")
        self.assertIn("Serial.begin(115200);", self.sender)
        self.assertIn("baudrate: int = 115200", config)


if __name__ == "__main__":
    unittest.main()
