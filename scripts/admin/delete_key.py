import requests, os, sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
for env_name in (".env.local", ".env"):
    env_path = ROOT / "config" / env_name
    if env_path.exists():
        load_dotenv(dotenv_path=str(env_path), override=False)

if len(sys.argv) < 2:
    print("Usage: python delete_key.py <key_id>")
    print("Run 'python utils/list_keys.py' to see all key IDs")
    sys.exit(1)

key_id = sys.argv[1]
admin_key = os.getenv('TYPESENSE_ADMIN_KEY') or os.getenv('TS_ADMIN_KEY')
host = os.getenv('TYPESENSE_HOST', 'http://localhost:8108')

if not admin_key:
    print("Error: TYPESENSE_ADMIN_KEY is not set.")
    sys.exit(1)

response = requests.delete(
    f'{host}/keys/{key_id}',
    headers={'X-TYPESENSE-API-KEY': admin_key}
)

if response.status_code == 200:
    print(f"✓ Deleted key: {key_id}")
else:
    print(f"Error: {response.text}")
