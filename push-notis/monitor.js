import fs from 'node:fs';
import process from 'node:process';

import admin from 'firebase-admin';
import Typesense from 'typesense';
import pMap from 'p-map';
import 'dotenv/config';

// --- Environment & configuration ------------------------------------------------

const {
  SERVICE_ACCOUNT_PATH,
  GOOGLE_APPLICATION_CREDENTIALS,
  TYPESENSE_HOST = 'localhost',
  TYPESENSE_PORT = '8108',
  TYPESENSE_PROTOCOL = 'http',
  TYPESENSE_API_KEY,
  USER_CONCURRENCY = '4',
  KEYWORD_CONCURRENCY = '4',
  TYPESENSE_PER_PAGE = '100',
  TYPESENSE_MAX_PAGES = '3',
  SEARCH_TIMEOUT_SECONDS = '5'
} = process.env;

const credentialPath = SERVICE_ACCOUNT_PATH || GOOGLE_APPLICATION_CREDENTIALS;
if (!credentialPath) {
  console.error('❌ Missing SERVICE_ACCOUNT_PATH (or GOOGLE_APPLICATION_CREDENTIALS).');
  process.exit(1);
}

if (!TYPESENSE_API_KEY) {
  console.error('❌ Missing TYPESENSE_API_KEY in environment variables.');
  process.exit(1);
}

const serviceAccount = JSON.parse(fs.readFileSync(credentialPath, 'utf-8'));

admin.initializeApp({
  credential: admin.credential.cert(serviceAccount)
});

const db = admin.firestore();
const messaging = admin.messaging();
const Timestamp = admin.firestore.Timestamp;

const typesenseClient = new Typesense.Client({
  nodes: [
    {
      host: TYPESENSE_HOST,
      port: TYPESENSE_PORT,
      protocol: TYPESENSE_PROTOCOL
    }
  ],
  apiKey: TYPESENSE_API_KEY,
  connectionTimeoutSeconds: Number(SEARCH_TIMEOUT_SECONDS) || 5
});

const USER_WORKERS = Number(USER_CONCURRENCY) || 4;
const KEYWORD_WORKERS = Number(KEYWORD_CONCURRENCY) || 4;
const PER_PAGE = Number(TYPESENSE_PER_PAGE) || 100;
const MAX_PAGES = Number(TYPESENSE_MAX_PAGES) || 3;

// --- Helpers --------------------------------------------------------------------

const nowIso = () => new Date().toISOString();

const toDate = (value) => {
  if (!value) return null;
  if (value instanceof Date) return value;
  if (typeof value.toDate === 'function') return value.toDate();
  if (typeof value === 'number') {
    return value > 1e12 ? new Date(value) : new Date(value * 1000);
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

const getEntryDate = (entry) => {
  const candidates = [entry.pubDate, entry.createdAt, entry.updatedAt];
  for (const candidate of candidates) {
    const parsed = toDate(candidate);
    if (parsed) return parsed;
  }
  return null;
};

const buildSearchableText = (entry) => {
  const parties = Array.isArray(entry.parties) ? entry.parties.join(' ') : entry.parties ?? '';
  return [entry.title ?? '', entry.description ?? '', parties ?? ''].join(' ');
};

const matchesKeyword = (text, keyword) => {
  if (!text) return false;
  if (keyword.caseSensitive) {
    return keyword.exactMatch ? text === keyword.term : text.includes(keyword.term);
  }
  const haystack = text.toLowerCase();
  const needle = (keyword.term ?? '').toLowerCase();
  return keyword.exactMatch ? haystack === needle : haystack.includes(needle);
};

const getQuarterId = (date = new Date()) => {
  const year = date.getUTCFullYear();
  const quarter = Math.floor(date.getUTCMonth() / 3) + 1;
  return `${year}-Q${quarter}`;
};

const timestampField = (date = new Date()) => Timestamp.fromDate(date);

// --- Typesense search -----------------------------------------------------------

async function typesenseSearchWithRetry(searchParams, retries = 3) {
  for (let i = 0; i < retries; i++) {
    try {
      return await typesenseClient.collections('rss_entries').documents().search(searchParams);
    } catch (error) {
      if (i === retries - 1) throw error;
      await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1)));
    }
  }
}

