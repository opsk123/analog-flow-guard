import unittest

import cv2
import numpy as np

from analog_flow_guard.config import DetectorConfig
from analog_flow_guard.vision import CircularMovingAverage, NeedleDetector, assess_image_quality


class NeedleDetectorTests(unittest.TestCase):
    def test_detects_synthetic_dark_needle(self):
        image = np.full((300, 300, 3), 235, dtype=np.uint8)
        center = (150, 150)
        cv2.line(image, center, (150, 45), (10, 10, 10), 5)
        detector = NeedleDetector(DetectorConfig(confidence_threshold=1.0))
        result = detector.detect(image, center, 140)
        self.assertIsNotNone(result)
        self.assertLess(abs((result.angle_deg - 270 + 180) % 360 - 180), 3)

    def test_circular_average_crosses_zero(self):
        average = CircularMovingAverage(2)
        average.add(359)
        result = average.add(1)
        self.assertTrue(result < 1 or result > 359)

    def test_allowed_sweep_ignores_darker_line_outside_gauge_range(self):
        image = np.full((300, 300, 3), 235, dtype=np.uint8)
        center = (150, 150)
        cv2.line(image, center, (150, 45), (0, 0, 0), 8)
        cv2.line(image, center, (255, 150), (30, 30, 30), 5)
        detector = NeedleDetector(DetectorConfig(confidence_threshold=0.5))
        result = detector.detect(image, center, 140, angle_allowed=lambda angle: angle < 20 or angle > 340)
        self.assertIsNotNone(result)
        self.assertLess(abs((result.angle_deg + 180) % 360 - 180), 3)

    def test_quality_reports_low_contrast_image(self):
        image = np.full((200, 200), 128, dtype=np.uint8)
        quality = assess_image_quality(image)
        self.assertLess(quality.score, 30)
        self.assertIsNotNone(quality.warning)

    def test_polar_detector_tolerates_brightness_gradient(self):
        gradient = np.tile(np.linspace(175, 250, 320, dtype=np.uint8), (320, 1))
        image = cv2.cvtColor(gradient, cv2.COLOR_GRAY2BGR)
        center = (160, 160)
        angle = 215.0
        endpoint = (
            int(center[0] + 145 * 0.65 * np.cos(np.deg2rad(angle))),
            int(center[1] + 145 * 0.65 * np.sin(np.deg2rad(angle))),
        )
        cv2.line(image, center, endpoint, (20, 20, 20), 5)
        detector = NeedleDetector(DetectorConfig(confidence_threshold=1.0))
        result = detector.detect(image, center, 145)
        self.assertIsNotNone(result)
        self.assertLess(abs((result.angle_deg - angle + 180) % 360 - 180), 3)


if __name__ == "__main__":
    unittest.main()
