import fs from 'node:fs';
import admin from 'firebase-admin';
import 'dotenv/config';

const credentialPath = process.env.SERVICE_ACCOUNT_PATH || process.env.GOOGLE_APPLICATION_CREDENTIALS;
const serviceAccount = JSON.parse(fs.readFileSync(credentialPath, 'utf-8'));

admin.initializeApp({
  credential: admin.credential.cert(serviceAccount)
});

const db = admin.firestore();

async function checkTokens() {
  const snapshot = await db.collection('user_settings').get();
  
  console.log(`Found ${snapshot.docs.length} user(s):\n`);
  
  for (const doc of snapshot.docs) {
    const data = doc.data();
    console.log(`User ID: ${doc.id}`);
    console.log(`  FCM Token: ${data.fcmToken ? '✅ Present' : '❌ Missing'}`);
    console.log(`  Token Updated: ${data.fcmTokenUpdatedAt?.toDate?.() || 'N/A'}`);
    console.log(`  Monitor Alerts: ${data.monitorAlertsEnabled ?? 'not set'}`);
    console.log(`  Keywords: ${data.keywords?.length || 0}`);
    console.log('');
  }
  
  process.exit(0);
}

checkTokens();
