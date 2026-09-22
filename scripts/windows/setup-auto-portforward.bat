@echo off
echo Setting up auto port forwarding on boot...

set SCRIPT_PATH=%USERPROFILE%\update-wsl-portforward.ps1

powershell -Command "& {$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-ExecutionPolicy Bypass -File \"%SCRIPT_PATH%\"'; $trigger = New-ScheduledTaskTrigger -AtStartup; $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -RunLevel Highest; $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries; Register-ScheduledTask -TaskName 'WSL2-PortForward' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force}"

echo Done! Task scheduled to run on boot.
pause
