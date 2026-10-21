@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHON=%CD%\.venv\Scripts\python.exe"
set "NEED_INSTALL="

if not exist "%PYTHON%" (
  where py >nul 2>nul
  if errorlevel 1 (
    echo Python Launcher was not found. Install 64-bit Python 3.13 and enable the launcher.
    pause
    exit /b 1
  )
  py -3.13 --version >nul 2>nul
  if errorlevel 1 (
    echo Sketch2GUI setup requires 64-bit Python 3.13.
    echo Install Python 3.13, then run this file again.
    pause
    exit /b 1
  )
  echo Creating the Sketch2GUI virtual environment...
  py -3.13 -m venv .venv
  if errorlevel 1 goto :failed
  set "NEED_INSTALL=1"
)

"%PYTHON%" -c "import struct, sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) and struct.calcsize('P') == 8 else 1)"
if errorlevel 1 (
  echo ERROR: The existing .venv must use 64-bit Python 3.13.
  echo Remove .venv and run this file again after installing 64-bit Python 3.13.
  pause
  exit /b 1
)

"%PYTHON%" -c "from importlib.metadata import version; [version(p) for p in ('PySide6', 'Pillow', 'paddlepaddle', 'paddleocr')]" >nul 2>nul
if errorlevel 1 set "NEED_INSTALL=1"

if defined NEED_INSTALL (
  echo Installing Sketch2GUI and the local English OCR engine. This may take several minutes...
  "%PYTHON%" -m pip install --upgrade pip
  if errorlevel 1 goto :failed
  "%PYTHON%" -m pip install -r requirements.txt -r requirements-ocr-paddle.txt
  if errorlevel 1 goto :failed
)

echo Starting Sketch2GUI...
"%PYTHON%" -m sketch2gui
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo Setup or launch failed. Check the error above.
pause
exit /b 1
