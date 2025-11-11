# Push Notification Testing Guide

## Manual Testing Scenarios

### 1. Single Match Test
**Setup:**
- User with 1 keyword
- 1 new matching entry in Typesense
- Valid FCM token

**Expected:**
- 1 individual notification sent
- Payload includes correct APNs headers
- Badge count = unread matches
- matchId added to deduplication cache

**Validation:**
```bash
# Check logs for:
# - "✅ Monitor run complete. New matches recorded: 1"
# - No duplicate send attempts
tail -f /var/log/caser-monitor.log
```

---

### 2. Burst Control Test (10+ matches)
**Setup:**
- User with 1 keyword
- 15 new matching entries in Typesense
- Valid FCM token

**Expected:**
- 1 summary notification: "15 new matches"
- Body: "Latest: {keyword}"
- All 15 matchIds added to deduplication cache
- No individual notifications sent

**Validation:**
```bash
# Check logs for summary notification
# Verify only 1 FCM send call
grep "new matches" /var/log/caser-monitor.log
```

---

### 3. Rate Limiting Test (5 matches)
**Setup:**
- User with 1 keyword
- 5 new matching entries
- Valid FCM token
- Run twice within 30 seconds

**Expected Run 1:**
- 4 individual notifications sent
- 1 summary notification: "1 new match"

**Expected Run 2:**
- No notifications (all matchIds already sent)

**Validation:**
```bash
# Run monitor twice quickly
node monitor.js && sleep 5 && node monitor.js

# Check that second run shows 0 new matches
```

---

### 4. Deduplication Test
**Setup:**
- User with 1 keyword
- Same entry appears in multiple searches
- Valid FCM token

**Expected:**
- Only 1 notification sent for first occurrence
- Subsequent occurrences skipped (matchId in cache)

**Validation:**
```bash
# Check Firestore user_matches collection
# Should only have 1 document per matchId
```

---

### 5. Invalid Token Test
**Setup:**
- User with expired/invalid FCM token
- 1 new matching entry

**Expected:**
- FCM send fails with invalid-registration-token error
- Token removed from Firestore user_settings
- No further send attempts for this user

**Validation:**
```bash
# Check logs for:
# "⚠️ Invalid/expired FCM token for user {userId}"

# Verify Firestore:
# user_settings/{userId}.fcmToken should be deleted
```

---

### 6. Missing Token Test
**Setup:**
- User with no fcmToken field
- 1 new matching entry

**Expected:**
- Matches recorded in Firestore
- No notification attempts
- processUser returns early

**Validation:**
```bash
# Check logs - should show matches recorded but no push attempts
grep "New matches recorded" /var/log/caser-monitor.log
```

---

### 7. Badge Count Test
**Setup:**
- User with 3 unread matches in Firestore
- 1 new match triggers notification

**Expected:**
- Notification badge = 4 (3 existing + 1 new)
- Badge count queried from Firestore before each send

**Validation:**
```javascript
// Query Firestore manually:
db.collection('user_matches').doc(userId).collection('matches')
  .where('read', '==', false).count().get()
  .then(snapshot => console.log('Unread:', snapshot.data().count));
```

---

## Automated Testing (Future)

### Unit Tests Needed
```javascript
// test/monitor.test.js
describe('Push Notifications', () => {
  test('deduplication prevents duplicate sends', async () => {
    // Add matchId to sentMatchIds
    // Attempt to send notification
    // Assert: sendNotification returns false
  });

  test('burst control triggers at 10 matches', async () => {
    // Create 10 pending notifications
    // Call sendNotificationsWithBurstControl
    // Assert: sendSummaryNotification called once
  });

  test('rate limiting enforces 4 pushes per 30s', async () => {
    // Add 3 recent timestamps to userPushTimestamps
    // Attempt to send 5 notifications
    // Assert: only 1 individual + 1 summary sent
  });

  test('invalid token removed from Firestore', async () => {
    // Mock FCM error: invalid-registration-token
    // Call sendNotification
    // Assert: Firestore update called with FieldValue.delete()
  });
});
```

---

## Production Monitoring

### Key Metrics to Track
1. **Notification success rate:** `sent / attempted`
2. **Token invalidation rate:** `invalid_tokens / total_users`
3. **Burst control triggers:** `summary_notifications / total_runs`
4. **Rate limit hits:** `rate_limited_users / active_users`
5. **Deduplication hits:** `duplicate_attempts / total_matches`

### Log Patterns to Monitor
```bash
# Success
grep "✅ Monitor run complete" /var/log/caser-monitor.log

# Token errors
grep "Invalid/expired FCM token" /var/log/caser-monitor.log

# Summary notifications
grep "new matches" /var/log/caser-monitor.log

# Rate limiting
grep "remaining" /var/log/caser-monitor.log
```

---

## Rollback Plan

If issues arise, revert to previous version:

```bash
cd /home/sm/caser-search/push-notis
git log --oneline  # Find commit before changes
git checkout <commit-hash> monitor.js
node monitor.js  # Test
```

Or restore from backup:
```bash
cp monitor.js.backup monitor.js
```

---

## Next Steps

1. **Deploy to production:** Run monitor.js manually first
2. **Monitor logs:** Watch for 24 hours
3. **Validate metrics:** Check notification delivery rates
4. **iOS app update:** Remove settings toggle UI (separate repo)
5. **User communication:** Notify users of server-only push behavior
