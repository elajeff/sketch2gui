@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "ROOT=%CD%"
set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
set "ICON=%ROOT%\assets\app_icon.ico"

if not exist "%PYTHON%" (
  echo ERROR: Project Python not found at "%PYTHON%".
  echo Run run.bat first, or create the project virtual environment with Python 3.13.
  exit /b 1
)
if not exist "%ICON%" (
  echo ERROR: Application icon is missing: "%ICON%".
  echo Restore the application icon at assets\app_icon.ico before building.
  exit /b 1
)

"%PYTHON%" -c "import struct, sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) and struct.calcsize('P') == 8 else 1)"
if errorlevel 1 (
  echo ERROR: This OCR-enabled Windows build requires a 64-bit Python 3.13 virtual environment.
  "%PYTHON%" --version
  exit /b 1
)

echo [1/5] Installing core, PaddleOCR, and PyInstaller dependencies...
"%PYTHON%" -m pip install --upgrade pip
if errorlevel 1 goto :failed
"%PYTHON%" -m pip install -r requirements.txt -r requirements-ocr-paddle.txt -r requirements-build.txt
if errorlevel 1 goto :failed

echo [2/5] Checking Python syntax...
"%PYTHON%" -m compileall -q sketch2gui tests tools
if errorlevel 1 goto :failed

echo [3/5] Running the complete test suite...
"%PYTHON%" -m unittest discover -s tests -v
if errorlevel 1 goto :failed

echo [4/5] Building an OCR-enabled Windows folder distribution...
if exist "%ROOT%\build\release-dist" rmdir /s /q "%ROOT%\build\release-dist"
"%PYTHON%" -m PyInstaller --noconfirm --clean --windowed --onedir ^
  --name Sketch2GUI ^
  --distpath "%ROOT%\build\release-dist" ^
  --workpath "%ROOT%\build\pyinstaller-work" ^
  --specpath "%ROOT%\build\pyinstaller-spec" ^
  --icon "%ICON%" ^
  --add-data "%ICON%;assets" ^
  --collect-all paddle ^
  --collect-all paddleocr ^
  --collect-all paddlex ^
  --additional-hooks-dir "%ROOT%\packaging\hooks" ^
  --hidden-import paddleocr ^
  --hidden-import paddlex ^
  "%ROOT%\launch_sketch2gui.py"
if errorlevel 1 goto :failed
if not exist "%ROOT%\build\release-dist\Sketch2GUI\Sketch2GUI.exe" (
  echo ERROR: PyInstaller did not create the expected executable.
  goto :failed
)

rem Replace the previous distribution only after the staged build succeeded.
rem Keep the previous folder available so a failed move can be rolled back.
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "STAMP=%%i"
set "PREVIOUS_DIST="
if not exist "%ROOT%\dist" mkdir "%ROOT%\dist"
if exist "%ROOT%\dist\Sketch2GUI" (
  set "PREVIOUS_DIST=%ROOT%\dist\Sketch2GUI-previous-%STAMP%"
  ren "%ROOT%\dist\Sketch2GUI" "Sketch2GUI-previous-%STAMP%"
  if errorlevel 1 goto :failed
)
move "%ROOT%\build\release-dist\Sketch2GUI" "%ROOT%\dist\Sketch2GUI"
if errorlevel 1 goto :restore_previous
if not exist "%ROOT%\dist\Sketch2GUI\Sketch2GUI.exe" goto :restore_previous

echo [5/5] Windows build completed.
echo App: %ROOT%\dist\Sketch2GUI\Sketch2GUI.exe
echo OCR runtime libraries are packaged. English model weights are downloaded on first OCR use.
echo Run the packaged EXE once and test OCR on the target machine before distributing it.
exit /b 0

:restore_previous
echo ERROR: The new distribution could not be installed. Restoring the previous build when available...
if exist "%ROOT%\dist\Sketch2GUI" rmdir /s /q "%ROOT%\dist\Sketch2GUI"
if defined PREVIOUS_DIST (
  if exist "%PREVIOUS_DIST%" (
    ren "%PREVIOUS_DIST%" "Sketch2GUI"
    if errorlevel 1 echo WARNING: Previous distribution remains at "%PREVIOUS_DIST%".
  )
)
goto :failed

:failed
echo.
echo BUILD FAILED. Read the first error above; the release script will not package this build.
exit /b 1
