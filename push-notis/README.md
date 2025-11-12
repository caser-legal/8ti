# CASER Push Notification System - Complete Guide

Server-side push notification monitor for CASER legal document search. Runs every 2 minutes via systemd timer, checks user keywords against Typesense, and sends iOS push notifications via Firebase Cloud Messaging (FCM).

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Quick Start](#quick-start)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [How It Works](#how-it-works)
6. [Systemd Setup](#systemd-setup)
7. [Monitoring & Operations](#monitoring--operations)
8. [Troubleshooting](#troubleshooting)
9. [Technical Specification](#technical-specification)
10. [Quick Reference](#quick-reference)

---

## System Overview

**Current Deployment:**
- **Environment:** WSL2 Ubuntu 24.04 + Docker
- **Location:** `/home/sm/caser-search/push-notis/`
- **Execution:** Systemd user timer (every 2 minutes)
- **Typesense:** localhost:8108 (Docker container)
- **Firebase:** FCM for iOS push notifications
- **Documents:** 1,214,078+ indexed

**Architecture:**
```
WSL2 Ubuntu 24.04
├── Docker Containers
│   ├── Typesense (localhost:8108)
│   └── Caddy (ports 80/443)
├── Systemd User Services
│   ├── caser-monitor.timer (every 2min)
│   ├── caser-scan@0.timer (every 10min)
│   └── caser-scan@1.timer (every 10min)
└── Node.js Monitor (/home/sm/caser-search/push-notis/)
```

**What It Does:**
1. Queries Firestore for active user keywords every 2 minutes
2. Searches Typesense for new matching documents
3. Writes matches to Firestore (`user_matches` collection)
4. Sends push notifications to iOS devices via FCM
5. Tracks usage stats and activity feed
6. Handles rate limiting and burst control
7. Manages FCM token hygiene

---

## Quick Start

```bash
# Install Node.js 20+
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install dependencies
cd /home/sm/caser-search/push-notis
npm install

# Configure environment
cp env.example .env
nano .env  # Set SERVICE_ACCOUNT_PATH and TYPESENSE_API_KEY

# Test run
node monitor.js

# Enable systemd timer
systemctl --user daemon-reload
systemctl --user enable --now caser-monitor.timer

# Check status
systemctl --user status caser-monitor.timer
journalctl --user -u caser-monitor.service -f
```

---

## Installation

### Prerequisites

1. **Node.js 20+** installed on the server
2. **Firebase service account key** with Firestore + FCM access
3. **Typesense** running and accessible (localhost:8108)
4. **Systemd** for scheduling (user services)

### Step 1: Install Node.js

```bash
# Install Node.js 20.x
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Verify installation
node --version  # Should be v20.x or higher
npm --version
```

### Step 2: Install Dependencies

```bash
cd /home/sm/caser-search/push-notis
npm install
```

**Installs:**
- `firebase-admin` - Firebase SDK for Node.js
- `typesense` - Typesense client
- `p-map` - Concurrent processing
- `dotenv` - Environment variable management

### Step 3: Get Firebase Service Account

1. Go to [Firebase Console](https://console.firebase.google.com)
2. Select your project
3. Go to **Project Settings** → **Service Accounts**
4. Click **"Generate new private key"**
5. Save the JSON file securely

```bash
# Create secrets directory
mkdir -p /home/sm/secrets

# Move the downloaded file
mv ~/Downloads/your-project-firebase-adminsdk-xxxxx.json /home/sm/secrets/firebase-service-account.json

# Set secure permissions
chmod 600 /home/sm/secrets/firebase-service-account.json
```

---

## Configuration

### Environment Variables

```bash
cd /home/sm/caser-search/push-notis
cp env.example .env
nano .env
```

**Required Configuration:**

```bash
# Firebase service account path
SERVICE_ACCOUNT_PATH=/home/sm/secrets/firebase-service-account.json

# Typesense connection
TYPESENSE_HOST=localhost
TYPESENSE_PORT=8108
TYPESENSE_PROTOCOL=http
TYPESENSE_API_KEY=your-admin-key-here

# Performance tuning (optional)
USER_CONCURRENCY=4
KEYWORD_CONCURRENCY=4
TYPESENSE_PER_PAGE=100
TYPESENSE_MAX_PAGES=3
```

**Get Typesense Admin Key:**
```bash
grep TYPESENSE_ADMIN_KEY /home/sm/caser-search/.env
```

### Push Notification Constants

Defined in `monitor.js`:

```javascript
const BURST_THRESHOLD = 10;           // Send summary if ≥10 matches
const RATE_LIMIT_WINDOW_MS = 30000;   // 30 second window
const RATE_LIMIT_MAX_PUSHES = 5;      // Max 5 pushes per window
```

### Test Manual Run

```bash
cd /home/sm/caser-search/push-notis
node monitor.js
```

**Expected Output:**
```
🔍 Starting monitor | 14:10:13 PST - 11-11-2025
👤 1 user profiles
✅ Complete | 0 new matches | 1s
```

---

## How It Works

### Execution Flow

1. **Load user settings** from Firestore (`user_settings` collection)
2. **Filter active users:**
   - Skip if `monitorAlertsEnabled == false`
   - Skip if `fcmToken` is missing
3. **Process keywords** (4 concurrent per user):
   - Skip if `keyword.enabled == false`
   - Query Typesense for new documents since `lastCheckedAt`
   - Filter by `selectedStates` if specified
4. **Write matches** to Firestore:
   - `user_matches/{userId}/matches/{matchId}`
   - `activity_feed/{userId}/entries/{auto-id}`
   - `usage_stats/{userId}/quarters/{quarterId}`
5. **Send push notifications:**
   - Individual notifications (up to 5 per 30s window)
   - Summary notifications (if ≥10 matches)
   - Badge count from unread matches

### Key Features

**Deduplication:**
- Match ID format: `{keywordId}_{entryObjectID}`
- Prevents duplicate notifications within run
- Firestore check prevents duplicate writes

**Rate Limiting:**
- Max 5 pushes per user per 30s window
- Burst control: ≥10 matches → 1 summary notification

**First-Run Safety:**
- If `lastCheckedAt == null`, set to now and skip notifications
- Prevents spam from historical matches

**Token Hygiene:**
- Invalid/expired FCM tokens automatically removed
- Graceful error handling for token issues

### Matching Logic

**Per Keyword Processing:**

1. Skip if `keyword.enabled == false`
2. First-run safety: If `lastCheckedAt == null`:
   - Set `lastCheckedAt = now`
   - Write matches to Firestore
   - **DO NOT send push notifications**
   - Return
3. Query Typesense:
   ```javascript
   {
     q: keyword.term,
     query_by: "title,description,parties",
     sort_by: "pubDate:desc",
     per_page: 100,
     page: 1,
     filter_by: "state:=[CA,NY]"  // if selectedStates
   }
   ```
4. Filter results: Only entries with `pubDate > lastCheckedAt`
5. Write matches and send notifications

### Push Notification Payloads

**Individual Notification:**
```javascript
{
  apns: {
    headers: {
      "apns-priority": "10",
      "apns-push-type": "alert"
    },
    payload: {
      aps: {
        alert: {
          title: "Monitor match: {keyword}",
          body: "{entry.title}"
        },
        sound: "default",
        "thread-id": "alerts",
        badge: <unread_count>
      },
      matchId: "{keywordId}_{entryObjectID}",
      link: "{entry.link}"
    }
  }
}
```

**Summary Notification (≥10 matches):**
```javascript
{
  apns: {
    headers: {
      "apns-priority": "10",
      "apns-push-type": "alert",
      "apns-collapse-id": "alerts-summary"
    },
    payload: {
      aps: {
        alert: {
          title: "{N} new matches",
          body: "Latest: {keyword}"
        },
        sound: "default",
        "thread-id": "alerts",
        badge: <unread_count>
      },
      matchId: "summary-{timestamp}",
      link: "{latest-entry.link}"
    }
  }
}
```

---

## Systemd Setup

The monitor runs automatically via systemd user timer every 2 minutes.

### Service Files

**Service:** `~/.config/systemd/user/caser-monitor.service`
```ini
[Unit]
Description=CASER Monitor - Check for new court filings
After=network.target

[Service]
Type=oneshot
User=sm
WorkingDirectory=/home/sm/caser-search/push-notis
ExecStart=/usr/bin/node /home/sm/caser-search/push-notis/monitor.js
StandardOutput=append:/var/log/caser-monitor.log
StandardError=append:/var/log/caser-monitor.log

[Install]
WantedBy=multi-user.target
```

**Timer:** `~/.config/systemd/user/caser-monitor.timer`
```ini
[Unit]
Description=CASER Monitor Timer - Run every 2 minutes
Requires=caser-monitor.service

[Timer]
OnBootSec=2min
OnUnitActiveSec=2min
AccuracySec=1s

[Install]
WantedBy=timers.target
```

### Enable and Start

```bash
# Reload systemd
systemctl --user daemon-reload

# Enable timer (auto-start on boot)
systemctl --user enable caser-monitor.timer

# Start timer
systemctl --user start caser-monitor.timer

# Check status
systemctl --user status caser-monitor.timer
systemctl --user list-timers | grep caser-monitor
```

### View Logs

```bash
# Live tail
journalctl --user -u caser-monitor.service -f

# Recent runs
journalctl --user -u caser-monitor.service --since "1 hour ago"

# Check for errors
journalctl --user -u caser-monitor.service | grep "❌"

# Check completions
journalctl --user -u caser-monitor.service | grep "Complete"
```

---

## Monitoring & Operations

### Health Check

```bash
# Check timer status
systemctl --user status caser-monitor.timer

# Is timer active?
systemctl --user is-active caser-monitor.timer

# Is timer enabled?
systemctl --user is-enabled caser-monitor.timer

# When is next run?
systemctl --user list-timers | grep caser-monitor

# Recent runs
journalctl --user -u caser-monitor.service --since "1 hour ago" | grep "Complete"
```

### Manual Run

```bash
cd /home/sm/caser-search/push-notis
node monitor.js
```

### Restart Timer

```bash
systemctl --user restart caser-monitor.timer
```

### Stop Timer

```bash
systemctl --user stop caser-monitor.timer
```

### Disable Timer

```bash
systemctl --user disable caser-monitor.timer
```

### Log Analysis

```bash
# Total runs today
journalctl --user -u caser-monitor.service --since today | grep "Complete" | wc -l

# Total matches today
journalctl --user -u caser-monitor.service --since today | grep "Complete"

# Token errors
journalctl --user -u caser-monitor.service | grep "Invalid/expired FCM token"

# Summary notifications
journalctl --user -u caser-monitor.service | grep "new matches"
```

---

## Troubleshooting

### No Notifications Sent

**Check user configuration:**
```bash
# User must have:
# - fcmToken (non-empty string)
# - monitorAlertsEnabled == true
# - At least one enabled keyword
```

**Check keyword configuration:**
```bash
# Keyword must have:
# - enabled == true
# - notifyPush == true
# - lastCheckedAt != null (not first run)
# - term (non-empty string)
```

**Debug:**
```bash
# Check recent runs
journalctl --user -u caser-monitor.service --since "1 hour ago" | grep "Complete"

# Check for errors
journalctl --user -u caser-monitor.service | grep "❌"

# Manual test run
cd /home/sm/caser-search/push-notis
node monitor.js
```

### Firebase Connection Issues

**Check service account:**
```bash
# Verify file exists
ls -lh /home/sm/secrets/firebase-service-account.json

# Verify permissions (should be 600)
stat /home/sm/secrets/firebase-service-account.json

# Test Firebase connection
cd /home/sm/caser-search/push-notis
node -e "
const admin = require('firebase-admin');
const sa = require('/home/sm/secrets/firebase-service-account.json');
admin.initializeApp({ credential: admin.credential.cert(sa) });
console.log('✅ Firebase connected');
"
```

**Common errors:**
- `Missing SERVICE_ACCOUNT_PATH` - Set in `.env` file
- `ENOENT: no such file` - Check file path
- `Permission denied` - Run `chmod 600` on service account file
- `Auth error from APNS` - Invalid FCM token (auto-removed)

### Typesense Connection Issues

**Check Typesense:**
```bash
# Verify Typesense is running
docker ps | grep typesense

# Test connection
curl -s "http://localhost:8108/health"

# Test API key
ADMIN_KEY=$(grep TYPESENSE_ADMIN_KEY /home/sm/caser-search/.env | cut -d'=' -f2 | tr -d "'\"")
curl -s "http://localhost:8108/collections/rss_entries" \
  -H "X-TYPESENSE-API-KEY: $ADMIN_KEY" | jq '.num_documents'
```

**Common errors:**
- `ECONNREFUSED` - Typesense not running
- `Missing TYPESENSE_API_KEY` - Set in `.env` file
- `Unauthorized` - Wrong API key

### Timer Not Running

**Check timer status:**
```bash
# Is timer active?
systemctl --user is-active caser-monitor.timer

# Is timer enabled?
systemctl --user is-enabled caser-monitor.timer

# When is next run?
systemctl --user list-timers | grep caser-monitor

# Check for errors
systemctl --user status caser-monitor.timer
```

**Fix:**
```bash
# Reload systemd
systemctl --user daemon-reload

# Restart timer
systemctl --user restart caser-monitor.timer

# Check logs
journalctl --user -u caser-monitor.service -f
```

### Badge Count Issues

**Badge computation:**
```javascript
// Server queries Firestore before each push
const unreadCount = await db
  .collection('user_matches')
  .doc(userId)
  .collection('matches')
  .where('read', '==', false)
  .count()
  .get();

const badge = unreadCount.data().count || 0;
```

**iOS app must:**
- Update `read` field when user opens a match
- Reconcile badge when app is foregrounded
- Clear badge when Alerts tab is viewed

### Duplicate Notifications

**Deduplication logic:**
- `matchId = {keywordId}_{entryObjectID}`
- Checked before sending each notification
- Firestore document check prevents duplicate writes

**If duplicates occur:**
1. Check `sentMatchIds` Set is working
2. Verify Firestore write is checking for existing document
3. Check logs for errors

---

## Technical Specification

### Data Contracts

**Firestore: `user_settings/{userId}`**
```javascript
{
  monitorAlertsEnabled: boolean,
  fcmToken: string,
  keywords: [
    {
      id: string,
      term: string,
      enabled: boolean,
      notifyPush: boolean,
      caseSensitive: boolean,
      exactMatch: boolean,
      selectedStates: [string],
      createdAt: Timestamp,
      lastCheckedAt: Timestamp | null
    }
  ]
}
```

**Firestore: `user_matches/{userId}/matches/{matchId}`**
```javascript
{
  id: string,              // matchId = "{keywordId}_{entryObjectID}"
  keyword: string,
  keywordId: string,
  caseId: string,
  courtId: string,
  title: string,
  matchedText: string,
  link: string,
  read: boolean,
  starred: boolean,
  notified: boolean,
  createdAt: Timestamp,
  pubDate: Timestamp,
  courtName: string,
  caseNumber: string,
  citation: string,
  documentUrl: string
}
```

**Typesense: `rss_entries` Collection**
```javascript
{
  id: string,
  objectID: string,
  title: string,
  description: string,
  parties: string[],
  courtId: string,
  courtName: string,
  state: string,
  link: string,
  pubDate: number,  // Unix timestamp
  createdAt: number
}
```

### Performance

- **Typical run:** < 2 minutes
- **User concurrency:** 4 parallel
- **Keyword concurrency:** 4 per user
- **Typesense queries:** Max 300 results per keyword (3 pages × 100)
- **Rate limiting:** 5 pushes per user per 30s
- **Burst control:** ≥10 matches → 1 summary

### Security

- **Service account key:** Stored outside repo, permissions 600
- **API keys:** Never committed to git
- **Typesense:** Internal only (localhost:8108)
- **Firebase rules:** Restrict token writes to authenticated users
- **Token hygiene:** Invalid tokens auto-removed

---

## Quick Reference

### Common Commands

```bash
# Test run
cd /home/sm/caser-search/push-notis && node monitor.js

# Check status
systemctl --user status caser-monitor.timer

# View logs
journalctl --user -u caser-monitor.service -f

# Restart timer
systemctl --user restart caser-monitor.timer

# Check next run
systemctl --user list-timers | grep caser-monitor
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SERVICE_ACCOUNT_PATH` | (required) | Path to Firebase service account JSON |
| `TYPESENSE_HOST` | localhost | Typesense hostname |
| `TYPESENSE_PORT` | 8108 | Typesense port |
| `TYPESENSE_PROTOCOL` | http | Typesense protocol |
| `TYPESENSE_API_KEY` | (required) | Typesense admin API key |
| `USER_CONCURRENCY` | 4 | Concurrent users to process |
| `KEYWORD_CONCURRENCY` | 4 | Concurrent keywords per user |
| `TYPESENSE_PER_PAGE` | 100 | Results per page |
| `TYPESENSE_MAX_PAGES` | 3 | Max pages to fetch per keyword |

### Push Conditions

Send push if **ALL** true:
- ✅ `monitorAlertsEnabled == true`
- ✅ `fcmToken` exists
- ✅ `keyword.enabled == true`
- ✅ `keyword.notifyPush == true`
- ✅ `keyword.lastCheckedAt != null` (not first run)
- ✅ `matchId` not already sent

### File Structure

```
push-notis/
├── monitor.js                  # Main implementation
├── package.json                # Node.js dependencies
├── package-lock.json           # Dependency lock file
├── .env                        # Environment variables (not in git)
├── env.example                 # Environment template
├── README.md                   # This file
├── caser-monitor.service       # Systemd service file
├── caser-monitor.timer         # Systemd timer file
└── node_modules/               # Installed dependencies
```

### iOS App Integration

The iOS app must:

1. **Request FCM token:**
   ```swift
   Messaging.messaging().token { token, error in
       // Store token in Firestore
   }
   ```

2. **Store token in Firestore:**
   ```
   user_settings/{userId}.fcmToken = token
   ```

3. **Handle notifications:**
   - Parse `matchId` from notification payload
   - Update badge count
   - Route to match detail view
   - Update `read` field when match is opened

---

## Support

For issues or questions:
- **Email:** support@caserlegal.com
- **Website:** www.caserlegal.com

---

**Version:** 2.0.0  
**Last Updated:** November 11, 2025  
**Status:** ✅ Production  
**Timer Interval:** Every 2 minutes  
**Documents Indexed:** 1,214,078+
