#!/bin/bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="$REPO_DIR/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="$BACKUP_DIR/typesense_$TIMESTAMP"
ENV_LOCAL="$REPO_DIR/config/.env.local"
ENV_FALLBACK="$REPO_DIR/config/.env"

if [[ -f "$ENV_LOCAL" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_LOCAL"
elif [[ -f "$ENV_FALLBACK" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FALLBACK"
fi

API_KEY="${TYPESENSE_ADMIN_KEY:-${TS_ADMIN_KEY:-}}"
if [[ -z "$API_KEY" ]]; then
  echo "TYPESENSE_ADMIN_KEY or TS_ADMIN_KEY must be set in config/.env.local" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

# Create Typesense snapshot
SNAPSHOT_RESPONSE=$(curl -s -X POST \
  -H "X-TYPESENSE-API-KEY: $API_KEY" \
  "http://localhost:8108/operations/snapshot?snapshot_path=$BACKUP_PATH")

# Verify snapshot succeeded
if ! echo "$SNAPSHOT_RESPONSE" | grep -q '"success":true'; then
  echo "❌ Typesense snapshot creation failed!" >&2
  if command -v jq >/dev/null 2>&1; then
    printf '%s\n' "$SNAPSHOT_RESPONSE" | jq
  else
    printf '%s\n' "$SNAPSHOT_RESPONSE"
  fi
  
  # Send alert webhook if configured
  if [[ -n "${ALERT_WEBHOOK_URL:-}" ]]; then
    curl -X POST "$ALERT_WEBHOOK_URL" \
      -H "Content-Type: application/json" \
      -d "{\"text\":\"❌ Backup failed on caser-search at $(date '+%Y-%m-%d %H:%M:%S %Z')\"}" \
      --silent --show-error --max-time 10 || true
  fi
  
  exit 1
fi

# Pretty-print success response
if command -v jq >/dev/null 2>&1; then
  printf '%s\n' "$SNAPSHOT_RESPONSE" | jq
else
  printf '%s\n' "$SNAPSHOT_RESPONSE"
fi

# Encrypt snapshot if encryption key is set
if [[ -n "${BACKUP_ENCRYPTION_KEY:-}" ]]; then
  echo "🔒 Encrypting backup..."
  tar czf - "$BACKUP_PATH" | \
    openssl enc -aes-256-cbc -salt -pbkdf2 \
    -pass pass:"$BACKUP_ENCRYPTION_KEY" \
    -out "$BACKUP_DIR/typesense_$TIMESTAMP.tar.gz.enc"
  
  # Remove unencrypted snapshot after successful encryption
  if [[ -f "$BACKUP_DIR/typesense_$TIMESTAMP.tar.gz.enc" ]]; then
    rm -rf "$BACKUP_PATH"
    echo "✅ Encrypted backup: typesense_$TIMESTAMP.tar.gz.enc"
  fi
else
  echo "⚠️ BACKUP_ENCRYPTION_KEY not set - backup stored unencrypted"
fi

# Backup seen_ids
cp "$REPO_DIR/data/seen_ids.txt" "$BACKUP_DIR/seen_ids_$TIMESTAMP.txt"
if [[ -f "$REPO_DIR/data/seen_ids.sqlite3" ]]; then
  cp "$REPO_DIR/data/seen_ids.sqlite3" "$BACKUP_DIR/seen_ids_$TIMESTAMP.sqlite3"
fi

# Keep only last 7 days of backups
find "$BACKUP_DIR" -name "typesense_*" -mtime +7 -exec rm -rf {} \;
find "$BACKUP_DIR" -name "*.tar.gz.enc" -mtime +7 -delete
find "$BACKUP_DIR" -name "seen_ids_*.txt" -mtime +7 -delete
find "$BACKUP_DIR" -name "seen_ids_*.sqlite3" -mtime +7 -delete

echo "Backup completed: $BACKUP_PATH"
