"""Draw the app icon as SVG and render it to PNG with headless Chrome."""
import os, subprocess, math

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

def pent(cx, cy, r, rot):
    return " ".join("%.1f,%.1f" % (cx + r * math.cos(math.radians(rot + 72 * k)),
                                   cy + r * math.sin(math.radians(rot + 72 * k))) for k in range(5))

def star(cx, cy, R, r):
    pts = []
    for k in range(10):
        a = math.radians(-90 + 36 * k)
        rr = R if k % 2 == 0 else r
        pts.append("%.1f,%.1f" % (cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return " ".join(pts)

# the football, radius 1 geometry scaled later
BALL = ('<polygon points="%s"/>' % pent(0, 0, 15, -90) +
        "".join('<polygon points="%s"/>' % pent(40 * math.cos(math.radians(-90 + 72 * k)),
                                                  40 * math.sin(math.radians(-90 + 72 * k)), 14, -90 + 72 * k + 180)
                for k in range(5)) +
        '<g fill="none">' + "".join(
            '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (
                15 * math.cos(math.radians(-90 + 72 * k)), 15 * math.sin(math.radians(-90 + 72 * k)),
                26 * math.cos(math.radians(-90 + 72 * k)), 26 * math.sin(math.radians(-90 + 72 * k)))
            for k in range(5)) + "</g>")

COLORS = ["#4B86FA", "#689E2D", "#169EAF", "#CD711D", "#AE61E9", "#E54C7A"]

def art():
    # six gems along the bottom of the ring
    gems = ""
    for i, c in enumerate(COLORS):
        a = math.radians(90 + (i - 2.5) * 13)
        x, y = 256 + 176 * math.cos(a), 256 + 176 * math.sin(a)
        gems += ('<g transform="translate(%.1f %.1f)"><circle r="11" fill="url(#rim)"/>'
                 '<circle r="7.6" fill="%s"/><circle r="7.6" fill="url(#gemShine)"/></g>' % (x, y, c))
    # little sparkles
    sp = ""
    for (x, y, s) in [(150, 150, 1.0), (372, 128, 0.8), (392, 250, 0.6), (128, 262, 0.55)]:
        sp += ('<g transform="translate(%d %d) scale(%.2f)" fill="#FFF6D6">'
               '<path d="M0 -14 L3 -3 L14 0 L3 3 L0 14 L-3 3 L-14 0 L-3 -3Z" opacity=".9"/></g>' % (x, y, s))
    return '''
  <!-- stadium light behind -->
  <circle cx="256" cy="232" r="190" fill="url(#halo)"/>
  <!-- the ring -->
  <circle cx="256" cy="256" r="206" fill="none" stroke="url(#rim)" stroke-width="15"/>
  <circle cx="256" cy="256" r="196" fill="none" stroke="#5A3F0E" stroke-width="2" opacity=".8"/>
  <circle cx="256" cy="256" r="214" fill="none" stroke="#FFE9A8" stroke-width="1.5" opacity=".45"/>
  <!-- trophy shadow -->
  <ellipse cx="256" cy="404" rx="92" ry="12" fill="#000" opacity=".45"/>
  <!-- the ball in the cup -->
  <g transform="translate(256 138) scale(1.02)">
    <circle r="47" fill="url(#ballShade)"/>
    <g clip-path="url(#ballClip)" fill="#141821" stroke="#141821" stroke-width="1.6" stroke-linejoin="round">''' + BALL + '''</g>
    <circle r="47" fill="url(#ballGloss)"/>
    <circle r="47" fill="none" stroke="#0C0F14" stroke-width="2" opacity=".5"/>
  </g>
  <!-- handles -->
  <path d="M178 176 C120 170 118 250 196 268" fill="none" stroke="url(#goldV)" stroke-width="16" stroke-linecap="round"/>
  <path d="M334 176 C392 170 394 250 316 268" fill="none" stroke="url(#goldV)" stroke-width="16" stroke-linecap="round"/>
  <path d="M178 176 C128 172 126 244 194 262" fill="none" stroke="#FFF1BF" stroke-width="3" opacity=".55" stroke-linecap="round"/>
  <!-- the cup -->
  <path d="M168 160 H344 C344 240 312 290 270 304 V318 H242 V304 C200 290 168 240 168 160Z" fill="url(#goldH)"/>
  <path d="M168 160 H344 C344 240 312 290 270 304 V318 H242 V304 C200 290 168 240 168 160Z" fill="url(#cupShade)"/>
  <path d="M186 172 C188 232 210 272 240 290" fill="none" stroke="#FFF7D6" stroke-width="7" stroke-linecap="round" opacity=".75"/>
  <!-- rim of the cup -->
  <rect x="160" y="150" width="192" height="18" rx="9" fill="url(#rim)"/>
  <rect x="166" y="153" width="180" height="4" rx="2" fill="#FFF8DC" opacity=".8"/>
  <!-- cup front lip over the ball -->
  <path d="M160 159 H352 V166 H160Z" fill="url(#rim)"/>
  <!-- stem, knot and base -->
  <rect x="232" y="316" width="48" height="14" rx="5" fill="url(#goldH)"/>
  <path d="M238 330 H274 L282 356 H230Z" fill="url(#goldH)"/>
  <rect x="200" y="354" width="112" height="22" rx="6" fill="url(#goldH)"/>
  <rect x="200" y="354" width="112" height="5" rx="2.5" fill="#FFF3C8" opacity=".7"/>
  <rect x="184" y="374" width="144" height="26" rx="7" fill="url(#base)"/>
  <rect x="184" y="374" width="144" height="4" rx="2" fill="#6B7890" opacity=".7"/>
  <rect x="226" y="381" width="60" height="12" rx="3" fill="url(#rim)"/>
''' + gems + sp

DEFS = '''
  <defs>
    <radialGradient id="bg" cx="50%" cy="34%" r="75%">
      <stop offset="0" stop-color="#1F3052"/><stop offset=".5" stop-color="#0D1528"/><stop offset="1" stop-color="#04070D"/>
    </radialGradient>
    <radialGradient id="halo" cx="50%" cy="45%" r="50%">
      <stop offset="0" stop-color="#FFE7A0" stop-opacity=".42"/><stop offset=".55" stop-color="#F5C542" stop-opacity=".10"/>
      <stop offset="1" stop-color="#F5C542" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="goldH" x1="0" x2="1" y1="0" y2="0">
      <stop offset="0" stop-color="#7A4E0E"/><stop offset=".18" stop-color="#E4AE3C"/><stop offset=".34" stop-color="#FFF1B8"/>
      <stop offset=".5" stop-color="#F3C24C"/><stop offset=".72" stop-color="#B07A1C"/><stop offset=".88" stop-color="#E8B84A"/>
      <stop offset="1" stop-color="#7A4E0E"/>
    </linearGradient>
    <linearGradient id="goldV" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0" stop-color="#FFF0B0"/><stop offset=".45" stop-color="#E6AF3A"/><stop offset="1" stop-color="#8C5D12"/>
    </linearGradient>
    <linearGradient id="rim" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0" stop-color="#FFF5CC"/><stop offset=".5" stop-color="#F0BF45"/><stop offset="1" stop-color="#9A6814"/>
    </linearGradient>
    <linearGradient id="cupShade" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0" stop-color="#000" stop-opacity="0"/><stop offset=".75" stop-color="#000" stop-opacity=".08"/>
      <stop offset="1" stop-color="#3A2405" stop-opacity=".45"/>
    </linearGradient>
    <linearGradient id="base" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0" stop-color="#2B3445"/><stop offset="1" stop-color="#11161F"/>
    </linearGradient>
    <radialGradient id="ballShade" cx="36%" cy="30%" r="78%">
      <stop offset="0" stop-color="#FFFFFF"/><stop offset=".65" stop-color="#E4E8EE"/><stop offset="1" stop-color="#8D97A5"/>
    </radialGradient>
    <radialGradient id="ballGloss" cx="34%" cy="24%" r="40%">
      <stop offset="0" stop-color="#fff" stop-opacity=".75"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="gemShine" cx="35%" cy="30%" r="60%">
      <stop offset="0" stop-color="#fff" stop-opacity=".7"/><stop offset=".5" stop-color="#fff" stop-opacity="0"/>
      <stop offset="1" stop-color="#000" stop-opacity=".25"/>
    </radialGradient>
    <clipPath id="ballClip"><circle r="46"/></clipPath>
  </defs>'''

def svg(maskable):
    # maskable: full-bleed background, artwork shrunk into the 80% safe circle
    inner = art()
    if maskable:
        inner = '<g transform="translate(256 256) scale(.78) translate(-256 -256)">' + inner + "</g>"
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">' + DEFS +
            '<rect width="512" height="512" fill="url(#bg)"/>' + inner + "</svg>")

def render(name, maskable, size):
    html = os.path.join(HERE, name + ".html")
    with open(html, "w", encoding="utf-8") as f:
        f.write('<!doctype html><html><head><style>html,body{margin:0;background:transparent}svg{display:block;width:%dpx;height:%dpx}</style></head><body>%s</body></html>'
                % (size, size, svg(maskable)))
    out = os.path.join(HERE, name + ".png")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                    "--default-background-color=00000000",
                    "--screenshot=" + out, "--window-size=%d,%d" % (size, size), "file:///" + html.replace("\\", "/")],
                   check=True, capture_output=True, timeout=60)
    print(out, os.path.getsize(out))

render("icon-512", False, 512)
render("icon-192", False, 192)
render("icon-maskable-512", True, 512)
with open(os.path.join(HERE, "icon.svg"), "w", encoding="utf-8") as f:
    f.write(svg(False))
