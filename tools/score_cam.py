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


def cached_letters():
    if "letters" not in _TPL_CACHE:
        _TPL_CACHE["letters"] = letter_templates()
    return _TPL_CACHE["letters"]


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
    TPL = cached_letters()
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
    """One crest, shrunk and levelled so two pictures of it can be compared.

    In colour, not in grey. These badges differ from one another mostly by
    colour — PSG's navy against Bayern's red, Liverpool's red against Real's
    white — and in grey they were being mistaken for each other. Shape alone
    was naming the wrong club once in every six it named."""
    import cv2, numpy as np
    c = img if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    c = cv2.resize(c, (CW, CW), interpolation=cv2.INTER_AREA).astype(np.float32)
    v = c.reshape(-1)
    v -= v.mean()
    n = np.linalg.norm(v)
    return v / n if n else v


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


def read_crest(img, tpl, min_score=0.62, margin=0.10):
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


_TPL_CACHE = {}


def all_templates():
    """Every digit template, built once. Reading them off the disk for each
       digit of each frame cost more than everything else the reader does."""
    if "digits" not in _TPL_CACHE:
        TPL = dict(templates())
        for d, v in learned_templates().items():
            TPL[d] = v + TPL.get(d, [])
        _TPL_CACHE["digits"] = TPL
    return _TPL_CACHE["digits"]


def classify_shape(mask, min_score=0.60):
    """one cut-out digit (white ink on black) against every template we have"""
    import cv2, numpy as np
    TPL = all_templates()
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


