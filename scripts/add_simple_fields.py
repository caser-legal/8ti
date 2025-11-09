#!/usr/bin/env python3
import os, sys, requests, json
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
for env_name in (".env.local", ".env"):
    env_path = ROOT / "config" / env_name
    if env_path.exists():
        load_dotenv(dotenv_path=str(env_path), override=False)

HOST = os.getenv("TYPESENSE_HOST", "http://localhost:8108")
ADMIN = os.getenv("TYPESENSE_ADMIN_KEY") or os.getenv("TS_ADMIN_KEY")
COLL = "rss_entries"

resp = requests.get(f"{HOST}/collections/{COLL}", headers={"X-TYPESENSE-API-KEY": ADMIN})
current = resp.json()

# Only add string and string[] fields (no object[] for now)
new_fields = [
    {"name": "govinfoZipUrl", "type": "string", "optional": True},
    {"name": "govinfoPdfUrl", "type": "string", "optional": True},
    {"name": "govinfoModsUrl", "type": "string", "optional": True},
    {"name": "govinfoPremisUrl", "type": "string", "optional": True},
    {"name": "govinfoHtmlUrl", "type": "string", "optional": True},
    {"name": "govinfoSummaryXmlUrl", "type": "string", "optional": True},
    {"name": "govinfoSummary", "type": "string", "optional": True},
    {"name": "govinfoContextHtml", "type": "string", "optional": True},
    {"name": "govinfoCitation", "type": "string", "optional": True},
    {"name": "modsTitle", "type": "string", "optional": True},
    {"name": "modsParties", "type": "string[]", "optional": True},
    {"name": "modsCaseNumber", "type": "string", "optional": True},
    {"name": "modsSubjects", "type": "string[]", "optional": True},
    {"name": "modsPdfUrls", "type": "string[]", "optional": True},
    {"name": "modsCourtType", "type": "string", "optional": True},
    {"name": "modsCourtState", "type": "string", "optional": True},
    {"name": "premisObjectId", "type": "string", "optional": True},
    {"name": "zipPrimaryPdfPath", "type": "string", "optional": True},
    {"name": "category", "type": "string[]", "optional": True},
    {"name": "creator", "type": "string", "optional": True},
    {"name": "source", "type": "string", "optional": True, "facet": True},
]

existing_names = {f["name"] for f in current["fields"]}
fields_to_add = [f for f in new_fields if f["name"] not in existing_names]

if not fields_to_add:
    print("✅ All fields already exist")
    sys.exit(0)

print(f"Current fields: {sorted(existing_names)}")
print(f"Adding: {[f['name'] for f in fields_to_add]}")

# Don't send existing fields again
updated_schema = {"fields": fields_to_add}

resp = requests.patch(
    f"{HOST}/collections/{COLL}",
    headers={"X-TYPESENSE-API-KEY": ADMIN, "Content-Type": "application/json"},
    json=updated_schema
)

if resp.status_code == 200:
    print(f"✅ Added {len(fields_to_add)} fields:")
    for f in fields_to_add:
        print(f"   - {f['name']}")
else:
    print(f"❌ Failed: {resp.text}")
    sys.exit(1)
