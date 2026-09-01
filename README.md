# Analog Flow Guard

고정 웹캠으로 아날로그 유량계의 침을 읽어 현재 순간 유량(`L/min`)을 확인하고, 저유량 문제를 PC·ESP32·웹에서 보여 주는 MVP입니다.

현재 목표는 잔량이나 가스통의 소진 시점을 계산하는 것이 아닙니다. **현재 유량이 설정한 기준 이하로 약해졌는지**를 감시합니다. 유량 감소 추세로 저유량 도달 시점을 예측하는 기능은 핵심 연결이 완성된 뒤 추가합니다.

## 구성

```text
웹캠 → Python Flow Guard ─USB Serial→ ESP32 #1 ─ESP-NOW→ ESP32 #2 OLED
                    └─HTTPS→ Supabase ─조회→ GitHub Pages 대시보드
                                     └─저유량/복귀→ Slack
```

- `analog_flow_guard/`: 영상 인식, 보정, 저유량 경보, Serial, 웹 전송
- `esp32/esp32_1_pc_led_sender/`: PC 명령 수신, LED, ESP-NOW 송신
- `esp32/esp32_2_battery_display/`: 문제 상태 OLED 표시
- `supabase/`: 측정 테이블과 수신 Edge Function
- `web/`: Supabase 실데이터 대시보드
- `.github/workflows/pages.yml`: GitHub Pages 자동 배포

## 설치와 실행

Python 3.10 이상을 권장합니다. 기존 `.venv`는 다른 PC의 Python 경로를 포함할 수 있으므로 새 PC에서는 다시 만듭니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

다른 유량계 프로필을 사용하려면 설정 파일을 분리합니다.

```powershell
python run.py --config configs/gauge_a.json
```

## 최초 보정

1. 카메라를 계기판 정면에 고정합니다.
2. **원근 보정 4점 지정**에서 눈금판의 상 → 우 → 하 → 좌를 누릅니다.
3. 실제 기준 유량을 맞춘 뒤 **현재 각도 기준점 추가**로 최소 2개를 등록합니다.
4. 비선형 눈금이면 주요 눈금마다 기준점을 추가합니다.
5. 저유량 기준, 해제 여유값, 지속 시간을 입력합니다.
6. ESP32 #1의 COM 포트를 선택하고 출력 사용을 체크합니다.

카메라 또는 계기판을 움직인 뒤에는 원근 보정과 각도–유량 보정을 다시 수행해야 합니다.

## 보고 주기

설정 화면에서 두 모드를 선택할 수 있습니다.

- `1분 (MVP 시연)`: 현재 기본값. Supabase와 웹 갱신을 빠르게 시연합니다.
- `1시간 (운영)`: 실제 운영용 보고 주기입니다.

주기를 바꾸면 중복 방지용 `sample_id`도 같은 시간 단위로 자동 생성됩니다. 운영 모드로 바꿀 때는 `web/config.js`의 `expectedIntervalSec`도 `3600`으로 변경합니다.

## ESP32 상태 출력

Python과 ESP32 #1은 **115200 baud**로 통일되어 있습니다. PC는 정상 `0`, 저유량 문제 `1`을 전송하며 유량 숫자는 ESP32로 보내지 않습니다.

- 정상: 초록 LED 계속 켜짐, 빨간 LED 꺼짐
- 저유량·카메라 인식·보정 문제: 초록 LED 꺼짐, 빨간 LED 계속 켜짐
- PC 명령 6.5초 이상 단절: 빨간 LED 계속 켜짐, OLED `PC LINK ERROR`
- ESP-NOW 3.5초 이상 단절: OLED `RADIO LINK ERROR`

업로드·배선·시험 순서는 [ESP32_UPGRADE_GUIDE.md](ESP32_UPGRADE_GUIDE.md)를 따릅니다.

## Supabase와 GitHub Pages

처음 사용하는 사용자를 위한 계정 생성, 테이블 생성, Edge Function 배포, GitHub 저장소 생성, Pages 공개 순서는 [SETUP_SUPABASE_GITHUB.md](SETUP_SUPABASE_GITHUB.md)에 있습니다.

비밀값 관리 원칙:

- `FLOW_DEVICE_TOKEN`: Windows 환경변수와 Supabase Secrets에만 저장
- `FLOW_SUPABASE_SECRET_KEY`: Supabase Secrets에만 저장
- Supabase Publishable key: `web/config.js`에 사용 가능
- Secret key나 Slack Webhook URL: GitHub에 절대 커밋하지 않음

Supabase 함수는 장치별 경보 상태를 저장해 저유량 진입과 정상 복귀 때만 Slack 메시지를 한 번씩 보냅니다. Slack이 설정되지 않아도 측정값 저장은 계속됩니다.

## 유량 감소 예측의 우선순위

현재 유량이 시간에 따라 안정적으로 낮아지는 장치라면 최근 측정값을 선형 회귀해 “저유량 기준 도달 예상 시간”을 만드는 것 자체는 중간 난이도입니다. 그러나 밸브 조작, 공정 부하 변화, 일시적 흔들림을 오경보와 구분해 신뢰할 만한 예측으로 만드는 작업은 현장 데이터가 필요하므로 난이도가 높습니다.

따라서 개발 순서는 다음이 적절합니다.

1. 웹캠 → 로컬 경보 안정화
2. Supabase → GitHub Pages 실데이터 연결
3. ESP32 문제 상태 표시와 통신 단절 처리
4. Slack Webhook 연결과 저유량/복귀 알림 현장 시험
5. 충분한 데이터를 수집한 뒤 저유량 도달 시점 예측

## 검증

```powershell
python -m unittest discover -s tests -v
python -m compileall analog_flow_guard run.py
```

실제 현장에서는 정상·경계·저유량 위치, 조명 변화, 카메라 분리, USB 분리, ESP-NOW 거리, 인터넷 단절과 복구를 각각 시험해야 합니다.
