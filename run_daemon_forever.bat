@echo off
REM Resilient daemon launcher for Windows Task Scheduler.
REM Runs the daemon, and if it ever exits (crash, unhandled error), waits 60s and
REM restarts it — so an unattended deployment self-heals instead of going silent.
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
  echo No venv found. Run setup.bat first.
  exit /b 1
)

:loop
echo [%date% %time%] starting daemon...
.venv\Scripts\python.exe -m backend.daemon
echo [%date% %time%] daemon exited (code %errorlevel%). Restarting in 60s...
timeout /t 60 /nobreak >nul
goto loop
