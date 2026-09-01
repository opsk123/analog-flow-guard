import unittest

import cv2
import numpy as np

from analog_flow_guard.config import DetectorConfig
from analog_flow_guard.geometry import PerspectiveRectifier
from analog_flow_guard.vision import NeedleDetector


class PerspectiveRectifierTests(unittest.TestCase):
    def test_rectifies_multiple_camera_angles_and_recovers_needle_angle(self):
        cases = (
            ([[230, 45], [445, 205], [260, 405], [60, 230]], 35.0),
            ([[180, 65], [430, 125], [295, 390], [80, 300]], 145.0),
            ([[275, 40], [440, 285], [190, 410], [55, 150]], 255.0),
        )
        for points, angle in cases:
            with self.subTest(points=points, angle=angle):
                rectifier = PerspectiveRectifier(points, output_size=400, padding_ratio=0.06)
                canonical = np.full((400, 400, 3), 230, dtype=np.uint8)
                center = (200, 200)
                radius = 176
                cv2.circle(canonical, center, radius, (30, 30, 30), 3)
                endpoint = (
                    int(center[0] + radius * 0.62 * np.cos(np.deg2rad(angle))),
                    int(center[1] + radius * 0.62 * np.sin(np.deg2rad(angle))),
                )
                cv2.line(canonical, center, endpoint, (5, 5, 5), 6)
                tilted = cv2.warpPerspective(
                    canonical,
                    rectifier.inverse_matrix,
                    (500, 450),
                    flags=cv2.INTER_LINEAR,
                    borderValue=(230, 230, 230),
                )
                corrected = rectifier.rectify(tilted)
                detector = NeedleDetector(DetectorConfig(confidence_threshold=1.0))
                result = detector.detect(corrected.image, corrected.center, corrected.radius)
                self.assertIsNotNone(result)
                error = abs((result.angle_deg - angle + 180) % 360 - 180)
                self.assertLess(error, 3.0)

    def test_rejects_wrong_point_order(self):
        with self.assertRaises(ValueError):
            PerspectiveRectifier([[100, 20], [100, 180], [180, 100], [20, 100]])


if __name__ == "__main__":
    unittest.main()
