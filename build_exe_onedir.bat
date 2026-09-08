@echo off
setlocal
cd /d "%~dp0"
set PIP_DEFAULT_TIMEOUT=120
set PIP_RETRIES=10
if not exist .venv\Scripts\python.exe (
    where py >nul 2>nul
    if %errorlevel%==0 (
        py -3 -m venv .venv
    ) else (
        python -m venv .venv
    )
)
call .venv\Scripts\activate
python -m pip install pyinstaller matplotlib openpyxl reportlab
if errorlevel 1 goto :fail
python -m PyInstaller --noconfirm --clean --windowed --onedir --name "Prometheus Procurement" --collect-all matplotlib --collect-all openpyxl --collect-all reportlab "Prometheus_V10_9_2.py"
if errorlevel 1 goto :fail
echo.
echo Build complete:
echo %CD%\dist\Prometheus Procurement\Prometheus Procurement.exe
goto :end
:fail
echo.
echo Build failed. Review the messages above.
pause
:end
endlocal
