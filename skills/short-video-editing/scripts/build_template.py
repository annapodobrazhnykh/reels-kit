"""Reel build template: cut pauses, reorder, zooms, subtitles, b-roll, sfx -> one ffmpeg pass.

Copy to <reel>/work/build.py and edit only the blocks marked  # === CONFIG ===.
The example values are from london ep5 (videos/2026-11-09_london-ep5-publicity); replace them for every new reel.
Also mixes work/music.wav (from music_*.py) under the voice, ducked by the voice, if it exists.

Usage (from anywhere):  python3 build.py <version name, e.g. draft_v3>
Work files (proxy.mov, audio.wav, words.json, sfx.wav) live next to this script,
b-roll in ../broll/, results go to ../drafts/<name>.mp4.
Also writes work/offsets.json (source->reel map, read by accents.py) and work/words_out.json.
"""
import json, re, subprocess, sys

import os
S = os.path.dirname(os.path.abspath(__file__))
L = os.path.dirname(S)
OUT = f"{L}/drafts"
BROLL = f"{L}/broll"   # inserts; the main take lives in ../src, its working copy in work/proxy.mov
NAME = sys.argv[1] if len(sys.argv) > 1 else "draft_next"

# === CONFIG: b-roll (reel seconds) ===
#   ("full", start, end, src, source offset)            - video over the whole frame
#   ("pop",  start, end, src, cx, cy, width, angle)     - photo card that pops in and stays
#   ("dim",  start, end)                                - darken the talking head under a collage
#   pop + 9th item {"shake": t, "nopop": True}           - shake the card at t / appear without the pop
INSERTS = [
    ("full", 12.10, 13.40, "tg_scroll.mp4", 0.3),                 # вела телеграм-канал
    ("full", 13.40, 14.66, "stage.mp4", 0.3),                     # выступала на разных конференциях
    ("dim", 14.66, 15.41),                                        # писала статьи
    ("pop", 14.66, 15.41, "article_timeweb.png", 540, 1250, 860, -2),
    ("full", 15.41, 17.19, "conf_prep.mov", 0.8),                 # помогала делать конференции (зал до начала)
    ("dim", 17.19, 19.91),                                        # жюри разных хакатонов / делала курсы
    ("pop", 17.19, 18.77, "jury_smart500.png", 540, 1250, 960, 2),
    ("pop", 18.77, 19.91, "course_site.png", 540, 1250, 900, -3),
    ("dim", 24.16, 27.65),                                        # публичный профиль имеет огромный вес для визы
    ("pop", 24.16, 27.65, "approval_chat.jpg", 540, 1250, 900, -2),
    ("full", 60.14, 61.73, "speaker_selfie.mov", 0.2),            # вас уже хорошо знают в индустрии
    # the ending (61.7 -> end) stays on her, no overlays
]
SUB_LOW = [(60.14, 61.73)]  # reel seconds where subtitles move to the bottom (selfie insert: face at the top)
FF = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
PAD = 0.08

# silences from silencedetect (n=-35dB, d=0.25)
sil = []
log = subprocess.run([FF, "-hide_banner", "-i", f"{S}/audio.wav", "-af",
                      "silencedetect=n=-35dB:d=0.25", "-f", "null", "-"],
                     capture_output=True, text=True).stderr
starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", log)]
ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
sil = list(zip(starts, ends))

# speech chunks = gaps between silences, padded
speech, prev = [], 0.0
for a, b in sil:
    if a > prev:
        speech.append((max(0, prev - PAD), a + PAD))
    prev = b
speech = [(round(a, 3), round(b, 3)) for a, b in speech if b - a > 0.15]
# gaps under 0.2 s are soft consonants, not pauses ("девочку, С которой" was cut out in v1)
merged = []
for a, b in speech:
    if merged and a - merged[-1][1] < 0.2:
        merged[-1] = (merged[-1][0], b)
    else:
        merged.append((a, b))
speech = merged

# === CONFIG: order of speech chunks (source seconds) ===
# cuts (source seconds); every join checked by transcribing both sides and the joined audio.
# whisper word times drift up to ~1 s here, so subtitle drops (WORD_CUTS) are set separately per cut
CUTS = [  # (audio cut, subtitle words to drop)
    ((18.70, 19.76), (18.60, 19.50)),   # v2 «я не знаю» между «конференции» и «участвовала»
]
WORD_CUTS = [w for _, w in CUTS]
CUTS = [c for c, _ in CUTS]

