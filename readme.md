# CASER Search - Self-Hosted Legal Document Search Engine

[![Status](https://img.shields.io/badge/status-operational-brightgreen)]()
[![Documents](https://img.shields.io/badge/documents-48K%2B-blue)]()
[![Feeds](https://img.shields.io/badge/feeds-326-orange)]()
[![Uptime](https://img.shields.io/badge/uptime-24%2F7-success)]()

Production-grade legal search that ingests 300+ federal court RSS feeds, deduplicates filings across shards, and serves an HTTPS Typesense API from a spare Windows PC.

---

## Current Snapshot (November 2025)
- **Documents Indexed:** ~48,000 live filings
- **Feeds Monitored:** 326 (174 uscourts + 152 govinfo, 28 paused)
- **Scanner Cadence:** Every 10 minutes via two systemd shards
- **Monitor Cadence:** Every 5 minutes (Firebase push notifications)
- **Backups:** Daily 03:00 PT Typesense snapshots + seen-id mirror (7-day retention)
- **Public Endpoint:** https://search.caserlegal.com (Cloudflare proxied, SSL via Caddy DNS challenge)

---

## What Runs Here

### Core services
| Component | Location | Purpose |
|-----------|----------|---------|
| **Typesense 29.0** | Docker (`docker-compose.yml`) | Full-text search, stores `rss_entries` collection (~200 MB)
| **Caddy** | Docker + `Dockerfile.caddy` | Terminates TLS (Cloudflare DNS plugin), reverse proxies all HTTP(s) traffic to Typesense, exposes `/health`
| **Python Scanner** | `src/rss_scanner.py` + `scripts/run-scheduled-scan.sh` | Fetches RSS feeds, enriches entries, deduplicates in SQLite, batches upserts into Typesense
| **Govinfo Harvester** | `src/govinfo_harvester.py` | Scrapes MODS/PREMIS metadata, context pages, and best download URLs for govinfo feeds
| **Seen-ID Store** | `data/seen_ids.sqlite3` + mirror `data/seen_ids.txt` | Concurrent-safe duplicate registry with pending→committed workflow and TTL cleanup
| **Firebase Monitor** | `push-notis/monitor.js` + `caser-monitor.timer` | Searches Typesense for saved keywords and sends push notifications through Firebase Admin SDK
| **Backup Job** | `scripts/backup-typesense.sh` + `caser-backup.timer` | Triggers Typesense snapshot, copies seen-id artifacts, prunes to 7 days

### High-level architecture
```
Internet / Mobile App
        │  HTTPS (443)
        ▼
Cloudflare (DNS + WAF + proxy)
        │  Port forward 80/443
        ▼
Windows 11 PC → WSL2 Ubuntu 24.04
        │
        ├─ Docker → Caddy → Typesense (search API)
        │
        └─ Systemd user services (scanner shards, monitor, backup) running from ~/caser-search
```

---

## Scanner Pipeline
1. **Timer trigger** – `caser-scan@{0,1}.timer` calls `scripts/run-scheduled-scan.sh` with `SCAN_SHARD_INDEX/SCAN_SHARD_TOTAL` env vars.
2. **Environment bootstrap** – `.venv` is activated and `config/.env.local` is loaded (preferred over `.env`).
3. **Feed selection** – `config/uscourts-filtered-feed.json` and `config/govinfo-filtered-feed.json` hold curated feed metadata (state, court id, timezone). Shard slicing divides the combined list evenly.
4. **Network fetch** – Each feed is fetched through the Cloudflare Workers proxy (`https://nfq7btef6.j0mpz7gur2.workers.dev`) with fallback to direct requests based on `PROXY_MODE`.
5. **Govinfo enrichment** – Govinfo RSS entries go through `GovinfoHarvester` to pull MODS/PREMIS metadata, parties, case numbers, citations, and the most direct PDF link.
6. **Dedup + locking** – `SeenIdStore` reserves IDs in SQLite (pending rows with run owner). Per-shard file locks (`data/scanner-shard-*.lock`) prevent a shard overlap on restart. Pending rows expire automatically (`SEEN_IDS_PENDING_TTL` seconds) so interrupted runs don’t block future scans.
7. **Batching & upserts** – Entries are accumulated (`BATCH_BUFFER_SIZE`, default 512) and imported via `POST /collections/{coll}/documents/import?action=upsert`. Typesense rejects malformed rows so the scanner logs failures and continues.
8. **State tracking** – `src/scan_tracker.py` writes summaries to `logs/scan_state.json` and appends NDJSON records to `logs/scan-history.ndjson`.
9. **Mirror file** – After every run the committed IDs are mirrored to `data/seen_ids.txt` for quick stats, backups, and human inspection.

Supporting scripts:
- `scripts/scan-now.sh` – ad-hoc scan wrapper for a specific shard (`SCAN_SHARD_INDEX` exported before running).
- `scripts/manual_scan.py` – interactive troubleshooting scan (filters feeds, dry-run options).
- `scripts/dedupe_typesense.py` – rebuilds the collection from `seen_ids.txt` if duplicates ever slip in.
- `scripts/rebuild_seen_cache.py` – repopulates the SQLite store directly from Typesense documents.

---

## Automation & Scheduling
| Service | Timer | Command | Logs |
|---------|-------|---------|------|
| Scanner Shard 0 | `~/.config/systemd/user/caser-scan@0.timer` (10 min, persistent) | `bash scripts/run-scheduled-scan.sh` with `SCAN_SHARD_INDEX=0 SCAN_SHARD_TOTAL=2` | `logs/feed-scan.log`, `logs/scan-history.ndjson`
| Scanner Shard 1 | `caser-scan@1.timer` | Same command, `SCAN_SHARD_INDEX=1` | Same as above
| Firebase Monitor | `caser-monitor.timer` (every 5 min) | `node push-notis/monitor.js` (runs under `push-notis/.env`) | `logs/monitor.log` (inside `push-notis`)
| Typesense Backup | `caser-backup.timer` (daily 03:00 PT) | `bash scripts/backup-typesense.sh` | `backups/` directory + journalctl `--user`

Enable on a fresh host:
```bash
sudo loginctl enable-linger $USER
systemctl --user daemon-reload
systemctl --user enable --now caser-scan@0.timer caser-scan@1.timer \
  caser-monitor.timer caser-backup.timer
systemctl --user list-timers | grep caser
```

---

## Setup (Fresh Windows/WSL Host)
1. **Install WSL & Ubuntu**
   ```powershell
   wsl --install Ubuntu-24.04
   ```
2. **Install Docker Desktop** and enable WSL integration for Ubuntu-24.04.
3. **Clone the repository**
   ```bash
   cd ~
   git clone <repo-url> caser-search
   cd caser-search
   ```
4. **Configure secrets & runtime variables**
   ```bash
   cp config/.env config/.env.local  # or start from scratch
   nano config/.env.local
   ```
   Required keys:
   - `TYPESENSE_ADMIN_KEY` / `TS_ADMIN_KEY` – same 32+ char key shared with the Typesense container.
   - `CLOUDFLARE_API_TOKEN` – scoped DNS token for the Caddy DNS challenge.
   - `PROXY_ENDPOINT` (defaults to the maintained Cloudflare Worker) and `PROXY_MODE` (`proxy-first`, `proxy-only`, `direct-only`).
   - `SCAN_SHARD_INDEX`, `SCAN_SHARD_TOTAL` (overridden by the timers, defaults 0/1 for manual runs).
   - Optional tuning: `BATCH_BUFFER_SIZE`, `TS_IMPORT_BATCH_SIZE`, `SEEN_IDS_MAX`, `SEEN_IDS_PENDING_TTL`.

5. **Python environment**
   ```bash
   sudo apt update && sudo apt install -y python3-venv python3-pip
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   deactivate
   ```
6. **Start Docker services**
   ```bash
   set -a && source config/.env.local && set +a
   docker compose up -d
   docker compose ps
   ```
7. **Initial scan (both shards)**
   ```bash
   source .venv/bin/activate
   export SCAN_SHARD_TOTAL=2
   for shard in 0 1; do
     export SCAN_SHARD_INDEX=$shard
     bash scripts/run-scheduled-scan.sh
   done
   ```
8. **Expose the API externally** (PowerShell as admin)
   ```powershell
   $wslIp = (wsl -d Ubuntu-24.04 -- hostname -I).Split()[0]
   netsh interface portproxy delete v4tov4 listenport=80 listenaddress=0.0.0.0 2>$null
   netsh interface portproxy delete v4tov4 listenport=443 listenaddress=0.0.0.0 2>$null
   netsh interface portproxy add v4tov4 listenport=80 listenaddress=0.0.0.0 connectport=80 connectaddress=$wslIp
   netsh interface portproxy add v4tov4 listenport=443 listenaddress=0.0.0.0 connectport=443 connectaddress=$wslIp
   netsh advfirewall firewall add rule name="caser-80" dir=in action=allow protocol=TCP localport=80
   netsh advfirewall firewall add rule name="caser-443" dir=in action=allow protocol=TCP localport=443
   ```
9. **Firebase monitor secrets** – place the service account JSON at `/home/sm/secrets/firebase-service-account.json` and point `push-notis/.env` (`SERVICE_ACCOUNT_PATH=/home/sm/secrets/firebase-service-account.json`).

---

## Day-to-Day Operations
- **Mission Control dashboard**
  ```bash
  cd ~/caser-search
  source .venv/bin/activate
  python scripts/mission_control.py
  ```
  Shows container health, document counts, shard timers, last scans, and tail of `logs/feed-scan.log`.

- **Manual scan** (single shard)
  ```bash
  cd ~/caser-search
  source .venv/bin/activate
  export SCAN_SHARD_INDEX=0
  export SCAN_SHARD_TOTAL=2
  python src/rss_scanner.py --shard-index $SCAN_SHARD_INDEX --shard-count $SCAN_SHARD_TOTAL
  ```

- **Monitor run (one-off)**
  ```bash
  cd ~/caser-search/push-notis
  cp env.example .env  # adjust to point at /home/sm/secrets/firebase-service-account.json
  npm install  # already vendored, run only if node_modules missing
  SERVICE_ACCOUNT_PATH=/home/sm/secrets/firebase-service-account.json \
  TYPESENSE_API_KEY=$TS_ADMIN_KEY \
  node monitor.js
  ```

- **Check Typesense doc count**
  ```bash
  API_KEY=$(grep -m1 '^TYPESENSE_ADMIN_KEY=' config/.env.local | cut -d'=' -f2)
  curl -s "http://localhost:8108/collections/rss_entries" \
    -H "X-TYPESENSE-API-KEY: $API_KEY" | jq '.num_documents'
  ```

- **Inspect duplicate registry**
  ```bash
  sqlite3 data/seen_ids.sqlite3 'SELECT COUNT(*) FROM seen_ids WHERE status=1;'
  tail data/seen_ids.txt
  ```

- **Watch logs / timers**
  ```bash
  tail -f logs/feed-scan.log
  systemctl --user status caser-scan@0.service caser-scan@1.service
  journalctl --user -u caser-monitor.service -n 100 --since "1 hour ago"
  ```

---

## Backups & Recovery
- **Daily snapshot** – handled by `caser-backup.timer`, output stored in `backups/typesense_YYYYMMDD_HHMMSS`. Each run also exports `seen_ids.txt` and `seen_ids.sqlite3` with matching timestamps; files older than 7 days are purged.
- **Manual backup**
  ```bash
  bash scripts/backup-typesense.sh
  ls backups
  ```
- **Restoring Typesense** (inside repo)
  ```bash
  docker compose down
  SNAP=$(ls -td backups/typesense_* | head -n1)
  docker compose up -d typesense
  docker compose exec typesense bash -lc \
    "typesense-server --restore-from $SNAP --data-dir /data"
  ```
  Afterwards rebuild the duplicate cache if needed:
  ```bash
  source .venv/bin/activate
  python scripts/rebuild_seen_cache.py
  ```
- **Recreate shards after issues** – stop timers, delete any `data/scanner-shard-*.lock` files, restart timers.

---

## Repository Map
```
caser-search/
├── README.md                      # High-level status / marketing copy (leave as-is)
├── readme.md                      # This operational guide
├── SYSTEM_OVERVIEW.md             # Quick reference summary
├── docker-compose.yml             # Typesense + Caddy services
├── Caddyfile / Dockerfile.caddy   # Reverse proxy with Cloudflare DNS challenge
├── config/
│   ├── .env.local (gitignored)    # Runtime secrets
│   ├── uscourts-filtered-feed.json
│   └── govinfo-filtered-feed.json
├── src/
│   ├── rss_scanner.py             # Sharded RSS scanner (Typesense upserts)
│   ├── govinfo_harvester.py       # Rich metadata scraper
│   ├── seen_ids_store.py          # SQLite-backed duplicate registry
│   └── scan_tracker.py            # Persists scan stats/telemetry
├── scripts/
│   ├── run-scheduled-scan.sh      # Systemd entrypoint, log rotation
│   ├── scan-now.sh / manual_scan.py
│   ├── mission_control.py         # CLI dashboard
│   ├── backup-typesense.sh        # Snapshot helper
│   ├── rebuild_seen_cache.py      # Rehydrate duplicate store
│   └── admin/                     # Typesense API key helpers
├── push-notis/
│   ├── monitor.js                 # Firebase / FCM notifications
│   ├── env.example                # Monitor env template
│   └── package*.json, node_modules
├── data/                          # Typesense data dir + seen-id store
├── logs/                          # feed-scan.log, scan_history, run locks
├── backups/                       # Daily snapshots + seen-id exports
└── docs/                          # Feed reference lists
```

---

## Troubleshooting Cheat Sheet
- **WSL IP changed** – rerun the `netsh interface portproxy` commands (see setup step 8) or schedule the provided PowerShell helper to run on startup.
- **Stuck shard** – `systemctl --user stop caser-scan@0.service`, delete `data/scanner-shard-0.lock`, restart the timer. Pending IDs expire automatically after `SEEN_IDS_PENDING_TTL` seconds, but clearing the lock speeds recovery.
- **Typesense unavailable** – `docker compose logs typesense`, restart via `docker compose restart typesense`. Check that `TS_ADMIN_KEY` in `.env.local` matches the key passed to Docker.
- **Cloudflare DNS / SSL issues** – ensure `CLOUDFLARE_API_TOKEN` is present and has DNS edit scope for `search.caserlegal.com`, then `docker compose restart caddy`.
- **Monitor failures** – confirm `/home/sm/secrets/firebase-service-account.json` exists and that `push-notis/.env` points at it. Run `node push-notis/monitor.js` manually to surface Firestore/FCM errors.
- **Doc count mismatch** – compare Typesense count with `wc -l data/seen_ids.txt`. If the SQLite store is corrupt, run `python scripts/rebuild_seen_cache.py` and restart the scanners.

---

## License
Proprietary – CASER Legal, LLC

---

## 📢 Alerting & Monitoring

Get instant notifications when things go wrong! See [ALERTING.md](ALERTING.md) for complete setup.

### Quick Setup

```bash
# 1. Get webhook URL from Slack or Discord
# 2. Add to config/.env.local
export ALERT_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

# 3. Test it
curl -X POST "$ALERT_WEBHOOK_URL" -d '{"text":"✅ Test alert"}'

# 4. Enable health monitoring (optional)
crontab -e
# Add: */5 * * * * /home/sm/caser-search/scripts/health-check.sh
```

### Alerts Configured

- 🔴 **Backup failures** - Daily backup script fails
- ⚠️ **High feed failure rate** - More than 10% of feeds fail
- 🔴 **Typesense downtime** - Health check fails

---

## 🚀 Quick Deployment

### One-Command Setup

```bash
git clone https://github.com/caser-legal/8ti.git
cd 8ti
cp config/.env.example config/.env.local
# Edit config/.env.local with your API keys
bash scripts/deploy.sh
```

The deploy script handles:
- ✅ Installing dependencies (Docker, Python, etc.)
- ✅ Setting up Python virtual environment
- ✅ Configuring systemd services
- ✅ Starting Docker containers
- ✅ Enabling automated timers

---

## 🔒 Security Features

- ✅ **Request size limits** - 10MB max to prevent memory exhaustion
- ✅ **Backup encryption** - Optional AES-256 encryption
- ✅ **HTTPS only** - TLS via Let's Encrypt + Cloudflare
- ✅ **Rate limiting** - 100 requests/minute per IP
- ✅ **No public ports** - Typesense only accessible via Caddy proxy
- ✅ **Automatic retries** - HTTP requests retry on transient failures

---

## 📊 Production Audit Score: 9.5/10

Recent improvements:
- ✅ Firebase token error handling
- ✅ HTTP retry logic with exponential backoff
- ✅ Typesense retry wrapper
- ✅ Request size limits (10MB max)
- ✅ Backup encryption support
- ✅ Webhook alerting (Slack/Discord)
- ✅ Health monitoring
- ✅ Deployment automation

