@echo off
rem Starts Clipper. First run creates a virtual environment and installs dependencies.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Setting up Clipper for the first time...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  .venv\Scripts\python.exe -m pip install --upgrade pip
  .venv\Scripts\python.exe -m pip install -r requirements.txt || goto :fail
  .venv\Scripts\python.exe -m playwright install chromium
)
.venv\Scripts\python.exe -m clipper %*
goto :eof
:fail
echo Installing dependencies failed. Check that Python 3.10+ is installed and try again.
pause
