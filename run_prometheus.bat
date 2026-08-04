@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 Prometheus_V10_8_15.py
) else (
    python Prometheus_V10_8_15.py
)
if errorlevel 1 (
    echo.
    echo Prometheus exited with an error. Review Documents\ImportDecisionApp\error_log.txt
    pause
)
endlocal