def subtract(chunk, cuts):
    """chunk minus every cut interval (a cut may fall inside a chunk)"""
    parts = [chunk]
    for ca, cb in cuts:
        nxt = []
        for a, b in parts:
            if cb <= a or ca >= b:
                nxt.append((a, b))
                continue
            if a < ca:
                nxt.append((a, ca))
            if cb < b:
                nxt.append((cb, b))
        parts = nxt
    return [(a, b) for a, b in parts if b - a > 0.12]

order = [p for c in speech for p in subtract(c, CUTS)]
# open on the last bit of the head turn, speech right after: one continuous piece from 0.10
# (v8 first try: a 0.17 s noise chunk at 0.10 and then a jump to 0.91)
while len(order) > 1 and order[1][0] < 1.2:
    order[0:2] = [(order[0][0], order[1][1])]
if order and order[0][0] < 1.2:
    order[0] = (0.10, order[0][1])
FADE_OUT = {}  # chunk end -> fade-out seconds (default 0.02)
FORCE_END = {82.789: 83.10}  # keep a short breath after the last word «голове»
fixed = []
for a, b in order:
    for k, v in FORCE_END.items():
        if abs(b - k) < 0.05:
            b = v
    if fixed and a < fixed[-1][1]:   # swallowed by an extended chunk
        if b <= fixed[-1][1]:
            continue
        a = fixed[-1][1]
    fixed.append((a, b))
order = fixed

# === CONFIG: zooms (reel seconds; find accents with accents.py, not with transcript times) ===
# zooms on the output timeline (CapCut keyframe logic): snap in on the accent word,
# then drift back to 1.0 by the end of the phrase, so nothing jumps at the next cut.
#   (accent time, amount, phrase end)
HOOK_ZOOM = (0.20, 0.45)           # open zoomed-in, snap out = hook
ZOOMS = [  # on accents of voice AND hands (work/accents.py), >=7s apart, never under a b-roll insert
    (6.35, 0.12, 8.30),    # начните соБИРАТЬ: +11.5 dB, hands 12.0 ... уже сейчас
    (22.85, 0.12, 24.00),  # удиВИлась: +10.2 dB, hands 10.6
    (39.88, 0.12, 41.10),  # ОТ нескольких месяцев: +4.0 dB, hands 14.1; ends before the 41.13 join
    (57.38, 0.12, 59.45),  # в ЖИЗни: +9.3 dB, hands 11.4 ... проще найти работу (no join inside)
    (64.45, 0.12, 69.90),  # ДО того: +9.3 dB, hands 14.1 ... другим людям
    (74.80, 0.14, 77.00),  # final: не систематиЗИРОВАВ: +6.9 dB, hands 11.4 ... в голове
]
SNAP = 0.15
MUSIC_DB = -6  # ep6: «можно чуть громче» -> -6 (~-26 LUFS); music.wav is -20 LUFS -> was ~-29 LUFS at -9 under a -14 LUFS voice, ducked further while she talks (v7 -14 was inaudible)
zooms = [0] * len(order)

# words
d = json.load(open(f"{S}/words.json"))
words = []
for s in d["transcription"]:
    t = s["text"].strip()
    if not t:
        continue
    words.append([s["offsets"]["from"] / 1000, s["offsets"]["to"] / 1000, t])
# whisper stacks sentence-initial words on one timestamp: spread each such run evenly
i = 0
while i < len(words):
    j = i
    while j + 1 < len(words) and words[j + 1][0] == words[i][0]:
        j += 1
    if j > i:
        t0 = words[i][0]
        nxt = words[j + 1][0] if j + 1 < len(words) else words[j][1]
        t1 = max(nxt if nxt > t0 else words[j][1], t0 + 0.12 * (j - i + 1))
        step = (t1 - t0) / (j - i + 1)
        for k in range(i, j + 1):
            words[k][0], words[k][1] = t0 + step * (k - i), t0 + step * (k - i + 1)
    i = j + 1
# keep spoken order strictly increasing
for k in range(1, len(words)):
    if words[k][0] <= words[k - 1][0]:
        words[k][0] = words[k - 1][0] + 0.01
        words[k][1] = max(words[k][1], words[k][0] + 0.05)
# === CONFIG: transcript fixes, dropped retakes, accent words, hook text ===
FIX = {}
for w in words:
    for k, v in FIX.items():
        w[2] = w[2].replace(k, v)
