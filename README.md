# Analog Flow Guard

고정 웹캠으로 아날로그 유량계의 바늘을 읽어 **현재 순간 유량(`L/min`)**을 감시하는 MVP입니다. 저유량이나 측정 장애를 현장 PC와 ESP32에 표시하고, 측정 이력을 Supabase에 저장해 웹 대시보드에서 확인하며, 저유량 진입·정상 복구 시 Slack으로 알릴 수 있습니다.

> 이 프로젝트는 유량 감시용 보조 시스템입니다. 안전 차단장치나 법정 가스 검지 설비를 대신하지 않습니다.

## 주요 기능

- OpenCV 기반 아날로그 계기판 바늘 인식
- 4점 원근 보정과 다중 각도–유량 기준점 보정
- 저유량 지속 시간 및 히스테리시스 판정
- ESP32 #1의 LED로 정상·문제 상태 표시
- ESP-NOW를 통해 ESP32 #2의 1602 LCD로 상태 표시
- Supabase Edge Function을 통한 측정값 저장
- GitHub Pages 실시간 대시보드
- Slack 저유량·정상 복구 알림 및 중복 알림 방지
- 카메라, Serial, 인터넷 장애 후 자동 재연결·재시도

웹 대시보드: <https://opsk123.github.io/analog-flow-guard/>

## 전체 구조

```text
아날로그 유량계
      ↓ 촬영
Windows PC: Python/Tkinter + OpenCV
      ├─ 유량 계산 및 저유량 판정
      ├─ USB Serial (115200 baud) → ESP32 #1 → LED
      │                                      └─ ESP-NOW → ESP32 #2 → 1602 LCD
      └─ HTTPS → Supabase Edge Function
                       ├─ flow_readings / flow_alert_state
                       ├─ Slack 저유량·복구 알림
                       └─ REST API → GitHub Pages 대시보드
```

PC 프로그램이 시스템의 중심입니다. 웹캠과 USB 장치는 Windows PC에 연결해야 하며 GitHub Pages나 Supabase가 카메라를 직접 제어하지는 않습니다.

## 폴더와 파일 안내

| 경로 | 역할 |
|---|---|
| `run.py` | 프로그램 실행 진입점. Windows 사용자 환경변수와 프로젝트 가상환경을 자동 사용합니다. |
| `flow_guard_config.json` | 카메라, 보정점, 저유량 기준, COM 포트, 원격 전송 설정 |
| `analog_flow_guard/app.py` | Tkinter 화면과 전체 실행 흐름 |
| `analog_flow_guard/vision.py` | 영상 품질 평가와 바늘 각도 검출 |
| `analog_flow_guard/geometry.py` | 계기판 4점 원근 보정 |
| `analog_flow_guard/calibration.py` | 바늘 각도를 `L/min` 값으로 변환 |
| `analog_flow_guard/alarm.py` | 저유량 지속 시간·히스테리시스 판정 |
| `analog_flow_guard/arduino.py` | ESP32 #1 Serial 연결, 재연결, 상태 전송 |
| `analog_flow_guard/remote.py` | Supabase 주기 전송과 실패 재시도 |
| `esp32/esp32_1_pc_led_sender/` | PC 상태 수신, LED 표시, ESP-NOW 송신 스케치 |
| `esp32/esp32_2_battery_display/` | ESP-NOW 수신 및 1602 I2C LCD 표시 스케치 |
| `esp32/tools/` | ESP32 검색 및 I2C 주소 확인 도구 |
| `supabase/migrations/` | 측정값·경보 상태 테이블과 RLS 정책 |
| `supabase/functions/ingest-flow/` | 장치 인증, 데이터 저장, Slack 알림 Edge Function |
| `web/` | GitHub Pages에 배포되는 정적 대시보드 원본 |
| `.github/workflows/pages.yml` | `web/`을 GitHub Pages에 자동 배포하는 워크플로 |
| `tests/` | Python 로직과 ESP32 스케치 구조 자동 테스트 |

## 준비물

- Windows 10/11 PC와 Python 3.10 이상
- 고정 가능한 USB 웹캠
- 아날로그 유량계
- ESP32 보드 2개
- 초록·빨간 LED와 각 LED용 220Ω 저항
- PCF8574 I2C 백팩이 장착된 1602 LCD
- USB 케이블과 점퍼선
- 원격 기능 사용 시 Supabase 프로젝트와 선택 사항인 Slack Incoming Webhook

