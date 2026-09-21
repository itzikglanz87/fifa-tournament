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
   Pushes through ntfy.sh. Anyone subscribed to this topic in the ntfy app gets
   "the next match" the moment a new result is saved. The topic is the only
   key — it is in this public repo, so treat it as unlisted, not secret. To cut
   off everyone, change it here and send the new subscribe link.
   Subscribe: https://ntfy.sh/fifa-glanz-36439c219ca7
   -------------------------------------------------------------------------- */
window.PUSH_TOPIC = "fifa-glanz-36439c219ca7";
