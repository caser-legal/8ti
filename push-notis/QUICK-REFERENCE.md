# Quick Reference Card

## 🚀 Deployment

```bash
cd /home/sm/caser-search/push-notis
node monitor.js  # Test run
tail -f /var/log/caser-monitor.log  # Monitor
```

## 📋 Key Constants

```javascript
const BURST_THRESHOLD = 10;
const RATE_LIMIT_WINDOW_MS = 30000;
const RATE_LIMIT_MAX_PUSHES = 5;
```

## ⚠️ Critical Rules

| Rule | Behavior |
|------|----------|
| `monitorAlertsEnabled == false` | Skip user |
| `fcmToken` missing | Skip user |
| `keyword.enabled == false` | Skip keyword |
| `keyword.lastCheckedAt == null` | Set to now; write NO historical matches; send NO pushes |
| `keyword.notifyPush == false` | Write matches; send NO pushes |
| Firestore `matchId` exists | Skip write/push |
| `matchId` already sent this run | Skip push |

## 📦 Match ID Format

```javascript
matchId = `${keyword.id}_${entry.objectID}`
summaryMatchId = `summary-${Date.now()}`
```

## 🔔 Push Conditions

Send push if **ALL** true:
- ✅ `monitorAlertsEnabled == true`
- ✅ `fcmToken` exists
- ✅ `keyword.enabled == true`
- ✅ `keyword.notifyPush == true`
- ✅ `keyword.lastCheckedAt != null` (not first run)
- ✅ `matchId` not already sent

## 📊 Firestore Writes

```javascript
// Match document (user_matches/{userId}/matches/{matchId})
// Required:
{
  id: string,              // matchId
  keyword: string,         // keyword.term
  keywordId: string,       // keyword.id
  caseId: string,          // entry.objectID
  createdAt: Timestamp     // server timestamp
}

// Recommended:
{
  courtId: string,
  title: string,           // entry.displayTitle || entry.title
  matchedText: string,     // entry.cleanedDescription || entry.description
  link: string,            // entry.link
  read: false,
  starred: false,
  notified: boolean,       // keyword.notifyPush
  pubDate: Timestamp,      // entry.pubDate || entry.createdAt
  courtName: string,
  caseNumber: string,      // modsCaseNumber
  citation: string,        // govinfoCitation
  documentUrl: string      // primaryDocumentURL
}

// Activity feed
activity_feed/{userId}/entries/{auto-id}

// Usage stats
usage_stats/{userId}/quarters/{quarterId}

// Keyword checkpoint
user_settings/{userId}.keywords[i].lastCheckedAt
```

## 🎯 APNs Payload

### Individual Notification
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

### Summary Notification
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

## 🔍 Typesense Query

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

## 🛡️ Token Hygiene

```javascript
// On FCM error:
if (error.code === 'messaging/invalid-registration-token' ||
    error.code === 'messaging/registration-token-not-registered') {
  await db.collection('user_settings').doc(userId).update({
    fcmToken: admin.firestore.FieldValue.delete()
  });
}
```

## 📈 Badge Computation

```javascript
const agg = await db
  .collection('user_matches').doc(userId).collection('matches')
  .where('read', '==', false).count().get();

const badge = agg.data().count || 0;
```

## 🔄 Burst Control Logic

```javascript
const now = Date.now();
const recentTimestamps = userPushTimestamps.get(userId) || [];
const windowPushCount = recentTimestamps.filter(t => now - t < RATE_LIMIT_WINDOW_MS).length;
const overBurst = pending.length >= BURST_THRESHOLD;

if (overBurst) {
  // Send 1 summary for all
  sendSummaryNotification(userId, fcmToken, pending.length, latestKeyword);
  pending.forEach(n => sentMatchIds.add(n.matchId));
} else {
  // Send up to RATE_LIMIT_MAX_PUSHES individual
  let sent = 0;
  for (const notification of pending) {
    if (windowPushCount + sent >= RATE_LIMIT_MAX_PUSHES) {
      const remaining = pending.length - sent;
      if (remaining > 0) {
        sendSummaryNotification(userId, fcmToken, remaining, notification.keyword);
        pending.slice(sent).forEach(n => sentMatchIds.add(n.matchId));
      }
      break;
    }
    sendNotification(userId, fcmToken, notification);
    sent++;
  }
}
```

## 🧪 Quick Tests

```bash
# Test single run
node monitor.js

# Check last 10 runs
grep "Monitor run complete" /var/log/caser-monitor.log | tail -10

# Check errors
grep "❌" /var/log/caser-monitor.log | tail -20

# Check token errors
grep "Invalid/expired FCM token" /var/log/caser-monitor.log

# Check summaries
grep "new matches" /var/log/caser-monitor.log | tail -10

# Validate first-run (no pushes, no historical matches written)
# Add new keyword with lastCheckedAt=null, verify only timestamp updated
```

## 🚨 Troubleshooting

| Issue | Check |
|-------|-------|
| No pushes sent | `monitorAlertsEnabled`, `fcmToken`, `notifyPush`, `lastCheckedAt != null` |
| Duplicate pushes | Deduplication logic, `sentMatchIds` |
| Wrong badge count | `getUnreadCount()` query, app `read` updates |
| Token errors | Firebase permissions, FCM config |
| Historical spam | First-run safety: `lastCheckedAt == null` → no matches written, no pushes |
| Summary tap doesn't route | Ensure `link` field includes latest entry URL |

## 📁 Files

```
push-notis/
├── monitor.js                  # Main implementation
├── SERVER-SPEC.md              # Complete specification
├── IMPLEMENTATION.md           # Technical details
├── DEPLOYMENT-CHECKLIST.md     # Deployment guide
├── test-validation.md          # Testing scenarios
├── FINAL-SUMMARY.md            # Implementation summary
├── QUICK-REFERENCE.md          # This file
└── monitor.js.backup-*         # Backup
```

## 🔗 Key Sections in SERVER-SPEC.md

- **Triggers** - When to run, what to check
- **Data Contracts** - Firestore schemas, Typesense fields
- **Matching Logic** - Query parameters, filtering
- **Deduplication** - matchId format, idempotency
- **Push Delivery** - Payload format, headers
- **Rate Limiting** - Burst control, grouping
- **Badge Management** - Computation, reconciliation
- **Token Hygiene** - Validation, cleanup
- **First-Run Safety** - Historical spam prevention
- **Validation Checklist** - Functional tests, edge cases

## ⚡ Performance

- **User concurrency:** 4 (configurable)
- **Keyword concurrency:** 4 per user (configurable)
- **Typesense pagination:** 100 per page, max 3 pages
- **Run duration:** < 5 minutes (typical)
- **Cron schedule:** Every 5 minutes

## 📞 Support

- **Logs:** `/var/log/caser-monitor.log`
- **Backup:** `monitor.js.backup-*`
- **Rollback:** `cp monitor.js.backup-* monitor.js`
- **Test:** `node monitor.js`

---

**Last Updated:** 2025-11-10  
**Version:** 2.0.0 (Server-Driven Push)