ESP32 #2 스케치는 Arduino IDE의 Library Manager에서 설치할 수 있는 `LiquidCrystal_I2C` 라이브러리가 필요합니다.

## 설치

저장소 루트에서 PowerShell을 열고 다음을 실행합니다.

```powershell
git clone https://github.com/opsk123/analog-flow-guard.git
cd analog-flow-guard
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-lock.txt
```

`requirements-lock.txt`는 현재 검증된 Windows 환경을 재현할 때 권장합니다. 최신 호환 버전을 설치하려면 대신 `requirements.txt`를 사용합니다.

## 실행

```powershell
python run.py
```

`run.py`는 저장소의 `.venv`가 있으면 그 Python으로 자동 재실행합니다. 다른 설정 파일을 사용하려면 다음처럼 지정합니다.

```powershell
python run.py --config C:\경로\gauge-a.json
```

원격 전송을 사용하려면 장치 토큰을 코드나 JSON 파일에 넣지 말고 Windows 사용자 환경변수로 등록합니다.

```powershell
[Environment]::SetEnvironmentVariable("FLOW_DEVICE_TOKEN", "발급받은-토큰", "User")
```

등록 후 프로그램을 다시 실행합니다. `run.py`가 Windows 사용자 환경변수에서 토큰을 불러옵니다.

## 최초 설정과 보정

1. 웹캠과 계기판이 움직이지 않도록 정면에 단단히 고정합니다.
2. 프로그램의 **원근 보정 4점 지정**을 누릅니다.
3. 눈금판의 `상 → 우 → 하 → 좌` 순서로 네 점을 클릭합니다.
4. 실제 유량을 알고 있는 위치로 바늘을 맞춥니다.
5. **현재 위치 유량**에 실제 값을 입력하고 **현재 각도 기준점 추가**를 누릅니다.
6. 최소 두 지점에서 반복합니다. 비선형 눈금은 주요 눈금마다 기준점을 추가합니다.
7. 유량 증가 방향이 실제 계기판과 같은지 선택합니다.
8. 저유량 기준, 해제 여유값, 지속 시간을 입력합니다.
9. ESP32 #1의 COM 포트를 입력하고 **Arduino/ESP32 출력 사용**을 체크합니다.
10. 웹 전송을 사용할 경우 Function URL, 장치 ID, 전송 주기를 확인합니다.
11. **설정 저장 및 적용**을 누릅니다.

설정은 `flow_guard_config.json`에 저장됩니다. 카메라나 계기판의 위치가 달라지면 원근 보정과 각도–유량 보정을 다시 해야 합니다. 현재 저장소의 보정값과 `COM8`은 설치된 MVP 장비 기준이므로 다른 장비에서는 반드시 다시 설정하십시오.

## 전송 주기

프로그램에서 다음 세 가지 주기를 선택할 수 있습니다.

- `10초 (빠른 감시)`: 현재 MVP 기본값
- `1분 (MVP 시연)`: 일반 시연용
- `1시간 (운영)`: 낮은 빈도의 장기 기록용

웹 대시보드의 데이터 지연 판단 기준은 `web/config.js`의 `expectedIntervalSec`입니다. PC의 전송 주기를 변경하면 이 값도 같은 초 단위 값으로 맞춥니다.

## ESP32 연결

### ESP32 #1: PC 연결 및 LED

- USB Serial: `115200 baud`
- GPIO26 → 220Ω → 초록 LED 애노드(+)
- GPIO27 → 220Ω → 빨간 LED 애노드(+)
- 두 LED 캐소드(-) → GND

PC는 `0`(정상) 또는 `1`(문제)을 보내며, 유량 숫자 자체는 보내지 않습니다. ESP32 #1의 Serial Monitor는 Flow Guard 실행 전에 닫아야 합니다.

### ESP32 #2: 1602 I2C LCD

- LCD VCC → 모듈 사양에 맞는 전원
- LCD GND → ESP32 GND
- LCD SDA → GPIO21
- LCD SCL → GPIO22
- 기본 I2C 주소: `0x3F`

LCD가 표시되지 않으면 `esp32/tools/i2c_scanner/`를 먼저 실행하고 실제 주소를 `esp32/esp32_2_battery_display/config.h`에 반영합니다. 두 ESP32의 ESP-NOW 채널은 모두 `6`이어야 합니다.

