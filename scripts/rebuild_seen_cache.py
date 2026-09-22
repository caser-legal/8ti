#!/usr/bin/env python3
from __future__ import annotations

"""Rebuild data/seen_ids.txt from the current Typesense collection."""

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.seen_ids_store import SeenIdStore  # noqa: E402

for env_name in (".env.local", ".env"):
    env_path = ROOT / "config" / env_name
    if env_path.exists():
        load_dotenv(env_path, override=False)

HOST = os.getenv("TYPESENSE_HOST", "http://localhost:8108")
ADMIN = os.getenv("TYPESENSE_ADMIN_KEY") or os.getenv("TS_ADMIN_KEY")
COLLECTION = os.getenv("COLLECTION", "rss_entries")
TARGET = ROOT / "data" / "seen_ids.txt"
DB_PATH = ROOT / "data" / "seen_ids.sqlite3"

if not ADMIN:
    print("TYPESENSE_ADMIN_KEY or TS_ADMIN_KEY must be set.", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    url = f"{HOST}/collections/{COLLECTION}/documents/export"
    headers = {"X-TYPESENSE-API-KEY": ADMIN}
    resp = requests.get(url, headers=headers, stream=True, timeout=120)
    resp.raise_for_status()

    ids: list[str] = []
    seen: set[str] = set()
    for chunk in resp.iter_lines():
        if not chunk:
            continue
        record = json.loads(chunk)
        doc_id = record.get("objectID") or record.get("id")
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        ids.append(doc_id)

    store = SeenIdStore(DB_PATH, TARGET)
    store.replace_with(ids)
    store.write_mirror_file()
    store.close()
    print(f"Wrote {len(ids):,} IDs to {TARGET.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