# drop the retake
words = [w for w in words if not any(ca <= w[0] < cb for ca, cb in WORD_CUTS)]
# map source time -> output time
offsets, acc = [], 0.0
for a, b in order:
    offsets.append((a, b, acc))
    acc += b - a
TOTAL = acc
json.dump(offsets, open(f"{S}/offsets.json", "w"))
# zooms on a join look bad (Аня, ep5): warn if a zoom starts <0.4 s after a join or runs across one
joins = [o for _, _, o in offsets[1:]]
for t0, _, t1 in ZOOMS:
    for j in joins:
        if 0 <= t0 - j < 0.4 or t0 < j < t1 - 0.05:
            print(f"WARNING zoom {t0}-{t1} touches the join at {j:.2f}")

def remap(t):
    for a, b, o in offsets:
        if a - 0.05 <= t <= b + 0.05:
            return o + min(max(t, a), b) - a
    return None

mw = []
for a, b, t in words:
    ra = remap(a)
    if ra is None:
        # start fell in a cut: use the next chunk start
        cands = [o for (ca, cb, o) in offsets if ca >= a]
        ra = min(cands) if cands else None
    if ra is None:
        continue
    mw.append([ra, ra + (b - a), t, len(mw), a])
# ties (several words snapped to one chunk start) keep the spoken order (v6: «я Когда выбрала»)
mw.sort(key=lambda w: (round(w[0], 3), w[4]))
# words whisper placed before a chunk start all land on that start (v4: «Я потратила примерно» at 0.00
# -> a 0.1 s subtitle stacked under the next one); spread such runs evenly up to the next word
i = 0
while i < len(mw):
    j = i
    while j + 1 < len(mw) and mw[j + 1][0] - mw[i][0] < 0.05:
        j += 1
    if j > i:
        t0 = mw[i][0]
        t1 = mw[j + 1][0] if j + 1 < len(mw) else mw[j][1]
        step = (t1 - t0) / (j - i + 1)
        for k in range(i, j + 1):
            mw[k][0], mw[k][1] = t0 + step * (k - i), t0 + step * (k - i + 1)
    i = j + 1
json.dump([[round(w[0], 2), w[2]] for w in mw], open(f"{S}/words_out.json", "w"), ensure_ascii=False)

# group 1-3 words, break on punctuation or >17 chars
# === CONFIG: words highlighted yellow in subtitles (1 in ~10 words at most) ===
ACC_WORDS = set()
groups, cur = [], []
for w in mw:
    if cur and len(" ".join(x[2] for x in cur + [w])) > 17:
        groups.append(cur); cur = []
    cur.append(w)
    if re.search(r"[,.!?]$", w[2]) or len(cur) == 3:
        groups.append(cur); cur = []
if cur:
    groups.append(cur)

def ts(t):
    t = max(0, t)
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"

def clean(t):
    return re.sub(r"[,.]+$", "", t)

# whisper squeezes phrase starts, so some groups got 0.1-0.25 s and flashed (v5: «В принципе», «визу»);
# give each group at least MIN_SUB by moving the next group's start later, if the next one can spare it
MIN_SUB = 0.4
starts = [g[0][0] for g in groups] + [TOTAL]
for i in range(len(groups)):
    need = starts[i] + MIN_SUB - starts[i + 1]
    if need > 0 and i + 1 < len(groups):
        # the next group may drop to 0.25 s here: on its own turn it borrows from the one after it,
        # so a run of squeezed groups cascades forward until there is slack (v7: «В принципе» 0.18 s)
        spare = starts[i + 2] - starts[i + 1] - 0.25
        starts[i + 1] += max(0, min(need, spare))

events = []
for i, g in enumerate(groups):
    st = starts[i]
    en = starts[i + 1]
    en = min(en, max(g[-1][1], st) + 0.6)
    if en - st < 0.1:  # libass drops later layers after zero-length events
        en = st + 0.1
    parts = []
    for w in g:
        c = clean(w[2])
        if c.strip(",.") in ACC_WORDS or c in ACC_WORDS:
            parts.append(r"{\c&H2DDDFF&}" + c + r"{\c&HFFFFFF&}")
        else:
            parts.append(c)
    txt = r"{\fscx85\fscy85\t(0,120,\fscx100\fscy100)}" + " ".join(parts)
    if any(min(en, b_) - max(st, a_) > 0.05 for a_, b_ in SUB_LOW):  # face is low on the insert: subtitle at the bottom
        events.append(f"Dialogue: 0,{ts(st)},{ts(en)},Sub,,0,0,420,,{{\\an2}}{txt}")
    else:
        events.append(f"Dialogue: 0,{ts(st)},{ts(en)},Sub,,0,0,0,,{txt}")

