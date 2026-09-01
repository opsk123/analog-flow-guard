# Analog Flow Guard — AI 작업 지침

이 문서는 다른 AI 에이전트가 이 저장소를 처음 열었을 때 전체 시스템을 안전하고 일관되게 수정·검증·배포하기 위한 기준이다. 사용자의 최신 명시적 지시가 이 문서보다 우선한다.

## 1. 프로젝트의 목적

고정 웹캠으로 아날로그 유량계의 침을 읽어 **현재 순간 유량(L/min)** 을 측정하고 다음 기능을 제공하는 MVP이다.

1. Windows PC에서 카메라 영상으로 현재 유량 판독
2. 설정된 저유량 기준 이하인지 판단
3. 측정값을 Supabase에 주기적으로 저장
4. 정적 웹 대시보드에서 현재값과 최근 기록 표시
5. 저유량 진입과 정상 복귀를 Slack으로 통지
6. USB로 연결된 ESP32 #1에 정상/문제 상태 전달
7. ESP32 #1이 LED를 제어하고 ESP-NOW로 ESP32 #2에 상태 전송
8. ESP32 #2 OLED에 정상·문제·통신 오류 표시

### 데이터 의미에 대한 불변 조건

- 측정 대상은 잔량, 압력, 퍼센트가 아니라 **현재 순간 유량**이다.
- 단위는 `L/min`이다.
- `flow_rate_lpm`을 가스 잔량이나 남은 부피로 해석하지 않는다.
- 현재 구현의 경보는 저유량 경보이다.
- 향후 예측 기능은 “바닥날 시간”이 아니라 **저유량 기준에 도달할 예상 시간**으로 정의해야 한다.
- 예측 기능은 현장 데이터가 쌓인 뒤 수행하는 최후 우선순위이다.

## 2. 전체 구조

```text
Webcam
  ↓
Windows Python/Tkinter app
  ├─ OpenCV needle detection and L/min calibration
  ├─ local low-flow / vision-error decision
  ├─ USB Serial 115200 → ESP32 #1 → ESP-NOW → ESP32 #2 OLED
  └─ HTTPS + x-device-token → Supabase ingest-flow Edge Function
                                      ├─ Postgres flow_readings
                                      ├─ flow_alert_state
                                      ├─ Slack webhook
                                      └─ REST read → static web dashboard
                                                        ├─ Netlify
                                                        ├─ Render, if configured as a static site
                                                        └─ GitHub Pages mirror
```

중요: 카메라와 USB/ESP32를 사용하는 Python 프로그램은 현장 Windows PC에서 실행해야 한다. Netlify, Render 또는 GitHub Pages에서 웹캠 감시 프로그램을 실행하려 하지 않는다.

## 3. 저장소 구조와 책임

| 경로 | 역할 |
|---|---|
| `run.py` | 데스크톱 앱 진입점 |
| `analog_flow_guard/app.py` | Tkinter UI와 전체 로컬 실행 흐름 |
| `analog_flow_guard/vision.py` | 침 검출과 영상 품질 판정 |
| `analog_flow_guard/geometry.py` | 4점 원근 보정 |
| `analog_flow_guard/calibration.py` | 각도–유량 다점 보간 |
| `analog_flow_guard/alarm.py` | 저유량 지연·히스테리시스·검출 오류 상태 |
| `analog_flow_guard/arduino.py` | ESP32/Arduino Serial 재연결과 상태 전송 |
| `analog_flow_guard/remote.py` | Supabase Edge Function 비동기 전송 |
| `flow_guard_config.json` | 현재 장비의 카메라·보정·경보·통신 설정 |
| `supabase/migrations/` | DB 스키마와 RLS 변경 이력 |
| `supabase/functions/ingest-flow/` | 장치 인증, 측정 저장, Slack 경보 |
| `web/` | 정적 대시보드의 실제 배포 원본 |
| `index.html`, `flow-dashboard.html` | 로컬에서 `web/`으로 보내는 호환용 리다이렉트 |
| `.github/workflows/pages.yml` | `web/`을 GitHub Pages에 배포 |
| `esp32/esp32_1_pc_led_sender/` | PC Serial 수신, LED, ESP-NOW 송신 |
| `esp32/esp32_2_battery_display/` | ESP-NOW 수신과 OLED 표시 |
| `esp32/tools/` | 포트 및 I2C 진단 도구 |
| `arduino/flow_guard_alarm/` | 현재 운영 스케치가 아닌 보드 확인용 코드 |
| `backups/` | 이전 코드 보관. 활성 구현으로 취급하지 말 것 |
| `tests/` | Python 로직 및 현재 ESP32 파일 구조 회귀 테스트 |

