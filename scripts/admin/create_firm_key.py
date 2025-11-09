import requests, os, sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
for env_name in (".env.local", ".env"):
    env_path = ROOT / "config" / env_name
    if env_path.exists():
        load_dotenv(dotenv_path=str(env_path), override=False)

if len(sys.argv) < 2:
    print("Usage: python create_firm_key.py 'Firm Name'")
    sys.exit(1)

firm_name = sys.argv[1]
admin_key = os.getenv('TYPESENSE_ADMIN_KEY') or os.getenv('TS_ADMIN_KEY')
host = os.getenv('TYPESENSE_HOST', 'http://localhost:8108')

if not admin_key:
    print("Error: TYPESENSE_ADMIN_KEY is not set.")
    sys.exit(1)

response = requests.post(
    f'{host}/keys',
    headers={'X-TYPESENSE-API-KEY': admin_key},
    json={
        'description': f'Search key for {firm_name}',
        'actions': ['documents:search'],
        'collections': ['rss_entries']
    }
)

if response.status_code == 201:
    key_data = response.json()
    print(f"\n✓ Created key for: {firm_name}")
    print(f"Key ID: {key_data['id']}")
    print(f"Key Value: {key_data['value']}")
    print(f"\nGive this key to {firm_name} - they can ONLY search, nothing else.\n")
else:
    print(f"Error: {response.text}")
