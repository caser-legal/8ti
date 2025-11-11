# CASER Monitor - Complete Server Specification

## Overview
Server-driven push notification system for legal document monitoring. All alerts originate from the server; no client-side polling or scheduling exists.

**Current System Configuration:**
- **Environment:** WSL2 Ubuntu 24.04 + Docker
- **Typesense:** localhost:8108 (internal only)
- **Execution:** Systemd timer every 5 minutes
- **Service:** caser-monitor.service + caser-monitor.timer
- **Logs:** systemd journal + /home/sm/caser-search/logs/

---

## Triggers

**Execution Schedule:**
- Run monitor job every 5 minutes via systemd timer
- Process per user only if:
  - `user_settings/{userId}.monitorAlertsEnabled == true`
  - `user_settings/{userId}.fcmToken` exists (non-empty string)

**Current Implementation:**
```bash
# Check timer status
systemctl --user status caser-monitor.timer

# View recent runs
journalctl --user -u caser-monitor.service -f
```

---

## Data Contracts

### Firestore: `user_settings/{userId}`

**Fields Used:**
```javascript
{
  monitorAlertsEnabled: boolean,
  fcmToken: string,
  keywords: [
    {
      id: string,              // unique keyword identifier
      term: string,            // search term
      enabled: boolean,        // skip if false
      notifyPush: boolean,     // send push if true
      caseSensitive: boolean,  // case-sensitive matching
      exactMatch: boolean,     // exact vs contains matching
      selectedStates: [string], // e.g., ["CA", "NY"]
      createdAt: Timestamp,
      lastCheckedAt: Timestamp | null  // null = first run
    }
  ]
}
```

### Typesense: `rss_entries` Collection

**Fields:**
- `id` / `objectID`: string (unique entry identifier)
- `title`: string
- `description`: string
- `parties`: string[]
- `courtId`: string
- `courtName`: string
- `state`: string
- `link`: string
- `pubDate`: number (Unix timestamp)
- `createdAt`: number (Unix timestamp)
- Optional: `displayTitle`, `cleanedDescription`, `modsCaseNumber`, `govinfoCitation`, `primaryDocumentURL`

### Firestore: `user_matches/{userId}/matches/{matchId}`

**Document Structure:**
```javascript
{
  id: string,              // matchId = "{keywordId}_{entryObjectID}"
  keyword: string,         // keyword.term
  keywordId: string,       // keyword.id
  caseId: string,          // entry.objectID
  courtId: string,         // entry.courtId
  title: string,           // entry.displayTitle || entry.title
  matchedText: string,     // entry.cleanedDescription || entry.description
  link: string,            // entry.link
  read: boolean,           // false (default)
  starred: boolean,        // false (default)
  notified: boolean,       // true if notifyPush == true
  createdAt: Timestamp,    // server timestamp
  pubDate: Timestamp,      // entry.pubDate || entry.createdAt
  
  // Optional (nice-to-have):
  courtName: string,
  caseNumber: string,      // modsCaseNumber
  citation: string,        // govinfoCitation
  documentUrl: string      // primaryDocumentURL
}
```

### Firestore: `activity_feed/{userId}/entries/{auto-id}`

**Document Structure:**
```javascript
{
  type: "monitor",
  title: "Monitor match: {keyword.term}",
  description: "{entry.title}",
  timestamp: Timestamp,
  monitorMetadata: {
    keyword: string,
    caseId: string,
    courtId: string,
    billableResults: 1,
    billablePages: 1
  }
}
```

---

## Matching Logic

### Per Keyword Processing

1. **Skip if disabled:**
   - If `keyword.enabled == false`, skip entirely

2. **First-run safety:**
   - If `keyword.lastCheckedAt == null`:
     - Set `lastChecked = now`
     - Write matches to Firestore
     - **DO NOT send push notifications** (prevents historical spam)
     - Update `lastCheckedAt` to current time
     - Return

3. **Subsequent runs:**
   - `lastChecked = keyword.lastCheckedAt`

### Typesense Query

**Current Configuration:**
- **Host:** localhost:8108 (Docker internal network)
- **Collection:** rss_entries
- **Documents:** 1,214,078+ indexed
- **Admin Key:** Loaded from /home/sm/caser-search/.env

**Endpoint:** `/collections/rss_entries/documents/search`

**Required Parameters:**
```javascript
{
  q: keyword.term,
  query_by: "title,description,parties",
  sort_by: "pubDate:desc",
  per_page: 100,
  page: 1  // paginate as needed (cap at 3 pages)
}
```

**Optional Filters:**
```javascript
// If keyword.selectedStates is non-empty:
filter_by: "state:=[CA,NY,TX]"  // array join
```

