@echo off
title ILT Repair Tool
cd /d "%~dp0"

rem ---------------------------------------------------------------------------
rem  Double-click this file to start the ILT Repair Tool.
rem
rem  It uses the built executable if one exists, otherwise it runs the app
rem  straight from the Python source. Nothing needs to be installed except
rem  Python itself, and only for the second case.
rem ---------------------------------------------------------------------------

if exist "dist\ILT Repair Tool.exe" (
    start "" "dist\ILT Repair Tool.exe"
    exit /b 0
)

rem Windowed Python launchers first, so no black console window appears.
where pyw >nul 2>&1
if %errorlevel%==0 (
    start "" pyw "ilt_repair_app.py"
    exit /b 0
)

where pythonw >nul 2>&1
if %errorlevel%==0 (
    start "" pythonw "ilt_repair_app.py"
    exit /b 0
)

rem Console Python as a fallback, so any startup error stays readable.
where py >nul 2>&1
if %errorlevel%==0 (
    py "ilt_repair_app.py"
    if errorlevel 1 pause
    exit /b 0
)

where python >nul 2>&1
if %errorlevel%==0 (
    python "ilt_repair_app.py"
    if errorlevel 1 pause
    exit /b 0
)

echo.
echo   ---------------------------------------------------------------
echo    Python was not found on this PC.
echo.
echo    Install Python 3.9 or newer from:
echo        https://www.python.org/downloads/
echo.
echo    IMPORTANT: tick "Add python.exe to PATH" in the installer.
echo    Then double-click this file again.
echo   ---------------------------------------------------------------
echo.
pause
exit /b 1
