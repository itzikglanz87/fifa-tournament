# -*- coding: utf-8 -*-
"""קורא את לוח התוצאות של FC 27 מהמצלמה ושולח אותו לאפליקציה.

    python tools/score_cam.py --calibrate      פעם אחת: לסמן איפה התוצאה במסך
    python tools/score_cam.py                  להריץ בזמן הטורניר
    python tools/score_cam.py --test           לראות מה המצלמה קוראת, בלי לשלוח

המצלמה מחוברת ב‑USB (--source 0) או ברשת (--source rtsp://user:pass@ip:554/…).
השליחה עוברת דרך אותו שרת ששולח את הפושים, עם מפתח האדמין, והיא מעדכנת את
המשחק שפתוח כרגע כ"חי" באפליקציה — לכן קודם לוחצים באפליקציה "התחל משחק חי".

הגנות מפני קריאה שגויה (ריפליי, חגיגת גול, השתקפות במסך):
  · כל תוצאה חייבת להיקרא אותו דבר כמה פעמים ברצף לפני שהיא נשלחת
  · תוצאה לא יורדת אף פעם — גם השרת מסרב להוריד גולים
  · קפיצה של יותר מגול אחד בבת אחת נדחית, אלא אם היא חוזרת על עצמה
"""
import argparse, io, json, os, re, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "score_cam.json")
KEY_FILE_DEFAULT = r"C:\Users\PC\OneDrive\Claude\Claude\מפתח אדמין - טורניר פיפא.txt"
ENDPOINT = "https://europe-west1-analytics-2bf94.cloudfunctions.net/liveScore"


def load_cfg():
    if os.path.exists(CFG):
        with io.open(CFG, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cfg(cfg):
    with io.open(CFG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print("נשמר:", CFG)


def admin_key(path):
    """the key file holds the key among other text; take the long token"""
    with io.open(path, encoding="utf-8-sig") as f:
        text = f.read()
    for tok in re.findall(r"[A-Za-z0-9]{16,}", text):
        return tok
    raise SystemExit("לא נמצא מפתח אדמין בקובץ " + path)


def open_camera(source):
    import cv2
    src = int(source) if str(source).isdigit() else source
    cap = cv2.VideoCapture(src, cv2.CAP_DSHOW if isinstance(src, int) and os.name == "nt" else cv2.CAP_ANY)
    if isinstance(src, int):                      # ask a USB camera for its best frame
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 3840)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 2160)
    if not cap.isOpened():
        raise SystemExit("המצלמה לא נפתחה (--source " + str(source) + ")")
    return cap


def grab(cap):
    ok, frame = cap.read()
    if not ok or frame is None:
        return None
    return frame


def list_cameras(args):
    """grab one picture from each camera on the computer and save it, so the
       right one can be recognised by looking"""
    import cv2
    found = []
    for i in range(6):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY)
        if not cap.isOpened():
            cap.release()
            continue
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 3840)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 2160)
        frame = None
        for _ in range(10):
            f = grab(cap)
            if f is not None:
                frame = f
            time.sleep(0.05)
        cap.release()
        if frame is None:
            continue
        path = os.path.join(HERE, "camera_%d.png" % i)
        cv2.imwrite(path, frame)
        found.append((i, frame.shape[1], frame.shape[0], path))
        print("מצלמה %d — %dx%d — %s" % (i, frame.shape[1], frame.shape[0], path))
    if not found:
        print("לא נמצאה אף מצלמה")
        return
    print("")
    print("פתח את התמונות, ראה איזו מצלמה מכוונת לטלוויזיה, והרץ עם המספר שלה:")
    print("   python tools/score_cam.py --calibrate --source <מספר>")


