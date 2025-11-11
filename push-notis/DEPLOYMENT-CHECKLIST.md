# Deployment Checklist - Server-Only Push Notifications

## ✅ Completed Changes

### Code Changes
- [x] Removed `monitorAlertsEnabled` check from `processUser()`
- [x] Implemented deduplication with `sentMatchIds` Set
- [x] Added burst control (10+ matches → summary notification)
- [x] Implemented rate limiting (4 pushes per 30s window)
- [x] Updated APNs payload format with proper headers
- [x] Added server-side badge counting via `getUnreadCount()`
- [x] Implemented FCM token hygiene (auto-remove invalid tokens)
- [x] Created backup: `monitor.js.backup-YYYYMMDD-HHMMSS`

### Documentation
- [x] Created `IMPLEMENTATION.md` - Technical details
- [x] Created `test-validation.md` - Testing guide
- [x] Created `DEPLOYMENT-CHECKLIST.md` - This file

---

## 🚀 Pre-Deployment Steps

### 1. Code Review
- [ ] Review all changes in `monitor.js`
- [ ] Verify constants are correct:
  - `BURST_THRESHOLD = 10`
  - `RATE_LIMIT_WINDOW_MS = 30000` (30 seconds)
  - `RATE_LIMIT_MAX_PUSHES = 4`

### 2. Environment Check
- [ ] Verify `.env` file has all required variables:
  ```bash
  cat /home/sm/caser-search/push-notis/.env | grep -E "SERVICE_ACCOUNT_PATH|TYPESENSE_API_KEY"
  ```
- [ ] Confirm Firebase service account has FCM permissions
- [ ] Test Typesense connectivity:
  ```bash
  curl -H "X-TYPESENSE-API-KEY: $TYPESENSE_API_KEY" \
    http://localhost:8108/collections/rss_entries
  ```

### 3. Backup Current State
- [ ] Backup already created: `monitor.js.backup-*`
- [ ] Document current cron schedule:
  ```bash
  crontab -l | grep monitor.js
  ```
- [ ] Export sample Firestore data for rollback testing

---

## 🧪 Testing Phase

### Manual Test Run
```bash
cd /home/sm/caser-search/push-notis
node monitor.js
```

**Expected output:**
```
[2025-11-10T...] 🔍 Starting CASER monitor run…
Found N user profiles to evaluate.
[2025-11-10T...] ✅ Monitor run complete. New matches recorded: X
```

### Validation Checks
- [ ] No errors in console output
- [ ] Matches recorded in Firestore `user_matches` collection
- [ ] Notifications sent (check FCM logs or iOS device)
- [ ] Badge count correct on iOS device
- [ ] No duplicate notifications for same matchId

### Edge Case Testing
- [ ] User with no fcmToken → no notifications sent
- [ ] User with 10+ matches → summary notification only
- [ ] User with 5 matches → 4 individual + 1 summary
- [ ] Invalid FCM token → token removed from Firestore

---

## 📦 Production Deployment

### 1. Deploy Code
```bash
cd /home/sm/caser-search/push-notis
# Code already updated in place
```

### 2. Update Cron (if needed)
Current schedule (verify):
```bash
crontab -l
```

If not set, add:
```bash
crontab -e
# Add line:
*/5 * * * * cd /home/sm/caser-search/push-notis && /usr/bin/node monitor.js >> /var/log/caser-monitor.log 2>&1
```

### 3. Monitor First Run
```bash
# Watch logs in real-time
tail -f /var/log/caser-monitor.log

# Or check recent entries
tail -n 100 /var/log/caser-monitor.log
```

### 4. Verify Firestore Updates
- [ ] Check `user_matches` for new matches
- [ ] Verify `fcmToken` removed for invalid tokens
- [ ] Confirm `lastCheckedAt` timestamps updated

---

## 📊 Post-Deployment Monitoring

### First 24 Hours
- [ ] Monitor logs every 2 hours
- [ ] Check notification delivery rate
- [ ] Verify no error spikes
- [ ] Confirm badge counts accurate

### Key Metrics
```bash
# Total runs
grep "Monitor run complete" /var/log/caser-monitor.log | wc -l

# Total matches
grep "New matches recorded" /var/log/caser-monitor.log | tail -20

# Token errors
grep "Invalid/expired FCM token" /var/log/caser-monitor.log | wc -l

# Summary notifications
grep "new matches" /var/log/caser-monitor.log | wc -l
```

### Alert Thresholds
- **Error rate > 5%:** Investigate immediately
- **Token invalidation > 10%:** Check FCM configuration
- **No matches for 6 hours:** Verify Typesense connectivity

---

## 🔄 Rollback Procedure

If critical issues arise:

### 1. Stop Cron
```bash
crontab -e
# Comment out monitor.js line
```

### 2. Restore Previous Version
```bash
cd /home/sm/caser-search/push-notis
cp monitor.js.backup-* monitor.js
```

### 3. Verify Rollback
```bash
node monitor.js
# Check logs for expected behavior
```

### 4. Re-enable Cron
```bash
crontab -e
# Uncomment monitor.js line
```

---

## 📱 iOS App Update (Separate Task)

**Note:** Backend changes are complete, but UI toggle still exists in iOS app.

### Required iOS Changes
1. Remove "Alerts Enabled" toggle from Settings screen
2. Update settings UI to show "Push notifications managed by server"
3. Keep FCM token registration logic (still needed)
4. Update help text to explain server-only behavior

### iOS App Repository
- Location: [Specify iOS repo URL]
- File to modify: `SettingsViewController.swift` (or equivalent)
- PR required: Yes
- Testing: Verify toggle removed, notifications still work

---

## 🎯 Success Criteria

### Technical
- [x] Code deployed without errors
- [ ] Notifications sent successfully
- [ ] Deduplication working (no duplicates)
- [ ] Burst control triggered correctly
- [ ] Rate limiting enforced
- [ ] Invalid tokens removed automatically

### User Experience
- [ ] Users receive timely notifications
- [ ] Badge counts accurate
- [ ] No notification spam
- [ ] Summary notifications clear and useful

### Performance
- [ ] Monitor run completes in < 5 minutes
- [ ] No memory leaks (check after 24 hours)
- [ ] Firestore read/write counts within budget

---

## 📞 Support Contacts

- **Backend Issues:** [Your contact]
- **iOS App Issues:** [iOS team contact]
- **Firebase/FCM Issues:** [DevOps contact]
- **Typesense Issues:** [Infrastructure contact]

---

## 📝 Notes

- Deduplication cache is in-memory (resets each run)
- For cross-run deduplication, consider Firestore persistence
- Rate limiting is per-user, per-run (resets each run)
- Badge count queries Firestore on every notification send

---

**Deployment Date:** 2025-11-10  
**Deployed By:** [Your name]  
**Version:** 2.0.0 (Server-Only Push)
