"""Reel cover in Аня's style: photo + title in Tektur Medium caps + «СЕРИЯ N» in Tektur Regular.

usage (| in the title = manual line break):
  venv/bin/python make_cover.py PHOTO "Заголовок" OUT.jpg [--sub "СЕРИЯ 3"] [--pos auto|top|middle|bottom]
                                [--focus 0.45] [--size 105] [--no-shadow]

Style (her covers for episodes 1-2, measured off the profile): white, caps, light tracking, centred, big
(~105 px, up to ~960 px wide, one line if it fits); the subtitle is 0.42 of the title, Regular, widely tracked,
right under the title. No highlight colours. A soft shadow is on by default and, on a light background, a dark band fading
out up and down (--no-shadow turns both off).
- Photo is cover-fitted to 1080x1920; the face (OpenCV) is put at --focus of the height.
- Text stays inside y 450..1450 and ≤ 960 px wide: the profile grid shows the cover as a 3:4 window
  (1080x1440, centred = y 240..1680) that she drags into place in the app, and the grid's reel icon sits
  in the top-right corner (ep1's title at the very top got cut). There is no 1:1 crop any more. --pos auto: re-crops so the title sits above the head at the top of the safe strip (as on her ep1/ep2 covers);
  bottom only if the photo has no room above the head.
- Writes OUT_grid.jpg: full cover | the 3:4 grid tile that holds the title and the face, and prints
  where to drag the grid window in the app (one cover image, positioned — not a second upload).
"""
import argparse, os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

W, H = 1080, 1920
SAFE_TOP, SAFE_BOTTOM, MAX_W = 450, 1450, 960
FONT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "Tektur-var.ttf")
WHITE = (255, 255, 255)

ap = argparse.ArgumentParser()
ap.add_argument("photo"); ap.add_argument("title"); ap.add_argument("out")
ap.add_argument("--sub", default="")
ap.add_argument("--pos", default="auto", choices=["auto", "top", "middle", "bottom"])
ap.add_argument("--focus", type=float, default=0.45)
ap.add_argument("--top", type=int, default=None, help="exact y of the title top (1080x1920), overrides --pos")
ap.add_argument("--size", type=int, default=105)
ap.add_argument("--no-shadow", action="store_true", help="opt-out: clean white text, no shadow / band")
a = ap.parse_args()

def font(size, weight):
    f = ImageFont.truetype(FONT, size)
    f.set_variation_by_axes([100, weight])   # width 100, weight 500 = Medium, 400 = Regular
    return f

def tracked_width(f, text, track):
    return sum(f.getlength(c) for c in text) + track * (len(text) - 1)

def draw_tracked(d, x, y, text, f, track, fill):
    for c in text:
        d.text((x, y), c, font=f, fill=fill)
        x += f.getlength(c) + track

# title: one line if it fits at a readable size, else two balanced lines
title = a.title.upper()
words = title.split()
def fit(lines):
    size = a.size
    while size > 56:
        f = font(size, 500); tr = size * 0.06
        if max(tracked_width(f, l, tr) for l in lines) <= MAX_W:
            return size, f, tr
        size -= 2
    f = font(size, 500)
    return size, f, size * 0.06
if "|" in title:   # manual line break: "МОЙ КЕЙС | НА ВИЗУ ТАЛАНТОВ"
    lines = [l.strip() for l in title.split("|")]
    size, tf, tr = fit(lines)
else:
    size, tf, tr = fit([title])
    lines = [title]
if "|" not in title and size < 90 and len(words) > 1:
    # balanced lines, but never leave a short preposition («на», «в», «с») hanging at the end of line 1
    best = min(range(1, len(words)), key=lambda k: max(font(80, 500).getlength(' '.join(words[:k])), font(80, 500).getlength(' '.join(words[k:]))) + (10000 if len(words[k - 1]) <= 2 else 0))
    two = [" ".join(words[:best]), " ".join(words[best:])]
    size2, tf2, tr2 = fit(two)
    if size2 > size:
        size, tf, tr, lines = size2, tf2, tr2, two
lh = int(size * 1.2)
sub = a.sub.upper()
ss = max(34, int(size * 0.42)); sf = font(ss, 400); st = ss * 0.32
block = lh * len(lines) + (int(ss * 0.15) + ss if sub else 0)

