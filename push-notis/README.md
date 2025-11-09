# CASER Monitor (Server-Side)

This folder contains a lightweight Node.js job that runs alongside your existing Typesense server (e.g. `search.caserlegal.com`). The script polls Firestore for user keywords, searches Typesense for new filings, writes matches back to Firestore, and sends push notifications through FCM — all without Firebase Cloud Functions or the Blaze plan.

## Directory Layout

```
backend/monitor/
├── monitor.js            # Main script (run manually or via cron)
├── package.json          # Node.js metadata / dependencies
├── package-lock.json     # Generated after `npm install`
├── .env.example          # Sample environment variables
└── README.md             # This file
```

The Firebase service-account JSON **is not** stored here. Place it somewhere secure on the server (e.g. `/root/firebase-service-account.json`) and point to it via `SERVICE_ACCOUNT_PATH` or `GOOGLE_APPLICATION_CREDENTIALS`.

## Prerequisites

1. **Server access** (SSH) to the machine that already hosts Typesense.
2. **Node.js 20+** installed on that server.
3. **Firebase service-account key** with Firestore + FCM access (`Project Settings → Service Accounts → Generate new private key`).
4. **Typesense admin API key**.

## Setup

```bash
cd /path/to/backend/monitor
npm install
cp .env.example .env
```

Edit `.env` and provide:

- `SERVICE_ACCOUNT_PATH` – absolute path to the Firebase service-account JSON.
- `TYPESENSE_*` values – host, port, protocol, and admin key for your Typesense instance.
- Optional concurrency / pagination overrides (see `.env.example` for defaults).

## Running Manually

```bash
node monitor.js
```

Watch logs:

```bash
tail -f /var/log/caser-monitor.log
```

## Scheduling with Cron (Example)

```bash
*/5 * * * * cd /root/backend/monitor && /usr/bin/node monitor.js >> /var/log/caser-monitor.log 2>&1
```

Adjust the schedule as needed (e.g., `*/1` for every minute). The script exits after each run, making it cron-friendly.

## iOS App Integration

1. Request the FCM token on the device via `Messaging.messaging().token`.
2. Store it in `user_settings/{uid}.fcmToken` (merge update).
3. Update Firestore rules to allow owners to write `fcmToken` and `fcmTokenUpdatedAt`.

## Security Notes

- Keep the service-account key outside the repo and restrict permissions (`chmod 600`).
- Never expose Typesense admin keys or Firebase creds over HTTP.
- Rotate keys if the server is compromised.

## Extending

- Adjust the cron frequency or concurrency env vars (`USER_CONCURRENCY`, `KEYWORD_CONCURRENCY`).
- Add structured logging / monitoring if desired.
- When you eventually move to Firebase Blaze, the same logic can be ported to Cloud Functions or Cloud Run.