`flow_guard_config.json`에는 사용자가 현장에서 만든 보정점이 들어 있다. 명시적 요청 없이 초기화하거나 예제 값으로 덮어쓰지 않는다.

## 4. 연결된 서비스의 역할

사용자는 GitHub, Supabase, Render, Netlify를 연결했다고 보고했다. 다만 2026-09-01 현재 이 작업 폴더에는 `.git`, `render.yaml`, `netlify.toml`이 보이지 않는다. 연결이 안 됐다고 단정하지 말고, 각 서비스 웹 대시보드에서 수동 연결됐을 가능성을 고려한다.

### GitHub

- 소스 코드와 변경 이력의 기준 저장소이다.
- `.github/workflows/pages.yml`은 `main` 브랜치의 `web/` 변경을 GitHub Pages에 배포한다.
- 로컬 `.git`이 없으면 원격 저장소 URL과 현재 브랜치를 확인하기 전 push나 remote 생성을 임의로 수행하지 않는다.
- `.venv`, `.env`, Secret key, 장치 토큰, Slack Webhook을 커밋하지 않는다.

### Supabase

- 측정 데이터의 유일한 기준 저장소이다.
- `flow_readings`: 시간별/분별 순간 유량 기록
- `flow_alert_state`: 저유량과 정상 복귀 Slack 알림의 중복 방지 상태
- `ingest-flow`: PC 측정값을 받는 Edge Function
- 웹 대시보드는 Supabase REST API를 읽는다.
- 쓰기는 Edge Function의 Secret key로만 수행하고, 브라우저에는 쓰기 권한을 주지 않는다.

### Netlify

- 현재 코드와 가장 잘 맞는 용도는 `web/` 폴더를 배포하는 정적 대시보드이다.
- 연결이 GitHub 대시보드에서 수동 구성됐을 수 있다.
- 저장소에 `netlify.toml`이 없으므로 다음 설정을 서비스 대시보드에서 확인한다.
  - Base directory: 저장소 루트 또는 빈 값
  - Build command: 현재 순수 정적 사이트에는 필요 없음
  - Publish directory: `web`
  - Production branch: 보통 `main`
- Netlify Function이나 서버 API가 있다고 추측하지 않는다. 현재 서버 로직은 Supabase Edge Function에 있다.

### Render

- 저장소에는 Render용 서버 진입점, `render.yaml`, Dockerfile 또는 Procfile이 없다.
- Render가 Static Site로 연결됐다면 배포 원본은 `web/`이어야 한다.
- Render가 Web Service로 생성됐다면 현재 코드만으로는 적절한 상시 웹 서버가 없으므로 서비스 유형과 Start Command를 확인한다.
- Render에서 데스크톱 Tkinter 앱, 카메라 또는 ESP32 기능을 실행하려 하지 않는다.
- 새로운 Render 백엔드를 만들기 전에 Supabase Edge Function과 역할이 중복되는지 확인한다.

### 여러 웹 호스팅 서비스의 원칙

- Netlify, Render Static Site, GitHub Pages가 모두 같은 `web/`을 제공할 수 있다.
- 기능을 호스팅 서비스별로 따로 복사하지 않는다. `web/` 하나를 단일 원본으로 유지한다.
- 운영 URL, 시연 URL, 백업 URL 중 무엇이 기준인지 사용자가 지정하지 않았다면 DNS나 도메인을 변경하기 전에 질문한다.
- 한 서비스에서만 수정한 설정은 다른 배포와 어긋날 수 있다. 대시보드 UI와 Supabase 연결 설정은 가능한 한 저장소에 기록한다.

