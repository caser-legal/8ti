import fs from 'node:fs';
import admin from 'firebase-admin';
import 'dotenv/config';

const credentialPath = process.env.SERVICE_ACCOUNT_PATH || process.env.GOOGLE_APPLICATION_CREDENTIALS;
const serviceAccount = JSON.parse(fs.readFileSync(credentialPath, 'utf-8'));

admin.initializeApp({
  credential: admin.credential.cert(serviceAccount)
});

const db = admin.firestore();
const messaging = admin.messaging();

async function sendTestNotification() {
  const snapshot = await db.collection('user_settings').get();
  
  for (const doc of snapshot.docs) {
    const data = doc.data();
    if (data.fcmToken) {
      console.log(`Sending test notification to user ${doc.id}...`);
      
      try {
        await messaging.send({
          token: data.fcmToken,
          apns: {
            headers: {
              'apns-priority': '10',
              'apns-push-type': 'alert'
            },
            payload: {
              aps: {
                alert: {
                  title: 'Test Notification',
                  body: 'Your CASER monitor is working correctly!'
                },
                sound: 'default',
                'thread-id': 'alerts',
                badge: 1
              }
            }
          }
        });
        console.log('✅ Test notification sent successfully!');
      } catch (error) {
        console.error(`❌ Failed to send: ${error.message}`);
      }
    } else {
      console.log(`User ${doc.id} has no FCM token`);
    }
  }
  
  process.exit(0);
}

sendTestNotification();
