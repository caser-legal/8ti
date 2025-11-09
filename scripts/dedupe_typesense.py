#!/usr/bin/env python3
from __future__ import annotations

"""Deduplicate the rss_entries collection in Typesense."""

import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

for env_name in (".env.local", ".env"):
    env_path = ROOT / "config" / env_name
    if env_path.exists():
        load_dotenv(env_path, override=False)

HOST = os.getenv("TYPESENSE_HOST", "http://localhost:8108")
ADMIN = os.getenv("TYPESENSE_ADMIN_KEY") or os.getenv("TS_ADMIN_KEY")
COLLECTION = os.getenv("COLLECTION", "rss_entries")

if not ADMIN:
    print("TYPESENSE_ADMIN_KEY or TS_ADMIN_KEY must be set.", file=sys.stderr)
    sys.exit(1)

HEADERS = {"X-TYPESENSE-API-KEY": ADMIN}


def fetch_schema() -> Dict[str, object]:
    resp = requests.get(f"{HOST}/collections/{COLLECTION}", headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return {
        "name": data["name"],
        "fields": data["fields"],
        "default_sorting_field": data.get("default_sorting_field"),
        "enable_nested_fields": data.get("enable_nested_fields", False),
    }


def export_documents() -> Dict[str, Dict[str, object]]:
    print("↻ Exporting current documents...")
    resp = requests.get(
        f"{HOST}/collections/{COLLECTION}/documents/export",
        headers=HEADERS,
        stream=True,
        timeout=300,
    )
    resp.raise_for_status()

    best: Dict[str, Dict[str, object]] = {}
    duplicate_counts = defaultdict(int)
    total = 0
    for chunk in resp.iter_lines():
        if not chunk:
            continue
        doc = json.loads(chunk)
        doc_id = doc.get("objectID") or doc.get("id")
        if not doc_id:
            continue
        total += 1
        doc["objectID"] = doc_id
        doc["id"] = doc_id
        current = best.get(doc_id)
        if current is None or doc.get("indexedAt", 0) >= current.get("indexedAt", 0):
            best[doc_id] = doc
        if current is not None:
            duplicate_counts[doc_id] += 1
    print(f"   • Exported {total:,} records ({len(best):,} unique objectIDs)")
    dup_total = sum(duplicate_counts.values())
    if dup_total:
        print(f"   • Found {len(duplicate_counts):,} duplicate clusters ({dup_total:,} stale docs)")
    else:
        print("   • No duplicates found")
    return best


def drop_collection() -> None:
    print("🗑️  Dropping existing collection...")
    resp = requests.delete(f"{HOST}/collections/{COLLECTION}", headers=HEADERS, timeout=30)
    resp.raise_for_status()


def recreate_collection(schema: Dict[str, object]) -> None:
    payload = {
        "name": schema["name"],
        "fields": schema["fields"],
        "default_sorting_field": schema.get("default_sorting_field"),
    }
    if schema.get("enable_nested_fields"):
        payload["enable_nested_fields"] = True

    print("🆕 Recreating collection schema...")
    resp = requests.post(
        f"{HOST}/collections",
        headers={**HEADERS, "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()


def chunked(seq: List[Dict[str, object]], size: int):
    for idx in range(0, len(seq), size):
        yield seq[idx : idx + size]


def ensure_import_success(expected: int, payload: str) -> None:
    successes = 0
    failures: List[Dict[str, object]] = []
    for line in payload.strip().splitlines():
        if not line:
            continue
        try:
            result = json.loads(line)
        except json.JSONDecodeError:
            failures.append({"success": False, "error": "invalid_json", "raw": line})
            continue
        if result.get("success"):
            successes += 1
        else:
            failures.append(result)
    if failures:
        sample = failures[:3]
        raise RuntimeError(f"Typesense import failures detected ({len(failures)} rows). Sample: {sample}")
    if successes != expected:
        raise RuntimeError(f"Typesense import mismatch (expected {expected}, got {successes})")


def import_documents(docs: List[Dict[str, object]]) -> None:
    print(f"⬆️  Importing {len(docs):,} deduplicated documents...")
    for index, batch in enumerate(chunked(docs, 500), start=1):
        ndjson = "\n".join(json.dumps(doc, ensure_ascii=False) for doc in batch)
        resp = requests.post(
            f"{HOST}/collections/{COLLECTION}/documents/import?action=upsert&batch_size=500",
            headers={**HEADERS, "Content-Type": "text/plain"},
            data=ndjson.encode("utf-8"),
            timeout=120,
        )
        resp.raise_for_status()
        ensure_import_success(len(batch), resp.text)
        if index % 10 == 0:
            imported = min(index * 500, len(docs))
            print(f"   • Imported {imported:,}/{len(docs):,} docs")


def main() -> None:
    schema = fetch_schema()
    current = export_documents()
    docs = sorted(current.values(), key=lambda d: d.get("indexedAt", 0))

    drop_collection()
    recreate_collection(schema)
    import_documents(docs)

    print("✅ Deduplication complete")


if __name__ == "__main__":
    main()
