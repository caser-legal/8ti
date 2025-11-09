# Auto-Update WSL2 Port Forwarding on Boot

## Quick Setup

1. **Copy script to Windows:**
   ```bash
   # From WSL, copy to Windows user directory
   cp /home/sm/caser-search/scripts/windows/update-wsl-portforward.ps1 /mnt/c/Users/$USER/
   ```

2. **Run once manually to test:**
   - Open PowerShell as Administrator
   - Run:
     ```powershell
     cd C:\Users\$env:USERNAME
     .\update-wsl-portforward.ps1
     ```

3. **Set up auto-run on boot:**
   - Open PowerShell as Administrator
   - Run:
     ```powershell
     # Update the path in the XML if needed
     $scriptPath = "C:\Users\$env:USERNAME\update-wsl-portforward.ps1"
     
     # Create scheduled task
     $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$scriptPath`""
     $trigger = New-ScheduledTaskTrigger -AtStartup
     $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
     $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
     
     Register-ScheduledTask -TaskName "WSL2-PortForward" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Auto-update WSL2 port forwarding for CASER Search"
     ```

4. **Verify:**
   ```powershell
   Get-ScheduledTask -TaskName "WSL2-PortForward"
   ```

## Manual Update

If you need to update port forwarding manually:

```powershell
# Run as Administrator
cd C:\Users\$env:USERNAME
.\update-wsl-portforward.ps1
```

## Troubleshooting

- **Script not found:** Make sure you copied it to `C:\Users\YourUsername\`
- **Access denied:** Run PowerShell as Administrator
- **Task not running:** Check Task Scheduler → Task Scheduler Library → find "WSL2-PortForward"
- **Still can't connect:** Check Windows Firewall allows ports 80/443

## What it does

1. Gets current WSL2 IP address
2. Removes old port forwarding rules
3. Creates new rules forwarding ports 80/443 to WSL2
4. Adds Windows Firewall exceptions
5. Runs automatically 30 seconds after Windows boots
