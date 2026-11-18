
@echo off
setlocal EnableExtensions
title IDS Project Launcher

cd /d "%~dp0"

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "VENV=%BACKEND%\.venv"
set "PYTHON=%VENV%\Scripts\python.exe"
set "REQUIREMENTS=%BACKEND%\requirements.txt"
set "ENV_FILE=%BACKEND%\.env"
set "ENV_EXAMPLE=%BACKEND%\.env.example"

if not exist "%BACKEND%\app\guest_app.py" (
    goto :failed
)

if not exist "%BACKEND%\app\management_app.py" (
    goto :failed
)

if not exist "%REQUIREMENTS%" (
    goto :failed
)

where py >nul 2>nul
if errorlevel 1 (
    goto :failed
)

py -3.14 --version >nul 2>nul
if errorlevel 1 (
    goto :failed
)
py -3.14 --version

if exist "%PYTHON%" (
    "%PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3,14) else 1)" >nul 2>nul
    if errorlevel 1 (
        rmdir /s /q "%VENV%"
    )
)

if not exist "%PYTHON%" (
    py -3.14 -m venv "%VENV%"
    if errorlevel 1 (
        goto :failed
    )
)
"%PYTHON%" -c "import fastapi, uvicorn, scapy, dotenv, httpx" >nul 2>nul

if errorlevel 1 (
    "%PYTHON%" -m ensurepip --upgrade
    if errorlevel 1 goto :failed

    "%PYTHON%" -m pip install --disable-pip-version-check --upgrade pip
    if errorlevel 1 goto :failed

    "%PYTHON%" -m pip install --disable-pip-version-check -r "%REQUIREMENTS%"
    if errorlevel 1 goto :failed
) else (
)
if not exist "%ENV_FILE%" (
    if not exist "%ENV_EXAMPLE%" (
        goto :failed
    )

    copy "%ENV_EXAMPLE%" "%ENV_FILE%" >nul
    if errorlevel 1 goto :failed

)

if not exist "%BACKEND%\data" mkdir "%BACKEND%\data"

netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul

if errorlevel 1 (
    start "IDS - Web Pengunjung" "%ComSpec%" /k "cd /d ""%BACKEND%"" && ""%PYTHON%"" -m uvicorn app.guest_app:app --host 0.0.0.0 --port 8000"
) else (
)

netstat -ano | findstr /R /C:":8001 .*LISTENING" >nul

if errorlevel 1 (
    start "IDS - Web Utama" "%ComSpec%" /k "cd /d ""%BACKEND%"" && ""%PYTHON%"" -m uvicorn app.management_app:app --host 127.0.0.1 --port 8001"
) else (
)
pause
exit /b 0