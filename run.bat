@echo off
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
  echo No venv found. Run setup.bat first.
  exit /b 1
)

REM --timeout-graceful-shutdown 1 = uvicorn waits at most 1s for clean shutdown before
REM force-exiting. Without it, daemon pipeline threads with stuck ffmpeg subprocesses
REM hold the server open indefinitely after Ctrl+C.
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --timeout-graceful-shutdown 1