def calibrate(args):
    """show the picture, let the user draw a box around each number"""
    import cv2
    cap = open_camera(args.source)
    print("מכוון את המצלמה… חלון ייפתח עם התמונה. סמן ריבוע סביב המספר ולחץ Enter.")
    frame = None
    for _ in range(30):                            # let exposure settle
        f = grab(cap)
        if f is not None:
            frame = f
        time.sleep(0.05)
    if frame is None:
        raise SystemExit("לא התקבלה תמונה מהמצלמה")
    cv2.imwrite(os.path.join(HERE, "score_cam_frame.png"), frame)
    boxes = {}
    for side, label in (("home", "השערים של הקבוצה הימנית בלוח (הבית)"), ("away", "השערים של הקבוצה השמאלית (החוץ)")):
        print("סמן:", label)
        r = cv2.selectROI("סמן את " + side + " ולחץ Enter", frame, showCrosshair=True)
        cv2.destroyAllWindows()
        if r[2] < 4 or r[3] < 4:
            raise SystemExit("לא סומן ריבוע")
        boxes[side] = [int(r[0]), int(r[1]), int(r[2]), int(r[3])]
    cap.release()
    cfg = load_cfg()
    cfg.update({"source": args.source, "home": boxes["home"], "away": boxes["away"]})
    save_cfg(cfg)
    print("אפשר להריץ עכשיו:  python tools/score_cam.py")


# ---------------------------------------------------------------- reading a number
# The camera is fixed and the game's font never changes, so the digits are cut
# out and matched against digit shapes rendered from a few system fonts. That
# beats general OCR here: it reads small, slightly blurred digits off a screen,
# needs nothing installed, and runs in milliseconds.
DW, DH = 24, 32
TPL_FONTS = ["arialbd.ttf", "segoeuib.ttf", "tahomabd.ttf", "verdanab.ttf", "calibrib.ttf"]
_TPL = None


def templates():
    global _TPL
    if _TPL is not None:
        return _TPL
    import cv2, numpy as np
    from PIL import Image, ImageDraw, ImageFont
    def render(ch, path, size=120):
        f = ImageFont.truetype(path, size)
        im = Image.new("L", (size * 2, int(size * 1.6)), 0)
        ImageDraw.Draw(im).text((size, int(size * 0.8)), ch, font=f, fill=255, anchor="mm")
        a = np.array(im)
        ys, xs = np.where(a > 40)
        a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        a = cv2.resize(a, (DW, DH), interpolation=cv2.INTER_AREA).astype(np.float32)
        a -= a.mean()
        n = np.linalg.norm(a)
        return a / n if n else a
    fonts = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", f) for f in TPL_FONTS]
    fonts = [f for f in fonts if os.path.exists(f)]
    if not fonts:
        raise SystemExit("לא נמצאו גופנים לבניית התבניות")
    _TPL = {str(d): [render(str(d), f) for f in fonts] for d in range(10)}
    return _TPL


LEARNED = os.path.join(HERE, "digits")


def learned_templates():
    """digit pictures taken off this television by --teach, if there are any"""
    import cv2, numpy as np
    out = {}
    if not os.path.isdir(LEARNED):
        return out
    for d in os.listdir(LEARNED):
        folder = os.path.join(LEARNED, d)
        if not (d.isdigit() and os.path.isdir(folder)):
            continue
        for name in os.listdir(folder):
            a = cv2.imread(os.path.join(folder, name), cv2.IMREAD_GRAYSCALE)
            if a is None:
                continue
            a = cv2.resize(a, (DW, DH), interpolation=cv2.INTER_AREA).astype(np.float32)
            a -= a.mean()
            n = np.linalg.norm(a)
            if n:
                out.setdefault(d, []).append(a / n)
    return out


def digit_boxes(img):
    """the digit shapes inside one box, left to right"""
    import cv2
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    g = cv2.resize(g, None, fx=6, fy=6, interpolation=cv2.INTER_CUBIC)
    g = cv2.GaussianBlur(g, (5, 5), 0)
    if g[[0, -1], :].mean() > g.mean():          # always end up light digits on dark
        g = 255 - g
    _, th = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    cnts, _h = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    H, W = th.shape
    out = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if h > H * 0.45 and w > 3 and w < W * 0.9 and h < H * 0.99:
            out.append((th[y:y + h, x:x + w], x))
    return sorted(out, key=lambda b: b[1])


