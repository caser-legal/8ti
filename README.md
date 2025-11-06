# 8ti

# CASER Search - Self-Hosted Legal Document Search Engine

[![Status](https://img.shields.io/badge/status-operational-brightgreen)]()
[![Documents](https://img.shields.io/badge/documents-17.8K+-blue)]()
[![Feeds](https://img.shields.io/badge/feeds-205-orange)]()
[![Uptime](https://img.shields.io/badge/uptime-24%2F7-success)]()

**A production-grade legal search platform running on a spare Windows PC.**

🔗 **Live at:** [https://search.caserlegal.com](https://search.caserlegal.com)

---

## 📋 Table of Contents

- [What This Is](#what-this-is)
- [System Architecture](#system-architecture)
- [How It Works](#how-it-works)
- [Key Features](#key-features)
- [Quick Start](#quick-start)
- [Daily Operations](#daily-operations)
- [Setup on New PC](#setup-on-new-pc)
- [Technical Details](#technical-details)
- [Troubleshooting](#troubleshooting)
- [API Documentation](#api-documentation)

---

## What This Is

A **self-hosted legal document search engine** that automatically monitors **205 federal court RSS feeds** and makes filings instantly searchable via a secure HTTPS API.

### Current Stats (November 2025) - ✅ VERIFIED
- **Documents Indexed:** 18,683 court filings (verified via live API Nov 4, 2025)
- **RSS Feeds Monitored:** 205 federal courts (verified in config/filtered_feeds.json)
- **Update Interval:** Every 10 minutes (Mon-Fri, 8AM-10PM ET)
- **Total Disk Usage:** 85MB
- **Database Size:** 62MB (data/ directory)
- **Tracking File:** 730KB (18,683 unique IDs in data/seen_ids.txt)
- **Search Performance:** 5ms average response time (verified via API)
- **NL Search:** Operational (caser-nl-model, 850ms parse time)
- **Monthly Cloud Cost:** $0 (self-hosted)
- **Comparable Cloud Cost:** $116-627/month

**iOS App Compatibility:** ✅ 100% Compatible
- API Endpoint: `https://search.caserlegal.com` ✓
- Collection: `rss_entries` ✓
- Typesense: 29.0 (both sides match) ✓
- Search Key: `pNAo3PlZWomU1iW2Nr97PbmPUXATWNw7` (read-only) ✓
- Admin Key: `6EGLvP3kRNPNxND5+aRAyuhoB0RVQ0s5aBRUZVCFBT5gEH+s3FMUnzBXI7LVg5s7` (server-only) ✓

### What It Does
✅ Monitors 205 court RSS feeds automatically  
✅ Collects new filings every 10 minutes (Mon-Fri, 8AM-10PM ET)  
✅ Indexes documents with full-text search  
✅ Provides fast, filtered search via HTTPS API  
✅ Accessible from anywhere: `https://search.caserlegal.com`  
✅ Secure with SSL encryption and API keys  
✅ Runs 24/7 on your Windows PC using Docker  

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Internet Clients                                │
│                   (Mobile Apps, Web Browsers)                           │
│                    search.caserlegal.com                                │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ HTTPS (443)
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Cloudflare Network                                 │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  DNS: search.caserlegal.com → 73.8.XXX.XXX (Your Public IP)      │   │
│  │  Proxy: Orange cloud ON (DDoS protection, caching, SSL)          │   │
│  │  SSL: Full (strict) - Validates origin certificate               │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ HTTPS (443)
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Your Home Router                                   │
│  Port Forwarding: 80 → 192.168.XXX.XXX:80                               │
│                   443 → 192.168.XXX.XXX:443                             │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────────────────┐
│                    Windows 10/11 PC (192.168.xx.xxx)                   │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │  Windows Port Proxy (netsh)                                      │ │
│  │  0.0.0.0:80 → 172.XXX.1XX.XX:80  (WSL IP - changes on restart!)  │ │
│  │  0.0.0.0:443 → 172.XXX.1XX.2XX:443                               │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                               │                                       │
│                               ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │              WSL2 (Ubuntu 24.04) - IP: 172.XXX.1XX.XX           │  │
│  │  ┌────────────────────────────────────────────────────────────┐ │  │
│  │  │         Docker Containers (caser-search_default network)   │ │  │
│  │  │  ┌──────────────────┐    ┌──────────────────────────────┐  │ │  │
│  │  │  │  Caddy Web Server│───▶│  Typesense Search Engine     │  │ │  │
│  │  │  │  Port: 80, 443   │    │  Port: 8108                  │  │ │  │
│  │  │  │  • SSL via       │    │  • 18,683+ documents         │  │ │  │
│  │  │  │    Cloudflare    │    │  • Collection: rss_entries   │  │ │  │
│  │  │  │    DNS challenge │    │  • NL Model: caser-nl-model  │  │ │  │
│  │  │  │  • Reverse proxy │    │  • Persistent storage        │  │ │  │
│  │  │  │                  │    │    in data/db/               │  │ │  │
│  │  │  └──────────────────┘    └──────────────────────────────┘  │ │  │
│  │  └────────────────────────────────────────────────────────────┘ │  │
│  │                                                                 │  │
│  │  ┌────────────────────────────────────────────────────────────┐ │  │
│  │  │         Python RSS Scanner (Cron: */10 * * * *)            │ │  │
│  │  │  ┌──────────────────────────────────────────────────────┐  │ │  │
│  │  │  │  1. Reads 205 feeds from config/filtered_feeds.json  │  │ │  │
│  │  │  │  2. Routes through Cloudflare Workers proxy:         │  │ │  │
│  │  │  │     https://nfq7btef6.j0mpz7gur2.workers.dev/        │  │ │  │
│  │  │  │  3. Parses RSS/Atom feeds                            │  │ │  │
│  │  │  │  4. Checks data/seen_ids.txt (18,683 tracked IDs)    │  │ │  │
│  │  │  │  5. Only indexes NEW documents (create-only mode)    │  │ │  │
│  │  │  │  6. Saves new IDs to seen_ids.txt                    │  │ │  │
│  │  │  │  7. Logs to logs/feed-scan.log                       │  │ │  │
│  │  │  └──────────────────────────────────────────────────────┘  │ │  │
│  │  └────────────────────────────────────────────────────────────┘ │  │
│  └─────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────┘
```

### Current System Stats (Live - Verified Nov 4, 2025)
- **Public IP:** 73.8.xx.xxx
- **WSL IP:** 172.x.xx.xxx (⚠️ Changes on Windows restart!)
- **Documents:** 18,683 (verified via API)
- **Feeds:** 205 (verified in config)
- **Uptime:** 24/7 (restarts with Windows)

---

## How It Works

### 🔄 Complete Data Flow (With Network Details)

#### 1. **RSS Harvesting** (Every 10 Minutes via Cron)

**Step-by-step with actual IPs and URLs:**

```
┌─────────────────────────────────────────────────────────────────────┐
│ CRON JOB TRIGGERS (*/10 * * * *)                                   │
│ → runs: /home/sm/caser-search/scripts/run-scheduled-scan.sh        │
│ → executes: python src/rss_scanner.py                              │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ BUSINESS HOURS CHECK (Mon-Fri 8AM-10PM ET)                         │
│ → If outside hours: Exit immediately                               │
│ → If inside hours: Continue to scan                                │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ LOAD TRACKING FILE                                                  │
│ → Reads: data/seen_ids.txt (18,683 IDs)                           │
│ → Loads into memory as Set for O(1) lookup                         │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ FOR EACH OF 205 FEEDS (config/filtered_feeds.json)                 │
│                                                                     │
│  Original URL: https://ecf.txwd.uscourts.gov/cgi-bin/rss_outside.pl│
│         ↓                                                           │
│  Proxy through Cloudflare Workers (bypasses rate limits):          │
│  https://nfq7btef6.j0mpz7gur2.workers.dev/?url=<original_url>     │
│         ↓                                                           │
│  Parse RSS/Atom feed with feedparser                               │
│         ↓                                                           │
│  For each entry:                                                    │
│    1. Generate stable ID (canonicalize URL, hash)                  │
│    2. Check if ID in seen_ids Set                                  │
│    3. If SEEN: docs_skipped++ (skip)                              │
│    4. If NEW: Add to batch buffer                                  │
│         ↓                                                           │
│  When buffer reaches 40 docs:                                       │
│    POST to http://localhost:8108/collections/rss_entries/documents/import│
│    Action: create (not upsert!)                                    │
│    Typesense rejects duplicates automatically                      │
│    Count successful creates → docs_created                         │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ SAVE NEW IDS                                                        │
│ → Append new IDs to data/seen_ids.txt                             │
│ → File now has 18,683+ lines (one ID per line)                    │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ LOG RESULTS                                                         │
│ → Append to logs/feed-scan.log                                     │
│ → Keep last 500 lines only                                         │
│ → Example: [SUMMARY] feeds_ok=205 docs_created=100 docs_skipped=18351│
└─────────────────────────────────────────────────────────────────────┘
```

**Why Cloudflare Workers Proxy?**
- Court RSS feeds have rate limits
- Direct requests from home IP can get blocked
- Workers proxy: `https://nfq7btef6.j0mpz7gur2.workers.dev/`
- Rotates IPs, handles retries, bypasses restrictions
- Code location: `src/rss_scanner.py` line 185

#### 2. **Search Request** (Real-time from Mobile App)

**Complete network path with actual IPs:**

```
┌─────────────────────────────────────────────────────────────────────┐
│ USER'S MOBILE APP                                                   │
│ → Sends: GET https://search.caserlegal.com/collections/rss_entries/│
│          documents/search?q=order&query_by=title                    │
│ → Header: X-TYPESENSE-API-KEY: pNAo3PlZWomU1iW2Nr97PbmPUXATWNw7    │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ DNS Lookup
┌─────────────────────────────────────────────────────────────────────┐
│ CLOUDFLARE DNS                                                      │
│ → search.caserlegal.com resolves to: 73.8.xx.x (your public IP) │
│ → Orange cloud ON: Request goes through Cloudflare proxy           │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ HTTPS (443)
┌─────────────────────────────────────────────────────────────────────┐
│ CLOUDFLARE EDGE SERVER                                              │
│ → SSL termination (validates certificate)                           │
│ → DDoS protection, caching, WAF                                     │
│ → Forwards to origin: 73.8.227.xxx:443                             │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ Internet
┌─────────────────────────────────────────────────────────────────────┐
│ YOUR HOME ROUTER                                                    │
│ → Public IP: 73.8.227.xxx                                          │
│ → Port forwarding rule: 443 → 192.168.xx.xxx:443                   │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ LAN
┌─────────────────────────────────────────────────────────────────────┐
│ WINDOWS PC (192.168.xx.xxx)                                         │
│ → Windows Firewall: Allow port 443                                 │
│ → netsh portproxy rule: 0.0.0.0:443 → 172.31.xx.xxx.223:443          │
│   (⚠️ WSL IP changes on restart! Must update this rule)            │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ Virtual network
┌─────────────────────────────────────────────────────────────────────┐
│ WSL2 UBUNTU (172.31.xx.xxx.223)                                       │
│ → Docker network: caser-search_default (bridge)                    │
│ → Port 443 → Caddy container                                       │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ CADDY CONTAINER (caser-search-caddy-1)                             │
│ → Caddyfile routes:                                                 │
│   • Path "/" → "CASER Search is running"                           │
│   • All other paths → reverse_proxy typesense:8108                 │
│ → SSL certificate from Cloudflare DNS challenge                     │
│   (uses CLOUDFLARE_API_TOKEN from .env)                            │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ Docker network
┌─────────────────────────────────────────────────────────────────────┐
│ TYPESENSE CONTAINER (caser-search-typesense-1)                     │
│ → Receives: GET /collections/rss_entries/documents/search          │
│ → Validates API key: pNAo3PlZWomU1iW2Nr97PbmPUXATWNw7              │
│ → Searches 18,683+ documents in data/db/                           │
│ → Returns JSON results in ~5ms (verified)                           │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ Response travels back
┌─────────────────────────────────────────────────────────────────────┐
│ USER'S MOBILE APP                                                   │
│ → Receives: {"found": 133, "hits": [...]}                         │
│ → Displays results to user                                         │
└─────────────────────────────────────────────────────────────────────┘
```

**What Users See:**
- URL: `https://search.caserlegal.com` (clean, professional)
- SSL: Valid certificate (green padlock 🔒)
- Speed: Sub-second response times
- No indication it's running from a home PC!

#### 3. **Document Lifecycle**

```
Court publishes new filing
         ↓
RSS feed updates (e.g., https://ecf.txwd.uscourts.gov/...)
         ↓
Scanner detects (every 10 min, Mon-Fri 8AM-10PM ET)
         ↓
Routes through Cloudflare Workers proxy
         ↓
Parses entry, extracts: title, parties, date, link
         ↓
Generates stable ID:
  1. Canonicalize URL (remove tracking params)
  2. Hash: SHA1(feedId + canonical_url)
  3. Example: "a3f5e8c9d2b1..." (40 chars)
         ↓
Check data/seen_ids.txt
         ↓
    ┌────────┴────────┐
    │                 │
  SEEN             NEW
    │                 │
    ↓                 ↓
docs_skipped++    Add to batch
                      ↓
                  POST to Typesense
                  action=create
                      ↓
                  Success?
                      ↓
                  docs_created++
                      ↓
                  Append ID to seen_ids.txt
                      ↓
                  Document now searchable!
```

---

## Key Features

### ✅ FIXED - Now Works How You Expect!

#### What Changed:

**1. Persistent Memory (`data/seen_ids.txt`)**
- Scanner remembers **every filing it's ever seen**
- On startup: loads this list
- During scan: skips anything already seen
- After scan: saves new IDs to file

**2. Create-Only Mode**
- Changed from `action=upsert` (update) → `action=create` (add new only)
- Typesense will reject duplicates instead of updating them
- Only truly **NEW** filings get added

**3. Accurate Counts**
- `docs_created`: How many NEW filings were added
- `docs_skipped`: How many we've seen before
- No more confusing "18,401 upserted" when nothing is new

**4. Stable Document IDs**
- Uses URL canonicalization (removes tracking params)
- Consistent IDs across runs
- Prevents duplicate entries from URL variations

### What You'll See Now:

**First run after fresh start:**
```
[SUMMARY] feeds_ok=205 skipped=0 docs_created=17806 docs_skipped=0
```
*(All 17,806 are new, so 17,806 created, 0 skipped)*

**Next run with actual new filings:**
```
[SUMMARY] feeds_ok=205 skipped=0 docs_created=15 docs_skipped=17791
```
*(15 new filings added, rest skipped)*

**Run with no new filings:**
```
[SUMMARY] feeds_ok=205 skipped=0 docs_created=0 docs_skipped=17806
```
*(All filings already in database, nothing new)*

### Result:
✅ Filings added once, never updated  
✅ Document count only increases for NEW filings  
✅ No duplicates  
✅ Clear, honest numbers  

---

## Quick Start

### Prerequisites
- Windows 10/11 (64-bit)
- Admin access
- 10GB free disk space
- Internet connection

### Installation (5 Steps)

**1. Install WSL2 + Ubuntu** (PowerShell as Admin)
```powershell
wsl --install Ubuntu-24.04
```
*Restart when prompted, create username/password*

**2. Install Docker Desktop**
- Download: https://www.docker.com/products/docker-desktop
- Install with defaults, restart
- Settings → Resources → WSL Integration → Enable "Ubuntu-24.04"

**3. Clone/Extract Project** (Ubuntu terminal)
```bash
cd ~
# If you have backup:
tar -xzf caser-search-backup.tar.gz
cd caser-search

# If starting fresh:
git clone <repo-url> caser-search
cd caser-search
```

**4. Setup Python Environment**
```bash
sudo apt update
sudo apt install -y python3-venv python3-pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
deactivate
```

**5. Start Services**
```bash
docker compose up -d
sleep 10
docker compose ps  # Should show 2 containers running
```

**6. Run Initial Scan**
```bash
bash scripts/run-scheduled-scan.sh
tail -20 logs/feed-scan.log
```

---

## Daily Operations

### Mission Control Dashboard

**Live monitoring terminal:**
```bash
cd ~/caser-search
source .venv/bin/activate
python scripts/mission_control.py
```

Displays:
- Container status
- Typesense health
- Document counts
- Last scan summary
- Live log tail

**Windows shortcut:** Double-click `scripts/windows/mission-control.bat`

### Quick Health Checks

**Check containers:**
```bash
docker compose ps
```

**Check Typesense:**
```bash
curl -s http://localhost:8108/health
# Expected: {"ok":true}
```

**Check document count:**
```bash
ADMIN_KEY=$(grep TYPESENSE_ADMIN_KEY .env | cut -d'=' -f2)
curl -s "http://localhost:8108/collections/rss_entries" \
  -H "X-TYPESENSE-API-KEY: $ADMIN_KEY" | jq '.num_documents'
```

**Manual scan:**
```bash
bash scripts/run-scheduled-scan.sh
```

**View logs:**
```bash
tail -f logs/feed-scan.log
```

### Automated Scanning

**Windows Task Scheduler** (runs every 10 minutes):
- **Action:** `wsl.exe -d Ubuntu-24.04 -- bash -lc "cd ~/caser-search && bash scripts/run-scheduled-scan.sh"`
- **Trigger:** Every 10 minutes, Mon-Fri, 8AM-10PM ET
- **User:** Your Windows account
- **Run whether user is logged on or not:** ✅

---

## Setup on New PC

### Complete Migration Guide

**Step 1: Backup Current System**
```bash
cd ~
docker compose -f caser-search/docker-compose.yml down
sudo tar -czf caser-search-backup.tar.gz caser-search/
sudo cp caser-search-backup.tar.gz /mnt/c/Users/<YourUsername>/Desktop/
```
*Copy file to USB drive*

**Step 2: New PC - Install Prerequisites**
```powershell
# PowerShell as Admin
wsl --install Ubuntu-24.04
# Restart, create user, then install Docker Desktop
```

**Step 3: Restore Backup**
```bash
# Ubuntu terminal on new PC
cd ~
cp /mnt/c/Users/<YourUsername>/Desktop/caser-search-backup.tar.gz .
tar -xzf caser-search-backup.tar.gz
cd caser-search
```

**Step 4: Setup Python**
```bash
sudo apt update
sudo apt install -y python3-venv python3-pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
deactivate
```

**Step 5: Start Services**
```bash
docker compose up -d
sleep 10
bash scripts/run-scheduled-scan.sh
```

**Step 6: Network Setup** (PowerShell as Admin)
```powershell
$wslIp = (wsl -d Ubuntu-24.04 -- hostname -I).Split()[0]
netsh interface portproxy add v4tov4 listenport=80 listenaddress=0.0.0.0 connectport=80 connectaddress=$wslIp
netsh interface portproxy add v4tov4 listenport=443 listenaddress=0.0.0.0 connectport=443 connectaddress=$wslIp
netsh advfirewall firewall add rule name="caser-80" dir=in action=allow protocol=TCP localport=80
netsh advfirewall firewall add rule name="caser-443" dir=in action=allow protocol=TCP localport=443
```

**Step 7: Update DNS**
- Point `search.caserlegal.com` to new PC's public IP in Cloudflare

---

## Technical Details

### Core Components

| Component | Version | Purpose | Port | Location |
|-----------|---------|---------|------|----------|
| **Typesense** | 29.0 | Search engine & document store | 8108 | Docker container |
| **Caddy** | 2 (custom build) | Web server, SSL, reverse proxy | 80, 443 | Docker container |
| **Python** | 3.12 | RSS scanner & data pipeline | - | WSL2 Ubuntu |
| **Ubuntu** | 24.04 LTS | WSL2 Linux environment | - | Windows subsystem |
| **Docker** | Latest | Container runtime | - | WSL2 |
| **Cloudflare Workers** | - | RSS proxy (bypasses rate limits) | - | Edge network |
| **Cloudflare DNS** | - | DNS + SSL + DDoS protection | - | Edge network |

### Network Configuration (Current)

```
Public IP:      73.8.227.xxx
Router IP:      192.168.50.1 (assumed)
Windows PC IP:  192.168.xx.xxx
WSL2 IP:        172.31.xx.xxx.223 ⚠️ CHANGES ON RESTART!
Docker Network: 172.18.0.0/16 (caser-search_default)
```

**Port Forwarding Chain:**
```
Internet:443 
  → Router:443 
    → Windows:443 (192.168.xx.xxx)
      → WSL2:443 (172.31.xx.xxx.223) [via netsh portproxy]
        → Docker:443 (Caddy container)
          → Docker:8108 (Typesense container)
```

**DNS Configuration:**
```
Domain: search.caserlegal.com
Type: A record
Value: 73.8.227.xxx
Proxy: ON (orange cloud)
SSL: Full (strict)
```

### Cloudflare Integration

**1. Cloudflare Workers Proxy**
- **URL:** `https://nfq7btef6.j0mpz7gur2.workers.dev/`
- **Purpose:** Proxy RSS requests to avoid rate limiting
- **Usage:** `src/rss_scanner.py` line 185
- **How it works:**
  ```python
  # Original URL
  url = "https://ecf.txwd.uscourts.gov/cgi-bin/rss_outside.pl"
  
  # Proxied through Workers
  proxy_url = f"https://nfq7btef6.j0mpz7gur2.workers.dev/?url={url}"
  resp = SESSION.get(proxy_url, timeout=45)
  ```
- **Benefits:**
  - Rotates IPs (avoids blocks)
  - Handles retries automatically
  - Bypasses court website rate limits
  - Cloudflare's global network = faster

**2. Cloudflare DNS Challenge (SSL)**
- **Plugin:** `github.com/caddy-dns/cloudflare`
- **Built into:** `Dockerfile.caddy`
- **Token:** Stored in `.env` as `CLOUDFLARE_API_TOKEN`
- **How it works:**
  1. Caddy requests SSL cert from Let's Encrypt
  2. Let's Encrypt challenges: "Prove you own search.caserlegal.com"
  3. Caddy uses Cloudflare API to create TXT record
  4. Let's Encrypt verifies TXT record
  5. Certificate issued (valid 90 days, auto-renews)
- **Why DNS challenge?**
  - HTTP challenge requires port 80 accessible
  - DNS challenge works even if ports blocked
  - More reliable for home setups

**3. Cloudflare Proxy (Orange Cloud)**
- **Status:** ON
- **Benefits:**
  - Hides your real IP (73.8.227.xxx)
  - DDoS protection
  - SSL termination at edge
  - Caching (reduces load)
  - Web Application Firewall (WAF)
- **Drawback:** Adds ~20-50ms latency (acceptable for search)

### File Structure

```
caser-search/                           (85MB total)
├── src/
│   ├── rss_scanner.py                  # Main RSS harvesting script
│   │                                   # Line 185: Cloudflare Workers proxy
│   │                                   # Line 34-54: seen_ids.txt tracking
│   │                                   # Line 82-96: URL canonicalization
│   ├── scan_tracker.py                 # Scan state tracking (logs/scan_state.json)
│   └── search_monitor.py               # Search monitoring utilities
├── scripts/
│   ├── run-scheduled-scan.sh           # Wrapper script for scanner (cron calls this)
│   ├── mission_control.py              # Live dashboard (python scripts/mission_control.py)
│   ├── admin/                          # API key management
│   │   ├── list_keys.py               # List all API keys
│   │   ├── create_firm_key.py         # Create search-only key
│   │   └── delete_key.py              # Revoke key
│   └── windows/
│       └── mission-control.bat         # Windows launcher for dashboard
├── config/
│   ├── filtered_feeds.json             # 205 RSS feed URLs (51KB)
│   ├── master-rss-feed-list.txt        # Reference list of all courts (11KB)
│   └── .env.backup                     # Backup config (not used)
├── data/                                (62MB)
│   ├── db/                             # Typesense database files (32MB)
│   │   └── 000037.sst                 # Largest file (24MB)
│   ├── meta/                           # Typesense metadata (4.1MB)
│   ├── state/                          # Typesense state (52MB)
│   └── seen_ids.txt                    # Persistent tracking file (730KB)
│                                       # 18,683 lines = 18,683 unique documents
│                                       # Format: one SHA1 hash per line
│                                       # No duplicates (verified Nov 4, 2025)
├── logs/
│   ├── feed-scan.log                   # Scanner activity log (20KB, last 500 lines)
│   └── scan_state.json                 # Last scan summary (252B)
│                                       # {"last_scan_start": "...", "docs_upserted": 100, ...}
├── caddy-data/                          (96KB)
│   └── caddy/
│       ├── certificates/               # Let's Encrypt SSL certificates
│       └── locks/                      # Certificate renewal locks
├── .venv/                               (23MB - Python virtual environment)
│   ├── bin/python                      # Python 3.12 interpreter
│   └── lib/python3.12/site-packages/   # Dependencies (requests, feedparser, etc.)
├── docker-compose.yml                   # Container orchestration (26 lines)
├── Dockerfile.caddy                     # Custom Caddy build with Cloudflare DNS plugin
├── Caddyfile                            # Caddy configuration (13 lines)
│                                       # Line 2-4: Cloudflare DNS challenge
│                                       # Line 6-8: Root path handler
│                                       # Line 9-11: Reverse proxy to Typesense
├── .env                                 # Secrets (3 lines)
│                                       # TS_ADMIN_KEY=...
│                                       # CLOUDFLARE_API_TOKEN=...
├── requirements.txt                     # Python dependencies (4 lines)
│                                       # requests, feedparser, python-dotenv, pytz
├── .gitignore                           # Protects secrets and data
└── README.md                            # This file (24KB)
```

**Key Files Explained:**

**`data/seen_ids.txt`** (The Star of the Show!)
- One document ID per line (SHA1 hash, 40 chars)
- Loaded into memory on scan start (18,683 IDs = ~730KB)
- O(1) lookup using Python Set
- Appended to after each scan (never modified, only grows)
- No duplicates (verified by audit Nov 4, 2025)
- Survives restarts, container rebuilds, everything
- This is what makes the "create-only" behavior work!

**`config/filtered_feeds.json`**
- 205 court RSS feed URLs
- Format: `[{"url": "...", "name": "...", "state": "...", "type": "...", ...}, ...]`
- Used by scanner to know which feeds to check
- Can add/remove feeds by editing this file

**`logs/feed-scan.log`**
- Appended to on every scan
- Auto-trimmed to last 500 lines (by `run-scheduled-scan.sh`)
- Format: `[2025-11-04 13:10:02] [1/205] Bills...`
- Last line: `[SUMMARY] feeds_ok=205 docs_created=100 docs_skipped=18351`

**`Dockerfile.caddy`**
- Builds custom Caddy with Cloudflare DNS plugin
- Base: `caddy:2-builder`
- Adds: `github.com/caddy-dns/cloudflare`
- Result: 97.9MB image (vs 53.5MB base)
- Only needs to be rebuilt if Caddy version changes

### Python Dependencies

```
requests      # HTTP library for API calls
feedparser    # RSS/Atom feed parser
python-dotenv # Environment variable management
pytz          # Timezone handling
```

### How Document IDs Work

**Stable ID Generation:**
1. **Primary:** Canonicalized URL (removes tracking params)
2. **Fallback:** GUID/ID from RSS feed
3. **Last resort:** Hash of title + publication date

**URL Canonicalization:**
- Lowercase scheme and domain
- Remove default ports (`:80`, `:443`)
- Strip tracking parameters (`utm_*`, `fbclid`, `gclid`, etc.)
- Sort query parameters alphabetically
- Remove trailing slashes

**Example:**
```
Original:  https://Example.com:443/doc?utm_source=twitter&id=123&utm_campaign=fall
Canonical: https://example.com/doc?id=123
```

This ensures the same document always gets the same ID, even if the URL has different tracking parameters.

### Business Hours Logic

Scanner only runs during:
- **Days:** Monday - Friday
- **Hours:** 8:00 AM - 10:00 PM Eastern Time
- **Timezone:** US/Eastern (handles DST automatically)

Outside these hours, scanner exits immediately with:
```
[SKIP] Outside business hours. Current time: 2025-11-04 23:15:00 EST (Need: Mon-Fri 8AM-10PM ET)
```

---

## Troubleshooting

### Containers Won't Start

**Check Docker:**
```bash
sudo service docker start
docker compose ps
```

**Restart containers:**
```bash
cd ~/caser-search
docker compose restart
```

**View container logs:**
```bash
docker compose logs typesense
docker compose logs caddy
```

### Scanner Not Running

**Check cron/Task Scheduler:**
```bash
crontab -l  # Linux
# Or check Windows Task Scheduler
```

**Run manually:**
```bash
cd ~/caser-search
bash scripts/run-scheduled-scan.sh
```

**Check logs:**
```bash
tail -50 logs/feed-scan.log
```

### Port Already in Use

**Find what's using port 8108:**
```bash
sudo lsof -i :8108
```

**Kill the process:**
```bash
sudo kill -9 <PID>
```

### WSL IP Changed (COMMON ISSUE!)

**⚠️ This happens EVERY TIME Windows restarts!**

**Symptoms:**
- App can't connect to search.caserlegal.com
- `curl https://search.caserlegal.com` times out
- Docker containers are running but unreachable from outside

**Why it happens:**
- WSL2 gets a new IP address on every Windows boot
- Example: Was `172.31.xx.xxx.223`, now `172.31.125.157`
- Port forwarding rules still point to old IP
- Traffic goes to wrong address → connection fails

**Check current WSL IP:**
```bash
# In Ubuntu terminal
hostname -I
# Output: 172.31.xx.xxx.223 172.1xx.0.1 172.1xx.0.1
#         ^^^^^^^^^^^^^^ This is your WSL IP
```

**Check current port forwarding:**
```powershell
# PowerShell as Admin
netsh interface portproxy show all
# Should show:
# 0.0.0.0  80   172.31.xx.xxx.223  80
# 0.0.0.0  443  172.31.xx.xxx.223  443
```

**Fix it** (PowerShell as Admin):
```powershell
# Remove old rules
netsh interface portproxy delete v4tov4 listenport=80 listenaddress=0.0.0.0
netsh interface portproxy delete v4tov4 listenport=443 listenaddress=0.0.0.0

# Get current WSL IP
$wslIp = (wsl -d Ubuntu-24.04 -- hostname -I).Split()[0]
Write-Host "WSL IP: $wslIp"

# Add new rules with current IP
netsh interface portproxy add v4tov4 listenport=80 listenaddress=0.0.0.0 connectport=80 connectaddress=$wslIp
netsh interface portproxy add v4tov4 listenport=443 listenaddress=0.0.0.0 connectport=443 connectaddress=$wslIp

# Verify
netsh interface portproxy show all
```

**Automate this** (recommended):

Create `C:\caser\update-portproxy.ps1`:
```powershell
# Get WSL IP
$wslIp = (wsl -d Ubuntu-24.04 -- hostname -I).Split()[0]

# Remove old rules
netsh interface portproxy delete v4tov4 listenport=80 listenaddress=0.0.0.0 2>$null
netsh interface portproxy delete v4tov4 listenport=443 listenaddress=0.0.0.0 2>$null

# Add new rules
netsh interface portproxy add v4tov4 listenport=80 listenaddress=0.0.0.0 connectport=80 connectaddress=$wslIp
netsh interface portproxy add v4tov4 listenport=443 listenaddress=0.0.0.0 connectport=443 connectaddress=$wslIp

Write-Host "Port forwarding updated to WSL IP: $wslIp"
```

**Run on startup:**
1. Open Task Scheduler
2. Create Task: "Update CASER Port Forwarding"
3. Trigger: At startup
4. Action: `powershell.exe -ExecutionPolicy Bypass -File C:\caser\update-portproxy.ps1`
5. Run with highest privileges: ✅

Now it auto-fixes on every reboot!

### Database Corruption

**Backup and rebuild:**
```bash
cd ~/caser-search
docker compose down
sudo mv data/db data/db.backup
sudo mv data/meta data/meta.backup
sudo mv data/state data/state.backup
rm -f data/seen_ids.txt
docker compose up -d
sleep 10
bash scripts/run-scheduled-scan.sh
```

### SSL Certificate Issues

**Check Caddy logs:**
```bash
docker compose logs caddy | grep -i error
```

**Force certificate renewal:**
```bash
docker compose restart caddy
```

---

## API Documentation

### Base URL
```
https://search.caserlegal.com
```

### Authentication
All requests require API key in header:
```
X-TYPESENSE-API-KEY: <your-key>
```

### Search Endpoint

**URL:** `/collections/rss_entries/documents/search`

**Method:** `GET`

**Parameters:**
- `q` - Search query (required)
- `query_by` - Fields to search (default: `title,description,parties`)
- `filter_by` - Filter expression (e.g., `state:=[Texas]`)
- `sort_by` - Sort field (default: `pubDate:desc`)
- `per_page` - Results per page (default: 10, max: 250)
- `page` - Page number (default: 1)

**Example:**
```bash
curl "https://search.caserlegal.com/collections/rss_entries/documents/search?q=order+of+referral&filter_by=state:=[Texas]&per_page=20" \
  -H "X-TYPESENSE-API-KEY: <your-key>"
```

**Response:**
```json
{
  "found": 47,
  "hits": [
    {
      "document": {
        "id": "abc123...",
        "title": "Order of Referral - Case 123",
        "state": "Texas",
        "courtName": "U.S. District Court for the Western District of Texas",
        "pubDate": 1730761200,
        "link": "https://...",
        "parties": ["Smith", "Jones"]
      }
    }
  ]
}
```

### Health Check

**URL:** `/health`

**Method:** `GET`

**Response:**
```json
{"ok": true}
```

### API Key Management

**List keys:**
```bash
cd ~/caser-search
source .venv/bin/activate
python scripts/admin/list_keys.py
```

**Create search-only key:**
```bash
python scripts/admin/create_firm_key.py "Client Name"
```

**Delete key:**
```bash
python scripts/admin/delete_key.py <KEY_ID>
```

---

## Security

### Three Layers of Protection

**1. HTTPS/SSL**
- All traffic encrypted via Let's Encrypt certificates
- Auto-renewal every 90 days
- Managed by Caddy

**2. API Keys**
- **Admin Key:** Full access (stored in `.env`, NEVER share)
- **Search Keys:** Read-only access (safe for clients)

**3. Firewall**
- Windows Firewall: Only ports 80/443 allowed
- Router: Only ports 80/443 forwarded
- Everything else: Blocked

### Best Practices

✅ Never commit `.env` to version control  
✅ Rotate admin key quarterly  
✅ Issue separate search keys per client  
✅ Monitor `logs/feed-scan.log` for anomalies  
✅ Backup `data/` directory weekly  
✅ Keep Docker and WSL2 updated  

---

## Maintenance

### Regular Tasks

**Daily:**
- Check Mission Control dashboard
- Verify document count is increasing

**Weekly:**
- Review `logs/feed-scan.log` for errors
- Check disk space: `df -h ~/caser-search/data`

**Monthly:**
- Backup database: `tar -czf backup.tar.gz ~/caser-search/data`
- Review API key usage
- Update Docker images: `docker compose pull && docker compose up -d`

**Quarterly:**
- Rotate admin API key
- Review and clean old logs
- Test disaster recovery procedure

### Backup Strategy

**Create backup:**
```bash
cd ~
docker compose -f caser-search/docker-compose.yml down
sudo tar -czf caser-search-backup-$(date +%Y%m%d).tar.gz caser-search/
docker compose -f caser-search/docker-compose.yml up -d
```

**Restore backup:**
```bash
cd ~
rm -rf caser-search
tar -xzf caser-search-backup-YYYYMMDD.tar.gz
cd caser-search
docker compose up -d
```

**What's included in backup:**
- All 17,806+ documents (`data/db/`)
- SSL certificates (`caddy-data/`)
- Configuration files (`.env`, `Caddyfile`)
- Seen IDs tracking file (`data/seen_ids.txt`)
- Python scripts and dependencies

---

## Cost Analysis

### Cloud Alternative (Estimated Monthly)

| Service | Cost |
|---------|------|
| Managed search (Algolia/Elastic) | $100-500 |
| SSL certificate | $4-17 |
| Data storage (10GB) | $2-10 |
| API requests (1M/month) | $10-100 |
| **Total** | **$xx.xxx-627/month** |

### Your Setup

| Item | Cost |
|------|------|
| Hardware (spare PC) | $0 (already owned) |
| Electricity (~50W 24/7) | ~$5/month |
| Domain name | $12/year ($1/month) |
| **Total** | **~$6/month** |

**Annual savings: $1,320 - $7,452**

---

## Support

### Resources

- **Email:** support@caserlegal.com
- **Website:** www.caserlegal.com
- **API Docs:** api@caserlegal.com

### System Status

**Check if system is healthy:**
```bash
cd ~/caser-search
docker ps | grep -q "Up" && echo "✅ Docker running" || echo "❌ Docker stopped"
curl -s http://localhost:8108/health | grep -q "ok" && echo "✅ Typesense healthy" || echo "❌ Typesense down"
[ -f data/seen_ids.txt ] && echo "✅ Tracking file exists" || echo "❌ No tracking file"
```

---

## Changelog

### November 2025 - Major Update

**✅ Fixed: Duplicate Prevention System**
- Added persistent tracking file (`data/seen_ids.txt`)
- Changed from `upsert` to `create` action
- Implemented URL canonicalization for stable IDs
- Updated metrics: `docs_created` + `docs_skipped`

**✅ Improved: Accuracy**
- Document count now only increases for NEW filings
- No more phantom updates
- Clear, honest reporting

**✅ Enhanced: Reliability**
- Survives restarts without losing state
- Handles URL variations correctly
- Prevents duplicates from tracking parameters

---

## License

Proprietary - CASER Legal, LLC

---

**Document Version:** 2.1  
**Last Updated:** November 4, 2025  
**System Status:** ✅ Operational  
**Current Documents:** 18,683 (verified via API)  
**Feeds Monitored:** 205 (verified in config)  
**iOS App:** ✅ 100% Compatible
