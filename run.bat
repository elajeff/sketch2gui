@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher was not found. Install Python 3.11 or newer and enable the launcher.
  pause
  exit /b 1
)
py -3.13 --version >nul 2>nul
if not errorlevel 1 (
  set "PYTHON=py -3.13"
) else (
  set "PYTHON=py -3"
)
if not exist ".venv\Scripts\python.exe" (
  %PYTHON% -m venv .venv
  if errorlevel 1 goto :failed
)
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto :failed
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :failed
.venv\Scripts\python.exe -m sketch2gui
if errorlevel 1 goto :failed
exit /b 0
:failed
echo.
echo Setup or launch failed. Check the error above.
pause
exit /b 1