def score_in_region(img, debug=None):
    """Read the score out of the whole scoreboard area, whatever it looks like.

    FC dresses the board differently in every competition: white digits on a
    dark panel, dark digits on white plates, with or without crests. What does
    not change is the shape of the thing: the two scores sit one above the
    other, at the right end of the board. So instead of a box per digit, take
    the board as a whole, find the digit-shaped marks (in either polarity),
    split them into an upper and a lower row, and read the rightmost group in
    each. Returns (home, away, home_shapes, away_shapes)."""
    if img is None or getattr(img, "size", 0) == 0 or min(img.shape[:2]) < 20:
        return None                              # a crop that fell outside the picture
    import cv2, numpy as np
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    # Blow the cut-out up to a working size rather than by a fixed amount: the
    # same board is three times smaller when the camera takes in the whole
    # television instead of one corner of it, and a doubling that was ample
    # there leaves the digits too coarse to tell apart here.
    # Scale the cut-out TO a working width, in both directions: a small board
    # is blown up, and a large one — which is what the camera gives now that it
    # is close and fixed to the wall — is brought down instead of being doubled
    # into something enormous to grind through.
    k = max(0.8, min(6.0, 1100.0 / max(40, g.shape[1])))
    g = cv2.resize(g, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
    g = cv2.GaussianBlur(g, (3, 3), 0)
    H, W = g.shape
    marks = []
    for invert in (False, True):
        work = 255 - g if invert else g
        _t, th = cv2.threshold(work, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        th = clear_border(th)
        cnts, _h = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            x, y, w, h = cv2.boundingRect(c)
            if not (0.10 * H < h < 0.55 * H):        # a digit is a fair slice of the board
                continue
            if not (0.01 * W < w < 0.22 * W) or w > 1.4 * h:
                continue
            marks.append({"x": x, "y": y, "w": w, "h": h, "img": th[y:y + h, x:x + w]})
    inside = lambda m, o: (m["x"] >= o["x"] and m["y"] >= o["y"] and
                           m["x"] + m["w"] <= o["x"] + o["w"] and
                           m["y"] + m["h"] <= o["y"] + o["h"] and m is not o)
    marks = [m for m in marks if not any(inside(m, o) for o in marks)]
    if len(marks) < 2:
        return None
    tall = sorted(marks, key=lambda m: -m["h"])[:14]
    mid = sorted(m["y"] + m["h"] / 2 for m in tall)
    split = (mid[0] + mid[-1]) / 2
    rows = ([m for m in tall if m["y"] + m["h"] / 2 <= split],
            [m for m in tall if m["y"] + m["h"] / 2 > split])
    if not rows[0] or not rows[1]:
        return None
    # A scoreboard has one score above the other, with real space between them.
    # A single line of writing — the word "Classic" on the pause menu — also
    # splits into two "rows", a handful of letters either side of an imaginary
    # line, and its letters read as digits. Insist on the gap.
    top = sum(m["y"] + m["h"] / 2 for m in rows[0]) / len(rows[0])
    bot = sum(m["y"] + m["h"] / 2 for m in rows[1]) / len(rows[1])
    if bot - top < 0.22 * H:
        return None
    out, shapes, groups = [], [], []
    for row in rows:
        right = max(m["x"] + m["w"] for m in row)
        group = sorted([m for m in row if m["x"] + m["w"] > right - 0.16 * W], key=lambda m: m["x"])
        group = group[-2:]                            # at most two digits (up to 99)
        digits, ok = "", True
        for m in group:
            val, score = classify_shape(m["img"])
            if val is None:
                ok = False
                break
            digits += str(val)
        if not ok or not digits:
            return None
        if int(digits) > 20:                          # that is the clock, not a score
            return None
        out.append(int(digits))
        shapes.append([m["img"] for m in group])
        groups.append(group)
    if debug is not None:
        debug["marks"] = len(marks)
        # where the figures start, back in the cut-out's own pixels: the club
        # codes are the writing immediately to their left, whatever else the
        # board happens to carry
        debug["score_x"] = int(min(min(m["x"] for m in r) for r in groups) / k)
        # and where they sit vertically. The block that is found reaches well
        # above the board — the crowd behind it is bright and nearly colourless
        # too, so neither brightness nor saturation ends it — and splitting
        # that block down the middle put the home club's letters outside its
        # own cell. The figures cannot be anywhere but on the board, so they
        # are what the rows are measured from.
        t0 = min(m["y"] for m in groups[0]) / k
        t1 = max(m["y"] + m["h"] for m in groups[0]) / k
        b0 = min(m["y"] for m in groups[1]) / k
        b1 = max(m["y"] + m["h"] for m in groups[1]) / k
        pad = 0.45 * (t1 - t0)
        debug["rows"] = (int(max(0, t0 - pad)), int((t1 + b0) / 2), int(b1 + pad))
    return out[0], out[1], shapes[0], shapes[1]


def ink_marks(img, hmin=0.10, hmax=0.55, wmax=0.22, wh_max=1.4):
    """Every mark on a cut-out of the board, with the ink white.

    Whichever way round the board is drawn, one of the two polarities leaves
    the writing as separate shapes once whatever touches the edge is flooded
    away. Used for both the digits and the club codes, so the two read the
    same way."""
    import cv2
    if img is None or getattr(img, "size", 0) == 0 or min(img.shape[:2]) < 16:
        return []
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    # Blow the cut-out up to a working size rather than by a fixed amount: the
    # same board is three times smaller when the camera takes in the whole
    # television instead of one corner of it, and a doubling that was ample
    # there leaves the digits too coarse to tell apart here.
    # Scale the cut-out TO a working width, in both directions: a small board
    # is blown up, and a large one — which is what the camera gives now that it
    # is close and fixed to the wall — is brought down instead of being doubled
    # into something enormous to grind through.
    k = max(0.8, min(6.0, 1100.0 / max(40, g.shape[1])))
    g = cv2.resize(g, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
    g = cv2.GaussianBlur(g, (3, 3), 0)
    H, W = g.shape
    marks = []
    for invert in (False, True):
        work = 255 - g if invert else g
        _t, th = cv2.threshold(work, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        th = clear_border(th)
        cnts, _h = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            x, y, w, h = cv2.boundingRect(c)
            if not (hmin * H < h < hmax * H):
                continue
            if not (0.01 * W < w < wmax * W) or w > wh_max * h:
                continue
            marks.append({"x": x, "y": y, "w": w, "h": h, "img": th[y:y + h, x:x + w]})
    inside = lambda m, o: (m["x"] >= o["x"] and m["y"] >= o["y"] and
                           m["x"] + m["w"] <= o["x"] + o["w"] and
                           m["y"] + m["h"] <= o["y"] + o["h"] and m is not o)
    return [m for m in marks if not any(inside(m, o) for o in marks)]


def split_merged(marks):
    """Cut apart letters that arrived stuck together.

    Letters set tight come through as one mark — RMA on the Spanish board
    gave MA as a single shape half the cell wide, and the English clock gave
    "33:44" as two marks instead of four — and a shape that wide is thrown out
    before it can be read, so the club went unnamed.

    What tells a run of letters from one wide letter is not how wide it is.
    The same letter is squat at this distance and narrow at that one: R
    measured 139 wide by 129 tall on the ordinary board and 250 by 430 on the
    Spanish one, so no ratio separates them. What does separate them is that
    between two letters the ink stops, and inside a letter it never does. So
    the cut is made only where the ink actually runs out — and nowhere else.
    """
    import numpy as np
    out = []
    for m in marks or []:
        out.extend(_split_at_gaps(m, 0))
    return out


def _split_at_gaps(m, depth):
    import numpy as np
    if depth >= 2 or m["w"] < 0.55 * m["h"] or m["w"] < 12:
        return [m]
    ink = (m["img"] > 0).sum(axis=0).astype(np.float32)
    if ink.size < 12 or ink.mean() <= 0:
        return [m]
    lo, hi = int(m["w"] * 0.22), int(m["w"] * 0.78)
    if hi - lo < 3:
        return [m]
    j = lo + int(np.argmin(ink[lo:hi]))
    # empty against both what the mark carries on average and what it carries
    # at its fullest: the middle column of an L is thin but not empty, and
    # judging it against the average alone would have cut it in two
    if not (ink[j] <= 0.22 * ink.mean() and ink[j] <= 0.25 * ink.max()):
        return [m]
    if j < 0.18 * m["h"] or m["w"] - j < 0.18 * m["h"]:
        return [m]
    a = {"x": m["x"], "y": m["y"], "w": j, "h": m["h"], "img": m["img"][:, :j]}
    b = {"x": m["x"] + j, "y": m["y"], "w": m["w"] - j, "h": m["h"],
         "img": m["img"][:, j:]}
    return _split_at_gaps(a, depth + 1) + _split_at_gaps(b, depth + 1)


def minutes_from_cell(cell, invert=False, min_score=0.55):
    """The minutes off a clock cell reading MM:SS.

    The two figures left of the colon are the minutes. The colon's own dots
    come through as marks too, but they are a fraction of the height of a
    figure, so the tallest mark sets the size and anything well short of it is
    not a digit."""
    import cv2, numpy as np
    if cell is None or getattr(cell, "size", 0) == 0 or min(cell.shape[:2]) < 14:
        return None
    g = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY) if cell.ndim == 3 else cell
    if invert:
        g = 255 - g
    g = cv2.copyMakeBorder(g, 10, 10, 10, 10, cv2.BORDER_CONSTANT,
                           value=int(np.median(g[:, :3])))
    im = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
    ms = ink_marks(im, hmin=0.25, hmax=0.95, wmax=0.60)
    if not ms:
        return None
    # the middle height is what a figure is, not the tallest thing found: the
    # edge of the clock strip comes through as a mark twice their height, and
    # measuring against that left the figures themselves out
    med_h = float(np.median([m["h"] for m in ms]))
    ms = [m for m in ms if 0.62 * med_h <= m["h"] <= 1.55 * med_h]
    # the two figures of the minute are set tight and arrive as one mark on
    # the English tab, where "33:44" gave two marks rather than four
    ms = sorted(split_merged(ms), key=lambda m: m["x"])[:2]
    if len(ms) < 2:
        return None
    out = ""
    for m in ms:
        v, _sc = classify_shape(m["img"], min_score=min_score)
        if v is None:
            return None
        out += str(v)
    try:
        n = int(out)
    except ValueError:
        return None
    return n if 0 <= n <= 90 else None


# --- the Spanish league board ---------------------------------------------
# Laid out quite unlike the ordinary one: a red league badge top left with the
# clock under it, then a dark column holding the two club codes in white, then
# a white column holding the two figures in black. Every few seconds the code
# column turns over to the clubs' crests and back. Only Barcelona and Real ever
# appear on it here, so the letters are matched against those two alone.
ES_PAIR = ("BAR", "RMA")


def find_laliga_badge(frame):
    """The red league badge: a big saturated-red square, found on a small copy
    and then measured full size, because sweeping every pixel of a 4K frame for
    it on every pass costs more than the rest of the reading put together."""
    import cv2, numpy as np
    h, w = frame.shape[:2]
    k = 4 if w >= 2400 else 2
    small = cv2.resize(frame, (w // k, h // k), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    H, Sa, V = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    red = ((((H <= 10) | (H >= 168)) & (Sa >= 90) & (V >= 110)).astype(np.uint8)) * 255
    red = cv2.morphologyEx(red, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, _l, st, _c = cv2.connectedComponentsWithStats(red, 8)
    best = None
    for i in range(1, n):
        x, y, bw, bh, a = (st[i, 0], st[i, 1], st[i, 2], st[i, 3], st[i, 4])
        if bw * k < 120 or bh * k < 100 or a < 0.62 * bw * bh:
            continue
        if not (0.95 < bw / float(bh) < 2.1):
            continue
        if best is None or a > best[0]:
            best = (a, [int(x) * k, int(y) * k, int(bw) * k, int(bh) * k])
    return best[1] if best else None


def laliga_parts(frame, badge):
    """The board's cells, measured out from the badge.

    The two columns right of the badge are told apart by what they are made of
    rather than by where they fall: the codes sit on black, the figures on
    white, so walking right from the badge gives first a dark run and then a
    bright one, whatever size the board is on screen."""
    import cv2, numpy as np
    bx, by, bw, bh = badge
    h, w = frame.shape[:2]
    y0, y1 = by, min(h, by + 2 * bh)
    x0, x1 = bx + bw, min(w, bx + int(bw * 3.0))
    if x1 - x0 < bw * 0.6 or y1 - y0 < bh:
        return None                       # the board runs off the picture
    g = cv2.cvtColor(frame[y0 + int(bh * 0.15):y1 - int(bh * 0.15), x0:x1], cv2.COLOR_BGR2GRAY)
    if g.size == 0:
        return None
    # how much of each column is dark or light, not its middle value: a column
    # down through the stem of a 1 has a dark stripe across it, and the middle
    # value there ended the white block halfway along, leaving both figures
    # unread
    dark = (g < 110).mean(axis=0) >= 0.50
    bright = (g > 150).mean(axis=0) >= 0.50
    gap = max(3, int(bw * 0.10))

    def walk(flag, start):
        i, miss = start, 0
        while i < len(flag) - 1:
            if flag[i + 1]:
                miss = 0
            else:
                miss += 1
                if miss > gap:
                    break
            i += 1
        return i - miss

    i = 0
    while i < len(dark) and not dark[i]:
        i += 1
    j = walk(dark, i) + 1
    while j < len(bright) and not bright[j]:
        j += 1
    k = walk(bright, j) + 1
    if j - i < bw * 0.25 or k - j < bw * 0.25:
        return None
    cod, fig = (x0 + i, x0 + j), (x0 + j, x0 + k)
    # The figures sit on white with grass above and crowd below, so that
    # column's top and bottom can simply be measured. The codes cannot: the
    # block is black and so is everything around it. But the board is one flat
    # panel, so the slope from the badge's top edge to the figures' says where
    # the code block starts and ends — which matters, because the camera sees
    # the board at an angle and a split line taken from the badge alone cut the
    # away row in half.
    gg = cv2.cvtColor(frame[max(0, by - bh):min(h, by + 3 * bh), fig[0]:fig[1]], cv2.COLOR_BGR2GRAY)
    if gg.size == 0:
        return None
    on = np.median(gg, axis=1) > 150
    top = max(0, by - bh)
    c = min(max((by + bh) - top, 0), len(on) - 1)
    u = d = int(c)
    while u > 0 and on[u - 1]:
        u -= 1
    while d < len(on) - 1 and on[d + 1]:
        d += 1
    fy0, fy1 = top + u, top + d
    if fy1 - fy0 < bh:
        return None
    slope = (fy0 - by) / float(max(1.0, (fig[0] + fig[1]) / 2.0 - (bx + bw / 2.0)))
    shift = int(slope * ((cod[0] + cod[1]) / 2.0 - (fig[0] + fig[1]) / 2.0))
    return {"code": cod, "fig": fig, "code_y": (fy0 + shift, fy1 + shift),
            "fig_y": (fy0, fy1)}


def laliga_cell(frame, p, side, which):
    import cv2
    t, bm = p[which + "_y"]
    mid = (t + bm) // 2
    y0, y1 = (t, mid) if side == "h" else (mid, bm)
    a, b = p[which]
    pad = int((y1 - y0) * 0.07)
    y0, y1 = y0 + pad, y1 - pad
    if y1 - y0 < 12 or b - a < 12:
        return None
    if which == "code":
        # trim to the black block itself for this row: the column's edges carry
        # thin coloured strips that the board draws between its panels, and one
        # of them read as an L and carried LIV past the real RMA beside it
        g = cv2.cvtColor(frame[y0:y1, a:b], cv2.COLOR_BGR2GRAY)
        on = (g < 110).mean(axis=0) >= 0.55
        c = len(on) // 2
        u = d = c
        while u > 0 and on[u - 1]:
            u -= 1
        while d < len(on) - 1 and on[d + 1]:
            d += 1
        if d - u > 0.4 * (b - a):
            a, b = a + u, a + d
    return frame[y0:y1, a:b]


def read_laliga(frame, clubs, want_codes=True):
    """Both figures and both clubs off the Spanish board, or None."""
    import cv2
    badge = find_laliga_badge(frame)
    if not badge:
        return None
    p = laliga_parts(frame, badge)
    if not p:
        return None
    out = {}
    pair = dict((k, v) for k, v in (clubs or {}).items() if k in ES_PAIR)
    for side in ("h", "a"):
        c = laliga_cell(frame, p, side, "code") if want_codes else None
        out["code_" + side] = None
        if c is not None and pair:
            g = 255 - cv2.cvtColor(c, cv2.COLOR_BGR2GRAY)
            g = cv2.copyMakeBorder(g, 14, 14, 14, 14, cv2.BORDER_CONSTANT, value=255)
            out["code_" + side] = read_code_plate(cv2.cvtColor(g, cv2.COLOR_GRAY2BGR), pair)
        d = laliga_cell(frame, p, side, "fig")
        got = ""
        if d is not None:
            for m in sorted(ink_marks(d, hmin=0.25, hmax=0.95, wmax=0.60), key=lambda m: m["x"]):
                got += (classify_shape(m["img"], min_score=0.5)[0] or "?")
        out[side] = int(got) if got.isdigit() and len(got) <= 2 else None
    # only two clubs ever appear on this board, so one side names the other
    if out["code_h"] in ES_PAIR and out["code_a"] not in ES_PAIR:
        out["code_a"] = ES_PAIR[1 - ES_PAIR.index(out["code_h"])]
    elif out["code_a"] in ES_PAIR and out["code_h"] not in ES_PAIR:
        out["code_h"] = ES_PAIR[1 - ES_PAIR.index(out["code_a"])]
    if out["h"] is None or out["a"] is None:
        return None
    # the clock is the white block under the badge, reading MM:SS in black
    bx, by, bw, bh = badge
    hh = frame.shape[0]
    out["min"] = minutes_from_cell(frame[min(hh, by + bh):min(hh, by + 2 * bh), bx:bx + bw])
    out["badge"] = badge
    return out


# --- the English league strip ---------------------------------------------
# One long strip across the middle of the upper screen: the home code on a
# claret block, the home figure, the league's lion, the away figure, the away
# code on a white block, and the clock on a purple tab underneath. No crests,
# and the left side is always home.
#
# The lion is the anchor. It has to be, because the advertising hoarding behind
# the strip is the same claret at the same height, so neither colour nor
# thickness tells the two apart — but the lion is the one strong purple thing
# on the screen, and everything on the strip keeps its distance from it.
PL_TILT = [None, 0.0]                    # when it was measured, and to what


def find_pl_lion(frame):
    """The league's lion: found on a small copy, measured full size."""
    import cv2, numpy as np
    h, w = frame.shape[:2]
    k = 4 if w >= 2400 else 2
    small = cv2.resize(frame[0:int(h * 0.62), :], (w // k, int(h * 0.62) // k),
                       interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    H, Sa, V = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    m = ((H >= 130) & (H <= 155) & (Sa >= 120) & (V >= 80)).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, _l, st, _c = cv2.connectedComponentsWithStats(m, 8)
    best = None
    for i in range(1, n):
        x, y, bw, bh, a = (st[i, 0], st[i, 1], st[i, 2], st[i, 3], st[i, 4])
        if a * k * k < 6000 or bh * k < 70 or not (0.55 < bw / float(bh) < 1.8):
            continue
        if best is None or a > best[0]:
            best = (a, [int(x) * k, int(y) * k, int(bw) * k, int(bh) * k])
    if not best:
        return None
    # Measure it again full size. Every cell on the strip is laid out in lion
    # widths, so a box a quarter-scale mask rounded off by a few pixels moves
    # the figures out of their cells.
    x, y, bw, bh = best[1]
    px, py = bw // 2, bh // 2
    ax, ay = max(0, x - px), max(0, y - py)
    win = frame[ay:y + bh + py, ax:x + bw + px]
    if win.size == 0:
        return best[1]
    hsv = cv2.cvtColor(win, cv2.COLOR_BGR2HSV)
    H, Sa, V = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    m2 = ((H >= 130) & (H <= 155) & (Sa >= 120) & (V >= 80)).astype(np.uint8) * 255
    n2, lab2, st2, _c2 = cv2.connectedComponentsWithStats(m2, 8)
    # the blob the small mask was pointing at, not the biggest one in the
    # window: the clock tab under the strip is purple too and larger
    cxw, cyw = (x - ax) + bw // 2, (y - ay) + bh // 2
    big = int(lab2[min(max(cyw, 0), lab2.shape[0] - 1), min(max(cxw, 0), lab2.shape[1] - 1)])
    if big <= 0:
        return best[1]
    return [int(st2[big, 0]) + ax, int(st2[big, 1]) + ay,
            int(st2[big, 2]), int(st2[big, 3])]


def pl_solid(img):
    """Strip pixels: anything bright or strongly coloured that is not grass."""
    import cv2
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    H, Sa, V = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    green = (H >= 35) & (H <= 85) & (Sa >= 60)
    return (~green) & ((V >= 140) | ((Sa >= 70) & (V >= 85)))


def pl_band(frame, lion, tilt=None):
    """The strip, levelled, cut to five lion-widths either side of the lion.

    The camera sees the board at a slight angle, which has to come out before
    the cells can be measured: tilted, the far end of the strip leaves the row
    the near end sits in. The angle is found by turning the picture until the
    strip's rows come out full, and then remembered, because neither the camera
    nor the television moves."""
    import cv2, numpy as np
    lx, ly, lw, lh = lion
    cx, cy = lx + lw // 2, ly + lh // 2
    hw, hh, pad = int(lw * 4.5), int(lh * 1.6), 300
    h, w = frame.shape[:2]
    x0, y0 = max(0, cx - hw - pad), max(0, cy - hh - pad)
    sub = frame[y0:min(h, cy + hh + pad), x0:min(w, cx + hw + pad)]
    if sub.size == 0:
        return None
    c2 = (cx - x0, cy - y0)
    if tilt is None:
        # Try the angles on a quarter-size copy. Turning the full picture
        # nineteen times costs the best part of a second, and a tenth of the
        # pixels decide the angle just as well.
        q = 4
        sm = cv2.resize(sub, (sub.shape[1] // q, sub.shape[0] // q), interpolation=cv2.INTER_AREA)
        cs = (c2[0] // q, c2[1] // q)
        bw2, bh2 = hw // q, hh // q
        best_ang, best_sc = 0.0, -1
        for ang in np.arange(-9, 9.01, 0.5):
            M = cv2.getRotationMatrix2D(cs, float(ang), 1.0)
            r = cv2.warpAffine(sm, M, (sm.shape[1], sm.shape[0]))
            win = r[max(0, cs[1] - bh2):cs[1] + bh2, max(0, cs[0] - bw2):cs[0] + bw2]
            if win.size == 0:
                continue
            sc = int((pl_solid(win).mean(axis=1) >= 0.985).sum())
            if sc > best_sc:
                best_ang, best_sc = float(ang), sc
        tilt = best_ang
    M = cv2.getRotationMatrix2D(c2, float(tilt), 1.0)
    flat = cv2.warpAffine(sub, M, (sub.shape[1], sub.shape[0]))
    H2, W2 = flat.shape[:2]
    a, b = max(0, c2[1] - int(lh * 0.44)), min(H2, c2[1] + int(lh * 0.44))
    u, v = max(0, c2[0] - int(lw * 5.2)), min(W2, c2[0] + int(lw * 5.2))
    if b - a < 20 or v - u < lw * 8:
        return None
    # The clock tab hangs under the middle of the strip; it is the one thing on
    # this board that says how far the match has got. Start a little below the
    # strip: the lion hangs over the top of the tab, and its tail came through
    # as a mark taller than the figures.
    t0, t1 = min(H2, b + int(lh * 0.17)), min(H2, b + int(lh * 0.80))
    tu, tv = max(0, c2[0] - int(lw * 1.3)), min(W2, c2[0] + int(lw * 1.3))
    tab = flat[t0:t1, tu:tv] if (t1 - t0 > 12 and tv - tu > 24) else None
    return {"band": flat[a:b, u:v], "angle": float(tilt), "lw": lw, "tab": tab}


def read_premier(frame, clubs, want_codes=True):
    """Both figures and both clubs off the English strip, or None."""
    import cv2, numpy as np
    lion = find_pl_lion(frame)
    if not lion:
        return None
    tilt = PL_TILT[1] if (PL_TILT[0] and time.time() - PL_TILT[0] < 60) else None
    got = pl_band(frame, lion, tilt)
    if not got:
        return None
    band, lw = got["band"], got["lw"]
    H, W = band.shape[:2]
    c = W // 2

    def cell(a, b, inv):
        x0, x1 = int(c + a * lw), int(c + b * lw)
        im = band[:, max(0, x0):min(W, x1)]
        if im.size == 0 or im.shape[1] < 20:
            return None
        g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        if inv:
            g = 255 - g
        g = cv2.copyMakeBorder(g, 12, 12, 12, 12, cv2.BORDER_CONSTANT,
                               value=int(np.median(g[:, :3])))
        return cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)

    def figure(im):
        if im is None:
            return None
        # the figures on this strip are drawn wide and stand nearly the full
        # height of their cell, so the usual width limit threw them out
        ms = ink_marks(im, hmin=0.25, hmax=0.95, wmax=0.80)
        if not ms:
            return None
        tall = max(m["h"] for m in ms)
        ms = [m for m in ms if m["h"] >= 0.55 * tall]
        out = ""
        for m in sorted(ms, key=lambda m: m["x"]):
            out += (classify_shape(m["img"], min_score=0.5)[0] or "?")
        return int(out) if out.isdigit() and len(out) <= 2 else None

    # The letters are white on claret on the home side and black on white on
    # the away side, so the home cells are turned round and the away code is
    # not. The offsets are in lion widths, measured off the strip itself.
    kh = read_code_plate(cell(-4.8, -2.6, True), clubs) if (clubs and want_codes) else None
    ka = read_code_plate(cell(2.4, 4.9, False), clubs) if (clubs and want_codes) else None
    h = figure(cell(-1.8, -0.70, True))
    a = figure(cell(0.45, 1.50, True))
    if h is None or a is None:
        return None
    PL_TILT[0], PL_TILT[1] = time.time(), got["angle"]
    tab = got.get("tab")
    mins = minutes_from_cell(tab, invert=True) if tab is not None else None
    return {"h": h, "a": a, "code_h": kh, "code_a": ka, "lion": lion,
            "badge": lion, "min": mins}


def read_code_plate(cell, known, min_score=0.40):
    """The club's three letters, off a scoreboard row.

    What goes wrong is not the letters but the company they keep: the edge of
    the plate, a corner of the crest or a strip of colour comes through the
    same filter and lands beside them, so three letters arrive as four marks
    and PSG reads as QPSG. Matching only equal lengths threw all of those
    away — 7% of real boards were being named.

    So the letters are not assumed to be exactly the marks found. Each code we
    know is tried against every run of marks its own length, and the best
    placement wins, which lets a stray mark at either end be ignored. The
    winner still has to beat the runner-up by a margin, because BAR and BAY
    differ by one letter and a guess between them opens the wrong match."""
    import cv2, numpy as np
    # Give the cut-out a margin of its own background first. Everything
    # touching the edge is flooded away before the marks are taken — that is
    # what leaves the letters standing alone — so a letter that happens to
    # reach the edge goes with it. Cut tight to the board, which is what makes
    # the letters findable at all, they reach the edge constantly: RMA came
    # through as one stray mark and the club went unnamed.
    if cell is not None and getattr(cell, "size", 0) and min(cell.shape[:2]) >= 12:
        import cv2 as _cv, numpy as _np
        _b = int(_np.median(_np.concatenate([cell[0, :], cell[-1, :]]).reshape(-1, cell.shape[2])[:, 0]))             if cell.ndim == 3 else int(_np.median(cell[0, :]))
        _m = max(4, int(0.10 * cell.shape[0]))
        cell = _cv.copyMakeBorder(cell, _m, _m, _m, _m, _cv.BORDER_CONSTANT,
                                  value=(_b, _b, _b) if cell.ndim == 3 else _b)

    def gather(wmax, wh_max):
        ms = ink_marks(cell, hmin=0.25, hmax=0.95, wmax=wmax, wh_max=wh_max)
        if not ms:
            return []
        # Letters on a board are all one size, so the middle height is what a
        # letter is — not the tallest thing found. The board draws a coloured
        # strip down its left edge that stands half as tall again as the
        # writing, and measuring against that kept the strip and threw the
        # letters out.
        import numpy as _np
        med_h = float(_np.median([m["h"] for m in ms]))
        ms = [m for m in ms if 0.62 * med_h <= m["h"] <= 1.55 * med_h]
        # the board draws hairline strips of colour between its panels, which
        # come through as marks as tall as the letters but a twentieth as wide.
        # No letter is that thin, and one of them read as an L and carried LIV
        # past the real RMA beside it.
        ms = [m for m in ms if m["w"] >= 0.18 * m["h"]]
        return split_merged(ms)

    # The ordinary board sets its letters apart and reads best from a tight
    # width limit: letting wide shapes in gives the coloured bands down the
    # plate to the splitter, which turns each into three false letters and
    # buries the real ones. So widen only when the tight pass found too few —
    # which is the case on the Spanish board, where the letters touch.
    marks = gather(0.40, 1.4)
    if len(marks) < 3:
        wide = gather(0.78, 3.6)
        if len(wide) > len(marks):
            marks = wide
    if not (2 <= len(marks) <= 6):
        return None
    marks = sorted(marks, key=lambda m: m["x"])

    TPL = cached_letters()
    if known:
        # score only the letters the known codes are actually spelt with. The
        # alphabet is twenty-six and the clubs between them use a third of it,
        # and this runs on every frame until the pair is named.
        want = set("".join(known))
        TPL = dict((ch, tl) for ch, tl in TPL.items() if ch in want)
    seen = []
    for m in marks:
        b = cv2.resize(m["img"], (DW, DH), interpolation=cv2.INTER_AREA).astype(np.float32)
        b -= b.mean()
        n = np.linalg.norm(b)
        if not n:
            return None
        b /= n
        seen.append({ch: max(float((b * t).sum()) for t in tl) for ch, tl in TPL.items()})

    if not known:
        out = ""
        for sc in seen:
            ch = max(sc, key=sc.get)
            out += ch if sc[ch] >= min_score else "?"
        return out

    fit = []
    for code in known:
        n = len(code)
        if n > len(seen):
            continue
        best = None
        for i in range(0, len(seen) - n + 1):
            v = sum(seen[i + j].get(code[j], -1.0) for j in range(n)) / n
            if best is None or v > best:
                best = v
        if best is not None:
            fit.append((best, code))
    fit.sort(reverse=True)
    if not fit or fit[0][0] < min_score:
        return None
    if len(fit) > 1 and fit[0][0] - fit[1][0] < 0.04:
        return None                      # two codes fit equally: that is a guess
    return fit[0][1]


def refine_plate(crop):
    """The board's own rectangle inside a cut-out that holds more than the board.

    Finding the board by brightness alone catches whatever else is bright and
    beside it — above all the green FC badge, which sits flush against it, and
    which a closing step happily bridges. Every crop taken from such a box is
    then wrong at its edges, which is why letters were being clipped and
    crests were coming out as crowd.

    Brightness is not what separates them. The board is white: bright AND
    almost colourless. The badge is bright and violently green, the crowd is
    bright and every colour at once. So look for pixels that are both light
    and unsaturated, and take the largest solid block of them. Returns a box
    [x, y, w, h] within the cut-out, or None if nothing in it looks like a
    board."""
    import cv2, numpy as np
    if crop is None or crop.size == 0 or min(crop.shape[:2]) < 20:
        return None
    c = crop if crop.ndim == 3 else cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
    hsv = cv2.cvtColor(c, cv2.COLOR_BGR2HSV)
    sat, val = hsv[:, :, 1], hsv[:, :, 2]
    vt = max(110.0, float(np.percentile(val, 85)) * 0.78)
    mask = ((val >= vt) & (sat <= 90)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 11), np.uint8))
    n, lab, stats, _c = cv2.connectedComponentsWithStats(mask, 8)
    if n <= 1:
        return None
    best = None
    for i in range(1, n):
        x, y, w, h, area = (stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP],
                            stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT],
                            stats[i, cv2.CC_STAT_AREA])
        if w < 0.35 * crop.shape[1] or h < 0.35 * crop.shape[0]:
            continue
        if area < 0.5 * w * h:                  # a board is a solid block
            continue
        if best is None or area > best[0]:
            best = (area, [int(x), int(y), int(w), int(h)])
    return best[1] if best else None


def plate_left_edge(crop):
    """Where the board itself starts inside the cut-out.

    The block that is found reaches past the board more often than not: the
    green FC badge sits flush against it and the closing step bridges the two,
    so the left part of the cut-out is badge, crowd or the end of an
    advertising hoarding. The board is the long run of columns that are bright
    all the way down, and the letters are inside that run — looking for them
    anywhere else is what left six boards in ten unnamed."""
    import cv2, numpy as np
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    if g.shape[1] < 30:
        return 0
    col = np.median(g, axis=0).astype(np.float32)
    thr = max(90.0, float(np.percentile(col, 80)) * 0.80)
    on = col >= thr
    best = (0, 0)                                  # (length, start)
    run = 0
    for i, v in enumerate(on):
        run = run + 1 if v else 0
        if run > best[0]:
            best = (run, i - run + 1)
    # only trust it when the bright run is most of the cut-out: a board is
    # wide, and a short bright patch is something else
    return best[1] if best[0] >= 0.45 * len(col) else 0


def read_final_screen(frame):
    """The MATCH RESULTS screen, which says the thing nothing else does.

    At the final whistle FC puts the score up in the middle of the screen in
    figures three times the size of anything on the scoreboard, with Home on
    the left and Away on the right. It is the one place the final score is
    stated plainly, it cannot be confused with the pause menu, and it settles
    the goal scored on ninety minutes that the board never had time to show.
    Returns (home, away) or None."""
    H, W = frame.shape[:2]
    # a generous band, so that re-aiming the camera does not lose the figures:
    # they are found by being far taller than anything else in it
    band = frame[int(H * 0.40):int(H * 0.98), int(W * 0.10):int(W * 0.97)]
    if min(band.shape[:2]) < 60:
        return None
    marks = ink_marks(band, hmin=0.20, hmax=0.90, wmax=0.30)
    if len(marks) < 2:
        return None
    tallest = max(m["h"] for m in marks)
    big = [m for m in marks if m["h"] >= 0.70 * tallest]
    # The club crests are exactly as large as the figures, so size alone will
    # not separate them. A crest simply does not look like a digit: ask for a
    # confident reading and the crests fall away on their own.
    hits = []
    for m in big:
        val, sc = classify_shape(m["img"], min_score=0.85)
        if val is not None:
            hits.append((m, str(val)))
    if not (2 <= len(hits) <= 4):
        return None
    ys = [m["y"] + m["h"] / 2.0 for m, _v in hits]
    hs = [m["h"] for m, _v in hits]
    if max(ys) - min(ys) > 0.3 * min(hs):        # the score sits on one line
        return None
    hits.sort(key=lambda t: t[0]["x"])
    gaps = [(hits[i + 1][0]["x"] - (hits[i][0]["x"] + hits[i][0]["w"]), i) for i in range(len(hits) - 1)]
    split = max(gaps)[1] + 1                      # the widest gap is the dash
    left, right = hits[:split], hits[split:]
    if not left or not right or len(left) > 2 or len(right) > 2:
        return None
    n1 = int("".join(v for _m, v in left))
    n2 = int("".join(v for _m, v in right))
    if n1 > 30 or n2 > 30:
        return None
    return n1, n2

def read_clock(frame, plate, prev=None):
    """The match minute, from the strip just under the scoreboard.

    FC counts to ninety however long the halves really are, so a clock reading
    ninety is full time and nothing else is. That matters because the screen
    you get at the final whistle is the same screen you get when somebody
    pauses to argue, and only the clock tells the two apart. Returns the
    minutes, or None."""
    x, y, w, h = plate
    H, W = frame.shape[:2]
    cy = y + h                                  # the clock sits directly below
    ch = int(h * 0.55)
    cx, cw = x, int(w * 0.55)
    if cy + ch > H or cx + cw > W or ch < 20:
        return None
    marks = ink_marks(frame[cy:cy + ch, cx:cx + cw], hmin=0.25, hmax=0.95, wmax=0.30)
    if not (2 <= len(marks) <= 6):
        marks = []
    marks = sorted(marks, key=lambda m: m["x"])
    digits = ""
    for m in marks[:2]:                         # the minutes, left of the colon
        val, score = classify_shape(m["img"], min_score=0.55)
        if val is None:
            digits = ""
            break
        digits += str(val)
    try:
        n = int(digits)
    except ValueError:
        n = None
    if n is not None and prev is not None and not (prev - 2 <= n <= prev + 15):
        n = None                     # a clock does not jump about; that is a misread
    if n is None or not (0 <= n <= 90):
        # Fall back on reading the strip whole. The figures sit hard against
        # the top of it, and everything touching the edge of a cut-out is
        # flooded away before the marks are taken, so they went with it — which
        # is why a match could run to its end with the clock last seen at the
        # seventy-eighth minute.
        import cv2, numpy as np
        band = frame[max(0, cy - int(h * 0.05)):min(H, cy + ch), cx:cx + cw]
        if band.size and min(band.shape[:2]) >= 14:
            g = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
            v = int(np.percentile(g, 20))
            band = cv2.copyMakeBorder(band, 14, 14, 14, 14, cv2.BORDER_CONSTANT,
                                      value=(v, v, v))
            n = minutes_from_cell(band)
            if n is not None and (prev is None or prev - 2 <= n <= prev + 15):
                return n
            if prev is not None:
                # Ask again, less sure of itself. An eight on this board is as
                # likely to be read as a three or a six, which is why the clock
                # stopped at seventy-seven in one match and seventy-eight in
                # another and never reached the ninety that ends them. A doubtful
                # figure is safe to take once it has to agree with the minute
                # before it: a clock that cannot run backwards and cannot jump a
                # quarter of an hour cannot invent an ending.
                n = minutes_from_cell(band, min_score=0.36)
                if n is not None and prev - 2 <= n <= prev + 15:
                    return n
        return None
    return n

def plate_parts(crop, score_x=None, rows=None):
    """The scoreboard plate split into the four things it carries: a club code
       on each row, and that row's score.

    Where the code sits is not a fixed fraction of the plate. The ordinary
    board puts it at the left with a crest beside it; the Spanish one puts a
    league badge and the clock on the left and the codes in the middle. And
    the cut-out itself shifts from frame to frame, which was enough on its own
    to miss the letters in six boards out of ten. What holds everywhere is
    that the code is the writing immediately to the left of the figures, so
    the cells are measured from the figures when their position is known."""
    h, w = crop.shape[:2]
    top, mid, bot = 0, h // 2, h
    if rows and 0 <= rows[0] < rows[1] < rows[2] <= h and rows[2] - rows[0] > 20:
        top, mid, bot = rows
    left = plate_left_edge(crop)
    if score_x and 0.2 * w < score_x < 0.98 * w:
        sx = int(score_x)
        # everything between the board's own left edge and the figures: on the
        # ordinary board a crest sits in there too, which the letter matching
        # steps over, but the badge and the crowd outside the board do not
        # belong in the picture at all
        cx0, cx1 = left, max(left + 1, int(sx - w * 0.015))
    else:
        sx, cx0, cx1 = int(w * 0.68), left, max(left + 1, int(w * 0.50))
    return {"code_h": crop[top:mid, cx0:cx1], "code_a": crop[mid:bot, cx0:cx1],
            "cell_h": crop[top:mid, sx:w], "cell_a": crop[mid:bot, sx:w]}


def clear_border(th):
    """Wipe everything that touches the edge of the cut-out.

    Whichever way round the board is drawn — dark digits on a white plate or
    white digits on a dark one — one of the two polarities leaves the digits as
    separate white shapes and everything around them as a single white mass
    running off the edge. Flooding that mass away from the border leaves the
    digits standing alone, with the ink white, which is what the classifier
    expects and what keeps the hole in a 0 a hole."""
    import cv2, numpy as np
    n, lab, _st, _c = cv2.connectedComponentsWithStats(th, 8)
    if n <= 1:
        return th
    edge = np.concatenate([lab[0, :], lab[-1, :], lab[:, 0], lab[:, -1]])
    keep = np.ones(n, np.uint8)
    keep[np.unique(edge)] = 0
    keep[0] = 0                                  # label 0 is the background
    return (keep[lab] * 255).astype(np.uint8)


def find_plate(frame, search=None, near=None):
    """the most board-like bright block, or None (see find_plates)"""
    got = find_plates(frame, search, near)
    return got[0] if got else None


def find_plates(frame, search=None, near=None):
    """Locate the white scoreboard plate, wherever FC has put it this minute.

    A fixed rectangle does not survive a match: the board is large at kick-off
    and shrinks once play settles, and it sits higher or lower depending on the
    broadcast camera. What stays constant is the thing itself — a bright, almost
    white block, about twice as wide as it is tall, up in the corner. Find that
    and the digits are inside it. Returns [x, y, w, h] or None."""
    import cv2, numpy as np
    H, W = frame.shape[:2]
    sx, sy, sw, sh = search or [0, int(H * 0.05), int(W * 0.60), int(H * 0.45)]
    sx, sy = max(0, sx), max(0, sy)
    sw, sh = min(sw, W - sx), min(sh, H - sy)
    if sw < 100 or sh < 100:
        return None
    area = frame[sy:sy + sh, sx:sx + sw]
    g = cv2.cvtColor(area, cv2.COLOR_BGR2GRAY) if area.ndim == 3 else area
    # A fixed brightness cannot serve: the television is dim in a night match
    # and glaring in a day one. Take the threshold from the picture itself —
    # the plate is among the brightest things in the corner — and try a couple
    # of levels rather than betting on one.
    levels = [max(120.0, float(np.percentile(g, p))) for p in (99, 97, 94, 90, 85, 75)]
    found = []
    for lvl in levels:
        _t, th = cv2.threshold(g, lvl, 255, cv2.THRESH_BINARY)
        th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((5, 15), np.uint8))
        found += _plate_from(th, sx, sy, sw, sh, near)
    if not found:
        return []
    out = []
    for _score, box in sorted(found, key=lambda t: -t[0]):
        x, y, w, h = box
        pad = int(h * 0.06)                     # a hair of margin, no more
        x, y = max(0, x - pad), max(0, y - pad)
        cand = [x, y, min(w + 2 * pad, W - x), min(h + 2 * pad, H - y)]
        if any(abs(cand[0] - o[0]) < 30 and abs(cand[1] - o[1]) < 30 for o in out):
            continue                            # the same thing at another level
        out.append(cand)
        if len(out) >= 12:
            break
    return out


def _plate_from(th, sx, sy, sw, sh, near=None):
    import cv2
    cnts, _h = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        # the board is a third of the size it was when the camera looked only
        # at the corner of the screen, so what counts as big enough has to come
        # down with it
        if w < 110 or h < 40 or w > sw * 0.9:
            continue
        if not (1.3 < w / float(h) < 4.0):
            continue
        # Not too strict about how solid it is: at a threshold high enough to
        # separate the board from a bright crowd behind it, only the whitest
        # part of the board survives, and demanding most of the box be white
        # threw the board away and kept an advertising hoarding.
        if cv2.countNonZero(th[y:y + h, x:x + w]) / float(w * h) < 0.33:
            continue
        # Once the board has been found, staying on it beats jumping to
        # whatever is brightest: a caption or a white shirt can be larger for a
        # frame, and following that loses the comparison the goals rely on.
        score = w * h
        if near:
            cx, cy = sx + x + w / 2.0, sy + y + h / 2.0
            nx, ny = near[0] + near[2] / 2.0, near[1] + near[3] / 2.0
            score = score * (4.0 if abs(cx - nx) < near[2] and abs(cy - ny) < near[3] else 1.0)
        out.append((score, [sx + x, sy + y, w, h]))
    return out


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


def send(key, h, a, dry, clubs=None, restart=False, finish=False, correct=False, exact=False,
         close_pred=False, clock=None):
    if dry:
        print("   (בדיקה בלבד — לא נשלח)")
        return {"dry": True}
    payload = {"key": key, "h": h, "a": a}
    if clubs:
        payload["clubs"] = clubs
    if restart:
        payload["restart"] = True
    if finish:
        payload["finish"] = True
    if correct:
        payload["correct"] = True
    if exact:
        payload["exact"] = True
    if close_pred:
        payload["closePred"] = True
    if clock is not None:
        payload["clock"] = clock          # the match minute, for the app to show
    body = json.dumps({"data": payload}).encode()
    req = urllib.request.Request(ENDPOINT, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode()).get("result", {})


class Watcher:
    """Asks the server what it wants, out of the way of the reading.

    The question — is a match open, is the camera wanted — changes once in a
    quarter of an hour, but asking it costs a round trip to Europe, and asking
    it on the reading loop meant every few seconds the camera simply stopped
    being looked at. A thread carries the cost instead; the loop reads the last
    answer and never waits."""

    def __init__(self, key):
        import threading
        self.key = key
        self.state = {}
        self.error = None
        self.stamp = 0
        self.lock = threading.Lock()
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _run(self):
        while True:
            try:
                st = ping(self.key)
                with self.lock:
                    self.state, self.error, self.stamp = st, None, time.time()
            except Exception as e:
                with self.lock:
                    self.error = e
            time.sleep(4)

    def get(self):
        with self.lock:
            return dict(self.state), self.error, self.stamp


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
    cell_ref, cell_pending = {}, {}          # the two score squares
    last_plate = None
    last_seen_plate = None                   # when the board was last on screen
    plate_reset = 0
    zero_since = None                        # since when the board has read nil-nil
    zero_n, zero_codes = 0, False            # how many, and were the clubs made out
    last_read = 0                            # when the digits were last legible
    open_try = 0
    code_run = None                          # the same club pair, seen how often
    es_run = None                            # the same, off the Spanish board
    full_time, clock_seen = None, None        # when the clock first showed ninety
    clock_at = 0                             # when that minute was read
    pred_closed = False                       # told the server the guessing is over
    late, late_first = False, None            # has this match reached its closing stretch
    opened_at = None                         # when this match was opened
    ninety = 0                                # how often it has said so
    final_seen, final_try = None, 0           # the MATCH RESULTS screen, read twice
    goals = {"h": 0, "a": 0}
    last_good_block = None
    beat = 0                                 # last heartbeat line
    cycles = reads_ok = 0                    # what the loop managed since then
    t_find = t_score = t_code = 0.0
    held_plate, held_at, held_ok = None, 0, False
    stuck, dumped = 0, 0                     # for keeping a picture of a failure
    dumped_codes = 0
    refused, refused_at, refused_first = None, 0, 0   # a value the server turned down
    warm_until = 0                           # no goals counted right after waking
    warm_note = None
    watcher = None if args.test else Watcher(key)
    try:
        while True:
            # the app decides when there is something to read; while there is
            # nothing, the camera is left alone and we only check now and then
            if not args.test:
                st, err, stamp = watcher.get()
                if stamp and time.time() - stamp < 60:
                    # a live tournament is enough: the camera opens the match
                    want = st.get("on", True) and bool(st.get("live", False) or st.get("tournament"))
                else:
                    want = False
                    if err and time.time() - idle_note > 120:
                        print(time.strftime("%H:%M:%S"), "אין קשר לשרת:", err)
                        idle_note = time.time()
                if want != working:
                    working = want
                    print(time.strftime("%H:%M:%S"), "קורא מהמצלמה" if want else "ממתין — אין משחק חי או שהקריאה כבויה")
                    if want:
                        change_ref, change_pending = {}, {}
                        last_seen_plate = time.time()   # so a match left open still closes
                        warm_until = time.time() + args.warmup
                        try:
                            st2 = st
                            last_sent = (st2.get("h") or 0, st2.get("a") or 0) if st2.get("live") else None
                            goals["h"], goals["a"] = last_sent
                            # Start the clock on it as well. A match left open
                            # in the app while the reader was restarted had
                            # nothing to measure its silence against — the
                            # closing rule needs a moment to count from — so it
                            # stayed open for fifty minutes with the television
                            # showing a menu, and the result was never written.
                            if last_sent and opened_at is None:
                                opened_at = time.time()
                                last_seen_plate = time.time()
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
            # "fixed": the camera is zoomed on the scoreboard and never moves,
            # so the marked boxes are better than hunting for the board
            found = None if cfg.get("fixed") else find_board(
                frame, cfg.get("search", [0, 0, frame.shape[1], frame.shape[0]]), last_block)
            if found:
                last_block = found["block"]
                cfg_boxes = found
            else:
                cfg_boxes = cfg                    # fall back to the marked boxes
            cut = lambda b: frame[max(0, b[1]):b[1] + b[3], max(0, b[0]):b[0] + b[2]]
            crop_h, crop_a = cut(cfg_boxes["home"]), cut(cfg_boxes["away"])
            region = cfg.get("region")
            if region:
                crop_h = crop_a = cut(region)          # one area, read as a whole
            # the clubs are read off the board that was found, below — the
            # calibrated crest boxes belong to a camera position from before
            # it was fixed to the wall, so whatever is at those coordinates
            # now is not a crest, and a badge bank large enough to match
            # something would name the wrong club and open the wrong fixture 
            codes = None
            cycles += 1
            # Hunting for the board costs more than everything else here put
            # together, and the board does not move between one frame and the
            # next. Keep the box that worked, and go looking again only when it
            # stops yielding a score, or every couple of seconds in case the
            # board has quietly shifted.
            _t0 = time.time()
            if held_plate and time.time() - held_at < (2 if held_ok else 0.5):
                plate = held_plate
            else:
                # An advertising hoarding is bright, wide and rectangular, and
                # on a Premier League pitch it is bigger than the scoreboard.
                # Size cannot choose between them; being readable can. Try the
                # likely blocks and keep the one a score comes off.
                cands = find_plates(frame, cfg.get("search"), last_plate)
                plate = cands[0] if cands else None
                # The block that is found often takes in the clock strip under
                # the board as well, and a third row of figures breaks the
                # reading. Try the block and a couple of trims of it, and keep
                # whichever a score actually comes off.
                done = False
                for c in cands[:6]:
                    for b in (c,
                              [c[0], c[1], c[2], max(60, int(c[3] * 0.62))],
                              [c[0] + int(c[2] * 0.15), c[1], int(c[2] * 0.85), max(60, int(c[3] * 0.70))]):
                        # A scoreboard carries two club codes and two scores,
                        # so it is always about twice as wide as it is tall and
                        # never small. An advertising hoarding reading AXA came
                        # through as 0-3 from a crop almost square; shape alone
                        # rules that out before a single digit is considered.
                        if b[2] < 230 or not (1.6 < b[2] / float(max(1, b[3])) < 3.4):
                            continue
                        if score_in_region(cut(b)):
                            plate = b
                            done = True
                            break
                    if done:
                        break
                held_plate, held_at = plate, time.time()
            t_find += time.time() - _t0
            if plate:
                # the board moves and changes size during a match, so where it
                # is now beats where it was when the camera was calibrated
                # Cut to the board itself before reading the clubs. The block
                # that was found usually reaches past it onto the green badge
                # flush against it, and cells measured from the wrong edges
                # clipped the letters. Over the boards the reader had kept,
                # this alone took naming both clubs from 17% to 25%.
                pc = cut(plate)
                inner = refine_plate(pc)
                if inner:
                    pc = pc[inner[1]:inner[1] + inner[3], inner[0]:inner[0] + inner[2]]
                dbg3 = {}
                sx3 = dbg3.get("score_x") if score_in_region(pc, debug=dbg3) else None
                parts = plate_parts(pc, sx3, dbg3.get("rows"))
                if cfg.get("clubs") and not codes:
                    _t0 = time.time()
                    kh = read_code_plate(parts["code_h"], cfg["clubs"])
                    ka = read_code_plate(parts["code_a"], cfg["clubs"])
                    t_code += time.time() - _t0
                    if kh and ka and kh != ka:
                        # Naming the clubs can end a match — the server takes a
                        # different pair to mean the next fixture has started —
                        # so one frame is not enough. The same pair three times
                        # running is.
                        if code_run and code_run[0] == (kh, ka):
                            code_run = (code_run[0], code_run[1] + 1)
                        else:
                            code_run = ((kh, ka), 1)
                        if code_run[1] >= 3:
                            codes = {"h": cfg["clubs"][kh], "a": cfg["clubs"][ka]}
            # The Spanish board is laid out quite differently — a red league
            # badge with the clock under it, the codes in white on black, the
            # figures in black on white — and the ordinary finder reads nothing
            # off it. Looking for the badge costs eight milliseconds and comes
            # back empty on every other board, so it is simply tried on each
            # pass and the ordinary reading left alone unless it answers.
            es = read_laliga(frame, cfg.get("clubs"), not codes) if cfg.get("clubs") else None
            if es is None and cfg.get("clubs"):
                # and the English strip, which is a different shape again: one
                # long band with the league's lion in the middle of it
                es = read_premier(frame, cfg.get("clubs"), not codes)
                if es and "badge" not in es:
                    es["badge"] = es["lion"]
            if es:
                last_seen_plate = time.time()
                if not plate:
                    plate = es["badge"]          # something to open the match on
                if es["code_h"] and es["code_a"] and es["code_h"] != es["code_a"]:
                    pair = (es["code_h"], es["code_a"])
                    # count readings that worked, not frames: the code column
                    # turns over to the clubs' crests every few seconds, and
                    # three frames running is a thing this board never gives
                    es_run = (pair, es_run[1] + 1) if es_run and es_run[0] == pair else (pair, 1)
                    if es_run[1] >= 2 and not codes:
                        codes = {"h": cfg["clubs"][pair[0]], "a": cfg["clubs"][pair[1]]}
            dh, da = {}, {}
            if region or plate:
                # the board drifts a little between styles and camera nudges, so
                # try the marked area and a few shifts around it
                _t0 = time.time()
                got = score_in_region(cut(plate)) if plate else None
                t_score += time.time() - _t0
                if got:
                    reads_ok += 1
                    held_ok = True
                    stuck = 0
                    # A board that gives a score but never gives the club
                    # names cannot open a fixture, and the names are what say
                    # which match is being played. Keep one picture of that so
                    # the codes can be taught.
                    if not codes and time.time() - dumped_codes > 90:
                        dumped_codes = time.time()
                        folder = os.path.join(HERE, "debug")
                        os.makedirs(folder, exist_ok=True)
                        tag = time.strftime("%H%M%S") + "_nocodes"
                        imwrite_any(os.path.join(folder, tag + "_plate.png"), cut(plate))
                        # and the whole picture: a cut-out cannot show whether the board
                        # was found in the right place, which is where most of these
                        # failures turn out to live
                        imwrite_any(os.path.join(folder, tag + "_whole.png"), frame)
                        print(now, "תוצאה נקראת אבל לא השמות — שמרתי תמונה ב־debug/" + tag)
                    # This is the board: a score came off it. A pale card on
                    # the main menu is bright and rectangular too, and while
                    # that counted as the board the match on screen never
                    # appeared to end, so nothing was ever written down.
                    last_seen_plate = time.time()
                else:
                    # Nothing legible for a good while: keep one picture of what
                    # the reader is looking at, so the fault can be seen without
                    # taking the camera away from the match.
                    stuck = stuck or time.time()
                    if time.time() - stuck > 30 and time.time() - dumped > 120:
                        dumped = time.time()
                        folder = os.path.join(HERE, "debug")
                        os.makedirs(folder, exist_ok=True)
                        tag = time.strftime("%H%M%S")
                        imwrite_any(os.path.join(folder, tag + "_frame.png"), frame)
                        if plate:
                            imwrite_any(os.path.join(folder, tag + "_plate.png"), cut(plate))
                        print(now, "לא מצליח לקרוא — שמרתי תמונה ב־debug/" + tag)
                    held_ok = False              # this box has gone stale
                H, W = frame.shape[:2]
                region = plate or region
                # only when the board could not be found do the marked area and
                # a few shifts around it get a turn; a reading already taken off
                # the real board must not be thrown away for one of those
                for dx, dy, ds in () if got else ((0, 0, 0), (0, 0, -40), (-40, 0, 0), (40, 0, 0),
                                   (0, -30, 0), (0, 30, 0), (60, 0, -60), (-60, 0, -60), (0, 0, 60)):
                    rx = [max(0, region[0] + dx), max(0, region[1] + dy),
                          max(120, region[2] + ds), max(120, region[3] + ds // 2)]
                    rx[2] = min(rx[2], W - rx[0])          # stay inside the picture
                    rx[3] = min(rx[3], H - rx[1])
                    if rx[2] < 60 or rx[3] < 60:
                        continue
                    got = score_in_region(cut(rx))
                    if got:
                        break
                h, a = (got[0], got[1]) if got else (None, None)
                dh["score"] = da["score"] = 0.9 if got else 0
                if es and not got:
                    h, a = es["h"], es["a"]
                    dh["score"] = da["score"] = 0.9
                # Nobody wins thirty-nil. A caption or a stray pair of digits
                # read off the screen between matches gave "30 - 0" once, and
                # had a match been open it would have gone in as the score.
                if (h is not None and not (0 <= h <= 15)) or (a is not None and not (0 <= a <= 15)):
                    h = a = None
                    dh["score"] = da["score"] = 0
            else:
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

            # --- the match starts: open it at nil-nil --------------------
            # Two clubs on a scoreboard mean a match is under way, and nobody
            # scores in the first second, so nil-nil is the safe opening. The
            # server works out which fixture it is from the two club codes.
            if plate:
                pass        # found something bright; whether it is the board
                            # is decided below, by whether it can be read
                if (last_sent is None and codes and not args.test
                        and time.time() >= warm_until and time.time() - open_try > 10):
                    open_try = time.time()
                    try:
                        r = send(key, 0, 0, args.dry_run, codes)
                        if r.get("live"):
                            last_sent = (r.get("h", 0), r.get("a", 0))
                            goals["h"], goals["a"] = last_sent
                            cell_ref, cell_pending = {}, {}
                            pred_closed = False
                            late, late_first = False, None
                            opened_at = time.time()
                            print(now, "נפתח משחק חי:", codes["h"], "נגד", codes["a"], "· 0 - 0")
                        elif r.get("golden") == "pending":
                            # the final is level and being played out: no fixture
                            # to open, but the first goal has to reach the server
                            last_sent = (0, 0)
                            goals["h"], goals["a"] = 0, 0
                            print(now, "שער זהב — ממתין לשער הראשון")
                        elif r.get("golden") == "decided":
                            print(now, "שער הזהב הוכרע")
                            last_sent = None
                        elif r.get("noFixture"):
                            print(now, "אין מחזור פתוח עם", codes["h"], "נגד", codes["a"])
                    except Exception as e:
                        print(now, "פתיחה נכשלה:", e)
            if plate and (got or es) and not args.no_clock:
                # the Spanish board keeps its clock under the league badge and
                # the English one on a tab below the strip, so each reader
                # hands back its own minute; only the ordinary board has it in
                # the strip under the plate
                mins = (es or {}).get("min")
                if mins is None:
                    mins = read_clock(frame, plate, clock_seen)
                if mins is not None:
                    clock_seen, clock_at = mins, time.time()
                    # A match that has been late once is late from then on.
                    # The last reading is no guide: the clock gave 89 and then
                    # 28 while the game was ending, and both were the same
                    # match. Two readings of 85 or more, half a minute apart,
                    # are what a real second half looks like and what a stray
                    # misread does not.
                    if mins >= 85:
                        if late_first is None:
                            late_first = time.time()
                        elif not late and time.time() - late_first > 30:
                            late = True
                            print(now, "המשחק בשלב מאוחר (דקה " + str(mins) + ")")
                    if mins >= 90:
                        # The clock is read the same way the score is, and it
                        # has been seen to say ninety and then eighty-three.
                        # Closing a match on one such reading would end it in
                        # the middle, so it has to say ninety three times.
                        ninety += 1
                        if ninety >= 3 and full_time is None:
                            full_time = time.time()
                            print(now, "השעון הגיע ל־90 שלוש פעמים — סוגר בעוד עשר שניות")
                    # Guessing closes when the match reaches its twentieth
                    # minute. Nobody watching the television can be expected to
                    # notice that themselves, so the reader says so once.
                    if mins >= 20 and not pred_closed and not args.test:
                        pred_closed = True
                        try:
                            r = send(key, 0, 0, args.dry_run, None, close_pred=True)
                            if r.get("closedPred"):
                                print(now, "דקה 20 — הניחושים נסגרו")
                        except Exception as e:
                            print(now, "סגירת ניחושים נכשלה:", e)
                    elif mins < 85:
                        # The clock is read as noisily as anything else — it
                        # gave 81, 16 and 18 during a match that was nowhere
                        # near any of them. Before ninety that noise only has
                        # to not accumulate; after ninety it must not cancel
                        # the ending, which is what stopped a match closing
                        # three seconds before it would have. Only a new match
                        # clears that, where it is opened.
                        ninety = 0
            # full time on the clock, and then the board goes: that is the
            # whistle, and there is no need to wait four minutes to be sure
            # --- ninety minutes on the clock -----------------------------
            # The clock reaching ninety is the end of the match, and waiting
            # for the board to leave the screen after that only delays writing
            # down what is already settled. Ten seconds for a goal in stoppage
            # time to appear, and then it goes down. A goal later than that is
            # rare enough to be worth typing in by hand.
            if full_time and time.time() - full_time > 10 and not args.test:
                print(now, "דקה 90 ועברו עשר שניות — מסיים ושומר")
                try:
                    r = send(key, 0, 0, args.dry_run, None, finish=True)
                    if r.get("saved"):
                        print(now, "התוצאה נשמרה בטורניר:", r.get("h"), "-", r.get("a"))
                    elif r.get("why"):
                        print(now, "לא נשמר:", r.get("why"))
                except Exception as e:
                    print(now, "סיום נכשל:", e)
                goals["h"], goals["a"] = 0, 0
                cell_ref, cell_pending, last_plate = {}, {}, None
                last_sent, last_seen_plate, code_run = None, None, None
                full_time, final_seen, clock_seen, ninety = None, None, None, 0
                late, late_first, opened_at = False, None, None
                time.sleep(args.interval)
                continue

            # --- the final whistle, stated in figures --------------------
            if not plate and not args.test and time.time() - final_try > 3:
                final_try = time.time()
                fin = read_final_screen(frame)
                if fin and final_seen and final_seen[0] == fin:
                    final_seen = (fin, final_seen[1] + 1)
                elif fin:
                    final_seen = (fin, 1)
                else:
                    final_seen = None
                if final_seen and final_seen[1] >= 2:
                    print(now, "מסך התוצאה הסופית:", fin[0], "-", fin[1], "— מסיים ושומר")
                    try:
                        r = send(key, fin[0], fin[1], args.dry_run, None, finish=True, exact=True)
                        if r.get("saved"):
                            print(now, "התוצאה נשמרה בטורניר:", r.get("h"), "-", r.get("a"))
                        elif r.get("why"):
                            print(now, "לא נשמר:", r.get("why"))
                    except Exception as e:
                        print(now, "סיום נכשל:", e)
                    goals["h"], goals["a"] = 0, 0
                    cell_ref, cell_pending, last_plate = {}, {}, None
                    last_sent, last_seen_plate, code_run = None, None, None
                    full_time, final_seen = None, None
                    time.sleep(args.interval)
                    continue

            # How long to wait for a board before deciding the match is over.
            # At ninety it is the final whistle and twenty seconds is plenty;
            # late in the second half, half a minute; otherwise seventy, which
            # is the heart of the matter: the next match starts about three
            # minutes after the last one ends, so a minute and ten with nothing
            # readable on the screen is the gap between matches and not a pause
            # to argue, which lasts seconds, nor a replay, which lasts less.
            #
            # It used to wait four minutes AND require the clock to have been
            # read — and the clock could not be read on any board but the
            # ordinary one, so no match ever closed and a whole tournament went
            # unrecorded. Now the clock only shortens the wait; it is not what
            # permits the match to end.
            gone = (time.time() - last_seen_plate) if last_seen_plate else 0
            patience = 20 if full_time else (35 if late else 150)
            # A board that cannot be read is not the same as a board that is
            # not there, and this reader fails to read one for a minute at a
            # time in the ordinary course of a match. Seventy seconds of that
            # closed a match at its tenth minute and wrote the score down. So
            # the quick answer is only allowed once the match is known to be
            # near its end; without that it is two and a half minutes, which
            # is still inside the three between one match and the next.
            old_enough = opened_at is not None and time.time() - opened_at > 120
            # and whatever the board is doing, a clock that said the tenth
            # minute a moment ago says the match is not over
            # "early" has to mean early. A match whose last readable minute
            # was the seventy-eighth is two minutes from its end, and holding
            # it open for four more on that basis left a finished match
            # unsaved. Below the sixtieth, and read in the last three minutes.
            early = (clock_seen is not None and clock_seen < 60
                     and time.time() - clock_at < 180)
            # What ends a match is that nothing has been read off it for a
            # long while — not that no bright block can be seen. On the screen
            # that follows a match the finder goes on returning a block of some
            # kind, and requiring none to be found meant the condition was
            # never once true: a finished match sat open until somebody noticed.
            # last_seen_plate is the last time a score actually came off the
            # board, which is the thing that matters.
            if (last_seen_plate and gone > patience and not args.test
                    and last_sent and not early and (full_time or late or old_enough)):
                print(now, "המשחק נגמר (דקה " + str(clock_seen) + ", אין קריאה " +
                      str(int(gone)) + " שניות) — מסיים ושומר")
                try:
                    r = send(key, 0, 0, args.dry_run, None, finish=True)
                    if r.get("saved"):
                        print(now, "התוצאה נשמרה בטורניר:", r.get("h"), "-", r.get("a"))
                    elif r.get("why"):
                        print(now, "לא נשמר:", r.get("why"))
                except Exception as e:
                    print(now, "סיום נכשל:", e)
                goals["h"], goals["a"] = 0, 0
                cell_ref, cell_pending, last_plate = {}, {}, None
                last_sent, last_seen_plate, code_run, full_time = None, None, None, None
                late, late_first, opened_at = False, None, None

            # --- a match restarted --------------------------------------
            # Players do start a match over. The board goes back to nil-nil
            # while the app is holding the old score, and since a lower reading
            # is normally noise the app would sit on a game nobody is playing.
            # The clubs are unchanged, so it is the same fixture, not the next
            # one: only the score goes back. Ten seconds of a steady nil-nil
            # before believing it, so one bad frame cannot wipe a real score.
            plausible = not (last_sent and h is not None and a is not None and
                             (h - last_sent[0] > 3 or a - last_sent[1] > 3))
            if h == 0 and a == 0 and plate:
                if zero_since is None:
                    zero_since, zero_n, zero_codes = time.time(), 0, False
                zero_n += 1
                zero_codes = zero_codes or bool(codes)
            elif h is not None and a is not None and plausible:
                zero_since = None        # a score was read, and it is not nil-nil
            # a reading already known to be impossible must not cancel the wait
            # either: it is a misread, and a misread is not evidence of a score
            # a frame nothing could be read from says nothing either way, and
            # must not keep restarting the count
            # Waiting ten seconds to believe a restart was cautious to the
            # point of being useless — the players are already playing. Several
            # clean nil-nil readings in a row, off a board whose club codes were
            # made out, say the same thing in about two seconds, and say it on
            # better evidence than the clock ever did.
            # Four clean nil-nil readings off a board whose clubs were also
            # made out is the quickest safe answer. Failing that, six clean
            # readings on their own will do — a stray nil-nil is unlikely to
            # survive six times over now that lines of writing are refused.
            waited = (time.time() - zero_since) if zero_since else 0
            sure = zero_since and ((zero_n >= 4 and zero_codes and waited > 1.5) or
                                   (zero_n >= 6 and waited > 2.5))
            patient = zero_since and zero_n >= 10 and waited > 8
            if ((sure or patient) and last_sent
                    and (last_sent[0] or last_sent[1]) and not args.test):
                try:
                    r = send(key, 0, 0, args.dry_run, codes, restart=True)
                    if r.get("restart"):
                        print(now, "המשחק התחיל מחדש — התוצאה חזרה ל־0 - 0",
                              "· לקח %.1f שניות · %d קריאות · שמות: %s" %
                              (waited, zero_n, "כן" if zero_codes else "לא"))
                        goals["h"], goals["a"] = 0, 0
                        last_sent = (0, 0)
                        cell_ref, cell_pending = {}, {}
                except Exception as e:
                    print(now, "איפוס נכשל:", e)
                zero_since = None

            # --- goals by the squares changing --------------------------
            # The digits cannot be read in every frame, but a goal always shows
            # as the square at the end of a row changing and then staying
            # changed. Top row is the home side, bottom row the away side. A
            # change must hold for a few seconds, so a replay cannot score, and
            # a board that has resized is a new baseline rather than two goals.
            if plate and not args.no_change:
                # The found box breathes by a few pixels from frame to frame.
                # Only a real move — the board changing size at half time, or
                # jumping across the picture — is worth forgetting the squares
                # over, and never twice within a few seconds.
                if (last_plate and time.time() - plate_reset > 5 and
                        (abs(plate[2] - last_plate[2]) > last_plate[2] * 0.30 or
                         abs(plate[3] - last_plate[3]) > last_plate[3] * 0.30 or
                         abs(plate[0] - last_plate[0]) > 150 or
                         abs(plate[1] - last_plate[1]) > 150)):
                    cell_ref, cell_pending = {}, {}
                    plate_reset = time.time()
                    print(now, "הלוח זז או שינה גודל — משווה מחדש")
                # keep the steadier of the two so a one-frame wobble is not a move
                last_plate = plate if last_plate is None else [
                    int(round(o * 0.7 + n * 0.3)) for o, n in zip(last_plate, plate)]
                fired = []
                for side, cell in (("h", parts["cell_h"]), ("a", parts["cell_a"])):
                    sig = plate_signature(cell)
                    ref = cell_ref.get(side)
                    if ref is None:
                        cell_ref[side] = sig
                        continue
                    if sig_same(sig, ref):
                        cell_pending.pop(side, None)
                        continue
                    pend = cell_pending.get(side)
                    if pend is None or not sig_same(sig, pend[0]):
                        cell_pending[side] = (sig, time.time())
                        continue
                    if time.time() - pend[1] < args.settle:
                        continue
                    cell_ref[side] = sig
                    cell_pending.pop(side, None)
                    fired.append(side)
                # The squares changing is the fallback, not the main story.
                # When the digits are being read there is no need to guess from
                # a picture moving, and guessing alongside them is how a 1-0
                # became a 1-1. Only if nothing has been read for a while does
                # a change get to stand for a goal on its own.
                if fired and time.time() - last_read < 20:
                    fired = []
                if len(fired) == 2:
                    # both squares at once is not two goals in the same instant;
                    # it is the board itself having changed
                    print(now, "שתי המשבצות השתנו יחד — לא גול, הלוח התחלף")
                    fired = []
                for side in fired:
                    if time.time() < warm_until:
                        continue                      # still settling: not a goal
                    goals[side] += 1
                    print(now, "שינוי במשבצת", "העליונה (בית)" if side == "h" else "התחתונה (חוץ)",
                          "— גול. ספירה:", goals["h"], "-", goals["a"])
                    if not args.test:
                        try:
                            r = send(key, goals["h"], goals["a"], args.dry_run, codes)
                            if r.get("live") is False:
                                print(now, "אין משחק חי פתוח באפליקציה")
                            else:
                                last_sent = (r.get("h", goals["h"]), r.get("a", goals["a"]))
                                print(now, "נשלח", goals["h"], "-", goals["a"], "(ספירת שינויים)")
                        except Exception as e:
                            print(now, "שליחה נכשלה:", e)

            # digits win whenever they can be read: they say what the score is,
            # not merely that it moved, so they put the count straight
            if h is not None and a is not None:
                last_read = time.time()
            if h is not None and a is not None and 0 <= h <= 20 and 0 <= a <= 20:
                wild = last_sent and (h - last_sent[0] > 3 or a - last_sent[1] > 3)
                if (not wild and (h, a) != (goals["h"], goals["a"])
                        and (h, a) == stable and stable_n >= args.stable):
                    print(now, "הספרות אומרות", h, "-", a, "· מיישר את הספירה")
                    goals["h"], goals["a"] = h, a
                    cell_ref, cell_pending = {}, {}

            if time.time() - beat > 20:
                beat = time.time()
                now = time.strftime("%H:%M:%S")
                sims = []
                for side, crop in (("h", crop_h), ("a", crop_a)):
                    ref = change_ref.get(side)
                    sig = plate_signature(plate_crop(crop)) if (found or cfg.get("fixed")) else None
                    sims.append("%s=%s" % (side, "-" if (ref is None or sig is None) else "%.2f" % float((sig * ref).sum())))
                took = time.time() - beat if beat else 0
                print(now, "מצב · לוח:", ("נמצא" if plate else "לא"), "· ספרות:", h, "-", a,
                      "· דקה:", clock_seen if clock_seen is not None else "-",
                      "· קצב: %.1f פריימים לשנייה · קריאות מוצלחות: %d/%d" %
                      ((cycles / took) if took else 0, reads_ok, cycles),
                      "· זמן: איתור %.0f מ״ש, ספרות %.0f מ״ש, קודים %.0f מ״ש" %
                      (t_find * 1000 / max(1, cycles), t_score * 1000 / max(1, cycles), t_code * 1000 / max(1, cycles)))
                cycles = reads_ok = 0
                t_find = t_score = t_code = 0.0
            now = time.strftime("%H:%M:%S")
            # --- goals by change ---------------------------------------
            # When the digits cannot be read, the plate itself still says a
            # goal went in: its picture changes and then stays changed. Each
            # side is watched on its own, and a change only counts after it
            # has held for a few seconds, so a replay or a flash cannot score.
            # when the score is read from the whole board area, the clock inside
            # it changes every second — counting "the picture changed" as a goal
            # would be nonsense. The digits themselves are the source there.
            if (found or cfg.get("fixed")) and not args.no_change and not region:
                # a board that jumped across the picture is a new detection, not
                # a goal: start over rather than count it
                if found:
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
                # a frame we could not read means nothing changed, only that we
                # did not see it: keep whatever run of identical readings we had
                pass
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
            elif time.time() < warm_until:
                # The camera opens dark and sharpens over a few seconds; digits
                # read out of those first frames are guesswork, and a wrong one
                # here starts the match on a score nobody scored.
                if warm_note != int(warm_until):
                    print(now, "המצלמה מתייצבת — לא שולח עדיין")
                    warm_note = int(warm_until)
            elif (stable_n >= args.stable and (h, a) != last_sent
                  and not ((h, a) == refused and time.time() - refused_at < 10)):
                # The same lower score, read steadily for a quarter of a minute
                # with the clubs matching, is not noise — it is the score, and
                # an extra goal from one misread got in somewhere.
                fix = bool(refused and (h, a) == refused and codes
                           and time.time() - refused_first > 15)
                # Nobody scores four while the reader blinks. A leap that big
                # is the clock being read as a score, not a goal rush.
                if last_sent and (h - last_sent[0] > 3 or a - last_sent[1] > 3):
                    if stable_n == args.stable:
                        print(now, "קריאה לא הגיונית", last_sent, "->", (h, a), "· מתעלם")
                        if time.time() - dumped > 60:      # keep one, to see what it read
                            dumped = time.time()
                            folder = os.path.join(HERE, "debug")
                            os.makedirs(folder, exist_ok=True)
                            tag = time.strftime("%H%M%S") + "_wild"
                            imwrite_any(os.path.join(folder, tag + "_frame.png"), frame)
                            if plate:
                                imwrite_any(os.path.join(folder, tag + "_plate.png"), cut(plate))
                            print(now, "שמרתי תמונה ב־debug/" + tag)
                    time.sleep(args.interval)
                    continue
                jump = last_sent and (h - last_sent[0]) + (a - last_sent[1]) > 1
                # A jump of several goals is either a stretch the reader slept
                # through or a digit misread — an 8 for a 0 is an easy mistake.
                # Only believe one when the club codes were read off the same
                # board in the same breath, which says it is the scoreboard
                # being looked at and not a panel that resembles one.
                if jump and not codes:
                    if stable_n == args.stable:
                        print(now, "קפיצה בלי שמות קבוצות", last_sent, "->", (h, a), "· לא מקבל")
                    time.sleep(args.interval)
                    continue
                if jump and stable_n < args.stable * 2:
                    print(now, "קפיצה חשודה", last_sent, "->", (h, a), "· מחכה לאישור נוסף")
                else:
                    if not args.no_learn and min(dh.get("score", 0), da.get("score", 0)) >= 0.8:
                        learn_from(crop_h, h, "home")
                        learn_from(crop_a, a, "away")
                    try:
                        # Keep the very picture each accepted reading came
                        # from. A high proportion of frames yielding a number
                        # says nothing about the numbers being right, and only
                        # the crop itself settles whether the board was read or
                        # something else was.
                        if plate:
                            folder = os.path.join(HERE, "debug", "sent")
                            os.makedirs(folder, exist_ok=True)
                            imwrite_any(os.path.join(folder, "%s_%d-%d.png" %
                                                     (time.strftime("%H%M%S"), h, a)), cut(plate))
                        r = send(key, h, a, args.dry_run, codes, correct=fix, clock=clock_seen)
                        if r.get("live") is False:
                            if time.time() - idle_note > 60:
                                print(now, "אין משחק חי פתוח באפליקציה")
                                idle_note = time.time()
                        else:
                            # believe the server, not the camera: when it
                            # refuses a reading the score is still the old one,
                            # and recording ours would hide that a restart has
                            # taken the board back to nil-nil
                            if r.get("ignored") == "lower":
                                if refused != (h, a):
                                    refused_first = time.time()
                                refused, refused_at = (h, a), time.time()
                            if r.get("corrected"):
                                print(now, "תוקן כלפי מטה:", h, "-", a)
                                refused, refused_first = None, 0
                            if r.get("golden") == "decided":
                                print(now, "שער הזהב הוכרע:", h, "-", a)
                                last_sent = None
                                goals["h"], goals["a"] = 0, 0
                            else:
                                last_sent = (r.get("h", h), r.get("a", a))
                                goals["h"], goals["a"] = last_sent
                            if r.get("updated") and opened_at is None:
                                # the reader was started while a match was
                                # already under way; from the app's answer we
                                # know one is open, and the clock on it has to
                                # start somewhere or the match could never be
                                # closed by its board going
                                opened_at = time.time()
                            print(now, "נשלח", h, "-", a, r.get("updated") and "- נרשם" or "- נדחה")
                    except Exception as e:
                        print(now, "שליחה נכשלה:", e)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nנעצר")
    finally:
        if cap is not None:
            cap.release()


def collect(args, seconds):
    """Grab the television a few times a second for a while and keep the
       pictures. Tuning the reader on a folder of real frames beats tuning it
       against a live match: the same frame can be tried a hundred ways."""
    import cv2, time
    cfg = load_cfg()
    out = os.path.join(HERE, "frames")
    os.makedirs(out, exist_ok=True)
    cap = open_camera(args.source if args.source is not None else cfg.get("source", 0))
    print("אוסף פריימים ל־", out, "למשך", seconds, "שניות…")
    t0, n = time.time(), 0
    while time.time() - t0 < seconds:
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        n += 1
        imwrite_any(os.path.join(out, "f%03d_%d.png" % (n, int((time.time() - t0) * 10))), frame)
        time.sleep(0.4)
    cap.release()
    print("נשמרו", n, "פריימים")


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
    p.add_argument("--no-clock", action="store_true", help="לא לקרוא את דקת המשחק")
    p.add_argument("--collect", type=int, metavar="שניות",
                   help="לאסוף פריימים בזמן משחק לתיקיית frames, כדי לכייל אחר כך")
    p.add_argument("--no-change", action="store_true", help="לא לספור גולים לפי שינוי במשבצת")
    p.add_argument("--settle", type=float, default=3.5, help="כמה שניות שינוי צריך להחזיק כדי להיחשב גול")
    p.add_argument("--warmup", type=float, default=8.0, help="כמה שניות להתייצב לפני שסופרים גולים")
    p.add_argument("--log", action="store_true", help="לכתוב את הפלט לקובץ במקום למסך (לריצה ברקע)")
    p.add_argument("--dry-run", action="store_true", help="לרוץ רגיל אבל בלי לשלוח")
    p.add_argument("--interval", type=float, default=0.05, help="כל כמה שניות לקרוא")
    p.add_argument("--stable", type=int, default=2, help="כמה קריאות זהות ברצף לפני שליחה")
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
    elif args.collect:
        collect(args, args.collect)
    else:
        run(args)


if __name__ == "__main__":
    main()
