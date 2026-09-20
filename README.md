# טורניר פיפא — אפליקציה לאנדרואיד

אותה אפליקציה בדיוק שרצה כארטיפקט, ארוזה כאתר עצמאי שאפשר להתקין בטלפון.
היא עובדת גם בלי רשת, יש לה אייקון במסך הבית, והיא נפתחת במסך מלא בלי סרגל
דפדפן.

מה יש כאן:

| קובץ | מה זה |
|---|---|
| `index.html` | האפליקציה כולה — 51 הטורנירים, התמונות, הקוד. קובץ אחד. |
| `db.js` | מתאם Firestore. חושף בדיוק את אותו ממשק שהארטיפקט חשף. |
| `firebase-config.js` | **הקובץ היחיד שצריך לערוך.** |
| `manifest.webmanifest` | מה שהופך אותה ל"אפליקציה" בעיני אנדרואיד. |
| `sw.js` | Service worker — שומר עותק מקומי כדי שתעבוד בלי רשת. |
| `firestore.rules` | כללי ההרשאות שצריך להדביק ב‑Firebase. |
| `icons/` | אייקוני האפליקציה. |

---

## 1 · Firebase — הסנכרון בין הטלפונים

בלי זה האפליקציה עובדת, אבל כל מכשיר שומר לעצמו. בשביל שכולם יראו את אותה
טבלה:

1. היכנס ל‑<https://console.firebase.google.com> ולחץ **Add project**.
   תן שם (למשל `fifa-tournament`), אפשר לכבות Google Analytics.
2. בתפריט הצד: **Build → Firestore Database → Create database**.
   בחר **Start in production mode** ואזור קרוב (`eur3` או `europe-west1`).
3. **Build → Authentication → Get started → Anonymous → Enable → Save.**
   זה מה שמאפשר לאפליקציה להיכנס לבד בלי שאף אחד יתחבר.
4. חזור ל‑**Firestore → Rules**, מחק את מה שיש, הדבק את התוכן של
   `firestore.rules` מכאן, ולחץ **Publish**.
5. גלגל שיניים (⚙) → **Project settings** → גלול ל‑**Your apps** →
   אייקון `</>` (Web) → תן שם → **Register app**.
   מופיע בלוק `firebaseConfig = { ... }`.
6. העתק את שש השורות שבתוכו לתוך `firebase-config.js` כאן, במקום
   ה‑`PASTE_...`.

הערכים האלה **אינם סוד** — הם מזהים את הפרויקט, הם לא נותנים גישה. הגישה
נקבעת ב‑`firestore.rules`.

אם `firebase-config.js` נשאר כמו שהוא, האפליקציה פשוט תרוץ מקומית ותכתוב
בתחתית המסך שהיא שומרת בדפדפן הזה בלבד.

---

## 2 · העלאה ל‑GitHub Pages

צריך כתובת `https://` אמיתית — אנדרואיד לא מתקין אפליקציה מקובץ מקומי.

```bash
# בתיקייה הזאת
git init -b main
git add -A
git commit -m "FIFA tournament app"
git remote add origin https://github.com/<שם-המשתמש-שלך>/fifa-tournament.git
git push -u origin main
```

ואז ב‑GitHub: **Settings → Pages → Source: Deploy from a branch →
Branch: `main`, folder: `/ (root)` → Save.**

אחרי דקה‑שתיים האפליקציה תהיה ב:

```
https://<שם-המשתמש-שלך>.github.io/fifa-tournament/
```

> הרפו ציבורי, כלומר הקוד, 51 הטורנירים ושש התמונות גלויים לכל מי שמגיע
> לכתובת. אם זה מפריע — אותו דבר בדיוק עובד עם רפו פרטי ב‑Netlify או
> ב‑Cloudflare Pages, בלי שינוי בקבצים.

---

## 3 · התקנה בטלפון

פתח את הכתובת ב‑**Chrome** באנדרואיד → תפריט ⋮ → **התקן אפליקציה**
(או "הוסף למסך הבית"). זהו. אייקון, מסך מלא, עובדת אופליין.