## 5. 비밀값과 공개값

### 절대 저장소에 기록하지 않는 값

- Supabase Secret key (`sb_secret_...`)
- `FLOW_DEVICE_TOKEN`의 실제 값
- Slack Incoming Webhook 실제 URL
- GitHub, Netlify, Render 개인 액세스 토큰
- Supabase DB password

이 값을 명령 출력, 로그, 문서, 스크린샷 또는 AI 응답에 다시 표시하지 않는다.

### 공개 저장소에 둘 수 있는 값

- Supabase Project URL
- Supabase Publishable key (`sb_publishable_...`)
- 공개 장치 ID `FLOW-01`
- 저유량 기준과 예상 보고 주기

Publishable key가 공개 가능하다는 사실은 RLS가 올바르다는 전제에 의존한다. `flow_readings`의 공개 읽기 정책을 바꾸려면 대시보드 인증 방식도 함께 바꾼다.

### 환경변수 위치

| 환경 | 변수 |
|---|---|
| Windows 현장 PC | `FLOW_DEVICE_TOKEN` |
| Supabase Edge Function Secrets | `FLOW_DEVICE_TOKEN` |
| Supabase Edge Function Secrets | `FLOW_SUPABASE_SECRET_KEY` |
| Supabase Edge Function Secrets | `SLACK_WEBHOOK_URL` 선택 사항 |
| Supabase Edge Function Secrets | `FLOW_LOW_THRESHOLD_LPM` 선택 사항, 기본 `0.15` |
| Supabase Edge Function Secrets | `FLOW_RECOVERY_MARGIN_LPM` 선택 사항, 기본 `0.05` |

PC와 Supabase의 `FLOW_DEVICE_TOKEN`은 동일해야 한다. 토큰 자체를 확인하려 하지 말고 불일치 여부만 진단한다.

## 6. 현재 설정과 프로토콜

### 보고 주기

- MVP 시연 기본값: `60초`
- 실제 운영 예정값: `3600초`
- 설정 UI에서 `1분 (MVP 시연)`과 `1시간 (운영)`을 전환한다.
- `web/config.js`의 `expectedIntervalSec`도 같은 값으로 맞춘다.
- `remote.py`는 전송 주기에 맞는 UTC 버킷으로 `sample_id`를 생성한다. 주기만 바꾸고 ID 생성 규칙을 시 단위로 고정하지 않는다.

### Supabase 수신 payload

```json
{
  "sample_id": "FLOW-01:<UTC bucket ISO timestamp>",
  "device_id": "FLOW-01",
  "flow_rate_lpm": 0.222,
  "measured_at": "UTC ISO-8601 timestamp"
}
```

헤더 `x-device-token`이 필요하다. `ingest-flow`는 `verify_jwt = false`이지만 내부에서 장치 토큰을 직접 검사하므로 그 검사를 제거하지 않는다.

### ESP32 상태 프로토콜

- Python ↔ ESP32 #1: USB Serial `115200 baud`
- 명령 `0`: 정상
- 명령 `1`: 문제
- 유량 숫자는 ESP32로 보내지 않는다.
- 문제에는 저유량, 지속적인 영상 인식 실패, 미보정 상태가 포함된다.
- 정상: 초록 LED 고정
- 문제: 빨간 LED 약 0.4초 간격 점멸
- PC 명령 약 6.5초 단절: `PC LINK ERROR`
- ESP-NOW 약 3.5초 단절: `RADIO LINK ERROR`
- ESP-NOW 채널은 두 보드 모두 `6`이어야 한다.

송수신기의 `protocol.h`는 항상 동일한 packet magic, version, enum, struct layout을 유지해야 한다. 한쪽만 변경하지 않는다.

## 7. 작업 시작 절차

다른 AI는 코드를 수정하기 전에 다음 순서로 확인한다.

