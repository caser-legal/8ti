Param(
    [string]$WslDistro = "Ubuntu-24.04",
    [string]$UserName = $env:USERNAME
)

$portProxyScript = "C:\caser\update-portproxy.ps1"

if (-not (Test-Path $portProxyScript)) {
    throw "Unable to locate portproxy script at $portProxyScript. Make sure the WSL distro is running."
}

$portProxyAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$portProxyScript`""
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn
$startupTrigger = New-ScheduledTaskTrigger -AtStartup

Register-ScheduledTask `
    -TaskName "CASER PortProxy Refresh" `
    -Description "Refresh WSL portproxy rules for CASER Search" `
    -Action $portProxyAction `
    -Trigger @($logonTrigger, $startupTrigger) `
    -RunLevel Highest `
    -User $UserName `
    -Force | Out-Null

$scanCommand = "wsl.exe -d $WslDistro -- bash -lc '/opt/8ti/scripts/run-scheduled-scan.sh'"
$scanAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command `"$scanCommand`""
try {
    $scanStart = (Get-Date).AddMinutes(1)
    $scanTrigger = New-ScheduledTaskTrigger -Once -At $scanStart -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration (New-TimeSpan -Days 30)

    Register-ScheduledTask `
        -TaskName "CASER RSS Sync" `
        -Description "Kick off CASER RSS sync every 10 minutes via WSL" `
        -Action $scanAction `
        -Trigger $scanTrigger `
        -RunLevel Highest `
        -User $UserName `
        -Force | Out-Null
}
catch {
    Write-Warning "Falling back to schtasks.exe for CASER RSS Sync: $($_.Exception.Message)"
    $schtasksCommand = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command `"wsl.exe -d $WslDistro -- bash -lc '/opt/8ti/scripts/run-scheduled-scan.sh'`""
    schtasks.exe /Delete /TN "CASER RSS Sync" /F 2>$null | Out-Null
    schtasks.exe /Create /TN "CASER RSS Sync" /SC MINUTE /MO 10 /TR $schtasksCommand /RL HIGHEST /RU $UserName /F | Out-Null
}
Write-Output "Scheduled tasks configured: CASER PortProxy Refresh, CASER RSS Sync."
