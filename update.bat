@echo off
setlocal
cd /d "%~dp0"
echo TYOS MediaPrompt Updater
echo Close ComfyUI before continuing.
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 updater.py
) else (
  python updater.py
)
echo.
pause