1. 사용자 요청이 로컬 앱, Supabase, 정적 웹, ESP32, 배포 중 어디에 해당하는지 분류한다.
2. `README.md`, 이 `AGENTS.md`, 관련 모듈과 테스트를 읽는다.
3. `.git` 존재 여부와 현재 변경 상태를 확인한다. 기존 사용자 변경을 덮어쓰지 않는다.
4. `flow_guard_config.json`은 비밀값을 출력하지 않고 필요한 필드만 선택적으로 확인한다.
5. Netlify/Render 관련 요청이면 저장소 manifest뿐 아니라 사용자가 알려 준 실제 서비스 유형·배포 URL을 확인한다.
6. 변경 범위와 함께 수정해야 할 소비자를 찾는다.
   - 전송 주기 변경: Python config + UI + web config + 문서 + 테스트
   - Supabase schema 변경: 새 migration + Edge Function + web query + RLS + 문서
   - ESP32 protocol 변경: 두 protocol header + 두 sketches + Python sender + tests + guide
7. 비밀값이 diff나 명령 출력에 포함되지 않는지 확인한다.

## 8. 로컬 실행과 검증

Windows PowerShell, 저장소 루트에서 실행한다.

```powershell
.\.venv\Scripts\python.exe run.py
```

전체 자동 테스트:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q analog_flow_guard run.py
```

대시보드 JavaScript 구문 검사에 Node.js가 있으면:

```powershell
node --check web\app.js
```

로컬 대시보드 확인:

```powershell
.\.venv\Scripts\python.exe -m http.server 8000
```

브라우저에서 `http://localhost:8000/web/`을 연다.

### 변경별 최소 검증

| 변경 | 최소 검증 |
|---|---|
| 영상/보정 | geometry, vision 테스트 + 실제 카메라 확인 |
| 경보 | alarm 테스트 + 경계/히스테리시스 시나리오 |
| Serial | arduino 테스트 + 실제 COM 포트 확인 |
| 원격 전송 | remote 테스트 + Supabase Table Editor/Function log 확인 |
| 대시보드 | JS syntax + 로컬 렌더 + 모바일 폭 확인 |
| Supabase | 새 migration 적용 + RLS read/write 확인 + Edge Function test |
| ESP32 | Python 정적 테스트 + Arduino IDE compile + 두 보드 실물 시험 |
| Netlify/Render/Pages | 배포 로그 + 실제 공개 URL + Supabase fetch 확인 |

하드웨어나 계정이 없어 검증하지 못한 항목은 통과했다고 쓰지 말고 `미검증`으로 분명히 보고한다.

## 9. 배포 변경 절차

### Supabase

- 이미 적용된 migration을 과거 파일에서 고치지 말고 새로운 timestamp migration을 추가한다.
- RLS와 grant를 같은 migration에서 검토한다.
- `ingest-flow` 변경 후 로컬 또는 별도 테스트 프로젝트에서 payload 검증을 먼저 한다.
- 배포 명령은 외부 상태를 변경하므로 사용자 요청 또는 승인 없이 실행하지 않는다.
- 배포 후 Function log에서 200, 401, 5xx를 확인하되 토큰이나 Secret을 출력하지 않는다.

### 정적 대시보드

- 실제 배포 원본은 `web/`이다.
- root `index.html`만 수정하고 `web/index.html`을 빠뜨리지 않는다.
- GitHub Pages workflow, Netlify publish directory, Render static publish path가 모두 `web`을 가리키는지 확인한다.
- 공개 URL 하나에서만 확인하지 말고 사용자가 운영으로 지정한 서비스에서 확인한다.

### GitHub

- 사용자가 push/deploy를 요청하지 않았다면 로컬 변경만 수행한다.
- branch, remote, dirty state를 확인하지 않고 `git init`, remote 변경, force push를 하지 않는다.
- `main` push가 GitHub Pages workflow를 실행할 수 있음을 고려한다.

### Netlify와 Render

- 대시보드 연결 설정을 읽을 권한이나 정보가 없으면 URL/서비스 ID를 추측하지 않는다.
- 둘 다 자동 배포 중이라면 한 번의 GitHub push가 여러 공개 사이트를 바꿀 수 있음을 사용자에게 알린다.
- 환경변수를 추가해야 한다면 이름과 목적만 문서화하고 실제 값을 저장소에 기록하지 않는다.

