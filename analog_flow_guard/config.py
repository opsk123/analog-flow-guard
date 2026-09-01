from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CameraConfig:
    index: int = 0
    width: int = 1280
    height: int = 720
    fps: float = 30.0
    use_mjpeg: bool = True
    buffer_size: int = 1
    autofocus: bool | None = None
    focus: float | None = None
    auto_exposure: bool | None = None
    exposure: float | None = None


@dataclass
class GaugeConfig:
    # ROI is stored in full camera-frame coordinates. Center is ROI-relative.
    roi: list[int] | None = None
    center: list[float] | None = None
    radius: float | None = None
    # Full-frame points clicked in this order: top, right, bottom, left.
    perspective_points: list[list[float]] = field(default_factory=list)
    rectified_size: int = 480
    rectified_padding_ratio: float = 0.06


@dataclass
class DetectorConfig:
    radial_min_ratio: float = 0.20
    radial_max_ratio: float = 0.65
    angle_step_deg: float = 1.0
    line_half_width_px: int = 2
    confidence_threshold: float = 1.8
    smoothing_window: int = 10
    continuity_weight: float = 0.18
    polar_mode: bool = True
    minimum_image_quality: float = 18.0


@dataclass
class CalibrationPoint:
    angle_deg: float
    flow: float


@dataclass
class CalibrationConfig:
    unit: str = "L/min"
    # OpenCV image coordinates increase clockwise (right=0, down=90).
    direction: str = "clockwise"
    points: list[CalibrationPoint] = field(default_factory=list)


@dataclass
class AlarmConfig:
    low_flow_threshold: float = 0.15
    hysteresis: float = 0.1
    trigger_duration_sec: float = 1.0
    detection_error_timeout_sec: float = 1.0


@dataclass
class ArduinoConfig:
    enabled: bool = False
    port: str = "COM3"
    baudrate: int = 115200
    heartbeat_sec: float = 2.0
    reconnect_sec: float = 3.0
    # Opening a USB serial port resets Arduino Uno and many ESP32 boards.
    connection_settle_sec: float = 2.0


@dataclass
class RemoteConfig:
    enabled: bool = False
    function_url: str = ""
    device_id: str = "FLOW-01"
    token_env_var: str = "FLOW_DEVICE_TOKEN"
    # 60 seconds is the MVP demonstration setting. Change to 3600 for
    # normal operation after the demonstration.
    upload_interval_sec: float = 60.0
    retry_interval_sec: float = 300.0
    request_timeout_sec: float = 15.0


@dataclass
class AppConfig:
    camera: CameraConfig = field(default_factory=CameraConfig)
    gauge: GaugeConfig = field(default_factory=GaugeConfig)
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    calibration: CalibrationConfig = field(default_factory=CalibrationConfig)
    alarm: AlarmConfig = field(default_factory=AlarmConfig)
    arduino: ArduinoConfig = field(default_factory=ArduinoConfig)
    remote: RemoteConfig = field(default_factory=RemoteConfig)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AppConfig":
        calibration = dict(raw.get("calibration", {}))
        calibration["points"] = [CalibrationPoint(**p) for p in calibration.get("points", [])]
        return cls(
            camera=CameraConfig(**raw.get("camera", {})),
            gauge=GaugeConfig(**raw.get("gauge", {})),
            detector=DetectorConfig(**raw.get("detector", {})),
            calibration=CalibrationConfig(**calibration),
            alarm=AlarmConfig(**raw.get("alarm", {})),
            arduino=ArduinoConfig(**raw.get("arduino", {})),
            remote=RemoteConfig(**raw.get("remote", {})),
        )


class ConfigStore:
    def __init__(self, path: str | Path = "flow_guard_config.json") -> None:
        self.path = Path(path)

    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()
        with self.path.open("r", encoding="utf-8") as stream:
            return AppConfig.from_dict(json.load(stream))

    def save(self, config: AppConfig) -> None:
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(asdict(config), stream, ensure_ascii=False, indent=2)
        temporary.replace(self.path)