def read_number(img, min_score=0.62, debug=None):
    """the number inside one box, or None when nothing digit-like is there"""
    import cv2, numpy as np
    boxes = digit_boxes(img)
    if not boxes or len(boxes) > 2:
        return None
    TPL = dict(templates())
    for d, v in learned_templates().items():       # your own digits come first
        TPL[d] = v + TPL.get(d, [])
    digits, worst = "", 1.0
    for img_b, _x in boxes:
        b = cv2.resize(img_b, (DW, DH), interpolation=cv2.INTER_AREA).astype(np.float32)
        b -= b.mean()
        n = np.linalg.norm(b)
        if not n:
            return None
        b /= n
        best, bs = None, -2.0
        for d, tl in TPL.items():
            sc = max(float((b * t).sum()) for t in tl)
            if sc > bs:
                best, bs = d, sc
        if bs < min_score:
            return None
        digits += best
        worst = min(worst, bs)
    if debug is not None:
        debug["score"] = round(worst, 2)
    v = int(digits)
    return v if v <= 30 else None


def learn_from(crop, value, side, cap_per_digit=12):
    """keep the digits of a score we are sure about, so the next reading of
       that digit is a match against this very television"""
    import cv2
    txt = str(value)
    boxes = digit_boxes(crop)
    if len(boxes) != len(txt):
        return 0
    saved = 0
    for (img_b, _x), ch in zip(boxes, txt):
        folder = os.path.join(LEARNED, ch)
        os.makedirs(folder, exist_ok=True)
        if len(os.listdir(folder)) >= cap_per_digit:
            continue
        cv2.imwrite(os.path.join(folder, "%s_%d.png" % (side, int(time.time() * 1000))), img_b)
        saved += 1
    return saved


def teach(args):
    """save what is on the television right now as the shapes of those digits"""
    import cv2
    cfg = load_cfg()
    if "home" not in cfg:
        raise SystemExit("קודם כיול:  python tools/score_cam.py --calibrate")
    cap = open_camera(args.source if args.source is not None else cfg.get("source", 0))
    print("עצור את המשחק על תוצאה ברורה. לסיום: Enter ריק.")
    try:
        while True:
            ans = input("מה התוצאה על המסך עכשיו? (למשל 2-1) ").strip()
            if not ans:
                break
            m = re.match(r"^(\d{1,2})\s*[-:]\s*(\d{1,2})$", ans)
            if not m:
                print("   בפורמט 2-1 בבקשה")
                continue
            frame = None
            for _ in range(8):
                f = grab(cap)
                if f is not None:
                    frame = f
            if frame is None:
                print("   אין תמונה מהמצלמה")
                continue
            for side, val in (("home", m.group(1)), ("away", m.group(2))):
                bx = cfg[side]
                crop = frame[bx[1]:bx[1] + bx[3], bx[0]:bx[0] + bx[2]]
                boxes = digit_boxes(crop)
                if len(boxes) != len(val):
                    print("   " + side + ": נמצאו " + str(len(boxes)) + " ספרות ולא " + str(len(val)) +
                          " — בדוק תאורה או כייל מחדש")
                    continue
                for (img_b, _x), ch in zip(boxes, val):
                    folder = os.path.join(LEARNED, ch)
                    os.makedirs(folder, exist_ok=True)
                    cv2.imwrite(os.path.join(folder, "%s_%d.png" % (side, int(time.time() * 1000))), img_b)
                print("   " + side + ": נשמר " + val)
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        cap.release()
    print("התבניות נשמרו ב־" + LEARNED)


def send(key, h, a, dry):
    if dry:
        print("   (בדיקה בלבד — לא נשלח)")
        return {"dry": True}
    body = json.dumps({"data": {"key": key, "h": h, "a": a}}).encode()
    req = urllib.request.Request(ENDPOINT, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode()).get("result", {})


def ping(key):
    """tell the app the computer is here, and ask whether to read right now"""
    body = json.dumps({"data": {"key": key, "ping": True, "h": 0, "a": 0}}).encode()
    req = urllib.request.Request(ENDPOINT, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode()).get("result", {})


