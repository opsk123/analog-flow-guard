from __future__ import annotations

import argparse
import math
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

from .alarm import LowFlowAlarm, MonitorStatus
from .arduino import ArduinoAlarmOutput
from .calibration import GaugeCalibration
from .config import AppConfig, CalibrationPoint, ConfigStore
from .geometry import PerspectiveRectifier
from .remote import PeriodicFlowUploader
from .vision import CircularMovingAverage, NeedleDetector


class FlowGuardApp:
    PREVIEW_MAX = (900, 650)

    def __init__(self, root: tk.Tk, store: ConfigStore) -> None:
        self.root = root
        self.store = store
        try:
            self.config = store.load()
        except Exception as exc:
            messagebox.showwarning("설정 오류", f"설정 파일을 읽지 못해 기본값으로 시작합니다.\n{exc}")
            self.config = AppConfig()
        self.capture: cv2.VideoCapture | None = None
        self.capture_thread: threading.Thread | None = None
        self.capture_stop = threading.Event()
        self.capture_lock = threading.Lock()
        self.captured_frame = None
        self.captured_frame_number = 0
        self.processed_frame_number = 0
        self.last_capture_time = 0.0
        self.frame_interval_ms = max(1, round(1000.0 / max(1.0, self.config.camera.fps)))
        self.frame = None
        self.current_angle: float | None = None
        self.interaction: str | None = None
        self.drag_start: tuple[int, int] | None = None
        self.drag_current: tuple[int, int] | None = None
        self.perspective_clicks: list[tuple[int, int]] = []
        self.image_scale = (1.0, 1.0)
        self.detector = NeedleDetector(self.config.detector)
        self.smoother = CircularMovingAverage(self.config.detector.smoothing_window)
        self.alarm = LowFlowAlarm(self.config.alarm)
        self.arduino = ArduinoAlarmOutput(self.config.arduino)
        self.remote = PeriodicFlowUploader(self.config.remote)
        self.calibration: GaugeCalibration | None = None
        self.rectifier: PerspectiveRectifier | None = None
        self._prepare_calibration(show_error=False)
        self._prepare_rectifier(show_error=False)
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.start_camera()
        self.root.after(0, self._tick)

    def _build_ui(self) -> None:
        self.root.title("Analog Flow Guard")
        self.root.minsize(1650, 1230)
        main = ttk.Frame(self.root, padding=8)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=1)

        self.preview = ttk.Label(main, anchor="nw", text="카메라 연결 중...")
        self.preview.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.preview.bind("<ButtonPress-1>", self._mouse_down)
        self.preview.bind("<B1-Motion>", self._mouse_move)
        self.preview.bind("<ButtonRelease-1>", self._mouse_up)

        panel = ttk.Frame(main, width=300)
        panel.grid(row=0, column=1, sticky="ns")

        status_box = ttk.LabelFrame(panel, text="FLOW MONITOR", padding=10)
        status_box.pack(fill="x", pady=(0, 8))
        self.flow_var = tk.StringVar(value="--")
        self.angle_var = tk.StringVar(value="각도: --")
        self.status_var = tk.StringVar(value="설정 필요")
        self.quality_var = tk.StringVar(value="영상 품질: --")
        self.arduino_status_var = tk.StringVar(value="Controller: --")
        self.web_status_var = tk.StringVar(value=f"Web: {self.remote.status}")
        ttk.Label(status_box, textvariable=self.flow_var, font=("Arial", 22, "bold")).pack()
        ttk.Label(status_box, textvariable=self.angle_var).pack()
        ttk.Label(status_box, textvariable=self.quality_var).pack()
        ttk.Label(status_box, textvariable=self.arduino_status_var).pack()
        ttk.Label(status_box, textvariable=self.web_status_var).pack()
        self.status_label = tk.Label(status_box, textvariable=self.status_var, font=("Arial", 13, "bold"))
        self.status_label.pack(fill="x", pady=(8, 0))

        setup = ttk.LabelFrame(panel, text="1. 게이지 위치", padding=8)
        setup.pack(fill="x", pady=(0, 8))
        ttk.Button(setup, text="원근 보정 4점 지정 (권장)", command=self._start_perspective).pack(fill="x")
        ttk.Button(setup, text="원근 보정 해제", command=self._clear_perspective).pack(fill="x", pady=(4, 0))
        ttk.Button(setup, text="ROI 드래그 지정", command=lambda: self._set_interaction("roi")).pack(fill="x")
        ttk.Button(setup, text="중심점 클릭 지정", command=lambda: self._set_interaction("center")).pack(fill="x", pady=(4, 0))
        ttk.Label(setup, text="4점 순서: 상 → 우 → 하 → 좌").pack(anchor="w", pady=(4, 0))
        self.autofocus_var = tk.BooleanVar(value=True if self.config.camera.autofocus is None else self.config.camera.autofocus)
        self.auto_exposure_var = tk.BooleanVar(value=True if self.config.camera.auto_exposure is None else self.config.camera.auto_exposure)
        ttk.Checkbutton(setup, text="자동 초점", variable=self.autofocus_var).pack(anchor="w")
        ttk.Checkbutton(setup, text="자동 노출", variable=self.auto_exposure_var).pack(anchor="w")

        calibration = ttk.LabelFrame(panel, text="2. 각도–유량 보정", padding=8)
        calibration.pack(fill="both", expand=True, pady=(0, 8))
        row = ttk.Frame(calibration)
        row.pack(fill="x")
        ttk.Label(row, text="현재 위치 유량").pack(side="left")
        self.point_flow_var = tk.StringVar(value="0")
        ttk.Entry(row, textvariable=self.point_flow_var, width=9).pack(side="right")
        ttk.Button(calibration, text="현재 각도 기준점 추가", command=self._add_calibration_point).pack(fill="x", pady=4)
        self.points_list = tk.Listbox(calibration, height=6)
        self.points_list.pack(fill="both", expand=True)
        ttk.Button(calibration, text="선택 기준점 삭제", command=self._delete_calibration_point).pack(fill="x", pady=(4, 0))
        direction_row = ttk.Frame(calibration)
        direction_row.pack(fill="x", pady=(5, 0))
        ttk.Label(direction_row, text="유량 증가 방향").pack(side="left")
        self.direction_var = tk.StringVar(value=self.config.calibration.direction)
        ttk.Combobox(
            direction_row,
            textvariable=self.direction_var,
            values=("clockwise", "counterclockwise"),
            state="readonly",
            width=15,
        ).pack(side="right")
        self._refresh_points()

        alarm_box = ttk.LabelFrame(panel, text="3. 경보/Arduino", padding=8)
        alarm_box.pack(fill="x", pady=(0, 8))
        self.threshold_var = tk.StringVar(value=str(self.config.alarm.low_flow_threshold))
        self.hysteresis_var = tk.StringVar(value=str(self.config.alarm.hysteresis))
        self.delay_var = tk.StringVar(value=str(self.config.alarm.trigger_duration_sec))
        self.port_var = tk.StringVar(value=self.config.arduino.port)
        self.arduino_enabled_var = tk.BooleanVar(value=self.config.arduino.enabled)
        for label, variable in (
            ("저유량 기준", self.threshold_var),
            ("해제 여유값", self.hysteresis_var),
            ("지속 시간(초)", self.delay_var),
            ("Arduino/ESP32 포트", self.port_var),
        ):
            line = ttk.Frame(alarm_box)
            line.pack(fill="x", pady=1)
            ttk.Label(line, text=label).pack(side="left")
            ttk.Entry(line, textvariable=variable, width=11).pack(side="right")
        ttk.Checkbutton(alarm_box, text="Arduino/ESP32 출력 사용", variable=self.arduino_enabled_var).pack(anchor="w")

        web_box = ttk.LabelFrame(panel, text="4. 웹 전송", padding=8)
        web_box.pack(fill="x", pady=(0, 8))
        self.remote_enabled_var = tk.BooleanVar(value=self.config.remote.enabled)
        self.remote_url_var = tk.StringVar(value=self.config.remote.function_url)
        self.remote_device_var = tk.StringVar(value=self.config.remote.device_id)
        ttk.Checkbutton(web_box, text="주기적으로 웹으로 전송", variable=self.remote_enabled_var).pack(anchor="w")
        interval_label = "1분 (MVP 시연)" if self.config.remote.upload_interval_sec < 3600 else "1시간 (운영)"
        self.remote_interval_var = tk.StringVar(value=interval_label)
        interval_row = ttk.Frame(web_box)
        interval_row.pack(fill="x", pady=1)
        ttk.Label(interval_row, text="전송 주기").pack(side="left")
        ttk.Combobox(
            interval_row,
            textvariable=self.remote_interval_var,
            values=("1분 (MVP 시연)", "1시간 (운영)"),
            state="readonly",
            width=15,
        ).pack(side="right")
        for label, variable in (
            ("Function URL", self.remote_url_var),
            ("장치 ID", self.remote_device_var),
        ):
            line = ttk.Frame(web_box)
            line.pack(fill="x", pady=1)
            ttk.Label(line, text=label).pack(side="left")
            ttk.Entry(line, textvariable=variable, width=24).pack(side="right")
        ttk.Label(web_box, text=f"인증 토큰: 환경변수 {self.config.remote.token_env_var}").pack(anchor="w", pady=(3, 0))
        ttk.Button(panel, text="설정 저장 및 적용", command=self.save_and_apply).pack(fill="x")

    def start_camera(self) -> None:
        self._stop_camera()
        # Let OpenCV use the Windows default backend (normally Media Foundation).
        # Forcing DirectShow caused visible brightness waves/tearing with some
        # UVC cameras and recent OpenCV builds, while the same camera was stable
        # in applications opening it through the default backend.
        self.capture = cv2.VideoCapture(self.config.camera.index)
        if self.config.camera.use_mjpeg:
            self.capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.camera.width)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.camera.height)
        self.capture.set(cv2.CAP_PROP_FPS, self.config.camera.fps)
        self.capture.set(cv2.CAP_PROP_BUFFERSIZE, max(1, self.config.camera.buffer_size))
        self.frame_interval_ms = max(1, round(1000.0 / max(1.0, self.config.camera.fps)))
        self._apply_camera_controls()
        if self.capture.isOpened():
            self.capture_stop.clear()
            self.capture_thread = threading.Thread(
                target=self._capture_frames,
                name="camera-capture",
                daemon=True,
            )
            self.capture_thread.start()

    def _capture_frames(self) -> None:
        """Continuously drain DirectShow and retain only the newest complete frame.

        Gauge analysis can occasionally take longer than one camera period. Reading
        on the Tk thread allowed compressed frames to accumulate in the driver,
        which presents as torn/corrupted video on a number of MJPEG webcams.
        """
        capture = self.capture
        while capture is not None and not self.capture_stop.is_set():
            ok, frame = capture.read()
            if not ok or frame is None or frame.size == 0:
                time.sleep(0.01)
                continue
            # Do not retain memory owned/reused by the camera backend.
            complete_frame = np.ascontiguousarray(frame).copy()
            with self.capture_lock:
                self.captured_frame = complete_frame
                self.captured_frame_number += 1
                self.last_capture_time = time.monotonic()

    def _stop_camera(self) -> None:
        self.capture_stop.set()
        capture = self.capture
        if capture is not None:
            capture.release()
        thread = self.capture_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
        self.capture_thread = None
        self.capture = None
        with self.capture_lock:
            self.captured_frame = None
            self.captured_frame_number = 0
            self.processed_frame_number = 0
            self.last_capture_time = 0.0

    def _apply_camera_controls(self) -> None:
        if self.capture is None:
            return
        camera = self.config.camera
        if camera.autofocus is not None:
            self.capture.set(cv2.CAP_PROP_AUTOFOCUS, 1 if camera.autofocus else 0)
        if camera.focus is not None:
            self.capture.set(cv2.CAP_PROP_FOCUS, camera.focus)
        if camera.auto_exposure is not None:
            # DirectShow uses 0.75 for auto and 0.25 for manual exposure.
            self.capture.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75 if camera.auto_exposure else 0.25)
        if camera.exposure is not None:
            self.capture.set(cv2.CAP_PROP_EXPOSURE, camera.exposure)

    def _tick(self) -> None:
        started = time.perf_counter()
        try:
            self._process_frame()
        except Exception as exc:
            self.status_var.set(f"오류: {exc}")
            self.status_label.configure(bg="#ffcc80", fg="black")
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            # Keep a stable target rate. The old implementation always waited
            # 30 ms after processing, unnecessarily adding processing time to
            # every frame and sharply reducing the effective FPS.
            delay_ms = max(1, round(self.frame_interval_ms - elapsed_ms))
            self.root.after(delay_ms, self._tick)

    def _process_frame(self) -> None:
        if self.capture is None or not self.capture.isOpened():
            self.status_var.set("CAMERA CONNECTION ERROR")
            self._apply_alarm(None)
            return
        with self.capture_lock:
            frame_number = self.captured_frame_number
            last_capture_time = self.last_capture_time
            if frame_number == self.processed_frame_number or self.captured_frame is None:
                frame = None
            else:
                frame = self.captured_frame.copy()
                self.processed_frame_number = frame_number
        if frame is None:
            # The UI timer can run just before the next capture completes. That
            # is not a camera failure; preserve the last result unless frames
            # have actually stopped arriving.
            stalled_for = time.monotonic() - last_capture_time if last_capture_time else float("inf")
            if stalled_for > max(0.5, self.frame_interval_ms / 1000.0 * 4):
                self._apply_alarm(None)
            return
        self.frame = frame
        if self.interaction == "perspective":
            display = frame.copy()
            self._draw_interaction(display)
            self._show_frame(display)
            return
        if self.rectifier is not None:
            corrected = self.rectifier.rectify(frame)
            roi = corrected.image
            display = roi.copy()
            center, radius = corrected.center, corrected.radius
            x, y = 0, 0
            cv2.putText(display, "PERSPECTIVE CORRECTED", (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (40, 180, 255), 2)
        else:
            display = frame.copy()
            roi_rect = self._roi_rect(frame)
            x, y, width, height = roi_rect
            cv2.rectangle(display, (x, y), (x + width, y + height), (255, 180, 0), 2)
            roi = frame[y : y + height, x : x + width]
            center, radius = self._center_radius(roi)
        cv2.circle(display, (int(x + center[0]), int(y + center[1])), 5, (0, 255, 255), -1)
        angle_allowed = None
        if self.calibration is not None:
            angle_allowed = lambda angle: self.calibration.is_angle_in_sweep(angle, margin_deg=10.0)
        detection = self.detector.detect(roi, center, radius, angle_allowed=angle_allowed)
        quality = self.detector.last_quality
        if quality is None:
            self.quality_var.set("영상 품질: --")
        else:
            suffix = f" · {quality.warning}" if quality.warning else ""
            self.quality_var.set(f"영상 품질: {quality.score:.0f}/100{suffix}")
        flow = None
        if detection is not None:
            self.current_angle = self.smoother.add(detection.angle_deg)
            self.angle_var.set(f"각도: {self.current_angle:.1f}°  신뢰도: {detection.confidence:.1f}")
            # Use the smoothed angle for both display and flow conversion.
            endpoint = (
                int(x + center[0] + radius * self.config.detector.radial_max_ratio * math.cos(math.radians(self.current_angle))),
                int(y + center[1] + radius * self.config.detector.radial_max_ratio * math.sin(math.radians(self.current_angle))),
            )
            cv2.line(display, (int(x + center[0]), int(y + center[1])), endpoint, (0, 255, 0), 3)
            if self.calibration is not None:
                flow = self.calibration.flow_for_angle(self.current_angle)
                self.flow_var.set(f"{flow:.2f} {self.config.calibration.unit}")
            else:
                self.flow_var.set("보정점 2개 필요")
        else:
            self.current_angle = None
            self.angle_var.set("각도: 인식 실패")
            self.flow_var.set("--")
        if self.calibration is None:
            # Missing calibration is not a trustworthy NORMAL state.
            self.arduino.update(True)
            self.arduino_status_var.set(f"Controller: {self.arduino.status}")
            self.status_var.set("CALIBRATION REQUIRED")
            self.status_label.configure(bg="#90a4ae", fg="white")
        else:
            self._apply_alarm(flow)
        if flow is not None:
            self.remote.observe(flow)
        self.web_status_var.set(f"Web: {self.remote.status}")
        self._draw_interaction(display)
        self._show_frame(display)

    def _apply_alarm(self, flow: float | None) -> None:
        result = self.alarm.update(flow)
        # ESP32 receives only NORMAL/PROBLEM. A persistent vision failure is a
        # problem as well, even when it did not originate from low flow.
        controller_problem = result.active or result.status == MonitorStatus.DETECTION_ERROR
        self.arduino.update(controller_problem)
        self.arduino_status_var.set(f"Controller: {self.arduino.status}")
        self.status_var.set(result.status.value)
        if result.status == MonitorStatus.LOW_FLOW:
            self.status_label.configure(bg="#e53935", fg="white")
        elif result.status == MonitorStatus.DETECTION_ERROR:
            self.status_label.configure(bg="#ffb300", fg="black")
        elif result.status == MonitorStatus.PENDING:
            self.status_label.configure(bg="#ffe082", fg="black")
        else:
            self.status_label.configure(bg="#43a047", fg="white")

    def _roi_rect(self, frame) -> tuple[int, int, int, int]:
        height, width = frame.shape[:2]
        if not self.config.gauge.roi:
            return 0, 0, width, height
        x, y, roi_width, roi_height = (int(v) for v in self.config.gauge.roi)
        x, y = max(0, x), max(0, y)
        return x, y, max(1, min(roi_width, width - x)), max(1, min(roi_height, height - y))

    def _center_radius(self, roi) -> tuple[tuple[float, float], float]:
        height, width = roi.shape[:2]
        center = self.config.gauge.center or [width / 2.0, height / 2.0]
        radius = self.config.gauge.radius or min(width, height) * 0.48
        return (float(center[0]), float(center[1])), float(radius)

    def _show_frame(self, frame) -> None:
        height, width = frame.shape[:2]
        scale = min(self.PREVIEW_MAX[0] / width, self.PREVIEW_MAX[1] / height, 1.0)
        shown_width, shown_height = int(width * scale), int(height * scale)
        shown = cv2.resize(frame, (shown_width, shown_height), interpolation=cv2.INTER_AREA)
        self.image_scale = (width / shown_width, height / shown_height)
        rgb = cv2.cvtColor(shown, cv2.COLOR_BGR2RGB)
        # Pillow/Tk can render corrupted rows when handed a non-contiguous
        # OpenCV view. Always provide a compact RGB buffer.
        rgb = np.ascontiguousarray(rgb)
        # Build an independent Pillow buffer. This prevents Tk from observing
        # memory that OpenCV may replace while the next frame is captured.
        image = Image.frombytes("RGB", (shown_width, shown_height), rgb.tobytes())
        photo = ImageTk.PhotoImage(image)
        self.preview.configure(image=photo, text="")
        self.preview.image = photo

    def _set_interaction(self, interaction: str) -> None:
        if interaction in {"roi", "center"} and self.rectifier is not None:
            messagebox.showinfo("원근 보정 사용 중", "ROI/중심 수동 지정은 원근 보정이 없는 정면 촬영용입니다.\n원근 보정을 다시 하려면 4점 지정 버튼을 사용하세요.")
            return
        self.interaction = interaction
        self.drag_start = None
        self.drag_current = None
        self.status_var.set("영상에서 ROI를 드래그하세요" if interaction == "roi" else "영상에서 침 회전 중심을 클릭하세요")

    def _start_perspective(self) -> None:
        if self.config.calibration.points and not messagebox.askyesno(
            "유량 재보정 필요",
            "원근 보정을 변경하면 기존 각도–유량 기준점이 무효가 되어 삭제됩니다. 계속하시겠습니까?",
        ):
            return
        self.interaction = "perspective"
        self.perspective_clicks = []
        self.drag_start = None
        self.drag_current = None
        self.status_var.set("계기판 테두리의 상단점을 클릭하세요 (1/4)")

    def _clear_perspective(self) -> None:
        if self.rectifier is None:
            return
        if self.config.calibration.points and not messagebox.askyesno(
            "유량 재보정 필요",
            "원근 보정을 해제하면 기존 각도–유량 기준점이 무효가 되어 삭제됩니다. 계속하시겠습니까?",
        ):
            return
        self.config.gauge.perspective_points = []
        self.rectifier = None
        self.config.calibration.points.clear()
        self._refresh_points()
        self._prepare_calibration(show_error=False)
        self.smoother.clear()
        self.detector.reset()
        self.status_var.set("원근 보정 해제됨: ROI와 중심점을 지정하세요")

    def _image_point(self, event) -> tuple[int, int]:
        return int(event.x * self.image_scale[0]), int(event.y * self.image_scale[1])

    def _mouse_down(self, event) -> None:
        if not self.interaction:
            return
        if self.interaction == "perspective":
            return
        self.drag_start = self._image_point(event)
        self.drag_current = self.drag_start

    def _mouse_move(self, event) -> None:
        if self.interaction == "roi" and self.drag_start:
            self.drag_current = self._image_point(event)

    def _mouse_up(self, event) -> None:
        if not self.interaction or self.frame is None:
            return
        point = self._image_point(event)
        if self.interaction == "perspective":
            self.perspective_clicks.append(point)
            labels = ("상단", "우측", "하단", "좌측")
            if len(self.perspective_clicks) < 4:
                next_index = len(self.perspective_clicks)
                self.status_var.set(f"계기판 테두리의 {labels[next_index]}점을 클릭하세요 ({next_index + 1}/4)")
                return
            old_points = self.config.gauge.perspective_points
            self.config.gauge.perspective_points = [[float(x), float(y)] for x, y in self.perspective_clicks]
            if not self._prepare_rectifier(show_error=True):
                self.config.gauge.perspective_points = old_points
                self._prepare_rectifier(show_error=False)
            else:
                self.config.gauge.center = None
                self.config.gauge.radius = None
                self.config.calibration.points.clear()
                self._refresh_points()
                self._prepare_calibration(show_error=False)
                self.smoother.clear()
                self.detector.reset()
            self.interaction = None
            self.perspective_clicks = []
        elif self.interaction == "roi" and self.drag_start:
            x1, y1 = self.drag_start
            x2, y2 = point
            x, y = min(x1, x2), min(y1, y2)
            width, height = abs(x2 - x1), abs(y2 - y1)
            if width >= 30 and height >= 30:
                self.config.gauge.roi = [x, y, width, height]
                self.config.gauge.center = [width / 2.0, height / 2.0]
                self.config.gauge.radius = min(width, height) * 0.48
                self.smoother.clear()
                self.detector.reset()
        elif self.interaction == "center":
            x, y, _, _ = self._roi_rect(self.frame)
            self.config.gauge.center = [point[0] - x, point[1] - y]
            self.smoother.clear()
            self.detector.reset()
        self.interaction = None
        self.drag_start = None
        self.drag_current = None

    def _draw_interaction(self, display) -> None:
        if self.interaction == "roi" and self.drag_start and self.drag_current:
            cv2.rectangle(display, self.drag_start, self.drag_current, (255, 0, 255), 2)
        elif self.interaction == "perspective":
            colors = ((0, 255, 255), (0, 220, 0), (255, 120, 0), (255, 0, 255))
            for index, point in enumerate(self.perspective_clicks):
                cv2.circle(display, point, 7, colors[index], -1)
                cv2.putText(display, str(index + 1), (point[0] + 8, point[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, colors[index], 2)
            if len(self.perspective_clicks) > 1:
                cv2.polylines(display, [np.asarray(self.perspective_clicks, dtype="int32")], False, (0, 255, 255), 2)

    def _prepare_rectifier(self, show_error: bool) -> bool:
        self.rectifier = None
        points = self.config.gauge.perspective_points
        if not points:
            return False
        try:
            self.rectifier = PerspectiveRectifier(
                points,
                output_size=self.config.gauge.rectified_size,
                padding_ratio=self.config.gauge.rectified_padding_ratio,
            )
            return True
        except ValueError as exc:
            if show_error:
                messagebox.showwarning("원근 보정 오류", str(exc))
            return False

    def _add_calibration_point(self) -> None:
        if self.current_angle is None:
            messagebox.showwarning("기준점 추가", "현재 침 각도가 인식되지 않았습니다.")
            return
        try:
            flow = float(self.point_flow_var.get())
        except ValueError:
            messagebox.showwarning("기준점 추가", "유량을 숫자로 입력하세요.")
            return
        self.config.calibration.points.append(CalibrationPoint(round(self.current_angle, 3), flow))
        self._refresh_points()
        self._prepare_calibration(show_error=len(self.config.calibration.points) >= 2)

    def _delete_calibration_point(self) -> None:
        selected = self.points_list.curselection()
        if selected:
            del self.config.calibration.points[selected[0]]
            self._refresh_points()
            self._prepare_calibration(show_error=False)

    def _refresh_points(self) -> None:
        self.points_list.delete(0, tk.END)
        for point in self.config.calibration.points:
            self.points_list.insert(tk.END, f"{point.angle_deg:7.2f}°  →  {point.flow:g} {self.config.calibration.unit}")

    def _prepare_calibration(self, show_error: bool) -> None:
        self.calibration = None
        if len(self.config.calibration.points) < 2:
            return
        try:
            self.calibration = GaugeCalibration(self.config.calibration.points, self.config.calibration.direction)
        except ValueError as exc:
            if show_error:
                messagebox.showwarning("보정값 오류", str(exc))

    def save_and_apply(self) -> None:
        try:
            self.config.alarm.low_flow_threshold = float(self.threshold_var.get())
            self.config.alarm.hysteresis = float(self.hysteresis_var.get())
            self.config.alarm.trigger_duration_sec = float(self.delay_var.get())
            alarm_values = (
                self.config.alarm.low_flow_threshold,
                self.config.alarm.hysteresis,
                self.config.alarm.trigger_duration_sec,
            )
            if not all(math.isfinite(value) for value in alarm_values):
                raise ValueError("경보 설정은 유한한 숫자여야 합니다.")
            if self.config.alarm.low_flow_threshold < 0:
                raise ValueError("저유량 기준은 0 이상이어야 합니다.")
            if self.config.alarm.hysteresis < 0 or self.config.alarm.trigger_duration_sec < 0:
                raise ValueError("히스테리시스와 지속 시간은 0 이상이어야 합니다.")
            remote_url = self.remote_url_var.get().strip()
            remote_device = self.remote_device_var.get().strip()
            if self.remote_enabled_var.get() and not remote_url.startswith("https://"):
                raise ValueError("웹 전송 Function URL은 https://로 시작해야 합니다.")
            if self.remote_enabled_var.get() and not remote_device:
                raise ValueError("웹 전송 장치 ID를 입력하세요.")
        except ValueError as exc:
            messagebox.showerror("입력 오류", str(exc))
            return
        self.config.calibration.direction = self.direction_var.get()
        self.config.camera.autofocus = self.autofocus_var.get()
        self.config.camera.auto_exposure = self.auto_exposure_var.get()
        self.config.arduino.port = self.port_var.get().strip()
        self.config.arduino.enabled = self.arduino_enabled_var.get()
        self.config.remote.enabled = self.remote_enabled_var.get()
        self.config.remote.function_url = self.remote_url_var.get().strip()
        self.config.remote.device_id = self.remote_device_var.get().strip()
        self.config.remote.upload_interval_sec = (
            60.0 if self.remote_interval_var.get().startswith("1분") else 3600.0
        )
        self._prepare_calibration(show_error=True)
        if len(self.config.calibration.points) >= 2 and self.calibration is None:
            return
        self.alarm = LowFlowAlarm(self.config.alarm)
        self.arduino.close()
        self.arduino = ArduinoAlarmOutput(self.config.arduino)
        self.remote.close()
        self.remote = PeriodicFlowUploader(self.config.remote)
        self.web_status_var.set(f"Web: {self.remote.status}")
        self._apply_camera_controls()
        try:
            self.store.save(self.config)
        except OSError as exc:
            messagebox.showerror("저장 오류", str(exc))
            return
        messagebox.showinfo("저장 완료", f"설정을 저장했습니다.\n{self.store.path.resolve()}")

    def close(self) -> None:
        self._stop_camera()
        self.arduino.close()
        self.remote.close()
        self.root.destroy()


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Analog Flow Guard")
    parser.add_argument(
        "--config",
        default=project_root / "flow_guard_config.json",
        type=Path,
        help="configuration JSON path",
    )
    args = parser.parse_args()
    root = tk.Tk()
    FlowGuardApp(root, ConfigStore(args.config))
    root.mainloop()


if __name__ == "__main__":
    main()
