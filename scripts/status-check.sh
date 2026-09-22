#!/usr/bin/env bash
set -euo pipefail

cd "$HOME/caser-search" || exit 1

echo "=== CASER Search System Status ==="
docker ps --format "{{.Names}}: {{.Status}}" | grep caser-search || true

echo -n "Typesense: "
curl -s http://localhost:8108/health || echo "DOWN"

ADMIN_KEY=$(grep -E '^TYPESENSE_ADMIN_KEY=' config/.env.local | head -n1 | cut -d'=' -f2-)
if command -v jq >/dev/null 2>&1; then
  doc_count=$(curl -s "http://localhost:8108/collections/rss_entries" \
    -H "X-TYPESENSE-API-KEY: $ADMIN_KEY" | jq -r '.num_documents // "ERROR"')
else
  # Fallback to Python for JSON parsing if jq is unavailable
  doc_count=$(python - <<'PY'
import json, sys
print(json.load(sys.stdin).get('num_documents','ERROR'))
PY
    < <(curl -s "http://localhost:8108/collections/rss_entries" -H "X-TYPESENSE-API-KEY: $ADMIN_KEY"))
fi
echo "Documents: $doc_count"

last_run=$(tail -1 logs/scan-history.ndjson 2>/dev/null | jq -r '.endedAt // "never"')
status=$(tail -1 logs/scan-history.ndjson 2>/dev/null | jq -r '.status // "unknown"')
echo "Last scan ended: $last_run"
echo "Last scan status: $status"
