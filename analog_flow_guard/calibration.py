from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import CalibrationPoint


def clockwise_distance(origin: float, angle: float) -> float:
    return (angle - origin) % 360.0


@dataclass(frozen=True)
class PreparedPoint:
    position: float
    flow: float
    angle_deg: float


class GaugeCalibration:
    """Circular angle to flow mapping with piecewise-linear interpolation."""

    def __init__(self, points: list[CalibrationPoint], direction: str = "clockwise") -> None:
        if direction not in {"clockwise", "counterclockwise"}:
            raise ValueError("direction must be 'clockwise' or 'counterclockwise'")
        if len(points) < 2:
            raise ValueError("at least two calibration points are required")
        if len({point.flow for point in points}) != len(points):
            raise ValueError("calibration flow values must be unique")

        ordered = sorted(points, key=lambda point: point.flow)
        origin = ordered[0].angle_deg % 360.0
        sign = 1.0 if direction == "clockwise" else -1.0
        prepared = [
            PreparedPoint(
                position=clockwise_distance(origin, sign * point.angle_deg),
                flow=point.flow,
                angle_deg=point.angle_deg % 360.0,
            )
            for point in ordered
        ]
        # Transforming both values puts the origin at zero for either direction.
        if direction == "counterclockwise":
            prepared = [
                PreparedPoint(
                    position=clockwise_distance((-origin) % 360.0, (-p.angle_deg) % 360.0),
                    flow=p.flow,
                    angle_deg=p.angle_deg,
                )
                for p in prepared
            ]
        if prepared[0].position > 1e-6:
            raise ValueError("internal calibration origin error")
        if any(b.position <= a.position for a, b in zip(prepared, prepared[1:])):
            raise ValueError(
                "angles must progress in the selected direction as flow increases; "
                "check point values or direction"
            )
        self.direction = direction
        self.origin = origin
        self.points = prepared

    def position_for_angle(self, angle_deg: float) -> float:
        if self.direction == "clockwise":
            return clockwise_distance(self.origin, angle_deg)
        return clockwise_distance((-self.origin) % 360.0, (-angle_deg) % 360.0)

    def flow_for_angle(self, angle_deg: float) -> float:
        positions = np.asarray([point.position for point in self.points], dtype=float)
        flows = np.asarray([point.flow for point in self.points], dtype=float)
        position = self.position_for_angle(angle_deg)
        # Outside the sweep, choose the closest circular endpoint. This prevents a
        # tiny jitter just before the zero point from wrapping to maximum flow.
        if position > positions[-1]:
            distance_to_min = min(position, 360.0 - position)
            distance_to_max = min(abs(position - positions[-1]), 360.0 - abs(position - positions[-1]))
            return float(flows[0] if distance_to_min <= distance_to_max else flows[-1])
        # Saturate rather than extrapolate; extrapolation is unsafe for alarms.
        return float(np.interp(position, positions, flows))

    def is_angle_in_sweep(self, angle_deg: float, margin_deg: float = 0.0) -> bool:
        position = self.position_for_angle(angle_deg)
        maximum = self.points[-1].position
        return position <= maximum + margin_deg or position >= 360.0 - margin_deg

    @property
    def min_flow(self) -> float:
        return self.points[0].flow

    @property
    def max_flow(self) -> float:
        return self.points[-1].flow
