Param(
    [string]$WslDistro = "Ubuntu-24.04"
)

function Ensure-PortProxy {
    param(
        [int]$Port,
        [string]$TargetIp
    )

    netsh interface portproxy delete v4tov4 listenport=$Port listenaddress=0.0.0.0 | Out-Null
    $result = netsh interface portproxy add v4tov4 listenport=$Port listenaddress=0.0.0.0 connectport=$Port connectaddress=$TargetIp
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to add portproxy for port $Port. netsh output: $result"
    }
}

function Ensure-FirewallRule {
    param(
        [string]$RuleName,
        [int]$Port
    )

    netsh advfirewall firewall delete rule name="$RuleName" | Out-Null
    netsh advfirewall firewall add rule name="$RuleName" dir=in action=allow protocol=TCP localport=$Port | Out-Null
}

try {
    $wslIpRaw = wsl.exe -d $WslDistro -- hostname -I
    $wslIp = $wslIpRaw.Trim().Split(" ",[System.StringSplitOptions]::RemoveEmptyEntries)[0]

    if (-not $wslIp) {
        throw "Unable to determine WSL IP. Raw output: '$wslIpRaw'"
    }

    Ensure-PortProxy -Port 80 -TargetIp $wslIp
    Ensure-PortProxy -Port 443 -TargetIp $wslIp

    Ensure-FirewallRule -RuleName "CASER WSL HTTP" -Port 80
    Ensure-FirewallRule -RuleName "CASER WSL HTTPS" -Port 443

    Write-Output "Portproxy rules now forward 80/443 to $wslIp"
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
