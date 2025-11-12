# Auto-update WSL2 port forwarding on boot
# Run as Administrator

$wslIP = (wsl hostname -I).Trim()

Write-Host "WSL2 IP: $wslIP"

# Remove old port forwarding rules
netsh interface portproxy delete v4tov4 listenport=80 listenaddress=0.0.0.0
netsh interface portproxy delete v4tov4 listenport=443 listenaddress=0.0.0.0

# Add new rules with current WSL2 IP
netsh interface portproxy add v4tov4 listenport=80 listenaddress=0.0.0.0 connectport=80 connectaddress=$wslIP
netsh interface portproxy add v4tov4 listenport=443 listenaddress=0.0.0.0 connectport=443 connectaddress=$wslIP

Write-Host "Port forwarding updated:"
netsh interface portproxy show all

# Allow through Windows Firewall
netsh advfirewall firewall add rule name="WSL2 HTTP" dir=in action=allow protocol=TCP localport=80
netsh advfirewall firewall add rule name="WSL2 HTTPS" dir=in action=allow protocol=TCP localport=443

Write-Host "Done! Ports 80 and 443 now forward to WSL2 at $wslIP"