בפעם הראשונה כדאי להיות מחובר לרשת כדי שהעותק המקומי יישמר.

---

## 4 · קובץ APK להפצה

כשהאתר כבר באוויר:

1. היכנס ל‑<https://www.pwabuilder.com> והדבק את כתובת האפליקציה.
2. **Start** → הוא סורק את המניפסט ואת ה‑service worker ונותן ציון.
3. **Package for stores → Android**.
4. ב‑**Signing key** בחר **Create new** (הוא ייצר מפתח ויתן לך אותו
   בתוך ה‑zip — **שמור אותו**, בלעדיו אי אפשר לפרסם עדכונים).
5. **Download package.** בתוך ה‑zip יש `app-release-signed.apk`
   (להפצה ישירה) ו‑`app-release-bundle.aab` (ל‑Google Play).

את ה‑APK אפשר לשלוח בוואטסאפ. בטלפון שמתקין צריך לאשר פעם אחת
"התקנת אפליקציות ממקורות לא מוכרים".

> ה‑APK הזה הוא TWA — מעטפת דקה שפותחת את האתר במנוע של Chrome בלי
> סרגל. זה אומר שכל `git push` מעדכן גם את מי שהתקין את ה‑APK, בלי
> להתקין מחדש.

### Google Play

ה‑`.aab` מוכן להעלאה. מה שצריך ממך: חשבון Google Play Console
(25$ חד‑פעמי), תיאור, צילומי מסך, מדיניות פרטיות, ובדיקה של גוגל
שלוקחת בין כמה ימים לשבועיים.

---

## 5 · נעילה אמיתית

ברירת המחדל היא כניסה אנונימית: האפליקציה מתחברת לבד, ואף אחד לא צריך
להקליד כלום. זה חוסם מעבר אקראי, אבל **זה לא זהות** — מי שמגיע לדף יכול
להיכנס. לשישה חברים וארכיון פיפא זו עסקה סבירה.

לנעילה אמיתית לפי חשבונות Google:

1. ב‑Firebase: **Authentication → Sign-in method → Google → Enable.**
2. ב‑`firestore.rules`, החלף `request.auth != null` ב:

   ```
   request.auth != null && request.auth.token.email in [
     'one@gmail.com', 'two@gmail.com'   // ... כל השישה
   ]
   ```

3. ב‑`db.js`, החלף את `signInAnonymously(auth)` ב‑
   `signInWithPopup(auth, new GoogleAuthProvider())`
   (ולייבא `GoogleAuthProvider`, `signInWithPopup` במקום
   `signInAnonymously`).

---

## 6 · בנייה מחדש אחרי שינוי

הקוד האמיתי יושב בארבעה חלקים (`p1`–`p4`) ולא כאן. מהתיקייה שבה הם נמצאים:

```bash
python assemble.py     # בונה את גרסת הארטיפקט
python build_pwa.py    # בונה מחדש את pwa/index.html מאותו מקור
```

אין פיצול בין שתי הגרסאות: ההבדל היחיד הוא ש‑`Store.provider()` מעדיף את
`window.APP_DB` (Firestore) כשהוא קיים, ואת `window.claude.use("db")`
כשלא. לכן תיקון באחת הוא תיקון בשתיהן.

אחרי שינוי אמיתי, העלה את `VERSION` ב‑`sw.js` (למשל `fifa-v2`) — אחרת
מי שכבר התקין ימשיך לקבל את העותק השמור.

---

## מה לא נבדק

ה‑service worker לא נבדק בפועל — סביבת הבדיקה שבה נבנתה האפליקציה חוסמת
רישום של service workers, גם לסקריפט בן שורה אחת. הקוד נבדק תחבירית והוא
תבנית סטנדרטית, אבל **את ההתנהגות אופליין תאשר בטלפון**: טען פעם אחת עם
רשת, עבור למצב טיסה, וסגור ופתח את האפליקציה. אמורה להיפתח כרגיל.
