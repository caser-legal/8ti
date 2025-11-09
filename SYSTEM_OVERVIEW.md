# CASER Search - System Overview

## Current Status (Updated: 2025-11-09)

### Statistics
- **Documents Indexed:** 48,000+ (weekend steady state)
- **RSS Feeds:** 326 active (174 uscourts + 152 govinfo, 28 inactive)
- **Database Size:** ~200MB (Typesense data dir)
- **Uptime:** 24/7 automated operation
- **Public Endpoint:** https://search.caserlegal.com

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     CASER Search System                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Scanner    │  │   Monitor    │  │   Backup     │      │
│  │  (10 min)    │  │   (5 min)    │  │  (daily 3AM) │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                  │                  │               │
│         ▼                  ▼                  ▼               │
│  ┌──────────────────────────────────────────────────┐       │
│  │              Typesense (Docker)                   │       │
│  │              Port: 8108                           │       │
│  └──────────────────────────────────────────────────┘       │
│         │                                                     │
│         ▼                                                     │
│  ┌──────────────────────────────────────────────────┐       │
│  │              Caddy (Docker)                       │       │
│  │              Ports: 80, 443                       │       │
│  │              SSL: Let's Encrypt + Cloudflare      │       │
│  └──────────────────────────────────────────────────┘       │
│         │                                                     │
│         ▼                                                     │
│    Internet (search.caserlegal.com)                         │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Automated Services

| Service | Schedule | Purpose | Status |
|---------|----------|---------|--------|
| Scanner | Every 10 min | Fetch RSS feeds, index documents | ✅ Active |
| Monitor | Every 5 min | Check for matches, send Firebase notifications | ✅ Active |
| Backup | Daily 3 AM | Create Typesense snapshots | ✅ Active |

### Data Flow

1. **Scanner** fetches 326 RSS feeds every 10 minutes across two parallel shards
2. **Per-shard locks** (`data/scanner-shard-*.lock`) + the SQLite seen-id store (`data/seen_ids.sqlite3` mirrored to `seen_ids.txt`) keep duplicate detection consistent across crashes
3. **New documents** indexed in Typesense (batch upserts)
4. **Monitor** checks for keyword matches every 5 minutes
5. **Firebase notifications** sent to mobile app
6. **Daily backups** (Typesense snapshot + `seen_ids.txt`) preserve last 7 days of data

### File Structure

```
~/caser-search/
├── config/
│   ├── .env.local                    # Environment variables (secrets)
│   ├── uscourts-filtered-feed.json   # 202 court feeds (174 active)
│   └── govinfo-filtered-feed.json    # 152 govinfo feeds
├── src/
│   ├── rss_scanner.py                # Main scanner
│   └── govinfo_harvester.py          # Govinfo metadata extractor
├── scripts/
│   ├── run-scheduled-scan.sh         # Systemd scanner wrapper
│   ├── scan-now.sh                   # Manual scan trigger
│   ├── backup-typesense.sh           # Backup script
│   ├── rebuild_seen_cache.py         # Rehydrate seen_ids from Typesense
│   └── dedupe_typesense.py           # Drop/recreate collection with unique docs
├── push-notis/
│   └── monitor.js                    # Firebase notification monitor
├── data/
│   ├── db/                           # Typesense database
│   ├── meta/                         # Typesense metadata
│   ├── state/                        # Typesense state
│   ├── seen_ids.sqlite3              # Duplicate detection store (w/ WAL)
│   └── seen_ids.txt                  # Mirror for quick stats/backups
├── backups/                          # Daily Typesense snapshots
├── logs/
│   ├── feed-scan.log                 # Scanner output
│   └── scan-history.ndjson           # Scan summaries
└── docker-compose.yml                # Docker services

~/.config/systemd/user/
├── caser-scan@.service               # Scanner shard template
├── caser-scan@0.timer                # Scanner shard 0 timer (10 min)
├── caser-scan@1.timer                # Scanner shard 1 timer (10 min)
├── caser-monitor.service             # Monitor service
├── caser-monitor.timer               # Monitor timer (5 min)
├── caser-backup.service              # Backup service
└── caser-backup.timer                # Backup timer (daily)
```

