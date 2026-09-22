#!/bin/bash
cd "$(dirname "$0")"
if [[ -f config/.env.local ]]; then
  set -a
  # shellcheck disable=SC1091
  source config/.env.local
  set +a
fi
if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
python src/rss_scanner.py