# === CONFIG: hook title for the first ~3 s (None to skip) ===
hook = None  # v4: no title, Аня: «нафиг не нужен»
_old_hook = r"{\fad(0,250)\an8\pos(540,170)\fs94}Виза талантов\Nв {\c&H2DDDFF&}10 раз дешевле"
if hook:
    events.insert(0, f"Dialogue: 1,{ts(0)},{ts(3.2)},Hook,,0,0,0,,{hook}")

ass = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,AvenirNext-Bold,92,&H00FFFFFF,&H00FFFFFF,&H70000000,&H8C000000,0,0,0,0,100,100,0,0,1,7,2,8,80,80,290,1
Style: Hook,AvenirNext-Bold,88,&H00FFFFFF,&H00FFFFFF,&H70000000,&H8C000000,0,0,0,0,100,100,0,0,1,7,2,8,70,70,300,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(events) + "\n"
ass = ass.replace(r"{\fscx85", r"{\blur9\fscx85").replace(r"{\fad(0,250)}", r"{\blur9\fad(0,250)}")
open(f"{OUT}/{NAME}.ass", "w").write(ass)

# filter graph
n = len(order)
fc = [f"[0:v]split={n}" + "".join(f"[v{i}]" for i in range(n)) + ";",
      f"[0:a]asplit={n}" + "".join(f"[a{i}]" for i in range(n)) + ";"]
for i, ((a, b), z) in enumerate(zip(order, zooms)):
    dur = b - a
    chain = f"[v{i}]trim={a}:{b},setpts=PTS-STARTPTS"
    if False:
        # ease-out in over 0.3s, hold, ease back to 1.0 over the last 0.8s
        zin, zout = 0.3, min(0.8, dur - 0.3)
        Z = (f"(1+{z}*min(1-pow(1-min(t/{zin},1),2),"
             f"1-pow(1-min(max({dur:.3f}-t,0)/{zout:.3f},1),2)))")
        chain += (f",scale=w='2*trunc(540*{Z})':h='2*trunc(960*{Z})':eval=frame:flags=lanczos,"
                  f"crop=1080:1920:(iw-1080)/2:(ih-1920)*0.32")
    chain += ",setsar=1"
    fc.append(chain + f"[cv{i}];")
    fo = FADE_OUT.get(round(b, 2), 0.02)
    fc.append(f"[a{i}]atrim={a}:{b},asetpts=PTS-STARTPTS,"
              f"afade=t=in:d=0.015,afade=t=out:st={dur-fo:.3f}:d={fo}[ca{i}];")
