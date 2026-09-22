#!/bin/bash
# CASER Search - Auto-start on WSL boot

cd "$(dirname "$0")/.."

# Start Docker containers
docker compose up -d

# Wait for services to be ready
sleep 5

# Check status
docker ps | grep caser-search

echo "✅ CASER Search started"
echo "WSL IP: $(hostname -I | awk '{print $1}')"
echo ""
echo "⚠️  IMPORTANT: Windows port forwarding must be updated!"
echo "Run this in PowerShell as Administrator:"
echo ""
echo "powershell.exe -ExecutionPolicy Bypass -File C:\\Users\\%USERNAME%\\update-wsl-portforward.ps1"