def run(args):
    import cv2
    cfg = load_cfg()
    if "home" not in cfg or "away" not in cfg:
        raise SystemExit("קודם כיול:  python tools/score_cam.py --calibrate")
    source = args.source if args.source is not None else cfg.get("source", 0)
    key = None if args.test else admin_key(args.key_file)
    cap = None
    print("קורא את לוח התוצאות. באפליקציה לחצו 'התחל משחק חי'. לעצירה: Ctrl+C")

    last_sent = None            # what the app already shows
    stable, stable_n = None, 0
    idle_note = 0
    working = args.test         # in --test mode always read; otherwise ask the app
    checked = 0
    try:
        while True:
            # the app decides when there is something to read; while there is
            # nothing, the camera is left alone and we only check now and then
            if not args.test and time.time() - checked > (3 if working else 15):
                checked = time.time()
                try:
                    st = ping(key)
                    want = st.get("on", True) and st.get("live", False)
                except Exception as e:
                    want = False
                    if time.time() - idle_note > 120:
                        print(time.strftime("%H:%M:%S"), "אין קשר לשרת:", e)
                        idle_note = time.time()
                if want != working:
                    working = want
                    print(time.strftime("%H:%M:%S"), "קורא מהמצלמה" if want else "ממתין — אין משחק חי או שהקריאה כבויה")
                    if not want and cap is not None:
                        cap.release()
                        cap = None
                        last_sent, stable, stable_n = None, None, 0
            if not working:
                time.sleep(1.0)
                continue
            if cap is None:
                cap = open_camera(source)
            frame = grab(cap)
            if frame is None:
                time.sleep(0.5)
                continue
            cut = lambda b: frame[b[1]:b[1] + b[3], b[0]:b[0] + b[2]]
            crop_h, crop_a = cut(cfg["home"]), cut(cfg["away"])
            dh, da = {}, {}
            h = read_number(crop_h, debug=dh)
            a = read_number(crop_a, debug=da)
            now = time.strftime("%H:%M:%S")
            if h is None or a is None:
                stable, stable_n = None, 0
                if args.test:
                    print(now, "לא נקרא (בית:", h, "חוץ:", a, ")")
                time.sleep(args.interval)
                continue
            if (h, a) == stable:
                stable_n += 1
            else:
                stable, stable_n = (h, a), 1
            if args.test:
                print(now, "נקרא", h, "-", a, "· יציב", stable_n, "פעמים")
            elif stable_n == args.stable and (h, a) != last_sent:
                jump = last_sent and (h - last_sent[0]) + (a - last_sent[1]) > 1
                if jump and stable_n < args.stable * 2:
                    print(now, "קפיצה חשודה", last_sent, "->", (h, a), "· מחכה לאישור נוסף")
                else:
                    if not args.no_learn and min(dh.get("score", 0), da.get("score", 0)) >= 0.8:
                        learn_from(crop_h, h, "home")
                        learn_from(crop_a, a, "away")
                    try:
                        r = send(key, h, a, args.dry_run)
                        if r.get("live") is False:
                            if time.time() - idle_note > 60:
                                print(now, "אין משחק חי פתוח באפליקציה")
                                idle_note = time.time()
                        else:
                            last_sent = (h, a)
                            print(now, "נשלח", h, "-", a, r.get("updated") and "✓" or "")
                    except Exception as e:
                        print(now, "שליחה נכשלה:", e)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nנעצר")
    finally:
        if cap is not None:
            cap.release()


def main():
    p = argparse.ArgumentParser(description="קורא תוצאה מהמצלמה לאפליקציית טורניר פיפא")
    p.add_argument("--source", default=None, help="מספר מצלמת USB (0) או כתובת RTSP")
    p.add_argument("--calibrate", action="store_true", help="לסמן איפה התוצאה על המסך")
    p.add_argument("--test", action="store_true", help="להדפיס מה נקרא בלי לשלוח")
    p.add_argument("--teach", action="store_true", help="ללמד את הספרות של הטלוויזיה שלך")
    p.add_argument("--list", action="store_true", help="לצלם תמונה מכל מצלמה כדי לבחור את הנכונה")
    p.add_argument("--no-learn", action="store_true", help="לא ללמוד ספרות תוך כדי")
    p.add_argument("--dry-run", action="store_true", help="לרוץ רגיל אבל בלי לשלוח")
    p.add_argument("--interval", type=float, default=1.0, help="כל כמה שניות לקרוא")
    p.add_argument("--stable", type=int, default=3, help="כמה קריאות זהות ברצף לפני שליחה")
    p.add_argument("--key-file", default=KEY_FILE_DEFAULT, help="קובץ מפתח האדמין")
    args = p.parse_args()
    if args.list:
        list_cameras(args)
    elif args.teach:
        teach(args)
    elif args.calibrate:
        args.source = args.source or load_cfg().get("source", 0)
        calibrate(args)
    else:
        run(args)


if __name__ == "__main__":
    main()
