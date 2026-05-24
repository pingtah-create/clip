@echo off
setlocal
cd /d "%~dp0"

echo Creating virtualenv with Python 3.12...
py -3.12 -m venv .venv
if errorlevel 1 (
  echo Failed to create venv. Make sure Python 3.12 is installed: py install 3.12
  exit /b 1
)

echo Upgrading pip...
.venv\Scripts\python.exe -m pip install --upgrade pip wheel

echo Installing requirements (this takes a few minutes)...
.venv\Scripts\pip.exe install -r requirements.txt

if not exist .env (
  echo Copying .env.example to .env  -  edit it to add your ANTHROPIC_API_KEY
  copy .env.example .env > nul
)

mkdir data\uploads 2>nul
mkdir data\jobs 2>nul
mkdir data\clips 2>nul

echo.
echo Setup complete. Edit .env to add your ANTHROPIC_API_KEY, then run: run.bat