fc.append("".join(f"[cv{i}][ca{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[cz][ca];")
z0, zd = HOOK_ZOOM
# perspective samples the source at sub-pixel positions, so the zoom glides instead of
# stepping in whole pixels (scale+crop rounding made v4 judder); T = frame / 30
T = "(in/30)"
Z = f"if(lt({T},{zd}),1+{z0}*pow(1-{T}/{zd},2),1)"
for t0, amp, t1 in reversed(ZOOMS):
    out = t1 - t0 - SNAP
    Z = (f"if(between({T},{t0},{t1}),1+{amp}*if(lt({T}-{t0},{SNAP}),1-pow(1-({T}-{t0})/{SNAP},2),"
         f"1-({T}-{t0 + SNAP:.3f})/{out:.3f}),{Z})")
CW, CH = f"(W/{Z})", f"(H/{Z})"
X0, Y0 = f"((W-{CW})/2)", f"((H-{CH})*0.32)"
fc.append(f"[cz]perspective=x0='{X0}':y0='{Y0}':x1='{X0}+{CW}':y1='{Y0}':"
          f"x2='{X0}':y2='{Y0}+{CH}':x3='{X0}+{CW}':y3='{Y0}+{CH}':"
          f"interpolation=cubic:eval=frame,setsar=1[cv];")
inputs = ["-i", f"{S}/proxy.mov"]
last = "cv"
k = 0
for ins in INSERTS:
    kind, st, en = ins[:3]
    dur = en - st
    if kind == "dim":
        fc.append(f"[{last}]drawbox=c=black@0.45:t=fill:enable='between(t,{st},{en})'[dim{len(fc)}];")
        last = f"dim{len(fc) - 1}"
        continue
    k += 1
    src = ins[3]
    if kind == "full":
        inputs += ["-ss", str(ins[4]), "-t", f"{dur + 0.5:.2f}", "-i", f"{BROLL}/{src}"]
        fc.append(f"[{k}:v]fps=30,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                  f"setsar=1,format=yuv420p,setpts=PTS-STARTPTS+{st}/TB[i{k}];")
        fc.append(f"[{last}][i{k}]overlay=0:0:eof_action=pass:enable='between(t,{st},{en})'[o{k}];")
    else:
        cx, cy, w, ang = ins[4:8]
        opt = ins[8] if len(ins) > 8 else {}
        inputs += ["-loop", "1", "-framerate", "30", "-t", f"{dur + 0.5:.2f}", "-i", f"{BROLL}/{src}"]
        # white-bordered card, tilted, pops from 135% to 100% in 0.15s
        S_ = "1" if opt.get("nopop") else "if(lt(t,0.15),1.35-0.35*(1-pow(1-t/0.15,2)),1)"
        sa = opt.get("shake")
        # damped side-to-side shake for ~0.4s (a "no" stamp)
        SH = f"+if(between(t,{sa},{sa}+0.4),24*sin(2*PI*14*(t-{sa}))*(1-(t-{sa})/0.4),0)" if sa else ""
        fc.append(f"[{k}:v]scale={w}:-2,pad=iw+28:ih+28:14:14:white,format=rgba,"
                  f"rotate={ang}*PI/180:c=none:ow=rotw({ang}*PI/180):oh=roth({ang}*PI/180),"
                  f"scale=w='2*trunc(iw*{S_}/2)':h='2*trunc(ih*{S_}/2)':eval=frame,"
                  f"setpts=PTS-STARTPTS+{st}/TB[i{k}];")
        fc.append(f"[{last}][i{k}]overlay=x='{cx}-w/2{SH}':y='{cy}-h/2':eof_action=pass:"
                  f"enable='between(t,{st},{en})'[o{k}];")
    last = f"o{k}"
fc.append(f"[{last}]subtitles={OUT}/{NAME}.ass[vout];")
# voice first, effects laid under it (sfx.wav from sfx.py), limiter keeps the sum from clipping
import os
if os.path.exists(f"{S}/sfx.wav"):
    sfx_idx = inputs.count("-i")
    inputs += ["-i", f"{S}/sfx.wav"]
    fc.append("[ca]loudnorm=I=-14:TP=-1.5:LRA=11[voice];")
    if os.path.exists(f"{S}/music.wav"):
        # background bed from music.py (-20 LUFS): MUSIC_DB below that, and ducked
        # a few dB more while she talks (voice drives the sidechain)
        mus_idx = inputs.count("-i")
        inputs += ["-i", f"{S}/music.wav"]
        fc.append("[voice]asplit=2[v1][vsc];")
        fc.append(f"[{mus_idx}:a]volume={MUSIC_DB}dB[mus];")
        fc.append("[mus][vsc]sidechaincompress=threshold=0.02:ratio=4:attack=80:release=600:makeup=1[duck];")
        fc.append(f"[v1][{sfx_idx}:a][duck]amix=inputs=3:normalize=0:duration=first,"
                  f"alimiter=limit=0.89:level=false[aout]")
    else:
        fc.append(f"[voice][{sfx_idx}:a]amix=inputs=2:normalize=0:duration=first,"
                  f"alimiter=limit=0.89:level=false[aout]")
else:
    fc.append("[ca]loudnorm=I=-14:TP=-1.5:LRA=11[aout]")
open(f"{S}/fc.txt", "w").write("\n".join(fc))

json.dump(inputs, open(f"{S}/inputs.json", "w"))
print("chunks", n, "total", round(TOTAL, 2))

subprocess.run([FF, "-v", "error", "-y", *inputs, "-/filter_complex", f"{S}/fc.txt",
                "-map", "[vout]", "-map", "[aout]",
                "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-profile:v", "high",
                "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709",
                "-colorspace", "bt709", "-r", "30", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-movflags", "+faststart", f"{OUT}/{NAME}.mp4"], check=True)
print("->", f"{OUT}/{NAME}.mp4")
