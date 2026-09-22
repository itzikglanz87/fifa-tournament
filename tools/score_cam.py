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
    for side, label in (("home", "השערים של הקבוצה העליונה בלוח (הבית)"),
                        ("away", "השערים של הקבוצה התחתונה (החוץ)"),
                        ("home_crest", "הסמל (או קיצור השם) של הקבוצה העליונה — Esc לדילוג"),
                        ("away_crest", "הסמל (או קיצור השם) של הקבוצה התחתונה — Esc לדילוג")):
        print("סמן:", label)
        r = cv2.selectROI("סמן את " + side + " ולחץ Enter", frame, showCrosshair=True)
        cv2.destroyAllWindows()
        if r[2] < 4 or r[3] < 4:
            if side.endswith("_crest") or side.endswith("_code"):
                print("   דולג — בלי קיצורי קבוצות המערכת תמלא את המחזור הפתוח")
                continue
            raise SystemExit("לא סומן ריבוע")
        boxes[side] = [int(r[0]), int(r[1]), int(r[2]), int(r[3])]
    cap.release()
    cfg = load_cfg()
    cfg.update(boxes)
    cfg["source"] = args.source
    save_cfg(cfg)
    print("אפשר להריץ עכשיו:  python tools/score_cam.py")


# ---------------------------------------------------------------- reading a number
# The camera is fixed and the game's font never changes, so the digits are cut
# out and matched against digit shapes rendered from a few system fonts. That
# beats general OCR here: it reads small, slightly blurred digits off a screen,
# needs nothing installed, and runs in milliseconds.
DW, DH = 24, 32
TPL_FONTS = ["arialbd.ttf", "segoeuib.ttf", "tahomabd.ttf", "verdanab.ttf", "calibrib.ttf"]
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_TPL = None
_TPL_L = None


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
        # a digit is tall; "1" can fill the whole height and be very narrow,
        # so only the width tells a digit from the plate around it
        if h > H * 0.40 and w >= 2 and w < W * 0.92:
            out.append((th[y:y + h, x:x + w], x))
    return sorted(out, key=lambda b: b[1])


def letter_templates():
    """the same idea as the digits, for the three-letter club codes"""
    global _TPL_L
    if _TPL_L is not None:
        return _TPL_L
    import cv2, numpy as np
    from PIL import Image, ImageDraw, ImageFont
    fonts = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", f) for f in TPL_FONTS]
    fonts = [f for f in fonts if os.path.exists(f)]
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
    _TPL_L = {ch: [render(ch, f) for f in fonts] for ch in LETTERS}
    return _TPL_L


def read_code(img, known, min_score=0.45):
    """the club's short code, snapped to one of the codes we know"""
    import cv2, numpy as np
    boxes = digit_boxes(img)
    if not (2 <= len(boxes) <= 4):
        return None
    TPL = letter_templates()
    got = ""
    for img_b, _x in boxes:
        b = cv2.resize(img_b, (DW, DH), interpolation=cv2.INTER_AREA).astype(np.float32)
        b -= b.mean()
        n = np.linalg.norm(b)
        if not n:
            return None
        b /= n
        best, bs = "?", -2.0
        for ch, tl in TPL.items():
            sc = max(float((b * t).sum()) for t in tl)
            if sc > bs:
                best, bs = ch, sc
        got += best if bs >= min_score else "?"
    if not known:
        return got
    # the codes are few and fixed, so the closest one wins as long as it is close
    def dist(a, b):
        if len(a) != len(b):
            return 9
        return sum(1 for x, y in zip(a, b) if x != y and x != "?")
    scored = sorted(((dist(got, k), k) for k in known), key=lambda x: x[0])
    return scored[0][1] if scored and scored[0][0] <= 1 else None


CRESTS = os.path.join(HERE, "crests")
CW = 56


def crest_key(img):
    """one crest, shrunk and levelled so two pictures of it can be compared"""
    import cv2, numpy as np
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    g = cv2.resize(g, (CW, CW), interpolation=cv2.INTER_AREA).astype(np.float32)
    g -= g.mean()
    n = np.linalg.norm(g)
    return g / n if n else g


def imread_any(path):
    """OpenCV cannot open a path with Hebrew in it, so read the bytes ourselves"""
    import cv2, numpy as np
    try:
        return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return None


