@echo off
setlocal enabledelayedexpansion
title TalentIQ Platform

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "BACKEND=%ROOT%\backend"
set "FRONTEND=%ROOT%\frontend"
set "VENV=%BACKEND%\venv"
set "DB=postgresql+asyncpg://neondb_owner:npg_XH2QFas3gYDd@ep-dawn-scene-aqma9lhs.c-8.us-east-1.aws.neon.tech/neondb"

if not exist "C:\Temp" mkdir "C:\Temp"

cls
echo  TalentIQ Platform
echo  ==========================================
echo.

:: ── Step 1: Find Python 3.11 ──────────────────────────────────────────────
echo  Step 1: Checking Python 3.11...
set "PYEXE="
if exist "C:\Users\Jupitor\AppData\Local\Programs\Python\Python311\python.exe" set "PYEXE=C:\Users\Jupitor\AppData\Local\Programs\Python\Python311\python.exe"
if not defined PYEXE if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe" set "PYEXE=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe"
if not defined PYEXE if exist "C:\Python311\python.exe" set "PYEXE=C:\Python311\python.exe"
if not defined PYEXE if exist "C:\Program Files\Python311\python.exe" set "PYEXE=C:\Program Files\Python311\python.exe"

if not defined PYEXE (
    echo  ERROR: Python 3.11 not found. Install from https://python.org/downloads
    pause & exit /b 1
)
for /f "tokens=2" %%V in ('"%PYEXE%" --version 2^>^&1') do echo  OK Python %%V
echo.

:: ── Step 2: Node.js ───────────────────────────────────────────────────────
echo  Step 2: Checking Node.js...
node --version >nul 2>&1
if errorlevel 1 ( echo  ERROR: Node.js not found & pause & exit /b 1 )
for /f %%V in ('node --version') do echo  OK Node %%V
echo.

:: ── Step 3: Virtual environment ───────────────────────────────────────────
echo  Step 3: Virtual environment...
if exist "%VENV%\Scripts\python.exe" (
    "%VENV%\Scripts\python.exe" --version > "C:\Temp\tiq_vv.tmp" 2>&1
    findstr /b "Python 3.11" "C:\Temp\tiq_vv.tmp" >nul
    if errorlevel 1 (
        echo  Wrong Python in venv - rebuilding...
        rmdir /s /q "%VENV%"
        del "C:\Temp\tiq_pip.stamp" >nul 2>&1
    )
    del "C:\Temp\tiq_vv.tmp" >nul 2>&1
)
if not exist "%VENV%\Scripts\activate.bat" (
    echo  Creating venv...
    "%PYEXE%" -m venv "%VENV%"
    if errorlevel 1 ( echo  ERROR: venv failed & pause & exit /b 1 )
    del "C:\Temp\tiq_pip.stamp" >nul 2>&1
)
call "%VENV%\Scripts\activate.bat"
set "VENVPY=%VENV%\Scripts\python.exe"
set "VENVPIP=%VENV%\Scripts\pip.exe"
echo  OK venv active (Python 3.11)
echo.

:: ── Step 4: Python packages ───────────────────────────────────────────────
echo  Step 4: Python packages...
set "DOPIP=0"
if not exist "C:\Temp\tiq_pip.stamp" set "DOPIP=1"
if "%DOPIP%"=="0" (
    "%VENVPIP%" show asyncpg >nul 2>&1
    if errorlevel 1 set "DOPIP=1"
)
if "%DOPIP%"=="1" (
    echo  Installing packages - please wait 3-5 min...
    echo  ^(This window will stay open^)
    cd /d "%BACKEND%"
    "%VENVPIP%" install -r requirements.txt > "C:\Temp\tiq_pip.log" 2>&1
    set "PIPERR=!errorlevel!"
    if "!PIPERR!"=="0" (
        echo %DATE%> "C:\Temp\tiq_pip.stamp"
        echo  OK packages installed
    ) else (
        echo  WARNING: Some packages may have failed.
        echo  Check C:\Temp\tiq_pip.log for details.
        echo  Continuing anyway...
    )
) else (
    echo  OK packages ready
)
echo.