## 10. 알려진 우선 점검 항목

### 10-1. `web/config.js`의 Supabase URL 형식

현재 검사 시 `supabaseUrl`에 다음처럼 Edge Function 전체 경로가 들어 있었다.

```text
https://<project-ref>.supabase.co/functions/v1/ingest-flow
```

그러나 `web/app.js`는 이 값 뒤에 `/rest/v1/flow_readings`를 붙인다. 따라서 대시보드의 `supabaseUrl`은 반드시 다음 **프로젝트 기본 URL**이어야 한다.

```text
https://<project-ref>.supabase.co
```

PC의 `flow_guard_config.json.remote.function_url`에는 반대로 Edge Function 전체 URL이 들어가야 한다. 두 URL의 용도를 혼동하지 않는다.

### 10-2. Render와 Netlify 구성의 저장소 비가시성

- 현재 repository-defined manifest가 없다.
- 서비스 대시보드의 수동 설정이 코드와 달라질 수 있다.
- 다음 수정 시 `netlify.toml` 또는 `render.yaml`을 추가할지는 사용자의 실제 서비스 유형을 확인한 뒤 결정한다.

### 10-3. 로컬 Git 메타데이터

- 현재 작업 폴더 검사에서는 `.git`이 보이지 않았다.
- GitHub 연결이 브라우저나 다른 폴더에서 완료됐을 수 있다.
- remote URL을 발명하거나 다른 저장소로 push하지 않는다.

### 10-4. 원격 업로드 내구성

- 현재 실패 payload는 프로세스 메모리에서 재시도한다.
- 앱 종료나 PC 재부팅 후까지 유지되는 SQLite outbox는 아직 없다.
- 장시간 운영 신뢰성이 필요해지면 예측보다 먼저 persistent outbox를 구현한다.

### 10-5. 공개 데이터 정책

- 현재 migration은 대시보드 편의를 위해 `flow_readings` 공개 읽기를 허용한다.
- 실제 공정 데이터가 민감하면 Netlify/Render 비공개 여부만으로 충분하지 않다. Supabase Auth와 RLS를 함께 바꿔야 한다.

## 11. 개발 우선순위

1. 카메라 판독과 현장 보정 신뢰성
2. Supabase 기록 누락·재시도와 대시보드 실데이터 연결
3. ESP32 상태 및 통신 단절 fail-safe
4. Slack 저유량/복귀 알림 신뢰성
5. Netlify/Render/GitHub Pages 배포 일관성
6. 24시간 이상 장시간 시험과 로그/상태 관측
7. 충분한 현장 데이터 수집 후 저유량 도달 시간 예측

예측 기능을 앞당기지 않는다. 현재 유량이 공정 조작에 따라 변할 수 있으므로 단순 선형 회귀만으로 안전 관련 결론을 내리지 않는다.

## 12. 완료 조건

변경 작업은 관련 항목에 대해 다음을 충족해야 완료로 보고한다.

- 요청한 동작이 실제 코드에 반영됨
- 기존 보정 데이터와 사용자 설정 보존
- 관련 자동 테스트 통과
- Python/JavaScript/ESP32 중 변경한 영역의 구문 또는 compile 검증
- 비밀값이 저장소, diff, 로그에 노출되지 않음
- Supabase schema와 소비자 코드가 일치함
- 서비스 배포를 수행했다면 실제 운영 URL 확인
- 검증하지 못한 하드웨어/클라우드 항목을 명시함
- 문서와 현재 폴더 경로가 일치함

## 13. 다른 AI의 보고 방식

최종 보고는 다음 순서로 짧고 구체적으로 작성한다.

1. 무엇을 완료했는가
2. 어떤 파일을 변경했는가
3. 어떤 테스트와 실제 서비스 URL을 확인했는가
4. 사용자가 입력하거나 승인해야 할 비밀값/외부 작업은 무엇인가
5. 남은 위험 또는 미검증 항목은 무엇인가

비밀값 자체는 보고하지 않는다. 단순히 “설정됨”, “누락됨”, “불일치 가능”으로만 표현한다.