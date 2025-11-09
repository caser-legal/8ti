#!/usr/bin/env python3
"""Manual scan - bypasses business hours check"""
import sys, os, requests
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Load env
for env_name in (".env.local", ".env"):
    env_path = ROOT / "config" / env_name
    if env_path.exists():
        load_dotenv(env_path, override=False)

HOST = os.getenv('TYPESENSE_HOST', 'http://localhost:8108')
ADMIN = os.getenv('TYPESENSE_ADMIN_KEY') or os.getenv('TS_ADMIN_KEY')

# Get starting count
try:
    resp = requests.get(f'{HOST}/collections/rss_entries', headers={'X-TYPESENSE-API-KEY': ADMIN})
    start_count = resp.json().get('num_documents', 0)
    print(f"📊 Starting documents: {start_count:,}")
except:
    start_count = 0

# Monkey-patch business hours check before importing
import rss_scanner
rss_scanner.is_business_hours = lambda: True

# Run scan
print("🚀 Starting manual scan (business hours check disabled)...")
print()
rss_scanner.run_once(limit=None)
print()

# Get ending count
try:
    resp = requests.get(f'{HOST}/collections/rss_entries', headers={'X-TYPESENSE-API-KEY': ADMIN})
    end_count = resp.json().get('num_documents', 0)
    print(f"📊 Ending documents: {end_count:,}")
    print(f"📈 Change: +{end_count - start_count:,}")
except:
    pass

print("✅ Scan complete")
