@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%~dp0update.py" %*
) else (
  python "%~dp0update.py" %*
)
echo.
pause
