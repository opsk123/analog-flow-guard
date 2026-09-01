from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class RectifiedGauge:
    image: np.ndarray
    center: tuple[float, float]
    radius: float


class PerspectiveRectifier:
    """Rectifies a planar gauge from top/right/bottom/left rim points."""

    def __init__(
        self,
        points: list[list[float]] | np.ndarray,
        output_size: int = 600,
        padding_ratio: float = 0.06,
    ) -> None:
        source = np.asarray(points, dtype=np.float32)
        if source.shape != (4, 2):
            raise ValueError("perspective correction requires four 2D points")
        if output_size < 100:
            raise ValueError("rectified output size must be at least 100 pixels")
        if not 0.0 <= padding_ratio < 0.25:
            raise ValueError("rectified padding ratio must be between 0 and 0.25")
        if not cv2.isContourConvex(source.reshape((-1, 1, 2)).astype(np.int32)):
            raise ValueError("points must be ordered top, right, bottom, left around the rim")
        area = abs(float(cv2.contourArea(source)))
        if area < 1000:
            raise ValueError("selected gauge area is too small")

        size = int(output_size)
        center = size / 2.0
        padding = size * float(padding_ratio)
        destination = np.asarray(
            [
                [center, padding],
                [size - 1 - padding, center],
                [center, size - 1 - padding],
                [padding, center],
            ],
            dtype=np.float32,
        )
        self.source_points = source
        self.output_size = size
        self.padding_ratio = float(padding_ratio)
        self.matrix = cv2.getPerspectiveTransform(source, destination)
        self.inverse_matrix = np.linalg.inv(self.matrix)

    @property
    def center(self) -> tuple[float, float]:
        value = self.output_size / 2.0
        return value, value

    @property
    def radius(self) -> float:
        return self.output_size * (0.5 - self.padding_ratio)

    def rectify(self, frame: np.ndarray) -> RectifiedGauge:
        image = cv2.warpPerspective(
            frame,
            self.matrix,
            (self.output_size, self.output_size),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        return RectifiedGauge(image=image, center=self.center, radius=self.radius)

    def point_to_source(self, point: tuple[float, float]) -> tuple[int, int]:
        values = np.asarray([[[point[0], point[1]]]], dtype=np.float32)
        transformed = cv2.perspectiveTransform(values, self.inverse_matrix)[0, 0]
        return int(round(float(transformed[0]))), int(round(float(transformed[1])))
