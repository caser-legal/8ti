#!/bin/bash
set -e
# Resolve repo root relative to this script for portability
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"
source "$REPO_ROOT/.venv/bin/activate"
python "$REPO_ROOT/scripts/manual_scan.py"
