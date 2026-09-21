# -*- coding: utf-8 -*-
"""Build the phone app from the four source parts.

    python src/build.py          (run from the project root)

Writes index.html, the page GitHub Pages serves to the phones.

The Claude Artifact version is retired (2026-09-21): Firestore is the only
database, and the artifact's own store is frozen at the migration. The seam
in Store.provider() still falls back to window.claude.use("db"), but nothing
builds or publishes that version any more.
"""
import io, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
P = lambda *a: os.path.join(HERE, *a)


def assemble():
    s = "".join(io.open(P('p%d.html' % i), encoding='utf-8').read() for i in (1, 2, 3, 4))
    data = io.open(P('data2.json'), encoding='utf-8').read()
    faces = io.open(P('faces.json'), encoding='utf-8').read()
    assert '__DATA__' in s and '__FACES__' in s
    s = s.replace('__DATA__', data).replace('__FACES__', faces)
    return s


HEAD_EXTRA = '''<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#070A0E">
<meta name="description" content="הארכיון והניהול של טורניר הפיפא — טבלאות, הגרלה, סיכויים וגמר.">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="טורניר פיפא">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" type="image/png" sizes="192x192" href="icons/icon-192.png">
<link rel="apple-touch-icon" href="icons/icon-192.png">
'''

SAFE_AREA = '''
/* ---------- standalone on a phone ---------- */
html{background:var(--pitch)}
body{min-height:100svh;
  padding-top:env(safe-area-inset-top); padding-bottom:env(safe-area-inset-bottom);
  padding-inline-start:env(safe-area-inset-left); padding-inline-end:env(safe-area-inset-right);
  overscroll-behavior-y:none; -webkit-tap-highlight-color:transparent}
@media (display-mode:standalone){ body{ user-select:none } input,select,textarea{ user-select:text } }
.updatebar{position:fixed; inset-inline:10px; bottom:10px; z-index:130; max-width:520px;
  margin-inline:auto; display:flex; gap:10px; align-items:center; padding:11px 14px;
  background:#121A10; border:1px solid #3E6B2E; color:#DDF2CF; font-size:13px;
  box-shadow:0 14px 40px rgba(0,0,0,.7)}
'''

BOOT = '''<script src="firebase-config.js"></script>
<script src="db.js"></script>
'''

TAIL = '''
<script>
/* Register the worker, and offer the new version rather than swapping the
   page out from under someone in the middle of typing a score. */
if ("serviceWorker" in navigator) {
  addEventListener("load", () => {
    navigator.serviceWorker.register("sw.js").then(reg => {
      reg.addEventListener("updatefound", () => {
        const w = reg.installing;
        if (!w) return;
        w.addEventListener("statechange", () => {
          if (w.state === "installed" && navigator.serviceWorker.controller) {
            const bar = document.createElement("div");
            bar.className = "updatebar";
            bar.innerHTML = "<span>יש גרסה חדשה של האפליקציה.</span>";
            const go = document.createElement("button");
            go.className = "btn sm";
            go.textContent = "רענן";
            go.onclick = () => { try { sessionStorage.setItem("fifa-nointro", "1"); } catch (e) {} w.postMessage("skipWaiting"); location.reload(); };
            const no = document.createElement("button");
            no.className = "btn ghost sm";
            no.textContent = "אחר כך";
            no.onclick = () => bar.remove();
            bar.append(go, no);
            document.body.appendChild(bar);
          }
        });
      });
    }).catch(() => {});
  });
}
</script>
</body>
</html>
'''


def pwa(s):
    head_end = s.index('</style>') + len('</style>')
    head_html = s[:head_end].replace('</style>', SAFE_AREA + '</style>')
    rest = s[head_end:]
    i = rest.index('\n<script>\n')
    body_html, app_script = rest[:i], rest[i:]
    assert '<script id="seed"' in body_html, 'seed payload moved'
    assert app_script.rstrip().endswith('</script>'), 'unexpected tail'

    doc = ('<!doctype html>\n<html lang="he" dir="rtl">\n<head>\n'
           + HEAD_EXTRA + head_html + '\n</head>\n<body>\n'
           + body_html + BOOT + app_script + TAIL)
    for tag in ('<html', '<head>', '<body>', '</html>'):
        assert doc.count(tag) == 1, (tag, doc.count(tag))
    assert doc.count('<script id="seed"') == 1
    io.open(os.path.join(ROOT, 'index.html'), 'w', encoding='utf-8').write(doc)
    print('index.html', len(doc), 'chars')

    for f in ('db.js', 'firebase-config.js', 'manifest.webmanifest', 'sw.js'):
        assert os.path.exists(os.path.join(ROOT, f)), 'missing ' + f
    for f in ('icon-192.png', 'icon-512.png', 'icon-maskable-512.png'):
        assert os.path.exists(os.path.join(ROOT, 'icons', f)), 'missing icons/' + f
    print('all assets present')


