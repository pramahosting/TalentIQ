@echo off
title TalentIQ Platform

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "BACKEND=%ROOT%\backend"
set "FRONTEND=%ROOT%\frontend"
set "VENV=%BACKEND%\venv"
set "DB=postgresql+asyncpg://neondb_owner:npg_XH2QFas3gYDd@ep-dawn-scene-aqma9lhs.c-8.us-east-1.aws.neon.tech/neondb"
set "PYEXE=C:\Users\Jupitor\AppData\Local\Programs\Python\Python311\python.exe"
if not exist "%PYEXE%" set "PYEXE=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe"
if not exist "%PYEXE%" set "PYEXE=C:\Python311\python.exe"

if not exist "C:\Temp" mkdir "C:\Temp"

cls
echo  TalentIQ Platform
echo  ==========================================
echo.

echo  Step 1: Checking Python...
if not exist "%PYEXE%" ( echo  ERROR: Python not found & pause & exit /b 1 )
for /f "tokens=2" %%V in ('"%PYEXE%" --version 2^>^&1') do echo  OK Python %%V
echo.

echo  Step 2: Checking Node.js...
node --version >nul 2>&1
if errorlevel 1 ( echo  ERROR: Node.js not found & pause & exit /b 1 )
for /f %%V in ('node --version') do echo  OK Node %%V
echo.

echo  Step 3: Virtual environment...
if exist "%VENV%\Scripts\python.exe" (
    "%VENV%\Scripts\python.exe" --version > "C:\Temp\tiq_vv.tmp" 2>&1
    findstr "3.11 3.12" "C:\Temp\tiq_vv.tmp" >nul
    if errorlevel 1 (
        echo  Rebuilding venv...
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
echo  OK venv active
echo.

echo  Step 4: Python packages...
set "DOPIP=0"
if not exist "C:\Temp\tiq_pip.stamp" set "DOPIP=1"
if "%DOPIP%"=="0" (
    pip show asyncpg >nul 2>&1
    if errorlevel 1 set "DOPIP=1"
)
if "%DOPIP%"=="1" (
    echo  Installing packages - please wait 3-5 min...
    cd /d "%BACKEND%"
    pip install -r requirements.txt > "C:\Temp\tiq_pip.log" 2>&1
    if errorlevel 1 ( echo  ERROR: pip failed. See C:\Temp\tiq_pip.log & pause & exit /b 1 )
    echo %DATE%> "C:\Temp\tiq_pip.stamp"
    echo  OK packages installed
) else (
    echo  OK packages ready
)
echo.

echo  Step 5: Writing .env...
echo DATABASE_URL=%DB%> "%BACKEND%\.env"
echo SECRET_KEY=talentiq-secret-key>> "%BACKEND%\.env"
echo ADZUNA_APP_ID=638c0962>> "%BACKEND%\.env"
echo ADZUNA_APP_KEY=04681adc21daeda69c41b271627d448a>> "%BACKEND%\.env"
echo GROQ_API_KEY=>> "%BACKEND%\.env"
echo  OK .env written
echo.

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

echo  Step 7: Writing launchers...
echo @echo off> C:\Temp\tiq_b.cmd
echo title TalentIQ Backend>> C:\Temp\tiq_b.cmd
echo set "DATABASE_URL=%DB%">> C:\Temp\tiq_b.cmd
echo cd /d "%BACKEND%">> C:\Temp\tiq_b.cmd
echo echo Backend: http://localhost:8000>> C:\Temp\tiq_b.cmd
echo echo Docs:    http://localhost:8000/docs>> C:\Temp\tiq_b.cmd
echo "%VENV%\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload>> C:\Temp\tiq_b.cmd
echo pause>> C:\Temp\tiq_b.cmd

echo @echo off> C:\Temp\tiq_f.cmd
echo title TalentIQ Frontend>> C:\Temp\tiq_f.cmd
echo cd /d "%FRONTEND%">> C:\Temp\tiq_f.cmd
echo echo Frontend: http://localhost:5173>> C:\Temp\tiq_f.cmd
echo npm run dev>> C:\Temp\tiq_f.cmd
echo pause>> C:\Temp\tiq_f.cmd
echo  OK launchers written
echo.

echo  Step 8: Starting services...
start "TalentIQ Backend"  cmd /k C:\Temp\tiq_b.cmd
echo  Waiting for backend...
timeout /t 12 /nobreak >nul
start "TalentIQ Frontend" cmd /k C:\Temp\tiq_f.cmd
echo  Waiting for frontend...
timeout /t 8 /nobreak >nul
start "" "http://localhost:5173"

echo.
echo  ==========================================
echo  RUNNING
echo  App:   http://localhost:5173
echo  Docs:  http://localhost:8000/docs
echo  Login: admin@talentiq.ai / Talent@1
echo  ==========================================
echo.
echo  Press any key to close this launcher.
pause >nul