async function searchTypesense(keyword, lastCheckedAt) {
  const hits = [];
  let page = 1;
  let hasMore = true;

  const filters = [];
  if (keyword.selectedStates?.length) {
    filters.push(`state:=[${keyword.selectedStates.join(',')}]`);
  }
  if (lastCheckedAt) {
    const seconds = Math.floor(lastCheckedAt.getTime() / 1000);
    filters.push(`pubDate:>=${seconds}`);
  }

  const filterBy = filters.length ? filters.join(' && ') : undefined;

  while (hasMore && page <= MAX_PAGES) {
    const searchParams = {
      q: keyword.term,
      query_by: 'title,description,parties',
      page,
      per_page: PER_PAGE,
      sort_by: 'pubDate:desc',
      filter_by: filterBy
    };

    const response = await typesenseSearchWithRetry(searchParams);
    const pageHits = response.hits ?? [];
    for (const hit of pageHits) {
      const entry = hit.document;
      const entryDate = getEntryDate(entry);
      if (!entryDate) continue;
      if (lastCheckedAt && entryDate <= lastCheckedAt) continue;

      const searchableText = buildSearchableText(entry);
      if (!matchesKeyword(searchableText, keyword)) continue;

      hits.push(entry);
    }

    hasMore = pageHits.length === PER_PAGE;
    page += 1;
  }
  return hits;
}

// --- Firestore writers ----------------------------------------------------------

async function upsertMatch(userId, keyword, entry) {
  const matchId = `${keyword.id}_${entry.objectID}`;
  const docRef = db.collection('user_matches').doc(userId).collection('matches').doc(matchId);
  const snapshot = await docRef.get();
  if (snapshot.exists) {
    return { created: false, matchId };
  }

  const entryDate = getEntryDate(entry) ?? new Date();
  const matchPayload = {
    id: matchId,
    keyword: keyword.term,
    keywordId: keyword.id,
    caseId: entry.objectID,
    courtId: entry.courtId ?? '',
    title: entry.displayTitle ?? entry.title ?? 'Untitled',
    matchedText: entry.cleanedDescription ?? entry.description ?? '',
    link: entry.link ?? '',
    notified: Boolean(keyword.notifyPush),
    read: false,
    starred: false,
    createdAt: admin.firestore.FieldValue.serverTimestamp(),
    courtName: entry.courtName ?? '',
    caseNumber: entry.modsCaseNumber ?? '',
    citation: entry.govinfoCitation ?? '',
    documentUrl: entry.primaryDocumentURL ?? '',
    pubDate: Timestamp.fromDate(entryDate)
  };

  await docRef.set(matchPayload, { merge: false });

  const activityRef = db.collection('activity_feed').doc(userId).collection('entries');
  await activityRef.add({
    type: 'monitor',
    title: `Monitor match: ${keyword.term}`,
    description: matchPayload.title,
    timestamp: admin.firestore.FieldValue.serverTimestamp(),
    monitorMetadata: {
      keyword: keyword.term,
      caseId: entry.objectID,
      courtId: entry.courtId ?? '',
      billableResults: 1,
      billablePages: 1
    }
  });

  return { created: true, matchId, entryDate };
}

async function recordMonitorUsage(userId, matches) {
  if (!matches) return;
  const quarterId = getQuarterId();
  const pageCount = Math.max(1, Math.ceil(matches / 10));
  await db
    .collection('usage_stats')
    .doc(userId)
    .collection('quarters')
    .doc(quarterId)
    .set(
      {
        monitorBillableResults: admin.firestore.FieldValue.increment(matches),
        monitorBillablePages: admin.firestore.FieldValue.increment(pageCount),
        updatedAt: admin.firestore.FieldValue.serverTimestamp()
      },
      { merge: true }
    );
}

