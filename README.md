# 8ti

Self-hosted search for public U.S. federal court and GovInfo filings.

8ti reads the court and GovInfo feeds in this repository, stores each new filing in [Typesense](https://typesense.org), and serves search on your own machine. Nothing in this repository is a hosted CASER product, and the software does not give legal advice.

## What you get

- A local Typesense collection named `rss_entries`
- A Python scanner for U.S. Courts RSS feeds and GovInfo pages
- Optional HTTPS in front of Typesense, using Caddy and a domain you control
- Optional phone alerts when a saved keyword matches a new filing

Search stays on your server. The admin key never belongs in a URL, a screenshot, or this git history.

## Requirements

- Docker, with Compose v2
- Python 3.11 or newer
- A domain and a Cloudflare API token, only if you turn on HTTPS

## Install

```bash
git clone https://github.com/caser-legal/8ti.git
cd 8ti
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config/.env.example config/.env.local
```

Open `config/.env.local` and replace every placeholder. Use a long random value for `TYPESENSE_ADMIN_KEY` and the same value for `TS_ADMIN_KEY`. Leave `CLOUDFLARE_API_TOKEN` blank until you serve a public hostname.

`config/.env.local` is gitignored. Do not commit it.

## Start search

```bash
docker compose up -d
```

Typesense listens on `127.0.0.1:8108` only. Check it:

```bash
curl -s http://127.0.0.1:8108/health
```

A healthy server answers `{"ok":true}`.

## Scan filings

```bash
source .venv/bin/activate
set -a && source config/.env.local && set +a
python src/rss_scanner.py
```

The first run takes a while. Later runs skip filings already stored in `data/seen_ids.txt`. Logs go to `logs/`.

Court feed lists:

- `config/uscourts-filtered-feed.json`
- `config/govinfo-filtered-feed.json`
- `config/govinfo-nonfiltered-feed.txt`

## Search

Create a search-only key with `scripts/admin/generate_search_key.py` after Typesense is up. Call search with that key, not the admin key:

```bash
curl -s "http://127.0.0.1:8108/collections/rss_entries/documents/search" \
  -H "X-TYPESENSE-API-KEY: $SEARCH_ONLY_KEY" \
  --data-urlencode "q=contract" \
  --data-urlencode "query_by=title,description"
```

## HTTPS

Set `SEARCH_DOMAIN` to a hostname that points at this machine, and set `CLOUDFLARE_API_TOKEN` in `config/.env.local`. Caddy reads both from the environment. The site template is `Caddyfile`.

```bash
export SEARCH_DOMAIN=search.example.com
docker compose up -d --build
```

Port 8108 stays on localhost. Public traffic uses ports 80 and 443.

## Phone alerts

The `push-notis/` folder is a separate Node process. It needs a Firebase service account that you create in your own Firebase project.

```bash
cd push-notis
cp env.example .env
npm install
```

Put the service-account JSON outside git and point `SERVICE_ACCOUNT_PATH` at that file. `push-notis/.env` is gitignored.

## Scripts

| Script | Purpose |
| --- | --- |
| `scripts/run-scheduled-scan.sh` | One scan, suitable for cron |
| `scripts/health-check.sh` | Check that Typesense answers |
| `scripts/backup-typesense.sh` | Snapshot the search index |
| `scripts/status-check.sh` | Document count and last scan |
| `scripts/admin/` | Create and delete Typesense API keys |

Windows helpers live in `scripts/windows/`. They assume the repo is cloned at `/opt/8ti` inside WSL. Change that path if you clone somewhere else. The systemd unit `push-notis/caser-monitor.service` uses the same `/opt/8ti` path.

## Keep secrets out of git

`.gitignore` already blocks `.env`, `config/.env.local`, key files, Firebase JSON, `data/`, and logs. If a key is ever pasted into a file that gets committed, treat that key as public: rotate it in Typesense, Cloudflare, or Firebase, then remove it from the file before the next push.

## License

MIT. See [LICENSE](LICENSE).
