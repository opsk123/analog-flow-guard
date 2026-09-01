[CmdletBinding()]
param(
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPath = Join-Path $projectRoot ".venv"
$lockFile = Join-Path $projectRoot "requirements-lock.txt"

if (-not $Python) {
    $registered = Get-ItemProperty "HKCU:\Software\Python\PythonCore\3.12\InstallPath" -ErrorAction SilentlyContinue
    if ($registered -and $registered.ExecutablePath) {
        $Python = $registered.ExecutablePath
    } else {
        $command = Get-Command python -ErrorAction SilentlyContinue
        if ($command) { $Python = $command.Source }
    }
}

if (-not $Python -or -not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Python 3.12 실행 파일을 찾을 수 없습니다. -Python 매개변수로 경로를 지정하세요."
}

if (Test-Path -LiteralPath $venvPath) {
    $resolvedProject = [IO.Path]::GetFullPath($projectRoot)
    $resolvedVenv = [IO.Path]::GetFullPath($venvPath)
    if (-not $resolvedVenv.StartsWith($resolvedProject + [IO.Path]::DirectorySeparatorChar)) {
        throw "안전하지 않은 가상환경 경로입니다: $resolvedVenv"
    }
    Remove-Item -LiteralPath $resolvedVenv -Recurse -Force
}

& $Python -m venv --upgrade-deps $venvPath
if ($LASTEXITCODE -ne 0) { throw "가상환경 생성에 실패했습니다." }

$venvPython = Join-Path $venvPath "Scripts\python.exe"
& $venvPython -m pip install --requirement $lockFile
if ($LASTEXITCODE -ne 0) { throw "의존성 설치에 실패했습니다." }

& $venvPython -m pip check
if ($LASTEXITCODE -ne 0) { throw "설치된 패키지의 의존성 검사에 실패했습니다." }

Write-Host "가상환경 준비 완료: $venvPath"