**Connection Example:**
```bash
# Test Typesense connectivity
ADMIN_KEY=$(grep TYPESENSE_ADMIN_KEY /home/sm/caser-search/.env | cut -d'=' -f2 | tr -d "'\"")
curl -s "http://localhost:8108/collections/rss_entries" \
  -H "X-TYPESENSE-API-KEY: $ADMIN_KEY" | jq '.num_documents'
```

### Result Filtering

**Per entry returned:**

1. **Time filter:**
   - Consider only if `(entry.pubDate || entry.createdAt) > lastChecked`

2. **Text match refinement** (optional, for client parity):
   ```javascript
   const searchable = [
     entry.title || '',
     entry.description || '',
     (entry.parties || []).join(' ')
   ].join(' ');
   
   if (keyword.exactMatch) {
     if (keyword.caseSensitive) {
       match = searchable === keyword.term;
     } else {
       match = searchable.toLowerCase() === keyword.term.toLowerCase();
     }
   } else {
     if (keyword.caseSensitive) {
       match = searchable.includes(keyword.term);
     } else {
       match = searchable.toLowerCase().includes(keyword.term.toLowerCase());
     }
   }
   ```

---

## Deduplication

**Deterministic Match ID:**
```javascript
matchId = `${keyword.id}_${entry.objectID}`
```

**Idempotency Check:**
- Before writing or pushing, check if `user_matches/{userId}/matches/{matchId}` exists
- If exists, skip (no write, no push)
- This prevents duplicates across retries and multiple runs

---

## Firestore Writes

### 1. Write Match Document

**Path:** `user_matches/{userId}/matches/{matchId}`

**Action:** Create document with fields listed in Data Contracts section

**Timing:** For every new match (after deduplication check)

### 2. Update Keyword Checkpoint

**Path:** `user_settings/{userId}`

**Action:**
```javascript
// For each keyword with ≥1 new match:
keywords[i].lastCheckedAt = Timestamp.now()

// Write back entire keywords array (merge update)
```

**Timing:** After processing all entries for a keyword

### 3. Activity Feed Entry (Optional)

**Path:** `activity_feed/{userId}/entries/{auto-id}`

**Action:** Add document with structure from Data Contracts

**Timing:** For each new match

### 4. Usage Stats

**Path:** `usage_stats/{userId}/quarters/{quarterId}`

**Action:**
```javascript
{
  monitorBillableResults: FieldValue.increment(matchCount),
  monitorBillablePages: FieldValue.increment(Math.ceil(matchCount / 10)),
  updatedAt: Timestamp.now()
}
```

**Timing:** After processing all keywords for a user

---

## Push Notification Delivery

### Conditions for Sending

Send push notification if:
- `keyword.notifyPush == true`
- `user.fcmToken` exists
- `keyword.lastCheckedAt != null` (not first run)
- `matchId` not already sent in this run

### Individual Push Payload

**FCM Target:** `user.fcmToken`

**APNs Headers:**
```javascript
{
  "apns-priority": "10",
  "apns-push-type": "alert"
}
```

**APNs Payload:**
```javascript
{
  aps: {
    alert: {
      title: "Monitor match: {keyword.term}",
      body: "{entry.title}"
    },
    sound: "default",
    "thread-id": "alerts",
    badge: <unread_count>  // computed from Firestore
  },
  matchId: "{keywordId}_{entryObjectID}",  // REQUIRED - top level
  link: "{entry.link}"                      // top level
}
```

### Summary Push Payload (Burst Control)

**Trigger:** ≥10 new matches within 30s window for a user

**APNs Headers:**
```javascript
{
  "apns-priority": "10",
  "apns-push-type": "alert",
  "apns-collapse-id": "alerts-summary"  // replaces older summaries
}
```

**APNs Payload:**
```javascript
{
  aps: {
    alert: {
      title: "{N} new matches",
      body: "Latest: {keyword.term}"
    },
    sound: "default",
    "thread-id": "alerts",
    badge: <unread_count>
  },
  matchId: "summary-{timestamp}",  // REQUIRED for badge counting
  link: "{latest-entry.link}"      // ensures tap routes to app
}
```

---

## Rate Limiting & Grouping

### Rate Limit Rules

- **Max 5 pushes per user per 30s window** (excluding summary)
- Track timestamps per user in-memory
- Filter timestamps older than 30s before checking limit

### Burst Control Logic

**Per user, after collecting all pending notifications:**

1. **If ≥10 pending notifications:**
   - Send 1 summary notification
   - Mark all matchIds as sent (add to deduplication cache)
   - Skip individual notifications

2. **If <10 pending notifications:**
   - Send individual notifications sequentially
   - Stop when rate limit reached (5 in 30s)
   - If remaining notifications exist:
     - Send 1 summary notification for remaining count
     - Mark all remaining matchIds as sent

### Implementation Flow