:: ── Step 5: Write .env ────────────────────────────────────────────────────
echo  Step 5: Writing .env...
echo DATABASE_URL=%DB%> "%BACKEND%\.env"
echo SECRET_KEY=talentiq-secret-key-2024>> "%BACKEND%\.env"
echo ADZUNA_APP_ID=638c0962>> "%BACKEND%\.env"
echo ADZUNA_APP_KEY=04681adc21daeda69c41b271627d448a>> "%BACKEND%\.env"
echo GROQ_API_KEY=>> "%BACKEND%\.env"
echo  OK .env written
echo.

:: ── Step 6: Frontend packages ─────────────────────────────────────────────
echo  Step 6: Frontend packages...
cd /d "%FRONTEND%"
if not exist "node_modules" (
    echo  Running npm install...
    npm install --no-fund --no-audit > "C:\Temp\tiq_npm.log" 2>&1
    echo  OK npm done
) else (
    echo  OK node_modules exist
)
echo.

:: ── Step 7: Write launchers ───────────────────────────────────────────────
echo  Step 7: Writing launchers...

(
echo @echo off
echo title TalentIQ Backend
echo set "DATABASE_URL=%DB%"
echo cd /d "%BACKEND%"
echo echo Backend: http://localhost:8000
echo echo Docs:    http://localhost:8000/api/docs
echo "%VENVPY%" -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
echo pause
) > C:\Temp\tiq_b.cmd

(
echo @echo off
echo title TalentIQ Frontend
echo cd /d "%FRONTEND%"
echo echo Frontend: http://localhost:5173
echo npm run dev
echo pause
) > C:\Temp\tiq_f.cmd

echo  OK launchers written
echo.

:: ── Step 8: Start services ────────────────────────────────────────────────
:: Polls the actual HTTP response of each service (not just whether the
:: port is open — Vite/uvicorn can accept a TCP connection before they're
:: actually ready to serve a working page) before opening the browser.
echo  Step 8: Starting services...
start "TalentIQ Backend" cmd /k "C:\Temp\tiq_b.cmd"

echo  Waiting for backend (http://localhost:8000)...
set "BACKEND_READY=0"
for /l %%i in (1,1,120) do (
    if "!BACKEND_READY!"=="0" (
        powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:8000/api/docs' -UseBasicParsing -TimeoutSec 3; exit 0 } catch { exit 1 }" >nul 2>&1
        if not errorlevel 1 (
            set "BACKEND_READY=1"
        ) else (
            timeout /t 1 /nobreak >nul
        )
    )
)
if "!BACKEND_READY!"=="1" (
    echo  OK backend responded.
) else (
    echo  WARNING: backend did not respond within 120s - continuing anyway.
    echo  Check the "TalentIQ Backend" window for errors.
)
echo.

start "TalentIQ Frontend" cmd /k "C:\Temp\tiq_f.cmd"

echo  Waiting for frontend (http://localhost:5173)...
set "FRONTEND_READY=0"
for /l %%i in (1,1,120) do (
    if "!FRONTEND_READY!"=="0" (
        powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:5173' -UseBasicParsing -TimeoutSec 3; exit 0 } catch { exit 1 }" >nul 2>&1
        if not errorlevel 1 (
            set "FRONTEND_READY=1"
        ) else (
            timeout /t 1 /nobreak >nul
        )
    )
)
if "!FRONTEND_READY!"=="1" (
    echo  OK frontend responded.
    timeout /t 2 /nobreak >nul
) else (
    echo  WARNING: frontend did not respond within 120s - opening anyway.
    echo  Check the "TalentIQ Frontend" window for errors.
)

start "" "http://localhost:5173"

echo.
echo  ==========================================
echo  RUNNING
echo  App:      http://localhost:5173
echo  API Docs: http://localhost:8000/api/docs
echo  ==========================================
echo.
echo  This window will close automatically in 8 seconds.
echo  (Backend and Frontend keep running in their own separate windows.)
timeout /t 8 >nul
exit