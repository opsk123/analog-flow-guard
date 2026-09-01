# Supabase와 GitHub Pages 처음 연결하기

이 문서는 계정을 한 번도 만들어 보지 않은 사용자가 Flow Guard의 측정값을 Supabase에 저장하고 GitHub Pages에서 확인하기 위한 순서입니다. 처음에는 **1분 시연 모드**로 연결하고, 시연이 끝난 뒤 **1시간 운영 모드**로 바꾸면 됩니다.

## 0. 두 서비스의 역할

- **Supabase**: PC가 보낸 측정값을 데이터베이스에 저장하고 웹에 읽기 API를 제공합니다.
- **GitHub**: 프로그램 소스와 변경 이력을 보관합니다.
- **GitHub Pages**: `web` 폴더의 대시보드를 웹사이트로 배포합니다.

측정값을 GitHub에 1분마다 커밋하지 않습니다. 측정값은 Supabase에만 저장합니다.

## 1. 준비물

1. [Supabase](https://supabase.com/) 계정
2. [GitHub](https://github.com/) 계정
3. Windows용 [Git](https://git-scm.com/download/win)
4. [Node.js LTS](https://nodejs.org/) — Supabase CLI를 `npx`로 실행할 때 사용
5. Python 3.10 이상

PowerShell을 열고 다음 명령이 각각 버전을 표시하는지 확인합니다.

```powershell
git --version
node --version
npx supabase --version
python --version
```

## 2. Supabase 프로젝트 만들기

1. Supabase에 로그인하고 **New project**를 누릅니다.
2. Organization을 선택하고 프로젝트 이름을 `analog-flow-guard`로 입력합니다.
3. Database Password는 암호 관리자에 보관합니다. 이 저장소에는 적지 않습니다.
4. 한국에서 시연한다면 가까운 리전을 선택하고 프로젝트 생성을 기다립니다.
5. 프로젝트 화면의 **Connect** 또는 **Settings → API Keys**에서 다음 값을 따로 기록합니다.
   - Project URL: `https://프로젝트참조.supabase.co`
   - Publishable key: `sb_publishable_...`
   - Secret key: `sb_secret_...`

Publishable key는 웹페이지에 공개되는 용도입니다. Secret key는 데이터베이스 권한을 우회할 수 있으므로 절대로 GitHub, `web/config.js`, 채팅 또는 화면 캡처에 노출하지 않습니다.

## 3. 측정 테이블 만들기

가장 쉬운 방법은 Supabase 웹 화면의 **SQL Editor**를 사용하는 것입니다.

1. 왼쪽 메뉴에서 **SQL Editor → New query**를 누릅니다.
2. 저장소의 `supabase/migrations/202608310001_create_flow_readings.sql` 내용을 전부 복사합니다.
3. SQL Editor에 붙여 넣고 **Run**을 누릅니다.
4. **Table Editor**에 `flow_readings`가 생겼는지 확인합니다.

이 SQL은 웹 대시보드에 읽기만 허용하고, 브라우저에서 삽입·수정·삭제하는 작업은 차단합니다. 쓰기는 다음 단계의 Edge Function만 수행합니다.

## 4. 장치 토큰 만들기

장치 토큰은 PC 프로그램과 Supabase 함수만 공유하는 암호입니다. PowerShell에서 다음 명령으로 임의 값을 만들 수 있습니다.

```powershell
$flowDeviceToken = ([guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N"))
$flowDeviceToken
```

표시된 값은 잠시 안전한 곳에 복사합니다. 이후 두 위치에 동일한 값을 입력합니다.

## 5. Supabase Edge Function 배포하기

이 프로젝트 폴더에서 PowerShell을 열고 실행합니다.

```powershell
npx supabase login
npx supabase projects list
npx supabase link --project-ref 여기에_프로젝트_REF
```

다음 명령의 두 값을 실제 값으로 바꿉니다. 명령 기록을 다른 사람과 공유하지 마십시오.

```powershell
npx supabase secrets set FLOW_DEVICE_TOKEN="4단계에서_만든_토큰" FLOW_SUPABASE_SECRET_KEY="sb_secret_실제_Secret_Key"
npx supabase functions deploy ingest-flow --use-api
```

배포 주소는 다음 형식입니다.

```text
https://프로젝트_REF.supabase.co/functions/v1/ingest-flow
```

이 함수는 Supabase 기본 JWT 대신 `x-device-token`을 직접 검사합니다. `supabase/config.toml`에서 해당 함수만 `verify_jwt = false`로 설정되어 있지만, 장치 토큰이 틀리면 HTTP 401을 반환합니다.

### 5-1. Slack 저유량 알림 연결하기

Slack을 아직 사용하지 않거나 웹 저장부터 시험하려면 이 절차는 건너뛰어도 됩니다. 측정 저장은 Slack 설정 없이도 동작합니다.

1. [Slack Incoming Webhooks 안내](https://api.slack.com/messaging/webhooks)에서 **Create your Slack app**을 누릅니다.
2. **From scratch**로 앱을 만들고 알림을 받을 Workspace를 선택합니다.
3. 앱 설정의 **Incoming Webhooks**를 켭니다.
4. **Add New Webhook to Workspace**를 눌러 알림 채널을 선택합니다.
5. `https://hooks.slack.com/services/...` 형식의 URL을 복사합니다.
6. 다음 명령으로 URL과 경보 기준을 Supabase Secrets에 저장합니다.

```powershell
npx supabase secrets set SLACK_WEBHOOK_URL="https://hooks.slack.com/services/실제_값" FLOW_LOW_THRESHOLD_LPM="0.15" FLOW_RECOVERY_MARGIN_LPM="0.05"
```

Slack Webhook URL은 메시지를 보낼 수 있는 비밀값입니다. GitHub나 `web/config.js`에 넣지 않습니다. 측정값이 `0.15 L/min` 이하로 처음 내려갈 때 한 번 알리고, `0.20 L/min` 이상으로 회복할 때 정상 복귀를 한 번 알립니다. 발송 실패 시 Supabase에 미발송 상태를 남기고 PC 업로더가 같은 측정값을 재시도합니다.

## 6. PC 프로그램 연결하기

PowerShell에서 장치 토큰을 현재 Windows 사용자 환경변수로 저장합니다.

```powershell
[Environment]::SetEnvironmentVariable("FLOW_DEVICE_TOKEN", "4단계에서_만든_토큰", "User")
```

열려 있던 Flow Guard와 PowerShell을 모두 닫았다가 다시 엽니다. `python run.py`로 실행한 다음 프로그램의 **4. 웹 전송**에서 다음을 입력합니다.

- 주기적으로 웹으로 전송: 체크
- 전송 주기: `1분 (MVP 시연)`
- Function URL: 5단계의 `.../functions/v1/ingest-flow`
- 장치 ID: `FLOW-01`

**설정 저장 및 적용**을 누른 뒤 `Web: 전송 완료`가 표시되는지 확인합니다. 1분 뒤 Supabase Table Editor의 `flow_readings`에 두 번째 행이 생기면 정상입니다.

## 7. 웹 대시보드 연결하기

`web/config.js`를 열고 다음 세 값을 변경합니다.

```javascript
supabaseUrl: "https://실제_프로젝트_REF.supabase.co",
publishableKey: "sb_publishable_실제_공개키",
deviceId: "FLOW-01",
```

시연 중에는 다음 값을 유지합니다.

```javascript
expectedIntervalSec: 60,
```

`web/index.html`을 열었을 때 현재값과 최근 기록이 보이면 Supabase 연결이 완료된 것입니다. 로컬 파일 접근 정책으로 브라우저가 요청을 차단하면 프로젝트 폴더에서 아래처럼 간단한 웹 서버를 실행하고 `http://localhost:8000/web/`을 엽니다.

```powershell
python -m http.server 8000
```

## 8. GitHub 저장소 만들고 올리기

1. GitHub에서 오른쪽 위 `+` → **New repository**를 누릅니다.
2. 이름을 `analog-flow-guard`로 입력합니다.
3. 처음에는 Public이 가장 간단합니다. 가스 데이터 공개가 곤란하면 Private 저장소와 대시보드 인증 설계를 먼저 검토합니다.
4. README나 `.gitignore` 자동 생성을 선택하지 않고 저장소를 만듭니다.
5. GitHub가 보여 주는 저장소 URL을 복사합니다.

프로젝트 폴더 PowerShell에서 실행합니다.

```powershell
git init -b main
git add .
git commit -m "Build Flow Guard MVP"
git remote add origin https://github.com/내_아이디/analog-flow-guard.git
git push -u origin main
```

처음 커밋할 때 이름과 이메일을 요구하면 Git의 안내에 따라 `git config --global user.name`과 `user.email`을 한 번 설정합니다.

## 9. GitHub Pages 켜기

1. GitHub 저장소에서 **Settings → Pages**로 이동합니다.
2. Build and deployment의 Source를 **GitHub Actions**로 선택합니다.
3. 저장소의 **Actions** 탭에서 `Deploy flow dashboard to GitHub Pages`가 성공하는지 확인합니다.
4. 완료된 작업에 표시되는 사이트 주소를 엽니다.

`.github/workflows/pages.yml`은 `web` 폴더만 배포합니다. 이후 `web` 폴더를 수정해 `main` 브랜치에 push하면 사이트가 자동 갱신됩니다.

## 10. 시연 후 1시간 운영 모드로 바꾸기

두 위치를 함께 바꿉니다.

1. Flow Guard 설정 화면의 전송 주기 → `1시간 (운영)`
2. `web/config.js` → `expectedIntervalSec: 3600`

변경한 대시보드를 배포합니다.

```powershell
git add web/config.js flow_guard_config.json
git commit -m "Switch reporting interval to one hour"
git push
```

## 11. 자주 발생하는 오류

- `Web: 환경변수 FLOW_DEVICE_TOKEN 필요`: 환경변수를 저장한 뒤 프로그램을 완전히 다시 시작합니다.
- HTTP 401: PC 환경변수와 Supabase `FLOW_DEVICE_TOKEN`이 다릅니다.
- HTTP 500 `server_not_configured`: `FLOW_SUPABASE_SECRET_KEY` Secret이 누락됐습니다.
- HTTP 502 `database_write_failed` 또는 `alert_state_*`: 최신 테이블 SQL을 전부 실행했는지, Secret key가 올바른지 확인합니다.
- HTTP 502 `slack_notification_failed`: Slack Webhook이 삭제됐거나 Slack 연결이 일시적으로 실패했습니다. URL과 Edge Function 로그를 확인합니다.
- 대시보드 `설정 필요`: `web/config.js`의 placeholder를 실제 Project URL과 Publishable key로 바꿉니다.
- 대시보드 HTTP 401/403: Secret key가 아니라 Publishable key를 썼는지 확인하고 SQL의 RLS 정책을 다시 실행합니다.
- GitHub Actions 실패: Settings → Pages의 Source가 GitHub Actions인지 확인합니다.

Supabase 공식 참고 문서: [Edge Functions 시작하기](https://supabase.com/docs/guides/functions/quickstart), [API 키 종류](https://supabase.com/docs/guides/getting-started/api-keys), [RLS](https://supabase.com/docs/guides/database/postgres/row-level-security)

GitHub 공식 참고 문서: [Pages 사용자 지정 워크플로](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