async function updateKeywordCheckpoint(userId, keywordIndex, checkpoint) {
  if (keywordIndex < 0) return;
  const docRef = db.collection('user_settings').doc(userId);
  await docRef.update({
    [`keywords.${keywordIndex}.lastCheckedAt`]: timestampField(checkpoint)
  });
}

async function sendNotification(token, keyword, entry) {
  if (!token) return;
  try {
    await messaging.send({
      token,
      notification: {
        title: `Monitor match: ${keyword.term}`,
        body: entry.title ?? 'New filing matched your alert.'
      },
      data: {
        matchKeyword: keyword.term,
        caseTitle: entry.title ?? '',
        link: entry.link ?? ''
      },
      apns: {
        payload: {
          aps: {
            sound: 'default',
            badge: 1,
            'thread-id': 'caser-monitor-alerts',
            'interruption-level': keyword.isCritical ? 'time-sensitive' : 'active'
          }
        }
      }
    });
    return true;
  } catch (error) {
    if (error.code === 'messaging/invalid-registration-token' ||
        error.code === 'messaging/registration-token-not-registered') {
      console.warn(`⚠️ Invalid/expired FCM token ${token?.slice(0, 8)}…`);
      return null;
    }
    console.error(`⚠️ Failed to send push to token ${token?.slice(0, 8)}…: ${error.message}`);
    return false;
  }
}

// --- Processing loops -----------------------------------------------------------

async function processKeyword({ userId, keyword, keywordIndex, fcmToken }) {
  if (!keyword?.enabled || !keyword.term) return 0;

  const lastCheckedAt = toDate(keyword.lastCheckedAt) ?? new Date(0);
  const entries = await searchTypesense(keyword, lastCheckedAt);
  if (!entries.length) {
    return 0;
  }

  let createdMatches = 0;
  for (const entry of entries) {
    try {
      const { created } = await upsertMatch(userId, keyword, entry);
      if (created) {
        createdMatches += 1;
        if (keyword.notifyPush) {
          await sendNotification(fcmToken, keyword, entry);
        }
      }
    } catch (error) {
      console.error(`❌ Failed to record match for user ${userId}: ${error.message}`);
    }
  }

  if (createdMatches > 0) {
    await updateKeywordCheckpoint(userId, keywordIndex, new Date());
  }
  return createdMatches;
}

async function processUser(doc) {
  const userId = doc.id;
  const data = doc.data() ?? {};
  if (data.monitorAlertsEnabled === false) return 0;

  const keywords = Array.isArray(data.keywords) ? data.keywords : [];
  if (!keywords.length) return 0;

  const keywordContexts = keywords.map((keyword, index) => ({
    userId,
    keyword,
    keywordIndex: index,
    fcmToken: data.fcmToken
  }));

  const keywordResults = await pMap(keywordContexts, (ctx) => processKeyword(ctx), {
    concurrency: KEYWORD_WORKERS
  });

  const totalMatches = keywordResults.reduce((sum, val) => sum + (val || 0), 0);
  if (totalMatches > 0) {
    await recordMonitorUsage(userId, totalMatches);
  }

  return totalMatches;
}

// --- Entrypoint -----------------------------------------------------------------

async function main() {
  console.log(`\n[${nowIso()}] 🔍 Starting CASER monitor run…`);
  const snapshot = await db.collection('user_settings').get();
  const userDocs = snapshot.docs;
  console.log(`Found ${userDocs.length} user profiles to evaluate.`);

  const results = await pMap(userDocs, (doc) => processUser(doc), {
    concurrency: USER_WORKERS
  });

  const newMatches = results.reduce((sum, val) => sum + (val || 0), 0);
  console.log(`[${nowIso()}] ✅ Monitor run complete. New matches recorded: ${newMatches}`);
}

main()
  .then(() => {
    process.exit(0);
  })
  .catch((error) => {
    console.error(`❌ Monitor run failed: ${error.stack || error.message}`);
    process.exit(1);
  });
