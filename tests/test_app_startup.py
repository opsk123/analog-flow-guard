import threading
import time
import unittest
from unittest.mock import patch

from analog_flow_guard.app import FlowGuardApp
from analog_flow_guard.config import AppConfig


class _SlowCamera:
    def __init__(self, _index):
        time.sleep(0.4)
        self.released = False

    def isOpened(self):
        return True

    def set(self, _property, _value):
        return True

    def read(self):
        time.sleep(0.01)
        return False, None

    def release(self):
        self.released = True


class CameraStartupTests(unittest.TestCase):
    def test_slow_camera_open_does_not_block_ui_caller(self):
        app = FlowGuardApp.__new__(FlowGuardApp)
        app.config = AppConfig()
        app.capture = None
        app.capture_thread = None
        app.capture_stop = threading.Event()
        app.capture_lock = threading.Lock()
        app.captured_frame = None
        app.captured_frame_number = 0
        app.processed_frame_number = 0
        app.last_capture_time = 0.0
        app.camera_open = False
        app.camera_error = None

        with patch("analog_flow_guard.app.cv2.VideoCapture", _SlowCamera):
            started = time.perf_counter()
            app.start_camera()
            elapsed = time.perf_counter() - started
            self.assertLess(elapsed, 0.2)
            app.capture_stop.set()
            app.capture_thread.join(timeout=2.0)

        self.assertFalse(app.capture_thread.is_alive())
        self.assertFalse(app.camera_open)


if __name__ == "__main__":
    unittest.main()