def stamp_worker():
    """Give the service worker a version derived from what it serves.

    The worker only replaces its cache when sw.js itself changes, so a new
    index.html behind an unchanged sw.js can sit stale on a phone. Hashing the
    shipped files into VERSION means every real change produces a new worker —
    and the "יש גרסה חדשה · רענן" bar — while a rebuild with no change leaves
    sw.js byte-identical and triggers nothing."""
    import hashlib, re
    h = hashlib.sha256()
    for rel in ('index.html', 'db.js', 'firebase-config.js', 'manifest.webmanifest',
                'icons/icon-192.png', 'icons/icon-512.png', 'icons/icon-maskable-512.png'):
        h.update(rel.encode())
        h.update(io.open(os.path.join(ROOT, rel), 'rb').read())
    ver = 'fifa-' + h.hexdigest()[:10]
    path = os.path.join(ROOT, 'sw.js')
    sw = io.open(path, encoding='utf-8').read()
    new = re.sub(r'const VERSION = "[^"]*";', 'const VERSION = "%s";' % ver, sw, count=1)
    assert new != sw or ('"%s"' % ver) in sw, 'VERSION line not found in sw.js'
    if new != sw:
        io.open(path, 'w', encoding='utf-8', newline='\n').write(new)
    print('sw.js VERSION', ver, '(changed)' if new != sw else '(unchanged)')


def server_data():
    """The push server needs the fixture templates and the player names to
    write "the next match". Hand it the very same values the app ships, from
    the same file, so the two can never disagree about who plays whom."""
    import json
    d = json.load(io.open(P('data2.json'), encoding='utf-8'))
    out = json.dumps({'P': d['P'], 'TPL': d['TPL']}, ensure_ascii=False, indent=1)
    path = os.path.join(ROOT, 'functions', 'data.json')
    old = io.open(path, encoding='utf-8').read() if os.path.exists(path) else None
    if old != out:
        io.open(path, 'w', encoding='utf-8', newline='\n').write(out)
    print('functions/data.json', '(changed)' if old != out else '(unchanged)')


def _write_if_changed(path, text, label):
    old = io.open(path, encoding='utf-8').read() if os.path.exists(path) else None
    if old != text:
        io.open(path, 'w', encoding='utf-8', newline='\n').write(text)
    print(label, '(changed)' if old != text else '(unchanged)')


def server_model(app_script):
    """The push server's odds model IS the app's odds model.

    "Peak moment" pushes need the forecasting model and the simulation — a few
    hundred lines of numeric code. Copying them would create a second model
    that drifts from the one the app shows. Instead the exact blocks are cut
    out of the built app script by marker, and the server runs them in a
    sandbox (functions/model.js). If a marker ever moves, the build stops."""
    import json
    blocks = [
        ('const P = SEED.P', 'function computeOVR'),       # model data, decorate, aggregate, rebuild, finals
        ('function computeOVR', 'const TIER'),              # aggregate() ends by calling it
        ('function hydrate(rec)', 'function paintRows()'),  # record -> tournament
        ('let MODEL = null;', 'const pct = x =>'),          # the Poisson odds model
        ('function rng(seed)', 'const yieldNow'),           # seeded simulation, snapshots
    ]
    parts = []
    for a, b in blocks:
        i = app_script.index(a)
        j = app_script.index(b, i + 1)
        parts.append(app_script[i:j])
    code = ('/* GENERATED by src/build.py from the app\'s own code — do not edit.\n'
            '   Run by functions/model.js in a sandbox; see server_model() in build.py. */\n'
            + '\n'.join(parts))
    _write_if_changed(os.path.join(ROOT, 'functions', 'app-rules.js'), code, 'functions/app-rules.js')
    seed = io.open(P('data2.json'), encoding='utf-8').read()
    _write_if_changed(os.path.join(ROOT, 'functions', 'seed.json'), seed, 'functions/seed.json')


if __name__ == '__main__':
    s = assemble()
    pwa(s)
    stamp_worker()
    server_data()
    i = s.index('\n<script>\n') + len('\n<script>\n')
    server_model(s[i:s.index('</script>', i)])
