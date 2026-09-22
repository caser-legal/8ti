#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

# Load environment variables
if [ -f "$REPO_ROOT/config/.env.local" ]; then
  set -a
  source "$REPO_ROOT/config/.env.local"
  set +a
fi

export SCAN_SHARD_INDEX="${SCAN_SHARD_INDEX:-0}"
export SCAN_SHARD_TOTAL="${SCAN_SHARD_TOTAL:-1}"

source "$REPO_ROOT/.venv/bin/activate"

LOG_DIR="$REPO_ROOT/logs"
LOG_FILE="$LOG_DIR/feed-scan.log"
MAX_BYTES=$((2 * 1024 * 1024 * 1024)) # 2 GB

mkdir -p "$LOG_DIR"

"$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/src/rss_scanner.py" \
  --shard-index "$SCAN_SHARD_INDEX" \
  --shard-count "$SCAN_SHARD_TOTAL" >> "$LOG_FILE" 2>&1

if [[ -f "$LOG_FILE" ]]; then
  CURRENT_SIZE=$(stat -c%s "$LOG_FILE")
  if (( CURRENT_SIZE > MAX_BYTES )); then
    TIMESTAMP=$(date +%Y%m%d%H%M%S)
    ARCHIVE_FILE="$LOG_DIR/feed-scan.$TIMESTAMP.log"
    mv "$LOG_FILE" "$ARCHIVE_FILE"
    : > "$LOG_FILE"
  fi
fi