```javascript
async function sendNotificationsWithBurstControl(userId, fcmToken, pendingNotifications) {
  const now = Date.now();
  const recentTimestamps = getUserTimestamps(userId).filter(t => now - t < 30000);
  
  // Burst control
  if (pendingNotifications.length >= 10) {
    await sendSummaryNotification(userId, fcmToken, pendingNotifications.length, latestKeyword);
    pendingNotifications.forEach(n => markAsSent(n.matchId));
    return;
  }
  
  // Rate limiting
  let sent = 0;
  for (const notification of pendingNotifications) {
    if (recentTimestamps.length + sent >= 5) {
      const remaining = pendingNotifications.length - sent;
      if (remaining > 0) {
        await sendSummaryNotification(userId, fcmToken, remaining, notification.keyword.term);
        pendingNotifications.slice(sent).forEach(n => markAsSent(n.matchId));
      }
      break;
    }
    
    const success = await sendNotification(userId, fcmToken, notification);
    if (success) {
      recentTimestamps.push(now);
      sent++;
    }
  }
  
  updateUserTimestamps(userId, recentTimestamps);
}
```

---

## Badge Management

### Computing Badge Count

**Query:**
```javascript
const unreadCount = await db
  .collection('user_matches')
  .doc(userId)
  .collection('matches')
  .where('read', '!=', true)
  .count()
  .get();

const badge = unreadCount.data().count || 0;
```

**Timing:** Before sending each push notification (individual or summary)

### Badge Behavior

- **Server sets badge:** On every push notification
- **App reconciles badge:** When foregrounded
- **App clears badge:** When Alerts tab viewed
- **App updates `read` field:** When user opens a match
- **Server recomputes:** On next push (reflects app-side changes)

### Critical: Summary Notifications Must Include matchId

**Why:** The iOS app counts delivered notifications by `matchId` presence. If a summary lacks `matchId`, the app's `monitorCount` will be lower than `aps.badge`, causing badge inconsistency.

**Solution:** Always include `matchId` in summary payloads:
```javascript
"custom-data": {
  matchId: "summary-{timestamp}",
  batch: true
}
```

---

## Token Hygiene

### Token Source

- **Always use:** `user_settings/{userId}.fcmToken`
- **Never maintain:** Separate user-token mapping outside Firestore

### Token Validation

**On FCM send error:**
```javascript
if (error.code === 'messaging/invalid-registration-token' ||
    error.code === 'messaging/registration-token-not-registered') {
  // Remove token from Firestore
  await db.collection('user_settings').doc(userId).update({
    fcmToken: admin.firestore.FieldValue.delete()
  });
}
```

### Token Lifecycle

- **Missing token:** Skip user entirely (no processing)
- **Token changes:** Use new token immediately on next run
- **Token removed:** Treat as unsubscribed (no pushes)

---

## First-Run Safety

### Problem
New keywords with `lastCheckedAt == null` would match all historical entries, causing notification spam.

### Solution

**On first run (lastCheckedAt == null):**
1. Set `lastCheckedAt = now`
2. **Skip Typesense query entirely**
3. **Write NO matches to Firestore**
4. **Send NO push notifications**
5. Return immediately

**On subsequent runs:**
- Normal behavior: query Typesense, write matches, send pushes

---

## Monitoring & Operations

### Logging Requirements

**Per run, log:**
- Total users processed
- Total keywords evaluated
- New matches found (per user, aggregate)
- Pushes sent (individual, summary)
- Deduplication hits (skipped matches)
- Token errors (invalid/expired)

**Example log format:**
```
[2025-11-10T08:30:00Z] 🔍 Starting monitor run
[2025-11-10T08:30:05Z] User abc123: 3 keywords, 5 new matches, 4 pushes sent, 1 summary
[2025-11-10T08:30:05Z] User def456: 2 keywords, 0 new matches
[2025-11-10T08:30:10Z] ✅ Run complete: 50 users, 127 matches, 89 pushes, 12 summaries
```

### Metrics to Track

1. **Notification success rate:** `sent / attempted`
2. **Token invalidation rate:** `invalid_tokens / total_users`
3. **Burst control triggers:** `summary_count / total_runs`
4. **Rate limit hits:** `rate_limited_users / active_users`
5. **Deduplication hits:** `duplicate_skips / total_matches`
6. **First-run safety triggers:** `first_run_keywords / total_keywords`

### Alerting Thresholds

- **Push failure rate > 5%:** Investigate FCM configuration
- **Token invalidation > 10%:** Check token refresh logic
- **No matches for 6+ hours:** Verify Typesense connectivity
- **Badge mismatches reported:** Audit badge computation logic

---

## Validation Checklist

### Functional Tests