### Security

- ✅ API keys stored in `.env.local` (gitignored) and loaded by scripts
- ✅ SSL/TLS via Let's Encrypt
- ✅ Cloudflare DNS protection
- ✅ Per-shard locks + SQLite duplicate store prevent overlapping writers
- ✅ Mirrored `seen_ids.sqlite3` → `seen_ids.txt` avoids torn caches
- ✅ No secrets in source code
- ✅ Daily backups with 7-day retention (Typesense snapshot + cache)

### Auto-Start Configuration

- ✅ User linger enabled: `loginctl enable-linger sm`
- ✅ All systemd timers enabled
- ✅ Docker containers restart policy: `unless-stopped`
- ✅ System survives reboots without manual intervention

### Monitoring Commands

```bash
# Scanner / timers
systemctl --user status caser-scan@0.service --no-pager
systemctl --user status caser-scan@1.service --no-pager
systemctl --user status caser-scan@0.timer --no-pager
systemctl --user status caser-scan@1.timer --no-pager
systemctl --user list-timers | grep caser

# Check document count
curl -s -H 'X-TYPESENSE-API-KEY: YOUR_KEY' \
  http://localhost:8108/collections/rss_entries | jq '.num_documents'

# Compare doc count to cache
wc -l ~/caser-search/data/seen_ids.txt

# View live logs
tail -f ~/caser-search/logs/feed-scan.log

# Expose lock status
ls ~/caser-search/data/scanner-shard-*.lock 2>/dev/null || echo "no shard locks"

# Check Docker status / snapshots
docker compose --env-file config/.env.local ps
docker compose exec typesense ls /home/sm/caser-search/backups
```

### Recovery Procedures

**If scanner stops or locks up:**
```bash
# Check for lingering lock / process
ls ~/caser-search/data/scanner-shard-*.lock
pgrep -af rss_scanner

systemctl --user restart caser-scan.timer
systemctl --user status caser-scan.service
```

**If Typesense crashes:**
```bash
cd ~/caser-search
docker compose --env-file config/.env.local restart typesense
```

**If data corruption / duplicate storm:**
```bash
# Stop services
systemctl --user stop caser-scan.timer
docker compose --env-file config/.env.local down

# Restore snapshot (replace TIMESTAMP) inside the Typesense container
docker compose up -d typesense
docker compose exec typesense bash -lc '
  SNAP=/home/sm/caser-search/backups/typesense_YYYYMMDD_HHMMSS
  typesense-server --restore-from $SNAP --data-dir /data
'

# Re-sync duplicate cache
source ~/caser-search/.venv/bin/activate && \
python ~/caser-search/scripts/rebuild_seen_cache.py

# Restart
docker compose --env-file config/.env.local up -d
systemctl --user start caser-scan.timer
```

### Performance

- **Scan duration:** ~20-30 minutes for all 326 feeds
- **Memory usage:** ~220MB (Typesense + Caddy)
- **CPU usage:** <5% average
- **Disk I/O:** Minimal (mostly reads)
- **Network:** ~10-20 MB per scan

### Maintenance

**Weekly:**
- Check logs for errors: `tail -100 ~/caser-search/logs/feed-scan.log | grep ERROR`
- Verify backups exist: `docker compose exec typesense ls /home/sm/caser-search/backups`
- Compare Typesense doc count with `wc -l data/seen_ids.txt`

**Monthly:**
- Review disk usage: `du -sh ~/caser-search/data`
- Check for feed failures: `grep "failed" ~/caser-search/logs/feed-scan.log | tail -20`

**Quarterly:**
- Update dependencies: `cd ~/caser-search && source .venv/bin/activate && pip install --upgrade -r requirements.txt`
- Review and update feed lists if courts add/remove RSS feeds
- Test the repair workflow end-to-end:
  - `bash scripts/backup-typesense.sh`
  - `python scripts/dedupe_typesense.py`
  - `python scripts/rebuild_seen_cache.py`

### Support

- Documentation: `~/caser-search/readme.md`
- Command reference: `~/caser-search/man-scan.txt`
- System overview: `~/caser-search/SYSTEM_OVERVIEW.md` (this file)
