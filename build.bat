@echo off
REM Rebuild the ILT Repair Tool executable.
REM Requires: pip install pyinstaller
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "ILT Repair Tool" ^
  --distpath dist --workpath build --specpath build ^
  --hidden-import ilt_core --paths . ^
  ilt_repair_app.py
echo.
echo Done. See dist\ILT Repair Tool.exe
pause
