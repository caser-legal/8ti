import requests
from pathlib import Path
from dotenv import load_dotenv
import os

ROOT = Path(__file__).resolve().parent.parent.parent
for env_name in (".env.local", ".env"):
    env_path = ROOT / "config" / env_name
    if env_path.exists():
        load_dotenv(dotenv_path=str(env_path), override=False)

ADMIN_KEY = os.getenv("TYPESENSE_ADMIN_KEY") or os.getenv("TS_ADMIN_KEY")
HOST = os.getenv("TYPESENSE_HOST", "http://localhost:8108")

if not ADMIN_KEY:
    raise RuntimeError("TYPESENSE_ADMIN_KEY is not set.")

response = requests.post(
    f"{HOST}/keys",
    headers={"X-TYPESENSE-API-KEY": ADMIN_KEY},
    json={
        "description": "Search-only key",
        "actions": ["documents:search"],
        "collections": ["rss_entries"]
    }
)

print(response.json())
