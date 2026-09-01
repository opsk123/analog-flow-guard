# ESP32 2대 상태 경보 설치 안내

현재 ESP32는 유량 숫자를 전송하지 않습니다. PC가 판정한 **정상 또는 문제 상태만** ESP32 #1로 보내고, ESP32 #1은 LED와 ESP-NOW로 이를 알립니다. ESP32 #2 OLED는 정상·문제·통신 오류를 표시합니다.

## 1. 사용하는 스케치

- ESP32 #1: `esp32/esp32_1_pc_led_sender/esp32_1_pc_led_sender.ino`
- ESP32 #2: `esp32/esp32_2_battery_display/esp32_2_battery_display.ino`
- I2C 주소 확인 도구: `esp32/tools/i2c_scanner/i2c_scanner.ino`

`backups` 폴더의 예전 스케치나 `arduino/flow_guard_alarm` 보드 확인 코드는 사용하지 않습니다.

## 2. 준비물

- ESP32 보드 2개
- 초록 LED, 빨간 LED, LED별 220Ω 저항
- SSD1306 또는 SH1106 방식 128×64 I2C OLED 1개
- 점퍼선과 USB 케이블
- Arduino IDE

Arduino IDE의 Library Manager에서 **U8g2** 라이브러리를 설치합니다. ESP32 보드 패키지는 최신 안정 버전을 사용합니다.

## 3. ESP32 #1 LED 배선

- GPIO26 → 220Ω → 초록 LED 애노드(+)
- GPIO27 → 220Ω → 빨간 LED 애노드(+)
- 두 LED 캐소드(-) → GND

문제 상태에서 빨간 LED는 점멸하지 않고 계속 켜집니다.

## 4. ESP32 #2 OLED 배선

일반적인 3.3V 동작 I2C OLED 기준입니다.

- OLED VCC → ESP32 3.3V
- OLED GND → ESP32 GND
- OLED SDA → GPIO21
- OLED SCL → GPIO22

화면이 나오지 않으면 I2C 스캐너를 먼저 업로드합니다. 주소가 `0x3D`라면 `esp32/esp32_2_battery_display/config.h`의 `OLED_I2C_ADDRESS`를 바꿉니다. SH1106 화면이면 `OLED_CONTROLLER_SH1106`을 `1`로 바꿉니다.

## 5. 업로드 순서

1. ESP32 #2를 연결하고 `esp32_2_battery_display.ino`를 업로드합니다.
2. Serial Monitor를 **115200 baud**로 열어 `Waiting for Unit 1 packet`을 확인합니다.
3. Serial Monitor를 닫고 ESP32 #2에 계속 전원을 공급합니다.
4. ESP32 #1을 연결하고 `esp32_1_pc_led_sender.ino`를 업로드합니다.
5. ESP32 #1의 Serial Monitor를 **115200 baud**로 엽니다.
6. 줄바꿈을 포함해 `0`을 보내 정상 상태를 확인합니다.
7. `1`을 보내 빨간 LED 고정 점등과 OLED의 `FLOW STATUS / PROBLEM`을 확인합니다.

두 보드는 `config.h`에서 ESP-NOW 채널 6을 사용합니다. 한쪽만 다른 채널로 변경하면 통신하지 못합니다.

## 6. Flow Guard 연결

1. ESP32 #1의 Serial Monitor를 반드시 닫습니다. 같은 COM 포트를 두 프로그램이 동시에 사용할 수 없습니다.
2. Flow Guard를 실행합니다.
3. **Arduino/ESP32 포트**에 ESP32 #1의 COM 포트를 입력합니다.
4. **Arduino/ESP32 출력 사용**을 체크합니다.
5. 설정을 저장합니다.

Python과 ESP32 #1은 모두 115200 baud입니다. Flow Guard는 상태가 바뀌지 않아도 2초마다 같은 상태를 다시 보내므로 ESP32 #1이 PC 연결 단절을 감지할 수 있습니다.

## 7. 표시 의미

- 초록 LED 고정: `NORMAL`
- 빨간 LED 고정: 저유량, 카메라/보정 문제 또는 PC 연결 문제
- OLED `SYSTEM / NORMAL`: 정상
- OLED `FLOW STATUS / PROBLEM`: 저유량 문제
- OLED `PC LINK / ERROR`: Python 명령이 6.5초 이상 오지 않음
- OLED `RADIO LINK / ERROR`: ESP32 #1 패킷이 3.5초 이상 오지 않음

전원이 켜졌다는 이유만으로 정상으로 표시하지 않습니다. 첫 정상 명령을 받기 전까지 연결 오류 상태를 유지합니다.

## 8. 현장 시험

1. 정상 유량에서 초록 LED와 OLED 정상 표시 확인
2. 저유량 기준 이하를 유지해 빨간 LED 고정 점등과 문제 표시 확인
3. USB 케이블을 분리해 PC 연결 오류 확인
4. ESP32 #1 전원을 꺼서 ESP32 #2의 무선 오류 확인
5. 전원과 USB를 다시 연결했을 때 자동 복구 확인
6. 실제 설치 거리에서 30분 이상 연속 동작 확인
