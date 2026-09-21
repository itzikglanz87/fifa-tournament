/* ----------------------------------------------------------------------------
   Firebase project: analytics-2bf94

   These values are not secret; they identify the project, they do not grant
   access. Access is decided by firestore.rules (signed-in callers only, and
   only the tournaments/ and meta/ collections).
   -------------------------------------------------------------------------- */
window.FIREBASE_CONFIG = {
  apiKey: "AIzaSyC6jrNqzjqPZLmva-OvrYBQltrThEoR1d4",
  authDomain: "analytics-2bf94.firebaseapp.com",
  projectId: "analytics-2bf94",
  storageBucket: "analytics-2bf94.firebasestorage.app",
  messagingSenderId: "608346890313",
  appId: "1:608346890313:web:1fc83f52a8ae299d4a9f98",
  measurementId: "G-9NHMF7RGB7"
};

/* ----------------------------------------------------------------------------
   Push notifications (Firebase Cloud Messaging).

   VAPID_KEY: Firebase console → Project settings → Cloud Messaging → Web
   configuration → "Generate key pair", then paste the key here. It is the
   PUBLIC half of the pair; publishing it is how web push is meant to work.
   Until it is filled in, the "הפעל התראות" button says push is not set up.

   FUNCTIONS_REGION: where functions/index.js is deployed — must match the
   REGION constant there.

   Who may SEND: the server alone decides. Automatic "next match" pushes come
   from the server after any new result; manual messages need the admin key,
   which is never in this repo.
   -------------------------------------------------------------------------- */
window.VAPID_KEY = "PASTE_VAPID_KEY";
window.FUNCTIONS_REGION = "europe-west1";
