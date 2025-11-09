import requests, os, sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
for env_name in (".env.local", ".env"):
    env_path = ROOT / "config" / env_name
    if env_path.exists():
        load_dotenv(dotenv_path=str(env_path), override=False)

admin_key = os.getenv('TYPESENSE_ADMIN_KEY') or os.getenv('TS_ADMIN_KEY')
host = os.getenv('TYPESENSE_HOST', 'http://localhost:8108')

if not admin_key:
    print("Error: TYPESENSE_ADMIN_KEY is not set.")
    sys.exit(1)

response = requests.get(f'{host}/keys', headers={'X-TYPESENSE-API-KEY': admin_key})

if response.status_code == 200:
    keys = response.json().get('keys', [])
    print(f"\nTotal keys: {len(keys)}\n")
    for key in keys:
        print(f"ID: {key.get('id', 'N/A')}")
        print(f"Description: {key.get('description', '(no description)')}")
        value = key.get('value')
        preview = (value[:20] + '...') if isinstance(value, str) and value else '(hidden)'
        print(f"Value: {preview}")
        print(f"Created: {key.get('created_at', 'N/A')}")
        print("-" * 50)
else:
    print(f"Error: {response.text}")
