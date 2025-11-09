#!/bin/bash
set -euo pipefail

echo "🚀 CASER Search Deployment Script"
echo "=================================="

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

# Check if running on supported OS
if [[ ! -f /etc/os-release ]]; then
  echo "❌ Unsupported OS - requires Linux with systemd"
  exit 1
fi

# Install system dependencies
echo "📦 Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip docker.io docker-compose jq curl

# Setup Python virtual environment
echo "🐍 Setting up Python environment..."
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Verify config exists
if [[ ! -f config/.env.local ]]; then
  echo "⚠️ config/.env.local not found - copying from example"
  cp config/.env.example config/.env.local
  echo "❌ Please edit config/.env.local with your credentials before continuing"
  exit 1
fi

# Setup Docker
echo "🐳 Configuring Docker..."
sudo usermod -aG docker "$USER" || true
sudo systemctl enable docker
sudo systemctl start docker

# Create data directories
echo "📁 Creating data directories..."
mkdir -p data logs backups

# Setup systemd services
echo "⚙️ Configuring systemd services..."
if [[ -f scripts/admin/setup-cron.sh ]]; then
  bash scripts/admin/setup-cron.sh
else
  echo "⚠️ setup-cron.sh not found - skipping systemd setup"
fi

# Enable user linger for background services
echo "🔄 Enabling user linger..."
sudo loginctl enable-linger "$USER"

# Start Docker services
echo "🚀 Starting Docker services..."
docker compose --env-file config/.env.local up -d

# Wait for Typesense to be ready
echo "⏳ Waiting for Typesense to be ready..."
for i in {1..30}; do
  if curl -s http://localhost:8108/health > /dev/null 2>&1; then
    echo "✅ Typesense is ready"
    break
  fi
  if [[ $i -eq 30 ]]; then
    echo "❌ Typesense failed to start"
    exit 1
  fi
  sleep 2
done

# Enable and start systemd timers
echo "⏰ Starting systemd timers..."
systemctl --user daemon-reload
systemctl --user enable --now caser-scan@0.timer caser-scan@1.timer
systemctl --user enable --now caser-monitor.timer caser-backup.timer

# Verify services are running
echo ""
echo "✅ Deployment complete!"
echo ""
echo "📊 Service Status:"
systemctl --user list-timers | grep caser || echo "⚠️ No timers found"
echo ""
echo "🐳 Docker Status:"
docker compose ps
echo ""
echo "📝 Next steps:"
echo "  1. Verify config/.env.local has correct credentials"
echo "  2. Check logs: tail -f logs/feed-scan.log"
echo "  3. Monitor: systemctl --user status caser-scan@0.service"