img = ImageOps.exif_transpose(Image.open(a.photo)).convert("RGB")
g = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
faces = casc.detectMultiScale(g, 1.1, 6, minSize=(g.shape[1] // 12, g.shape[1] // 12))
face = max(faces, key=lambda f: f[2] * f[3]) if len(faces) else None
s = max(W / img.width, H / img.height)
img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
fy = (face[1] + face[3] / 2) * s if face is not None else img.height * a.focus
fx = (face[0] + face[2] / 2) * s if face is not None else img.width / 2
x0 = int(min(max(fx - W / 2, 0), img.width - W))
# auto: text over the head (her ep1/ep2 covers) -> put the face top right under the text block
want = a.focus
if a.pos == "auto" and face is not None:
    want = (SAFE_TOP + block + 90 + (fy - face[1] * s)) / H
y0 = int(min(max(fy - H * want, 0), img.height - H))
img = img.crop((x0, y0, x0 + W, y0 + H))
face_top = (face[1] * s - y0) if face is not None else None
face_bot = ((face[1] + face[3]) * s - y0) if face is not None else None

pos = a.pos
if pos == "auto":
    pos = "top" if face_top is None or face_top > SAFE_TOP + block + 40 else "bottom"   # photo too short to make room above the head
top = {"top": SAFE_TOP, "middle": (SAFE_TOP + SAFE_BOTTOM - block) // 2, "bottom": SAFE_BOTTOM - block}[pos]
if a.top is not None:
    top, pos = a.top, f"y={a.top}"

txt = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(txt)
y = top
for l in lines:
    draw_tracked(d, (W - tracked_width(tf, l, tr)) / 2, y, l, tf, tr, WHITE); y += lh
if sub:
    y += int(ss * 0.15)
    draw_tracked(d, (W - tracked_width(sf, sub, st)) / 2, y, sub, sf, st, (235, 235, 235))
out = img.convert("RGBA")
# light background behind the text (sky, window): soft dark band so white stays readable, no hard plate
band = np.array(img.convert("L"))[max(0, top - 40):top + block + 40, 140:W - 140]
lum = float(band.mean()) if band.size else 0
if lum > 120 and not a.no_shadow:
    ys = np.arange(H)[:, None]
    c, half = top + block / 2, block / 2 + 260
    alpha = np.clip(1 - np.abs(ys - c) / half, 0, 1) ** 1.5 * min(0.55, (lum - 100) / 200)
    shade = np.zeros((H, W, 4), np.uint8); shade[..., 3] = (alpha * 255).astype(np.uint8).repeat(W, 1)
    out.alpha_composite(Image.fromarray(shade))
if not a.no_shadow:   # on by default (her call 2026-11-11): invisible on dark photos, keeps light ones readable in the grid
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0)); sh.putalpha(txt.getchannel("A").point(lambda v: v * 0.55))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)))
out.alpha_composite(txt)
out = out.convert("RGB"); out.save(a.out, quality=95)

# 3:4 grid window: centred if it holds the title and the face, else moved to hold them
need_top = top - 60
need_bot = max(top + block + 60, int(face_bot) + 40 if face_bot is not None else 0)
wy = 240
if need_top < wy or need_bot > wy + 1440:
    wy = int(min(max(need_top, need_bot - 1440, 0), H - 1440))
full = out.resize((360, 640))
fd = ImageDraw.Draw(full)
fd.rectangle((0, wy / 3, 359, (wy + 1440) / 3), outline=(255, 221, 45), width=2)
c34 = out.crop((0, wy, 1080, wy + 1440)).resize((480, 640))
sheet = Image.new("RGB", (870, 680), (40, 40, 40))
sheet.paste(full, (10, 10)); sheet.paste(c34, (380, 10))
ImageDraw.Draw(sheet).text((380, 656), "profile grid 3:4 (yellow frame on the left)", fill=WHITE)
base, _ = os.path.splitext(a.out)
sheet.save(f"{base}_grid.jpg", quality=85)
where = "centre (default, nothing to drag)" if wy == 240 else f"drag the grid window {'up' if wy < 240 else 'down'} to y {wy}..{wy + 1440} ({abs(wy - 240) / 480 * 100:.0f}% of the free travel)"
print(a.out, "title", size, "px,", len(lines), "line(s); text", pos, "at y", top, "; face", "found" if face is not None else "not found")
print("grid crop:", where)
