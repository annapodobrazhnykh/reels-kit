"""Where the speaker accents something: voice loudness peaks and hand motion, on the reel's timeline.

Usage: python accents.py FROM TO [FROM TO ...]   (seconds of the reel; run build.py once first)
Needs numpy (use <project>/tools/venv/bin/python).
Prints 0.1 s rows: voice dB above its local median, hand-zone motion, and the word being said.
"""
import json, os, subprocess, sys
import numpy as np

S = os.path.dirname(os.path.abspath(__file__))
FF = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"

# source->reel chunk map written by build.py (run build.py once before this script)
offsets = json.load(open(f"{S}/offsets.json"))

def to_src(t):
    for a, b, o in offsets:
        if o <= t < o + (b - a):
            return a + t - o
    return None

# voice: RMS in 50 ms windows, dB above the median of the surrounding 3 s
sr = 16000
raw = subprocess.run([FF, "-v", "error", "-i", f"{S}/audio.wav", "-f", "s16le", "-ac", "1", "-ar", str(sr), "-"],
                     capture_output=True).stdout
a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
win = int(0.05 * sr)
rms = np.array([np.sqrt(np.mean(a[i:i + win] ** 2)) + 1e-9 for i in range(0, len(a) - win, win)])
db = 20 * np.log10(rms)

def voice(ts):
    i = int(ts / 0.05)
    lo, hi = max(0, i - 30), i + 30
    seg = db[lo:hi]
    seg = seg[seg > -45]  # speech only
    return db[i] - (np.median(seg) if len(seg) else -30)

# hands: mean frame difference below the chin (rows 45-95 % of the frame), 10 fps
W, H = 108, 192
vid = subprocess.run([FF, "-v", "error", "-i", f"{S}/proxy.mov", "-vf", f"fps=10,scale={W}:{H},format=gray",
                      "-f", "rawvideo", "-"], capture_output=True).stdout
fr = np.frombuffer(vid, np.uint8).reshape(-1, H, W).astype(np.float32)
zone = fr[:, int(H * .45):int(H * .95), :]
mot = np.concatenate([[0], np.abs(np.diff(zone, axis=0)).mean(axis=(1, 2))])

words = json.load(open(f"{S}/words_out.json"))
def word_at(t):
    w = [x for x in words if x[0] <= t]
    return w[-1][1] if w else ""

args = list(map(float, sys.argv[1:]))
for lo, hi in zip(args[::2], args[1::2]):
    print(f"--- {lo}-{hi}  (reel s | source s | voice dB over local | hands | word)")
    t = lo
    while t < hi:
        s = to_src(t)
        if s is not None:
            v = voice(s); m = mot[min(int(s * 10), len(mot) - 1)]
            print(f"{t:6.1f} {s:6.2f} {v:+5.1f} {'#' * max(0, int(v))} | {m:4.1f} {'=' * int(m / 1.5)} | {word_at(t)}")
        t = round(t + 0.1, 2)
