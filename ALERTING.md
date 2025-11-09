# 📢 ALERTING SETUP GUIDE

## Overview

CASER Search includes webhook-based alerting for critical failures. Get instant notifications in Slack, Discord, or any webhook-compatible service.

## Alerts Configured

### 1. 🔴 Backup Failures
**When:** Daily backup script fails  
**Message:** `❌ Backup failed on caser-search at 2025-11-09 03:00:00 PST`

### 2. ⚠️ High Feed Failure Rate
**When:** More than 10% of RSS feeds fail  
**Message:** `⚠️ High feed failure rate: 15% (50/326 feeds failed)`

### 3. 🔴 Typesense Down
**When:** Health check fails  
**Messages:**
- Down: `🔴 Typesense is down`
- Recovered: `✅ Typesense recovered`

## Setup (5 Minutes)

### Slack Setup

1. Go to https://api.slack.com/apps
2. Create New App → "CASER Alerts"
3. Enable Incoming Webhooks
4. Add webhook to channel
5. Copy webhook URL

### Discord Setup

1. Server Settings → Integrations → Webhooks
2. New Webhook → "CASER Alerts"
3. Copy webhook URL

### Configuration

```bash
# config/.env.local
export ALERT_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```

### Test

```bash
source config/.env.local
curl -X POST "$ALERT_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"text":"✅ Test alert from caser-search"}'
```

### Enable Health Monitoring

```bash
# Add to crontab
crontab -e

# Add this line:
*/5 * * * * /home/sm/caser-search/scripts/health-check.sh >> /home/sm/caser-search/logs/health-check.log 2>&1
```

## Troubleshooting

### No alerts received

```bash
# Check webhook URL
source config/.env.local
echo $ALERT_WEBHOOK_URL

# Test manually
curl -X POST "$ALERT_WEBHOOK_URL" -d '{"text":"Test"}'
```

### Too many alerts

Adjust thresholds:

```python
# src/rss_scanner.py line ~810
if failure_rate > 0.10:  # Change to 0.20 for 20%
```

## Disable Alerts

```bash
# config/.env.local
# export ALERT_WEBHOOK_URL="..."
```

---

**Alerting configured! You'll be notified immediately when issues occur.** 🎉
