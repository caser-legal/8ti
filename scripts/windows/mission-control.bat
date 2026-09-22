@echo off
REM Launch the CASER Search mission control dashboard from Windows.
REM Double-click this file or create a shortcut to it.

set "DISTRO=Ubuntu-24.04"
set "WORKDIR=/opt/8ti"
set "SCRIPT=.venv/bin/python scripts/mission_control.py"

REM Resize the console (width 118, height 45). 118 matches the dashboard width (116) + padding.
powershell -NoProfile -Command ^
  "$host.UI.RawUI.WindowSize = New-Object Management.Automation.Host.Size(118,45);"

echo Starting CASER Search dashboard...
echo.
wsl.exe -d %DISTRO% -- bash -lc "cd %WORKDIR% && %SCRIPT%"

echo.
echo Dashboard exited. Press any key to close this window.
pause >nul
