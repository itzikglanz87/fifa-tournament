"""The notification badge: the trophy and ball as one white silhouette on
transparent, which is what Android draws in the status bar."""
import os, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96" width="96" height="96">
  <defs>
    <mask id="m">
      <rect width="96" height="96" fill="#fff"/>
      <!-- a thin gap between the ball and the cup, and the pentagon on the ball -->
      <path d="M22 33 H74" stroke="#000" stroke-width="3"/>
      <polygon points="48,11 52.8,14.5 51,20 45,20 43.2,14.5" fill="#000"/>
    </mask>
  </defs>
  <g fill="#fff" mask="url(#m)">
    <circle cx="48" cy="19" r="13"/>
    <path d="M24 34 H72 C72 52 64 63 53 66 V72.5 H43 V66 C32 63 24 52 24 34Z"/>
    <path d="M25 37 C12 37 12 55 30 59" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round"/>
    <path d="M71 37 C84 37 84 55 66 59" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round"/>
    <path d="M42 70.5 H54 L57.4 80 H38.6Z"/>
    <rect x="31" y="79" width="34" height="8" rx="2.5"/>
  </g>
</svg>'''

def render(size, name):
    html = os.path.join(HERE, name + ".html")
    with open(html, "w", encoding="utf-8") as f:
        f.write('<!doctype html><html><head><style>html,body{margin:0;background:transparent}svg{display:block;width:%dpx;height:%dpx}</style></head><body>%s</body></html>' % (size, size, SVG))
    out = os.path.join(HERE, name + ".png")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                    "--default-background-color=00000000", "--screenshot=" + out,
                    "--window-size=%d,%d" % (size, size), "file:///" + html.replace("\\", "/")],
                   check=True, capture_output=True, timeout=60)
    print(out)

render(96, "badge-96")
render(512, "monochrome-512")
with open(os.path.join(HERE, "badge.svg"), "w", encoding="utf-8") as f:
    f.write(SVG)