def imwrite_any(path, img):
    import cv2
    ok, buf = cv2.imencode(".png", img)
    if ok:
        buf.tofile(path)
    return ok


def crest_templates():
    """the badges taught so far: club name -> pictures of its crest"""
    out = {}
    if not os.path.isdir(CRESTS):
        return out
    for club in os.listdir(CRESTS):
        folder = os.path.join(CRESTS, club)
        if not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            img = imread_any(os.path.join(folder, name))
            if img is not None:
                out.setdefault(club, []).append(crest_key(img))
    return out


def read_crest(img, tpl, min_score=0.55, margin=0.06):
    """which club's badge this is — only when one is clearly ahead"""
    if not tpl:
        return None
    k = crest_key(img)
    scored = sorted(((max(float((k * t).sum()) for t in v), club) for club, v in tpl.items()), reverse=True)
    if not scored or scored[0][0] < min_score:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < margin:
        return None
    return scored[0][1]


def save_crest(img, club):
    folder = os.path.join(CRESTS, club)
    os.makedirs(folder, exist_ok=True)
    imwrite_any(os.path.join(folder, "%d.png" % int(time.time() * 1000)), img)


def find_board(frame, search, last=None):
    """Find the score plates in the picture instead of trusting fixed boxes:
       the two plates sit one on top of the other and are the brightest solid
       block inside the search area. A camera that drifts (or a picture that
       shifts) then costs nothing. Returns the home box, the away box, the
       two crest boxes, and the block itself for next time."""
    import cv2
    x0, y0, w0, h0 = search
    x0 = max(0, x0); y0 = max(0, y0)
    reg = frame[y0:y0 + h0, x0:x0 + w0]
    if reg.size == 0:
        return None
    g = cv2.cvtColor(reg, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    cnts, _h = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if w < 35 or h < 35:
            continue
        boxes.append((x, y, w, h))
    pairs = []
    for x, y, w, h in boxes:
        if 0.30 < w / float(h) < 0.72:            # already the two plates together
            pairs.append((x, y, w, h))
    if not pairs:
        # the two plates came out as separate blobs: put a stacked pair back together
        for i, (x1, y1, w1, h1) in enumerate(boxes):
            for x2, y2, w2, h2 in boxes[i + 1:]:
                if abs(x1 - x2) > 0.35 * max(w1, w2) or abs(w1 - w2) > 0.45 * max(w1, w2):
                    continue
                top, bot = ((x1, y1, w1, h1), (x2, y2, w2, h2)) if y1 < y2 else ((x2, y2, w2, h2), (x1, y1, w1, h1))
                gap = bot[1] - (top[1] + top[3])
                if -8 <= gap <= 0.6 * top[3]:
                    X = min(top[0], bot[0]); W = max(top[0] + top[2], bot[0] + bot[2]) - X
                    pairs.append((X, top[1], W, bot[1] + bot[3] - top[1]))
    if not pairs:
        return None
    def rank(b):
        score = b[2] * b[3]
        if last is not None:
            score -= 4 * (abs(b[0] + x0 - last[0]) + abs(b[1] + y0 - last[1]))
        return score
    x, y, w, h = max(pairs, key=rank)
    x, y = x + x0, y + y0
    half = h // 2
    pad = max(4, int(w * 0.08))
    home = [x - pad, y - pad, w + 2 * pad, half + pad]
    away = [x - pad, y + half - pad // 2, w + 2 * pad, half + pad]
    cw = int(w * 0.78)
    home_crest = [x - cw - pad, y, cw, half]
    away_crest = [x - cw - pad, y + half, cw, half]
    return {"home": home, "away": away, "home_crest": home_crest,
            "away_crest": away_crest, "block": [x, y, w, h]}


def classify_shape(mask, min_score=0.60):
    """one cut-out digit (white ink on black) against every template we have"""
    import cv2, numpy as np
    TPL = dict(templates())
    for d, v in learned_templates().items():
        TPL[d] = v + TPL.get(d, [])
    b = cv2.resize(mask, (DW, DH), interpolation=cv2.INTER_AREA).astype(np.float32)
    b -= b.mean()
    n = np.linalg.norm(b)
    if not n:
        return None, 0.0
    b /= n
    best, bs = None, -2.0
    for d, tl in TPL.items():
        sc = max(float((b * t).sum()) for t in tl)
        if sc > bs:
            best, bs = d, sc
    return (best, bs) if bs >= min_score else (None, bs)


def read_replay_bar(frame, want_shapes=False):
    """The wide white bar of a replay: full club names, and the exact score
       either side of the red league block. It is big and high-contrast, so
       when the small corner board is hidden this still says the score.
       Returns (home, away, home_shape, away_shape) or None."""
    import cv2, numpy as np
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    white = ((hsv[:, :, 1] < 70) & (hsv[:, :, 2] > 140)).astype(np.uint8) * 255
    white = cv2.morphologyEx(white, cv2.MORPH_CLOSE, np.ones((9, 81), np.uint8))
    cnts, _h = cv2.findContours(white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    bar = None
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if w > frame.shape[1] * 0.25 and 40 < h < 400 and w / float(h) > 4:
            if bar is None or w > bar[2]:
                bar = (x, y, w, h)
    if bar is None:
        return None
    x, y, w, h = bar
    inner = frame[y:y + h, x:x + w]
    ihsv = cv2.cvtColor(inner, cv2.COLOR_BGR2HSV)
    red = ((((ihsv[:, :, 0] < 12) | (ihsv[:, :, 0] > 168)) & (ihsv[:, :, 1] > 110) & (ihsv[:, :, 2] > 90))
           .astype(np.uint8) * 255)
    red = cv2.morphologyEx(red, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    rc, _h2 = cv2.findContours(red, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    blocks = sorted((cv2.boundingRect(c) for c in rc), key=lambda b: -b[2] * b[3])
    if not blocks or blocks[0][2] < 0.06 * w:
        return None
    rx, _ry, rw, _rh = blocks[0]
    g = cv2.cvtColor(inner, cv2.COLOR_BGR2GRAY)
    onwhite = (ihsv[:, :, 1] < 70) & (ihsv[:, :, 2] > 140)
    dark = cv2.morphologyEx((((g < 120) & ~onwhite) * 255).astype(np.uint8),
                            cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    dc, _h3 = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    left, right = [], []
    for c in dc:
        bx, by, bw, bh = cv2.boundingRect(c)
        if not (0.30 * h < bh < 0.80 * h and 0.02 * h < bw < 0.55 * h):
            continue
        sub_img = g[by:by + bh, bx:bx + bw]
        _t, th = cv2.threshold(sub_img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        val, score = classify_shape(th)
        if val is None and not want_shapes:
            continue
        (left if bx + bw < rx else right if bx > rx + rw else []).append(
            (bx, None if val is None else int(val), th, score))
    if not left or not right:
        return None
    left.sort(key=lambda z: z[0]); right.sort(key=lambda z: z[0])
    if want_shapes:
        return left[-1][2], right[0][2]
    return left[-1][1], right[0][1], left[-1][2], right[0][2]


def read_replay_bar_shapes(frame):
    """the two digit shapes on the replay bar, even when we cannot name them"""
    import cv2
    out = read_replay_bar(frame, want_shapes=True)
    return out if out else None


def plate_signature(img):
    """A plate boiled down to a small picture, for asking one question only:
       is this still the same number as a moment ago? Reading *which* digit it
       is needs detail the camera does not have at this distance; noticing
       that it changed does not."""
    import cv2, numpy as np
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    g = cv2.resize(g, (28, 36), interpolation=cv2.INTER_AREA).astype(np.float32)
    g = cv2.GaussianBlur(g, (3, 3), 0)
    g -= g.mean()
    n = np.linalg.norm(g)
    return g / n if n else g


def sig_same(a, b, thresh=0.93):
    if a is None or b is None:
        return False
    return float((a * b).sum()) >= thresh


def plate_crop(img):
    """The score sits on a bright plate. Find that plate inside the marked
       window and read only what is on it, so a small drift of the camera or
       of the picture does not cut the digit in half."""
    import cv2
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    _, th = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    cnts, _h = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    H, W = g.shape
    best = None
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if w * h < 0.12 * W * H or w < 0.25 * W or h < 0.25 * H:
            continue
        if not (0.35 < (w / float(h)) < 2.2):
            continue
        if best is None or w * h > best[2] * best[3]:
            best = (x, y, w, h)
    if best is None:
        return img
    x, y, w, h = best
    ix, iy = int(w * 0.14), int(h * 0.10)          # step inside the plate's edge
    return img[y + iy:y + h - iy, x + ix:x + w - ix]


def read_number(img, min_score=0.62, debug=None):
    """the number inside one box, or None when nothing digit-like is there"""
    import cv2, numpy as np
    boxes = digit_boxes(plate_crop(img))
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


def teach_clubs(args):
    """say which club the badge (or the code) on the scoreboard belongs to"""
    cfg = load_cfg()
    if "home_crest" not in cfg and "home_code" not in cfg:
        raise SystemExit("אין ריבועים לקיצורי הקבוצות — הרץ כיול מחדש:  python tools/score_cam.py --calibrate")
    data = json.load(io.open(os.path.join(HERE, "..", "functions", "data.json"), encoding="utf-8"))
    clubs = data.get("C", [])
    cap = open_camera(args.source if args.source is not None else cfg.get("source", 0))
    known = cfg.get("clubs", {})
    print("שים על המסך משחק עם הקבוצות שאתה רוצה ללמד. לסיום: Enter ריק.")
    try:
        while True:
            frame = None
            for _ in range(8):
                f = grab(cap)
                if f is not None:
                    frame = f
            if frame is None:
                print("אין תמונה"); break
            cut = lambda b: frame[b[1]:b[1] + b[3], b[0]:b[0] + b[2]]
            tpl = crest_templates()
            for side, where in (("home_crest", "העליונה"), ("away_crest", "התחתונה")):
                if side not in cfg:
                    continue
                img = cut(cfg[side])
                seen = read_crest(img, tpl)
                if seen:
                    print("הקבוצה", where, "מזוהה כבר:", seen)
                    save_crest(img, seen)            # another picture of the same badge
                    continue
                print("")
                for i, c in enumerate(clubs):
                    print("  %d) %s" % (i + 1, c))
                ans = input("מי הקבוצה " + where + " במסך? (מספר, או Enter לדילוג) ").strip()
                if not ans or not ans.isdigit() or not (1 <= int(ans) <= len(clubs)):
                    continue
                club = clubs[int(ans) - 1]
                save_crest(img, club)
                code = read_code(img, None)          # if it is letters, remember them too
                if code and "?" not in code:
                    known[code] = club
                print("   נשמר:", club)
            cfg["clubs"] = known
            save_cfg(cfg)
            tpl = crest_templates()
            if not input("להמשיך עם משחק אחר? (Enter לסיום, כל מקש להמשך) ").strip():
                break
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        cap.release()
    print("הקיצורים שידועים עכשיו:", json.dumps(known, ensure_ascii=False))


def send(key, h, a, dry, clubs=None):
    if dry:
        print("   (בדיקה בלבד — לא נשלח)")
        return {"dry": True}
    payload = {"key": key, "h": h, "a": a}
    if clubs:
        payload["clubs"] = clubs
    body = json.dumps({"data": payload}).encode()
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
    last_block = None           # where the board was a moment ago
    change_ref, change_pending = {}, {}      # what each plate looked like
    goals = {"h": 0, "a": 0}
    last_good_block = None
    beat = 0                                 # last heartbeat line
    warm_until = 0                           # no goals counted right after waking
    try:
        while True:
            # the app decides when there is something to read; while there is
            # nothing, the camera is left alone and we only check now and then
            if not args.test and time.time() - checked > (3 if working else 15):
                checked = time.time()
                try:
                    st = ping(key)
                    # a live tournament is enough: the camera opens the match
                    want = st.get("on", True) and bool(st.get("live", False) or st.get("tournament"))
                except Exception as e:
                    want = False
                    if time.time() - idle_note > 120:
                        print(time.strftime("%H:%M:%S"), "אין קשר לשרת:", e)
                        idle_note = time.time()
                if want != working:
                    working = want
                    print(time.strftime("%H:%M:%S"), "קורא מהמצלמה" if want else "ממתין — אין משחק חי או שהקריאה כבויה")
                    if want:
                        change_ref, change_pending = {}, {}
                        warm_until = time.time() + args.warmup
                        try:
                            st2 = ping(key)
                            last_sent = (st2.get("h") or 0, st2.get("a") or 0) if st2.get("live") else None
                            goals["h"], goals["a"] = last_sent
                            print(time.strftime("%H:%M:%S"), "מתחיל מ־", last_sent[0], "-", last_sent[1])
                        except Exception:
                            pass
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
            found = find_board(frame, cfg.get("search", [0, 0, frame.shape[1], frame.shape[0]]), last_block)
            if found:
                last_block = found["block"]
                cfg_boxes = found
            else:
                cfg_boxes = cfg                    # fall back to the marked boxes
            cut = lambda b: frame[max(0, b[1]):b[1] + b[3], max(0, b[0]):b[0] + b[2]]
            crop_h, crop_a = cut(cfg_boxes["home"]), cut(cfg_boxes["away"])
            codes = None
            if cfg_boxes.get("home_crest") and cfg_boxes.get("away_crest"):
                tpl = crest_templates()
                ch = read_crest(cut(cfg_boxes["home_crest"]), tpl)
                ca = read_crest(cut(cfg_boxes["away_crest"]), tpl)
                if not (ch and ca) and cfg.get("clubs"):      # the other board style: letters
                    known = cfg["clubs"]
                    kh = read_code(cut(cfg_boxes["home_crest"]), known)
                    ka = read_code(cut(cfg_boxes["away_crest"]), known)
                    ch, ca = ch or (known.get(kh) if kh else None), ca or (known.get(ka) if ka else None)
                if ch and ca and ch != ca:
                    codes = {"h": ch, "a": ca}
            dh, da = {}, {}
            h = read_number(crop_h, debug=dh)
            a = read_number(crop_a, debug=da)
            from_bar = False
            bar_shapes = None
            if not args.no_bar:
                bar = read_replay_bar(frame)
                if bar:
                    bh, ba, sh, sa = bar
                    bar_shapes = (sh, sa)
                    if bh is not None and ba is not None:
                        h, a = bh, ba          # the replay bar is the clearest source
                        from_bar = True
                        dh["score"], da["score"] = 0.9, 0.9
                elif not args.no_bar:
                    shapes = read_replay_bar_shapes(frame)
                    if shapes:
                        bar_shapes = shapes
            # the bar shows the score in big digits; when we know what the score
            # is, those digits are the best teacher for the ones we cannot read
            if (bar_shapes and last_sent and not args.no_learn
                    and h is not None and a is not None and (h, a) == tuple(last_sent)):
                for shape, val in zip(bar_shapes, last_sent):
                    if shape is None or not (0 <= val <= 9):
                        continue
                    folder = os.path.join(LEARNED, str(val))
                    os.makedirs(folder, exist_ok=True)
                    if len(os.listdir(folder)) < 12:
                        imwrite_any(os.path.join(folder, "bar_%d.png" % int(time.time() * 1000)), shape)
                        print(now, "למד את הספרה", val, "מהפס")

            if time.time() - beat > 20:
                beat = time.time()
                sims = []
                for side, crop in (("h", crop_h), ("a", crop_a)):
                    ref = change_ref.get(side)
                    sig = plate_signature(plate_crop(crop)) if found else None
                    sims.append("%s=%s" % (side, "-" if (ref is None or sig is None) else "%.2f" % float((sig * ref).sum())))
                print(now, "מצב · לוח:", "נמצא" if found else "לא", "· ספרות:", h, "-", a,
                      "· פס:", "כן" if bar_shapes else "לא", "· דמיון:", " ".join(sims))
            # --- goals by change ---------------------------------------
            # When the digits cannot be read, the plate itself still says a
            # goal went in: its picture changes and then stays changed. Each
            # side is watched on its own, and a change only counts after it
            # has held for a few seconds, so a replay or a flash cannot score.
            if found and not args.no_change:
                # a board that jumped across the picture is a new detection, not
                # a goal: start over rather than count it
                if last_good_block and (abs(found["block"][0] - last_good_block[0]) > 25 or
                                        abs(found["block"][1] - last_good_block[1]) > 25):
                    change_ref, change_pending = {}, {}
                    warm_until = time.time() + args.warmup
                last_good_block = found["block"]
                for side, crop in (("h", crop_h), ("a", crop_a)):
                    sig = plate_signature(plate_crop(crop))
                    ref = change_ref.get(side)
                    if ref is None:
                        change_ref[side] = sig
                        continue
                    if sig_same(sig, ref):
                        change_pending.pop(side, None)
                        continue
                    if time.time() < warm_until:          # still settling after waking
                        change_ref[side] = sig
                        continue
                    if sig_same(sig, ref, 0.80):          # a wobble, not a different number
                        continue
                    pend = change_pending.get(side)
                    if pend is None or not sig_same(sig, pend[0]):
                        change_pending[side] = (sig, time.time())      # new look, start the clock
                        continue
                    if time.time() - pend[1] >= args.settle:
                        change_ref[side] = sig
                        change_pending.pop(side, None)
                        change_ref.pop("h" if side == "a" else "a", None)   # re-read the other plate too
                        goals[side] += 1
                        print(now, "שינוי במשבצת של", "הבית" if side == "h" else "החוץ",
                              "— גול. ספירה:", goals["h"], "-", goals["a"])
                        if not args.test:
                            base = last_sent or (0, 0)   # nothing open yet: start from nothing
                            nh = base[0] + (1 if side == "h" else 0)
                            na = base[1] + (1 if side == "a" else 0)
                            try:
                                r = send(key, nh, na, args.dry_run, codes)
                                if r.get("live") is False:
                                    print(now, "אין משחק חי פתוח באפליקציה")
                                else:
                                    last_sent = (r.get("h", nh), r.get("a", na))
                                    print(now, "נשלח", last_sent[0], "-", last_sent[1], "(ספירת גולים)")
                            except Exception as e:
                                print(now, "שליחה נכשלה:", e)

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
                print(now, "נקרא", h, "-", a, "· יציב", stable_n, "פעמים" +
                      (" · מהפס התחתון" if from_bar else "") +
                      (" · " + codes["h"] + " נגד " + codes["a"] if codes else ""))
            elif stable_n == args.stable and (h, a) != last_sent:
                jump = last_sent and (h - last_sent[0]) + (a - last_sent[1]) > 1
                if jump and stable_n < args.stable * 2:
                    print(now, "קפיצה חשודה", last_sent, "->", (h, a), "· מחכה לאישור נוסף")
                else:
                    if not args.no_learn and min(dh.get("score", 0), da.get("score", 0)) >= 0.8:
                        learn_from(crop_h, h, "home")
                        learn_from(crop_a, a, "away")
                    try:
                        r = send(key, h, a, args.dry_run, codes)
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
    p.add_argument("--teach-clubs", action="store_true", help="ללמד איזה קיצור שייך לאיזו קבוצה")
    p.add_argument("--list", action="store_true", help="לצלם תמונה מכל מצלמה כדי לבחור את הנכונה")
    p.add_argument("--no-learn", action="store_true", help="לא ללמוד ספרות תוך כדי")
    p.add_argument("--no-bar", action="store_true", help="לא לקרוא מהפס של השידור החוזר")
    p.add_argument("--no-change", action="store_true", help="לא לספור גולים לפי שינוי במשבצת")
    p.add_argument("--settle", type=float, default=5.0, help="כמה שניות שינוי צריך להחזיק כדי להיחשב גול")
    p.add_argument("--warmup", type=float, default=12.0, help="כמה שניות להתייצב לפני שסופרים גולים")
    p.add_argument("--log", action="store_true", help="לכתוב את הפלט לקובץ במקום למסך (לריצה ברקע)")
    p.add_argument("--dry-run", action="store_true", help="לרוץ רגיל אבל בלי לשלוח")
    p.add_argument("--interval", type=float, default=1.0, help="כל כמה שניות לקרוא")
    p.add_argument("--stable", type=int, default=3, help="כמה קריאות זהות ברצף לפני שליחה")
    p.add_argument("--key-file", default=KEY_FILE_DEFAULT, help="קובץ מפתח האדמין")
    args = p.parse_args()
    if args.log:
        # running in the background with no console: keep a log to look at
        path = os.path.join(HERE, "score_cam.log")
        if os.path.exists(path) and os.path.getsize(path) > 2_000_000:
            os.replace(path, path + ".old")
        f = io.open(path, "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = f
        print("=== " + time.strftime("%Y-%m-%d %H:%M:%S") + " started ===")
    if args.teach_clubs:
        teach_clubs(args)
    elif args.list:
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