- [ ] **Toggle off:** `monitorAlertsEnabled = false` → no pushes sent
- [ ] **Toggle on:** `monitorAlertsEnabled = true` → pushes resume
- [ ] **First run:** `lastCheckedAt = null` → matches written, no pushes, timestamp updated
- [ ] **Single match:** 1 new entry → 1 push, 1 match doc, badge increments
- [ ] **Burst control:** 10+ matches → 1 summary push, all matches written
- [ ] **Rate limiting:** 7 matches in 30s → 5 individual + 1 summary for remaining 2
- [ ] **Deduplication:** Same matchId twice → only 1 write, 1 push
- [ ] **Invalid token:** FCM error → token removed from Firestore
- [ ] **Missing token:** No fcmToken → user skipped entirely
- [ ] **Badge accuracy:** Badge count matches unread count in Firestore
- [ ] **iOS grouping:** Notifications grouped under "alerts" thread
- [ ] **Summary matchId:** Summary includes `matchId` field for badge counting

### Edge Cases

- [ ] User with 0 keywords → skipped
- [ ] Keyword with empty term → skipped
- [ ] Entry with no pubDate/createdAt → skipped or use fallback
- [ ] Typesense timeout → retry with backoff
- [ ] Firestore write failure → log error, continue processing other users
- [ ] FCM send failure (non-token error) → log error, continue

---

## Implementation Notes

### Concurrency

- **User processing:** 4 concurrent (configurable via `USER_CONCURRENCY`)
- **Keyword processing:** 4 concurrent per user (configurable via `KEYWORD_CONCURRENCY`)
- **Notification sending:** Sequential per user (enforces rate limiting)

### State Management

- **In-memory (per run):**
  - `sentMatchIds`: Set<string>
  - `userPushTimestamps`: Map<userId, timestamp[]>
  
- **Persistent (Firestore):**
  - `user_matches/{userId}/matches/{matchId}`: Match documents
  - `user_settings/{userId}.keywords[].lastCheckedAt`: Checkpoint timestamps

### Performance Considerations

- **Typesense pagination:** Cap at 3 pages (300 results) per keyword
- **Firestore batch writes:** Consider batching for high-volume users
- **Badge count caching:** Cache per user for duration of run (avoid repeated queries)
- **Token cleanup:** Batch token deletions if many invalid tokens detected

---

## Deployment

### Environment Variables

**Current Configuration (.env):**
```bash
# Firebase
SERVICE_ACCOUNT_PATH=/home/sm/secrets/firebase-service-account.json

# Typesense
TYPESENSE_HOST=localhost
TYPESENSE_PORT=8108  
TYPESENSE_PROTOCOL=http
TYPESENSE_API_KEY=your-admin-key-here
COLLECTION=rss_entries

# Performance
USER_CONCURRENCY=4
KEYWORD_CONCURRENCY=4
TYPESENSE_PER_PAGE=100
TYPESENSE_MAX_PAGES=3
```

### Systemd Configuration

**Service File:** `~/.config/systemd/user/caser-monitor.service`
```ini
[Unit]
Description=CASER Firebase Monitor
After=docker.service

[Service]
Type=oneshot
WorkingDirectory=/home/sm/caser-search/push-notis
ExecStart=/usr/bin/node monitor.js
Environment=NODE_ENV=production

[Install]
WantedBy=default.target
```

**Timer File:** `~/.config/systemd/user/caser-monitor.timer`
```ini
[Unit]
Description=CASER Monitor Timer (every 5 minutes)

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min
Persistent=true

[Install]
WantedBy=timers.target
```

**Management Commands:**
```bash
# Enable and start
systemctl --user daemon-reload
systemctl --user enable --now caser-monitor.timer

# Check status
systemctl --user status caser-monitor.timer
systemctl --user list-timers | grep caser-monitor

# View logs
journalctl --user -u caser-monitor.service -f
```

### Monitoring

```bash
# Watch logs
journalctl --user -u caser-monitor.service -f

# Check recent runs
journalctl --user -u caser-monitor.service --since "1 hour ago" | grep "Monitor run complete"

# Check errors
journalctl --user -u caser-monitor.service --since "1 day ago" | grep "❌"

# Service health
systemctl --user is-active caser-monitor.timer
systemctl --user is-enabled caser-monitor.timer
```

---

## Summary

This specification ensures:
- ✅ All alerts originate from server (no client polling)
- ✅ Notifications are deduplicated (stable matchId)
- ✅ Burst control prevents spam (10+ → summary)
- ✅ Rate limiting enforced (5 per 30s)
- ✅ Badges remain consistent (server-computed, app-reconciled)
- ✅ Tokens managed hygienically (auto-cleanup on errors)
- ✅ First-run safety (no historical spam)
- ✅ Idempotent operations (safe retries)
- ✅ Proper APNs payload format (iOS compatibility)
- ✅ Activity feed and usage stats tracked

**Implementation Status:** ✅ Complete in `/home/sm/caser-search/push-notis/monitor.js`
