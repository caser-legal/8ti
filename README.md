

# CASER Search - Self-Hosted Legal Document Search Engine

[![Status](https://img.shields.io/badge/status-production-brightgreen)]()
[![Documents](https://img.shields.io/badge/documents-1.2M+-blue)]()
[![Feeds](https://img.shields.io/badge/feeds-322-orange)]()
[![Updated](https://img.shields.io/badge/updated-2025--11--09-blue)]()

**Production-grade legal search platform monitoring 322 federal court RSS feeds.**

🔗 **Live at:** [https://search.caserlegal.com](https://search.caserlegal.com)

---

## 🔒 Production Status (Updated 2025-11-09)

✅ **Fully operational** with recent reliability and security improvements:
- Firebase token error handling (graceful invalid/expired token handling)
- HTTP retry logic (3 retries with exponential backoff)
- Typesense retry wrapper (automatic search failure recovery)
- Security hardening (Typesense port no longer exposed publicly)
- Backup verification (ensures snapshot creation succeeds)

---

## What This Is

A **self-hosted legal document search engine** that automatically monitors **322 federal court RSS feeds** (171 uscourts + 151 govinfo) and makes filings instantly searchable via HTTPS API.

### Current Stats
- **Documents Indexed:** 48,000+ (weekend baseline)
- **RSS Feeds:** 326 active (174 uscourts + 152 govinfo)
- **Update Interval:** Every 10 minutes (2 parallel systemd shards)
- **Database Size:** 200MB (Typesense data dir)
- **Scan Speed:** ~20-30 minutes per full scan
- **Monthly Cost:** ~$6 (electricity + domain)
- **Backup Schedule:** Daily at 3 AM (7-day retention)

### What It Does
✅ Monitors 326 active court RSS feeds automatically  
✅ Scans every 10 minutes via dual systemd shard timers  
✅ Indexes documents with full-text search (Typesense)  
✅ Fast duplicate detection (skips already-seen entries)  
✅ Provides HTTPS API at `search.caserlegal.com`  
✅ SSL encryption via Cloudflare + Let's Encrypt  
✅ Runs 24/7 on spare PC using Docker + WSL2  
✅ Daily automated backups (7-day retention)  
✅ Push notifications via Firebase (every 5 minutes)  
✅ **Mission Control Slack alerts** - Real-time scan status, milestones, errors  
✅ **Case monitoring** - Instant alerts for specific cases  
✅ **10MB feed size limit** - Prevents memory exhaustion  
✅ **Auto-restart on reboot** - Systemd + Docker restart policies  

---

## Quick Start

### Prerequisites
- Windows 10/11 (64-bit)
- Admin access
- 10GB free disk space
- Internet connection

### Installation

**1. Install WSL2 + Ubuntu** (PowerShell as Admin)
```powershell
wsl --install Ubuntu-24.04
```

**2. Install Docker Desktop**
- Download: https://www.docker.com/products/docker-desktop
- Enable WSL Integration for Ubuntu-24.04

**3. Clone Project**
```bash
cd ~
git clone <repo-url> caser-search
cd caser-search
```

**4. Configure Environment**
```bash
cp config/.env.example config/.env.local
nano config/.env.local
```
Set:
- `TYPESENSE_ADMIN_KEY` - Typesense admin key used by all scanner scripts
- `TS_ADMIN_KEY` - Same value as above so the Typesense container starts up
- `CLOUDFLARE_API_TOKEN` - API token for the Cloudflare DNS plugin (Caddy)
- `PROXY_MODE` - `proxy-first` (default), `proxy-only`, or `direct-only`
- Optional: `TYPESENSE_HOST` and `COLLECTION` if you are not using the defaults

Docker Compose does not automatically read files from `config/`, so either pass `--env-file config/.env.local` to every `docker compose` command or export the variables in your shell before running compose (example below):

```bash
set -a
source config/.env.local
set +a
```

**5. Setup Python**
```bash
sudo apt update
sudo apt install -y python3-venv python3-pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Optional: developer tooling (pytest)
pip install -r requirements-dev.txt
deactivate
```

**6. Start Services**
```bash
docker compose --env-file config/.env.local up -d
sleep 10
docker compose --env-file config/.env.local ps  # Should show 2 containers running
```
> **Security Note:** Typesense port 8108 is NOT exposed publicly. Access is only
> available via internal Docker network or through Caddy reverse proxy at
> https://search.caserlegal.com. This prevents unauthorized direct access.

**7. Setup Systemd Timers**
```bash
# Enable user linger (auto-start on boot)
sudo loginctl enable-linger $USER

# Scanner services (templated at ~/.config/systemd/user/caser-scan@.service)
> When referencing the scanner units below, substitute `caser-scan@0` or
> `caser-scan@1` depending on the shard you are inspecting.
# Monitor service (already created at ~/.config/systemd/user/caser-monitor.service)
# Backup service (already created at ~/.config/systemd/user/caser-backup.service)

# Enable and start all timers
systemctl --user daemon-reload
systemctl --user enable --now caser-scan@0.timer caser-scan@1.timer
systemctl --user enable --now caser-monitor.timer
systemctl --user enable --now caser-backup.timer

# Check status
systemctl --user list-timers | grep caser
```

**Timers:**
- `caser-scan@0.timer` / `caser-scan@1.timer`: Run shard pair every 10 minutes
- `caser-monitor.timer`: Runs Firebase monitor every 5 minutes
- `caser-backup.timer`: Creates Typesense snapshots daily at 3 AM

[Install]
WantedBy=default.target
EOF

# Create timer file
> NOTE: The live system runs two shards via `caser-scan@.service` with timers
> `caser-scan@0.timer` and `caser-scan@1.timer`. Duplicate the timer snippet per
> shard (substitute the `@N` suffix) if you need to recreate them manually.

cat > ~/.config/systemd/user/caser-scan.timer <<'EOF'
[Unit]
Description=CASER Scanner Timer (every 10 minutes)

[Timer]
OnBootSec=2min
OnUnitActiveSec=10min
Persistent=true

[Install]
WantedBy=timers.target
EOF

# Enable and start
systemctl --user daemon-reload
systemctl --user enable caser-scan.timer
systemctl --user start caser-scan.timer
systemctl --user status caser-scan@0.timer caser-scan@1.timer
```

**8. Setup Network** (PowerShell as Admin)
```powershell
$wslIp = (wsl -d Ubuntu-24.04 -- hostname -I).Split()[0]
netsh interface portproxy add v4tov4 listenport=80 listenaddress=0.0.0.0 connectport=80 connectaddress=$wslIp
netsh interface portproxy add v4tov4 listenport=443 listenaddress=0.0.0.0 connectport=443 connectaddress=$wslIp
netsh advfirewall firewall add rule name="caser-80" dir=in action=allow protocol=TCP localport=80
netsh advfirewall firewall add rule name="caser-443" dir=in action=allow protocol=TCP localport=443
```

---

## System Architecture

```
Internet → Cloudflare (DNS/SSL/DDoS) → Your Router (port forward)
  → Windows PC → WSL2 → Docker
    ├── Caddy (reverse proxy, SSL)
    └── Typesense (search engine, 1.2M docs)

Python Scanner (systemd timer, every 10 min)
  → Cloudflare Worker Proxy → Court RSS feeds
    → Parse entries → Check duplicates → Index new docs
```

---

## How It Works

### RSS Scanning (Every 10 Minutes)

1. **Systemd timer triggers** `/home/sm/caser-search/src/rss_scanner.py`
2. **Load seen IDs cache** from `data/seen_ids.txt` (128k entries)
3. **For each feed** (322 total):
   - Fetch RSS via Cloudflare Worker proxy (bypasses rate limits)
   - Parse entries with feedparser
   - **For govinfo feeds**: Check duplicate BEFORE fetching metadata (optimization!)
   - Generate stable document ID (SHA1 hash of GUID)
   - Skip if ID already in cache
   - **For govinfo feeds**: Fetch MODS/PREMIS XML (small files, ~1-2KB each)
   - **Skip ZIP downloads** (optimization - we have the link, don't need 100MB+ files)
   - Batch upsert to Typesense (512 docs at a time)
   - Commit new IDs to cache
4. **Save updated cache** to `data/seen_ids.txt`
5. **Log results** to `logs/feed-scan.log` and `logs/scan-history.ndjson`

To keep persistence reliable, each shard grabs an exclusive lock file (`data/scanner-shard-<index>.lock`) before it starts and coordinates duplicate detection through `data/seen_ids.sqlite3` (mirrored back to `data/seen_ids.txt`). Even if timers overlap, crash, or reboot mid-run, the cache stays intact.

### Key Optimizations

**1. Early Duplicate Check (Govinfo)**
- Check if entry is duplicate BEFORE fetching metadata
- Saves 40+ seconds per 100 duplicates
- Reduces 3-hour scans to 20-30 minutes

**2. Skip ZIP Downloads**
- Don't download massive ZIP files (100MB+ for Supreme Court)
- We have the link - that's all we need
- Prevents 503 rate limiting errors

**3. Cloudflare Worker Proxy**
- Routes RSS requests through `https://nfq7btef6.j0mpz7gur2.workers.dev/`
- Bypasses court website rate limits
- Rotates IPs automatically

**4. Rolling Seen IDs Cache**
- Keeps up to `SEEN_IDS_MAX` IDs (default ~1B) in memory/disk
- O(1) duplicate lookups
- Persists between runs (`data/seen_ids.txt`)

---

## Daily Operations

### Health Check

```bash
# One-liner to print container status, Typesense health, doc count, and last scan
bash ./scripts/status-check.sh

# Or run individual checks:
docker compose ps
curl -s http://localhost:8108/health
ADMIN_KEY=$(grep TYPESENSE_ADMIN_KEY config/.env.local | cut -d'=' -f2)
curl -s "http://localhost:8108/collections/rss_entries" \
  -H "X-TYPESENSE-API-KEY: $ADMIN_KEY" | jq '.num_documents'
systemctl --user status caser-scan.timer
tail -20 logs/scan-history.ndjson | jq
```

### Monitor Scanner Lock & Active Runs

```bash
# Does a shard currently hold a lock?
if ls data/scanner-shard-*.lock >/dev/null 2>&1; then
  for lock in data/scanner-shard-*.lock; do
    shard="${lock##*-}"
    shard="${shard%.*}"
    printf "shard %s running (PID %s)\n" "$shard" "$(cat "$lock")"
  done
else
  echo "no scan in flight"
fi

# Confirm only one instance is alive
pgrep -af rss_scanner
```

Each shard acquires its own `data/scanner-shard-<index>.lock` before touching
Typesense or the seen-id store. Manual runs should wait for those files to
disappear (or stop the systemd services) before launching to avoid immediate
“Another instance is running” exits.

### Verify Document & Cache Parity

```bash
DOCS=$(curl -s -H "X-TYPESENSE-API-KEY: $ADMIN_KEY" \
  http://localhost:8108/collections/rss_entries | jq '.num_documents')
IDS=$(wc -l < data/seen_ids.txt)
printf "typesense=%s cached_ids=%s delta=%s\n" "$DOCS" "$IDS" "$((IDS - DOCS))"
```

Expect these two numbers to track within a handful of IDs (the window where a
batch finished importing but has not yet been flushed to disk). If the delta
grows into the hundreds, run the dedupe + cache rebuild workflow below.

### Rebuild Seen IDs Cache

```bash
cd ~/caser-search
source .venv/bin/activate
python scripts/rebuild_seen_cache.py
```

This streams every document from Typesense, deduplicates by `objectID`, and atomically rewrites `data/seen_ids.txt`. Run it after restoring Typesense from backup or whenever duplicate detection needs to be resynchronized with the index.

### Deduplicate Typesense Collection

```bash
cd ~/caser-search
source .venv/bin/activate
python scripts/dedupe_typesense.py
python scripts/rebuild_seen_cache.py
```

The first script exports the entire collection, keeps the freshest document for every `objectID`, drops the collection, and re-imports the deduplicated data. Always follow it up with `rebuild_seen_cache.py` so the scanner's cache matches the cleaned index.

> **Tip:** Snapshot first with `bash scripts/backup-typesense.sh`. Backups live
> inside the Typesense container at `/home/sm/caser-search/backups/` and retain
> 7 days of `typesense_*` snapshots plus matching `seen_ids_*` files.

### Manual Scan

```bash
cd ~/caser-search
# Optionally pause the timer to avoid overlap:
# systemctl --user stop caser-scan.service
source .venv/bin/activate
python src/rss_scanner.py
# Resume the service afterwards:
# systemctl --user start caser-scan.service
deactivate
```

### View Logs

```bash
# Live tail
tail -f logs/feed-scan.log

# Recent errors
grep ERROR logs/feed-scan.log | tail -20

# Scan summary
tail -1 logs/scan-history.ndjson | jq
```

---

## File Structure

```
caser-search/
├── src/
│   ├── rss_scanner.py          # Main scanner (optimized)
│   ├── govinfo_harvester.py    # Govinfo metadata fetcher
│   └── scan_tracker.py         # Scan state tracking
├── scripts/
│   ├── run-scheduled-scan.sh   # Wrapper script
│   ├── mission_control.py      # Live dashboard
│   ├── rebuild_seen_cache.py   # Rebuild duplicate cache from Typesense
│   ├── dedupe_typesense.py     # Drop/recreate index with unique docs
│   └── admin/                  # API key management
├── config/
│   ├── uscourts-filtered-feed.json  # 171 uscourts feeds
│   ├── govinfo-filtered-feed.json   # 151 govinfo feeds
│   ├── .env.example            # Template for local secrets
│   └── .env.local              # Secrets (not in git)
├── data/
│   ├── db/                     # Typesense database (1.2GB)
│   ├── seen_ids.txt            # Duplicate tracking (128k IDs)
│   ├── meta/                   # Typesense metadata
│   └── state/                  # Typesense state (744MB)
├── logs/
│   ├── feed-scan.log           # Detailed logs
│   └── scan-history.ndjson     # Per-scan summaries
├── docker-compose.yml          # Container orchestration
├── Dockerfile.caddy            # Custom Caddy with Cloudflare DNS
├── Caddyfile                   # Reverse proxy config
└── requirements.txt            # Python deps (requests, feedparser, python-dotenv)
```

---

## API Usage

### Search Endpoint

```bash
curl "https://search.caserlegal.com/collections/rss_entries/documents/search?q=order&query_by=title&per_page=10" \
  -H "X-TYPESENSE-API-KEY: <your-search-key>"
```

**Parameters:**
- `q` - Search query
- `query_by` - Fields to search (default: `title,description,parties`)
- `filter_by` - Filter expression (e.g., `state:=[Texas]`)
- `sort_by` - Sort field (default: `pubDate:desc`)
- `per_page` - Results per page (max: 250)

### API Key Management

```bash
cd ~/caser-search
source .venv/bin/activate

# List keys
python scripts/admin/list_keys.py

# Create search-only key
python scripts/admin/create_firm_key.py "Client Name"

# Delete key
python scripts/admin/delete_key.py <KEY_ID>

deactivate
```

---

## Troubleshooting

### Containers Won't Start

```bash
docker compose restart
docker compose logs typesense
docker compose logs caddy
```

### Scanner Not Running

```bash
# Check timer
systemctl --user status caser-scan.timer

# Check last run
systemctl --user status caser-scan.service

# Restart timer
systemctl --user restart caser-scan.timer
```

### WSL IP Changed (After Windows Restart)

**⚠️ This happens every time Windows restarts!**

```powershell
# PowerShell as Admin
$wslIp = (wsl -d Ubuntu-24.04 -- hostname -I).Split()[0]
netsh interface portproxy delete v4tov4 listenport=80 listenaddress=0.0.0.0
netsh interface portproxy delete v4tov4 listenport=443 listenaddress=0.0.0.0
netsh interface portproxy add v4tov4 listenport=80 listenaddress=0.0.0.0 connectport=80 connectaddress=$wslIp
netsh interface portproxy add v4tov4 listenport=443 listenaddress=0.0.0.0 connectport=443 connectaddress=$wslIp
```

**Automate:** Create Task Scheduler task to run this script on startup.

### Slow Scans

Check if optimizations are enabled:

```bash
# Should see early duplicate checks for govinfo
grep "duplicate check" src/rss_scanner.py

# Should NOT see ZIP downloads
grep "inventory_zip" src/govinfo_harvester.py | grep "#"
```

---

## Maintenance

### Backup

```bash
cd ~/caser-search
bash scripts/backup-typesense.sh

# List snapshots (inside the Typesense container)
docker compose exec typesense ls /home/sm/caser-search/backups
```

The backup script now:
1. Loads `TYPESENSE_ADMIN_KEY` / `TS_ADMIN_KEY` from `config/.env.local`
2. Triggers a Typesense snapshot at `backups/typesense_YYYYMMDD_HHMMSS`
3. Copies `data/seen_ids.txt` to `backups/seen_ids_YYYYMMDD_HHMMSS.txt`
4. Prunes items older than 7 days

### Restore

```bash
# Stop scanners & Typesense
systemctl --user stop caser-scan.service caser-scan.timer
docker compose down

# Restore snapshot directory (example timestamp)
docker compose up -d typesense
docker compose exec typesense bash -lc '
  SNAP=/home/sm/caser-search/backups/typesense_YYYYMMDD_HHMMSS
  typesense-server --restore-from $SNAP --data-dir /data
'

# Rebuild seen_ids from Typesense to guarantee parity
source .venv/bin/activate && python scripts/rebuild_seen_cache.py

# Restart services/timers
systemctl --user start caser-scan.service caser-scan.timer
```

### Update

```bash
cd ~/caser-search
git pull
docker compose pull
docker compose up -d
systemctl --user restart caser-scan.timer
```

---

## Performance Stats

### Before Optimizations
- Full scan: 3+ hours
- Govinfo feed (100 entries): 40+ seconds
- ZIP downloads: 503 errors, rate limiting

### After Optimizations
- Full scan: 20-30 minutes
- Govinfo feed (100 duplicates): ~1 second
- No ZIP downloads: No rate limiting

**Speed improvement: 6-9x faster**

---

## Technical Details

### Components
- **Typesense 29.0** - Search engine
- **Caddy 2** - Web server with Cloudflare DNS plugin
- **Python 3.12** - RSS scanner
- **Ubuntu 24.04** - WSL2 environment
- **Docker** - Container runtime

### Network
- **Public domain:** search.caserlegal.com
- **Cloudflare:** DNS, SSL, DDoS protection
- **Proxy mode:** proxy-only (all requests via Cloudflare Worker)

### Dependencies
```
requests      # HTTP client
feedparser    # RSS/Atom parser
python-dotenv # Environment variables
```

---

## Alerting & Monitoring

The system sends real-time Slack notifications using Mission Control style formatting:

**System Alerts** (`ALERT_WEBHOOK_URL`):
- 🚀 **Scan start** - When each scan begins with run ID and shard info
- ✅ **Scan completion** - Dashboard with feeds processed, new docs, duration
- 📊 **Milestones** - Every 100K documents indexed
- ⚠️ **High failure rate** - When >10% of feeds fail (requires investigation)

**Case Monitoring** (`CASE_MONITOR_WEBHOOK_URL`):
- 🔔 **Instant alerts** when monitored cases have new documents
- Includes case name, court, title, date, and link
- Configure via `MONITORED_CASE` environment variable

**Setup:**
1. Create Slack incoming webhooks at https://api.slack.com/apps
2. Add to `config/.env.local`:
   ```bash
   ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
   CASE_MONITOR_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/CASE/WEBHOOK
   MONITORED_CASE=Case Name Here
   ```

---

## Security

- **HTTPS:** All traffic encrypted (Cloudflare DNS + automatic TLS via Caddy)
- **API Keys:** Admin (full access) + Search (read-only)
- **Firewall:** Only ports 80/443 need to be public; Typesense’s 8108 mapping is host-only and can be removed once the scanner runs inside Docker.
- **Single-writer lock:** `data/scanner.lock` + `fcntl` ensures only one scanner instance touches `seen_ids.txt` or Typesense at a time.
- **Atomic cache writes:** `seen_ids.txt` is always written via `*.tmp + os.replace` so power loss cannot truncate the cache.
- **Feed allowlist:** Scanner refuses any RSS URL outside `govinfo.gov` / `uscourts.gov` and enforces HTTPS.
- **Secrets:** Never committed to git (`.env.local` in `.gitignore`)
- **Rate limiting + headers:** Caddy now sets standard security headers and limits abusive clients (100 req/min/IP).

---

## Cost Comparison

| Setup | Monthly Cost |
|-------|--------------|
| **Self-hosted (this)** | ~$6 (electricity + domain) |
| **Cloud (Algolia/Elastic)** | $116-627 |
| **Annual savings** | $1,320-7,452 |

---

## Support

- **Email:** support@caserlegal.com
- **Website:** www.caserlegal.com

---

## Changelog

### November 2025 - v2.0

**Major Optimizations:**
- ✅ Early duplicate check for govinfo feeds (6-9x faster)
- ✅ Skip ZIP downloads (prevents rate limiting)
- ✅ Fixed datetime deprecation warning
- ✅ Removed non-existent Federal Circuit feed
- ✅ Added all Circuit Court feeds (CA1-CA11, CADC)
- ✅ Added Supreme Court feed
- ✅ Systemd timer (more reliable than cron)

**Performance:**
- Full scan: 3+ hours → 20-30 minutes
- Govinfo duplicates: 40s → 1s per 100 entries
- No more 503 errors from ZIP downloads

---

## License

Proprietary - CASER Legal, LLC

---

**Version:** 2.0  
**Last Updated:** November 6, 2025  
**Status:** ✅ Operational  
**Documents:** 1,214,078+  
**Feeds:** 322
