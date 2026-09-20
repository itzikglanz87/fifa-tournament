# -*- coding: utf-8 -*-
"""Build both versions of the app from the four source parts.

    python src/build.py          (run from the project root)

Writes:
    src/_artifact.html   the fragment to publish as a Claude Artifact
    index.html           the standalone page GitHub Pages serves

There is no fork between them. p1..p4 are identical for both; the only seam
is Store.provider(), which prefers window.APP_DB (Firestore, standalone) and
falls back to window.claude.use("db") (inside the artifact). A fix in one is
a fix in both.
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
    io.open(P('_artifact.html'), 'w', encoding='utf-8').write(s)
    print('src/_artifact.html', len(s), 'chars')
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
            go.onclick = () => { w.postMessage("skipWaiting"); location.reload(); };
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


if __name__ == '__main__':
    pwa(assemble())
