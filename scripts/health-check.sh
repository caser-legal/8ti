#!/bin/bash
set -euo pipefail

# Health check script for CASER Search
# Run via cron every 5 minutes to monitor Typesense availability

REPO_DIR="/home/sm/caser-search"
ENV_LOCAL="$REPO_DIR/config/.env.local"
ENV_FALLBACK="$REPO_DIR/config/.env"
STATE_FILE="$REPO_DIR/data/.health-check-state"

# Load environment
if [[ -f "$ENV_LOCAL" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_LOCAL"
elif [[ -f "$ENV_FALLBACK" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FALLBACK"
fi

# Check Typesense health
if curl -s --max-time 5 http://localhost:8108/health > /dev/null 2>&1; then
  # Typesense is healthy
  if [[ -f "$STATE_FILE" ]]; then
    # Was down, now recovered
    if [[ -n "${ALERT_WEBHOOK_URL:-}" ]]; then
      curl -X POST "$ALERT_WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -d "{\"text\":\"✅ Typesense recovered on caser-search at $(date '+%Y-%m-%d %H:%M:%S %Z')\"}" \
        --silent --show-error --max-time 10 || true
    fi
    rm -f "$STATE_FILE"
  fi
  exit 0
else
  # Typesense is down
  if [[ ! -f "$STATE_FILE" ]]; then
    # First detection of downtime
    echo "$(date +%s)" > "$STATE_FILE"
    
    # Send alert
    if [[ -n "${ALERT_WEBHOOK_URL:-}" ]]; then
      curl -X POST "$ALERT_WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -d "{\"text\":\"🔴 Typesense is down on caser-search at $(date '+%Y-%m-%d %H:%M:%S %Z')\"}" \
        --silent --show-error --max-time 10 || true
    fi
  fi
  exit 1
fi
