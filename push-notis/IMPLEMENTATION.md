# Push Notification Implementation Summary

## Changes Made (2025-11-10)

### ✅ Server-Only Push Enforcement
- **REMOVED** `monitorAlertsEnabled` check from `processUser()`
- Push notifications now sent **only if** `fcmToken` is present
- No client-side toggle can disable server pushes

### ✅ Deduplication
- Implemented `sentMatchIds` Set to track sent notifications
- `matchId` format: `{keywordId}_{entryObjectID}`
- Prevents duplicate pushes for same match within run session
- Checked before sending each notification

### ✅ Burst Control
- **Threshold:** 10+ matches in single run → send summary notification
- **Summary format:**
  - Title: `{N} new matches`
  - Body: `Latest: {keyword}`
  - Uses `apns-collapse-id: alerts-summary` for iOS replacement
- All individual matches marked as sent (added to `sentMatchIds`)

### ✅ Rate Limiting
- **Window:** 30 seconds (30000ms)
- **Max pushes:** 4 per user per window
- Tracks timestamps per user in `userPushTimestamps` Map
- When limit reached, remaining matches consolidated into summary notification

### ✅ APNs Payload Format
**Individual notifications:**
```json
{
  "apns": {
    "headers": {
      "apns-priority": "10",
      "apns-push-type": "alert"
    },
    "payload": {
      "aps": {
        "alert": {
          "title": "Monitor match: {keyword}",
          "body": "{case title}"
        },
        "sound": "default",
        "thread-id": "alerts",
        "badge": <unread_count>
      },
      "custom-data": {
        "matchId": "{keywordId}_{entryObjectID}",
        "link": "{url}"
      }
    }
  }
}
```

**Summary notifications:**
```json
{
  "apns": {
    "headers": {
      "apns-priority": "10",
      "apns-push-type": "alert",
      "apns-collapse-id": "alerts-summary"
    },
    "payload": {
      "aps": {
        "alert": {
          "title": "{N} new matches",
          "body": "Latest: {keyword}"
        },
        "sound": "default",
        "thread-id": "alerts",
        "badge": <unread_count>
      }
    }
  }
}
```

### ✅ Badge Strategy
- Server-side unread count via `getUnreadCount(userId)`
- Queries Firestore: `user_matches/{userId}/matches` where `read == false`
- Badge set on every notification (individual and summary)

### ✅ FCM Token Hygiene
- Invalid/expired tokens automatically removed from Firestore
- On error codes:
  - `messaging/invalid-registration-token`
  - `messaging/registration-token-not-registered`
- Action: `fcmToken` field deleted via `FieldValue.delete()`
- Prevents repeated failed sends to dead tokens

## Architecture

### Flow
1. `processUser()` checks for `fcmToken` (skip if missing)
2. `processKeyword()` collects pending notifications (doesn't send yet)
3. All keywords processed in parallel
4. `sendNotificationsWithBurstControl()` applies logic:
   - **≥10 matches:** Send 1 summary notification
   - **<10 matches:** Send individual notifications up to rate limit
   - **Rate limit hit:** Consolidate remaining into summary

### State Management
- `sentMatchIds`: Set (in-memory, per run)
- `userPushTimestamps`: Map<userId, timestamp[]> (in-memory, per run)
- Resets on each monitor run (cron job)

### Concurrency
- User processing: 4 concurrent (configurable via `USER_CONCURRENCY`)
- Keyword processing: 4 concurrent per user (configurable via `KEYWORD_CONCURRENCY`)
- Notifications sent sequentially per user (to enforce rate limiting)

## Testing Checklist

- [ ] Single match → individual notification with correct payload
- [ ] 10+ matches → summary notification only
- [ ] 5 matches in 30s → 4 individual + 1 summary for remaining
- [ ] Duplicate matchId → no second notification
- [ ] Invalid FCM token → token removed from Firestore
- [ ] Missing fcmToken → no notifications sent
- [ ] Badge count reflects actual unread matches
- [ ] iOS groups notifications under "alerts" thread

## Configuration

No new environment variables required. Uses existing:
- `SERVICE_ACCOUNT_PATH` or `GOOGLE_APPLICATION_CREDENTIALS`
- `TYPESENSE_*` variables
- `USER_CONCURRENCY`, `KEYWORD_CONCURRENCY`

## Deployment

```bash
cd /home/sm/caser-search/push-notis
node monitor.js
```

Or via cron (existing setup):
```bash
*/5 * * * * cd /home/sm/caser-search/push-notis && /usr/bin/node monitor.js >> /var/log/caser-monitor.log 2>&1
```

## Notes

- **UI Toggle:** Backend no longer respects `monitorAlertsEnabled`. To fully remove the toggle, update the iOS app settings screen (separate repository).
- **Persistence:** Deduplication cache is in-memory. If you need cross-run deduplication, store `sentMatchIds` in Firestore with TTL.
- **Scaling:** For high-volume users, consider moving to Cloud Functions with Pub/Sub for better rate limiting across distributed runs.
