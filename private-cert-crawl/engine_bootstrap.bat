@echo off
setlocal enabledelayedexpansion

REM ==== 캐시/TEMP를 D:로 (선택) ====
set "PIP_CACHE_DIR=D:\pip-cache"
set "TMP=D:\temp"
set "TEMP=D:\temp"
if not exist "%PIP_CACHE_DIR%" mkdir "%PIP_CACHE_DIR%"
if not exist "%TMP%" mkdir "%TMP%"

REM ==== 엔진 루트 ====
set "ENGINE_ROOT=%~dp0"
cd /d "%ENGINE_ROOT%"
echo [BOOT] Engine root: %ENGINE_ROOT%

REM ==== 전역 파이썬 경로(베이스) ====
set "BASE_PY=C:\Python\Python311\python.exe"

REM ==== venv 생성 ====
if not exist ".venv\Scripts\python.exe" (
  echo [BOOT] Creating venv with %BASE_PY% ...
  "%BASE_PY%" -m venv .venv
  if errorlevel 1 (
    echo [BOOT][ERROR] venv 생성 실패
    exit /b 1
  )
)

REM ==== pip 업그레이드 + 의존성 설치 ====
".venv\Scripts\python.exe" -m pip install -U pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [BOOT][ERROR] requirements 설치 실패 (requirements.txt 파일명/경로 확인)
  exit /b 1
)

REM ==== 환경 확인 ====
".venv\Scripts\python.exe" -c "import sys,platform;print('[ENV] exe=',sys.executable);print('[ENV] ver=',sys.version.split()[0]);print('[ENV] plat=',platform.platform())"

echo [BOOT] Done. Venv: ".venv\Scripts\python.exe"
pause
endlocal
