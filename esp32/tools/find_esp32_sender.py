from __future__ import annotations

import time

import serial
from serial.tools import list_ports


IDENTITY = "DEVICE:FLOW_GUARD_ESP32_SENDER"


def candidate_ports():
    for port in list_ports.comports():
        description = (port.description or "").lower()
        if any(name in description for name in ("cp210", "ch340", "usb", "uart", "esp32")):
            yield port.device, port.description


def identify(port_name: str) -> tuple[bool, str]:
    try:
        with serial.Serial(port_name, 9600, timeout=0.2) as connection:
            # Opening the port resets most ESP32 development boards.
            time.sleep(2.5)
            connection.reset_input_buffer()
            connection.write(b"?\n")
            deadline = time.monotonic() + 2.0
            received: list[str] = []
            while time.monotonic() < deadline:
                line = connection.readline().decode("utf-8", errors="replace").strip()
                if line:
                    received.append(line)
                    if IDENTITY in line:
                        return True, line
            return False, "; ".join(received[-3:]) or "응답 없음"
    except serial.SerialException as exc:
        return False, f"포트 열기 실패: {exc}"


def main() -> None:
    ports = list(candidate_ports())
    if not ports:
        print("USB-UART ESP32 포트를 찾지 못했습니다.")
        return
    found = False
    for port_name, description in ports:
        matched, detail = identify(port_name)
        marker = "송신기" if matched else "아님/확인 실패"
        print(f"{port_name}: {marker} | {description} | {detail}")
        found = found or matched
    if not found:
        print("송신기를 찾지 못했습니다. Flow Guard와 Arduino Serial Monitor를 모두 닫고 다시 실행하세요.")


if __name__ == "__main__":
    main()

