# 이 프로젝트는 Google Drive 동기화 폴더 안에 있어서, 가상환경(.venv)을
# Drive 밖(로컬 디스크)에 두어야 pip/uv 가 느려지거나 잠기지 않는다.
# 이 래퍼는 uv 에게 가상환경 위치를 알려준 뒤 명령을 그대로 전달한다.
#
# 사용 예:
#   .\run.ps1 sync                         <- 의존성 설치/갱신
#   .\run.ps1 run python capture_app.py    <- 캡처 프로그램 실행
#   .\run.ps1 run python ocr_pipeline.py --selftest
if (-not $env:UV_PROJECT_ENVIRONMENT) {
    $env:UV_PROJECT_ENVIRONMENT = Join-Path $env:LOCALAPPDATA "uv-envs\quiz-capture"
}
& uv @args
