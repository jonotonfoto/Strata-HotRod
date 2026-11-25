@echo off
rem Update a copy of this fork that was installed as docs\SPEED_FIXES_SETUP.md says:
rem   1. UPDATE.bat: the newest code from the address this folder was cloned from (git pull), then the engine is
rem      compiled again if its source changed, and the Python packages and each model's settings are brought up to date;
rem   2. tools\speed_decline\apply_env.py: the speed-fix variables this fork recommends are added to the "env" of every
rem      strata-<model>.json that does not have them yet (a value that is already there is kept; a copy of the config is
rem      saved first as <name>.json.bak-speed-fixes).
rem Close the model window first: a running engine cannot be replaced. The model files are not touched.
rem Options are passed on to UPDATE.bat (and from there to setup.py).
setlocal
title Strata-HotRod - update
cd /d "%~dp0"
rem All of it in one block: cmd reads a .bat file while it runs it, and the git pull can change this very file.
(
  if exist ".git" (
    echo  Updating from:
    git remote get-url origin
    echo.
  )
  call "%~dp0UPDATE.bat" %*
  if errorlevel 1 (
    echo.
    echo  The update did not finish ^(the reason is above^): the variables were not touched.
    pause
    exit /b 1
  )
  echo.
  echo  The speed-fix variables:
  if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "%~dp0tools\speed_decline\apply_env.py"
  ) else (
    echo  No .venv here yet: install first ^(docs\SPEED_FIXES_SETUP.md, section 0^).
  )
  echo.
  echo  How to check that the fixes work: docs\SPEED_FIXES_SETUP.md, section 4.
  pause
  exit /b
)
