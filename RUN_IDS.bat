@echo off
setlocal EnableExtensions EnableDelayedExpansion
title IDS Launcher

set "ROOT=%~dp0"

if exist "%ROOT%backend\requirements.txt" (
    set "BACKEND=%ROOT%backend"
) else if exist "%ROOT%requirements.txt" (
    set "BACKEND=%ROOT%"
) else (
    echo Backend tidak ditemukan.
    pause
    exit /b 1
)

for %%I in ("%BACKEND%") do set "BACKEND=%%~fI"

set "VENV_PY=%BACKEND%\.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3 -m venv "%BACKEND%\.venv"
    ) else (
        python -m venv "%BACKEND%\.venv"
    )

    if errorlevel 1 (
        echo Gagal membuat virtual environment.
        pause
        exit /b 1
    )
)

"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 (
    echo Gagal menyiapkan pip.
    pause
    exit /b 1
)

"%VENV_PY%" -m pip install -r "%BACKEND%\requirements.txt"
if errorlevel 1 (
    echo Instalasi dependency gagal.
    pause
    exit /b 1
)

pushd "%BACKEND%"

set "GUEST_TARGET="
set "MAIN_TARGET="

for /r "%BACKEND%" %%F in (*.py) do (
    echo %%~fF | findstr /i /c:"\.venv\" /c:"\venv\" /c:"\__pycache__\" >nul
    if errorlevel 1 (
        findstr /i /c:"FastAPI(" "%%~fF" >nul
        if not errorlevel 1 (
            set "REL=%%~fF"
            set "REL=!REL:%BACKEND%\=!"
            set "REL=!REL:.py=!"
            set "MOD=!REL:\=.!"
            if /i "!MOD:~-9!"==".__init__" set "MOD=!MOD:~0,-9!"

            echo %%~fF | findstr /i "guest visitor pengunjung" >nul
            if not errorlevel 1 set "GUEST_TARGET=!MOD!:app"

            echo %%~fF | findstr /i "management admin utama" >nul
            if not errorlevel 1 set "MAIN_TARGET=!MOD!:app"
        )
    )
)

if not defined GUEST_TARGET (
    echo Web Pengunjung tidak ditemukan.
    popd
    pause
    exit /b 1
)

if not defined MAIN_TARGET (
    echo Web Utama tidak ditemukan.
    popd
    pause
    exit /b 1
)

start "IDS Web Pengunjung" "%ComSpec%" /k ""%VENV_PY%" -m uvicorn !GUEST_TARGET! --host 0.0.0.0 --port 8000"

start "IDS Web Utama" "%ComSpec%" /k ""%VENV_PY%" -m uvicorn !MAIN_TARGET! --host 127.0.0.1 --port 8001"

echo.
echo Web Pengunjung: http://127.0.0.1:8000
echo Web Utama: http://127.0.0.1:8001
echo.

popd
pause