표시 상태는 다음과 같습니다.

| 상태 | ESP32 #1 | ESP32 #2 LCD |
|---|---|---|
| 정상 | 초록 LED 켜짐 | `GAS STATUS / NORMAL` |
| 저유량 또는 측정 문제 | 빨간 LED 켜짐 | `GAS STATUS / LOW` |
| PC 명령 단절 | 빨간 LED 켜짐 | `PC LINK / ERROR` |
| ESP-NOW 단절 | 해당 없음 | `RADIO LINK / ERROR` |

스케치 업로드와 상세 시험은 [ESP32_UPGRADE_GUIDE.md](ESP32_UPGRADE_GUIDE.md)를 참고하되, 현재 ESP32 #2 하드웨어는 이 README의 1602 LCD 구성을 기준으로 합니다.

## Supabase, 대시보드, Slack

상세 초기 구축 절차는 [SETUP_SUPABASE_GITHUB.md](SETUP_SUPABASE_GITHUB.md)를 참고합니다.

PC는 `x-device-token` 헤더로 `ingest-flow` Edge Function에 측정값을 전송합니다. 함수는 측정값을 저장하고 장치별 경보 상태를 비교하여 상태가 바뀌는 순간에만 Slack 메시지를 보냅니다. Slack Webhook이 없어도 Supabase 저장과 웹 대시보드는 동작합니다.

Supabase Edge Function에서 사용하는 주요 Secret은 다음과 같습니다.

| 이름 | 용도 |
|---|---|
| `FLOW_DEVICE_TOKEN` | PC 장치 요청 인증 |
| `FLOW_SUPABASE_SECRET_KEY` | 서버 측 DB 저장 |
| `SLACK_WEBHOOK_URL` | 선택 사항, Slack Incoming Webhook |
| `FLOW_LOW_THRESHOLD_LPM` | Slack 저유량 기준, 기본 `0.15` |
| `FLOW_RECOVERY_MARGIN_LPM` | Slack 복구 여유값, 기본 `0.05` |
| `FLOW_DEVICE_DISPLAY_NAME` | Slack에 표시할 설비명 |
| `FLOW_DEVICE_LOCATION` | Slack에 표시할 설치 위치 |

`web/config.js`에는 브라우저 공개용 Supabase URL과 Publishable key만 둡니다. Secret key, 장치 토큰, Slack Webhook URL은 절대 커밋하지 마십시오.

## 검증

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q analog_flow_guard run.py
node --check web\app.js
```

대시보드를 로컬에서 확인하려면 다음 명령을 실행한 뒤 <http://localhost:8000/web/>을 엽니다.

```powershell
.\.venv\Scripts\python.exe -m http.server 8000
```

자동 테스트와 별도로 실제 현장에서는 정상·경계·저유량 위치, 조명 변화, 카메라 분리·복구, USB 분리·복구, ESP-NOW 거리와 단절, 인터넷 단절·복구를 각각 시험해야 합니다.

## GitHub Pages 배포

`main` 브랜치의 `web/` 또는 `.github/workflows/pages.yml`이 변경되면 GitHub Actions가 대시보드를 자동 배포합니다.

```powershell
git add .
git commit -m "Describe the verified MVP"
git push origin main
```

README만 변경한 경우에는 Pages 워크플로의 경로 조건상 대시보드를 다시 배포하지 않습니다. 필요하면 GitHub Actions의 **Deploy flow dashboard to GitHub Pages** 워크플로에서 `Run workflow`를 실행할 수 있습니다.

## 운영 시 주의사항

- 로컬 ESP32 경보를 1차 경보로 사용하고 Slack은 보조 원격 알림으로 사용합니다.
- PC, 카메라, 프로그램, 인터넷 또는 Supabase가 중단되면 새 원격 알림이 지연되거나 누락될 수 있습니다.
- 로컬 경보 기준과 Supabase Slack 기준은 별도 설정이므로 운영 전에 같은 정책으로 맞춥니다.
- `flow_guard_config.json`의 장치별 보정점과 COM 포트를 임의로 덮어쓰지 않습니다.
- 비밀값은 환경변수와 Supabase Secrets에만 저장하고 로그, 문서, 이슈에 남기지 않습니다.

## 라이선스

현재 별도의 라이선스 파일이 없습니다. 외부 사용이나 재배포가 필요하면 저장소 소유자에게 먼저 문의하십시오.
