

# CASER Search - Self-Hosted Legal Document Search Engine

[![Status](https://img.shields.io/badge/status-production-brightgreen)]()
[![Documents](https://img.shields.io/badge/documents-197K+-blue)]()
[![Feeds](https://img.shields.io/badge/feeds-354-orange)]()
[![Updated](https://img.shields.io/badge/updated-2025--11--11-blue)]()

**Production-grade legal search platform monitoring 354 federal court RSS feeds.**

🔗 **Live at:** [https://search.caserlegal.com](https://search.caserlegal.com)

---

## 🔒 Production Status (Updated 2025-11-11)

✅ **Fully operational** with recent reliability and security improvements:
- Push notification system (2-minute monitoring interval)
- Firebase token error handling (graceful invalid/expired token handling)
- HTTP retry logic (3 retries with exponential backoff)
- Typesense retry wrapper (automatic search failure recovery)
- Security hardening (Typesense port no longer exposed publicly)
- Backup verification (ensures snapshot creation succeeds)
- Comprehensive documentation (complete redeployment guides)

---

## What This Is

A **self-hosted legal document search engine** that automatically monitors **354 federal court RSS feeds** (202 uscourts + 152 govinfo) and makes filings instantly searchable via HTTPS API.

### Current Stats (Updated 2025-11-11)
- **Documents Indexed:** 197,732
- **RSS Feeds:** 354 active (202 uscourts + 152 govinfo)
- **Update Interval:** Every 2 minutes (64 parallel systemd shards)
- **Database Size:** 473 MB (Typesense data)
- **Scan Speed:** ~8-10 seconds per shard
- **Monthly Cost:** ~$6 (electricity + domain)
- **Backup Schedule:** Daily at 3 AM (7-day retention)
- **System:** WSL2 Ubuntu 24.04 on Windows 10/11
- **Runtime:** Docker containers with systemd timers

### What It Does
✅ Monitors 354 active court RSS feeds automatically  
✅ Scans every 2 minutes via 64 systemd shard timers  
✅ Indexes documents with full-text search (Typesense)  
✅ Fast duplicate detection (skips already-seen entries)  
✅ Provides HTTPS API at `search.caserlegal.com`  
✅ SSL encryption via Cloudflare + Let's Encrypt  
✅ Runs 24/7 on spare PC using Docker + WSL2  
✅ Daily automated backups (7-day retention)  
✅ Push notifications via Firebase (every 2 minutes)  
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
cp config/.env.example .env
nano .env
```
Set required environment variables:
- `TYPESENSE_ADMIN_KEY` - Typesense admin key (generate a secure random string)
- `TS_ADMIN_KEY` - Same value as TYPESENSE_ADMIN_KEY
- `CLOUDFLARE_API_TOKEN` - API token for Cloudflare DNS plugin (if using Cloudflare)
- `TYPESENSE_HOST` - http://localhost:8108 (default)
- `COLLECTION` - rss_entries (default)
- `PROXY_MODE` - proxy-first (default), proxy-only, or direct-only
- `ALERT_WEBHOOK_URL` - Slack webhook for system alerts (optional)
- `CASE_MONITOR_WEBHOOK_URL` - Slack webhook for case monitoring (optional)
- `MONITORED_CASE` - Case name to monitor (optional)

Docker Compose reads from `.env` in project root automatically.

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
docker compose up -d
sleep 10
docker compose ps  # Should show 2 containers running
```
> **Security Note:** Typesense port 8108 is NOT exposed publicly. Access is only
> available via internal Docker network or through Caddy reverse proxy at
> https://search.caserlegal.com. This prevents unauthorized direct access.

**7. Setup Systemd Timers**
```bash
# Enable user linger (auto-start on boot)
sudo loginctl enable-linger $USER

# Scanner services are templated at ~/.config/systemd/user/caser-scan@.service
# 64 timer instances (caser-scan@0.timer through caser-scan@63.timer)
# Monitor service at ~/.config/systemd/user/caser-monitor.service
# Backup service at ~/.config/systemd/user/caser-backup.service

# Enable and start all timers (64 scan shards + monitor + backup)
systemctl --user daemon-reload
for i in {0..63}; do systemctl --user enable --now caser-scan@$i.timer; done
systemctl --user enable --now caser-monitor.timer
systemctl --user enable --now caser-backup.timer

# Check status
systemctl --user list-timers | grep caser
```

**Active Timers:**
- `caser-scan@0.timer` through `caser-scan@63.timer`: 64 shards running every 2 minutes
- `caser-monitor.timer`: Runs Firebase monitor every 2 minutes  
- `caser-backup.timer`: Creates Typesense snapshots daily at 3 AM

**8. Setup Push Notifications (Optional)**

The system includes Firebase Cloud Messaging (FCM) push notifications for iOS app alerts.

```bash
# Install Node.js 20+ (if not already installed)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Setup push notification monitor
cd ~/caser-search/push-notis
npm install

# Create .env file
cp env.example .env
nano .env
```

Configure the following in `push-notis/.env`:
- `SERVICE_ACCOUNT_PATH` - Path to Firebase service account JSON (e.g., `/home/sm/secrets/firebase-service-account.json`)
- `TYPESENSE_HOST` - localhost (default)
- `TYPESENSE_PORT` - 8108 (default)
- `TYPESENSE_PROTOCOL` - http (default)
- `TYPESENSE_API_KEY` - Same admin key from main `.env`
- `USER_CONCURRENCY` - 4 (default)
- `KEYWORD_CONCURRENCY` - 4 (default)

**Get Firebase Service Account:**
1. Go to Firebase Console → Project Settings → Service Accounts
2. Click "Generate new private key"
3. Save JSON file to `/home/sm/secrets/firebase-service-account.json`
4. Set permissions: `chmod 600 /home/sm/secrets/firebase-service-account.json`

**Test the monitor:**
```bash
cd ~/caser-search/push-notis
node monitor.js
```

The systemd timer (`caser-monitor.timer`) is already enabled and will run every 2 minutes automatically.

**Current Status:**
```bash
# Check running containers
docker ps
# CONTAINER ID   IMAGE                      STATUS         PORTS
# e216da4a444e   caser-search-caddy         Up 3 minutes   0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
# 38ffeefd1fb9   typesense/typesense:29.0   Up 3 minutes   127.0.0.1:8108->8108/tcp

# Check systemd services
systemctl --user status caser-scan@0.timer caser-scan@1.timer
```

**9. Setup Network** (PowerShell as Admin)
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
  → Windows PC (172.xxx.xxx.xx) → WSL2 Ubuntu 24.04 → Docker
    ├── Caddy (reverse proxy, SSL) - ports 80/443
    └── Typesense (search engine, 1.2M docs) - port 8108 (localhost only)

Python Scanner (systemd timer, every 10 min)
  → Cloudflare Worker Proxy → Court RSS feeds
    → Parse entries → Check duplicates → Index new docs

Network Configuration:
- WSL2 IP: 172.xxx.xxx.xx (dynamic, changes on Windows restart)
- Port forwarding: Windows host → WSL2 instance
- Typesense: localhost:8108 (not exposed externally)
- Caddy: 0.0.0.0:80/443 (public via port forwarding)
```

---

## How It Works

### RSS Scanning (Every 2 Minutes)

1. **Systemd timer triggers** `/home/sm/caser-search/src/rss_scanner.py` for each shard
2. **Load seen IDs cache** from `data/seen_ids.sqlite3` (197K+ entries)
3. **For each feed** (354 total, divided across 64 shards):
   - Fetch RSS via Cloudflare Worker proxy (bypasses rate limits)
   - Parse entries with feedparser
   - **For govinfo feeds**: Check duplicate BEFORE fetching metadata (optimization!)
   - Generate stable document ID (SHA1 hash of GUID)
   - Skip if ID already in cache
   - **For govinfo feeds**: Fetch MODS/PREMIS XML (small files, ~1-2KB each)
   - **Skip ZIP downloads** (optimization - we have the link, don't need 100MB+ files)
   - Batch upsert to Typesense (512 docs at a time)
   - Commit new IDs to cache
4. **Save updated cache** to `data/seen_ids.txt` (mirrored from SQLite)
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
ADMIN_KEY=$(grep TYPESENSE_ADMIN_KEY .env | cut -d'=' -f2 | tr -d "'\"")
curl -s "http://localhost:8108/collections/rss_entries" \
  -H "X-TYPESENSE-API-KEY: $ADMIN_KEY" | jq '.num_documents'
systemctl --user status caser-scan@0.timer caser-scan@1.timer
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
│   ├── seen_ids_store.py       # Duplicate tracking with SQLite
│   └── scan_tracker.py         # Scan state tracking
├── scripts/
│   ├── run-scheduled-scan.sh   # Wrapper script
│   ├── mission_control.py      # Live dashboard
│   ├── rebuild_seen_cache.py   # Rebuild duplicate cache from Typesense
│   ├── dedupe_typesense.py     # Drop/recreate index with unique docs
│   ├── backup-typesense.sh     # Automated backup script
│   ├── health-check.sh         # System health monitoring
│   └── admin/                  # API key management
├── config/
│   ├── uscourts-filtered-feed.json  # 171 uscourts feeds
│   ├── govinfo-filtered-feed.json   # 151 govinfo feeds
│   ├── .env.example            # Template for local secrets
│   └── .env.local              # Local secrets (not in git)
├── push-notis/
│   ├── monitor.js              # Firebase push notification monitor
│   ├── caser-monitor.service   # Systemd service file
│   ├── caser-monitor.timer     # Systemd timer file
│   └── *.md                    # Documentation files
├── data/
│   ├── db/                     # Typesense database (1.2GB)
│   ├── seen_ids.txt            # Duplicate tracking (1.2M+ IDs)
│   ├── seen_ids.sqlite3        # SQLite duplicate store (28MB)
│   ├── meta/                   # Typesense metadata
│   └── state/                  # Typesense state files
├── logs/
│   ├── feed-scan.log           # Detailed logs (93MB)
│   ├── scan-history.ndjson     # Per-scan summaries (15MB)
│   ├── scan_state.json         # Current scan state
│   └── active/                 # Active scan logs
├── backups/                    # Daily Typesense snapshots
├── caddy-data/                 # Caddy SSL certificates and data
├── .env                        # Environment variables (not in git)
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
docker compose exec typesense ls /data/snapshots
```

The backup script now:
1. Loads `TYPESENSE_ADMIN_KEY` / `TS_ADMIN_KEY` from `.env`
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
- Per-shard scan: 8-10 seconds (64 shards running in parallel)
- Govinfo feed (100 duplicates): ~1 second
- No ZIP downloads: No rate limiting

**Speed improvement: 20x+ faster with parallel sharding**

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
2. Add to `.env`:
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

### November 2025 - v2.2 (Current)

**System Updates:**
- ✅ 64-shard parallel scanning (every 2 minutes)
- ✅ 354 active RSS feeds (202 uscourts + 152 govinfo)
- ✅ 197K+ documents indexed
- ✅ 473MB database size
- ✅ PID-specific temp files (eliminates race conditions)
- ✅ WSL2 Ubuntu 24.04 environment
- ✅ Docker containers: Caddy + Typesense 29.0
- ✅ Systemd user services with timers
- ✅ SQLite seen_ids store (29MB) + text backup
- ✅ Daily automated backups with 7-day retention
- ✅ Firebase push notification monitoring
- ✅ Slack alerting with Mission Control formatting

**Performance & Reliability:**
- ✅ 64 parallel shards (8-10 seconds per shard)
- ✅ Exclusive file locking prevents race conditions
- ✅ Atomic cache writes with PID-specific temp files
- ✅ Graceful error handling and retries
- ✅ Security headers and rate limiting via Caddy

### November 2025 - v2.1

**System Updates:**
- ✅ WSL2 Ubuntu 24.04 environment
- ✅ Docker containers: Caddy + Typesense 29.0
- ✅ Systemd user services with timers
- ✅ 1.2M+ documents indexed (production scale)
- ✅ SQLite seen_ids store (28MB) + text backup
- ✅ Daily automated backups with 7-day retention
- ✅ Firebase push notification monitoring
- ✅ Slack alerting with Mission Control formatting

**Performance & Reliability:**
- ✅ Dual shard scanning (caser-scan@0, caser-scan@1)
- ✅ Exclusive file locking prevents race conditions
- ✅ Atomic cache writes with temp files
- ✅ Graceful error handling and retries
- ✅ Security headers and rate limiting via Caddy

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

**Version:** 2.2  
**Last Updated:** November 11, 2025  
**Status:** ✅ Operational  
**Documents:** 197,732  
**Feeds:** 354  
**System:** WSL2 Ubuntu 24.04 + Docker
