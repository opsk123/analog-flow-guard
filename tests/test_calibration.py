import unittest

from analog_flow_guard.calibration import GaugeCalibration
from analog_flow_guard.config import CalibrationPoint


class GaugeCalibrationTests(unittest.TestCase):
    def test_clockwise_wrap_and_piecewise_interpolation(self):
        calibration = GaugeCalibration(
            [
                CalibrationPoint(300, 0),
                CalibrationPoint(350, 25),
                CalibrationPoint(40, 100),
            ],
            "clockwise",
        )
        self.assertAlmostEqual(calibration.flow_for_angle(325), 12.5)
        self.assertAlmostEqual(calibration.flow_for_angle(15), 62.5)

    def test_counterclockwise(self):
        calibration = GaugeCalibration(
            [CalibrationPoint(40, 0), CalibrationPoint(300, 100)],
            "counterclockwise",
        )
        self.assertAlmostEqual(calibration.flow_for_angle(350), 50.0)

    def test_jitter_before_minimum_clamps_to_minimum(self):
        calibration = GaugeCalibration(
            [CalibrationPoint(300, 0), CalibrationPoint(40, 100)],
            "clockwise",
        )
        self.assertEqual(calibration.flow_for_angle(299), 0)
        self.assertEqual(calibration.flow_for_angle(41), 100)

    def test_sweep_supports_wrap_and_margin(self):
        calibration = GaugeCalibration(
            [CalibrationPoint(300, 0), CalibrationPoint(40, 100)],
            "clockwise",
        )
        self.assertTrue(calibration.is_angle_in_sweep(350))
        self.assertTrue(calibration.is_angle_in_sweep(295, margin_deg=10))
        self.assertFalse(calibration.is_angle_in_sweep(200, margin_deg=10))

    def test_rejects_wrong_direction(self):
        with self.assertRaises(ValueError):
            GaugeCalibration(
                [CalibrationPoint(300, 0), CalibrationPoint(200, 50), CalibrationPoint(350, 100)],
                "clockwise",
            )


if __name__ == "__main__":
    unittest.main()
