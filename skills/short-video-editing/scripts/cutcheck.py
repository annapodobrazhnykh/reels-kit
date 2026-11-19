"""Check a cut (A..B, source seconds) so no word loses its head or tail.

usage: python cutcheck.py A B [A B ...]      (run from <reel>/work, needs audio.wav)

For every cut prints:
  - the 20 ms loudness envelope around A and B (word tails sit at -50..-58 dB, pauses below -60);
  - Whisper on the left piece ending at A, A±shifts, and on the right piece starting at B, B±shifts,
    each transcribed ON ITS OWN (a word tail heard alone is a word, not "ээ");
  - Whisper on the joined audio.
Pick the A where the last word is complete and the B where the next word starts complete
(ep4: «признаЮТ» was cut 3 times because «-ют» looked like «ээ» on the envelope).
"""
import os, subprocess, sys, tempfile, wave
import numpy as np

S = os.getcwd()
FF = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
WH = "/opt/homebrew/bin/whisper-cli"
MODEL = os.path.expanduser("~/Desktop/shortVideos/_system/tools/ggml-large-v3-turbo.bin")
LANG = os.environ.get("REEL_LANG", "ru")  # language of the reel: ru, en, de...
CTX = 2.5
SHIFTS = (-0.12, -0.06, 0, 0.06, 0.12)
tmp = tempfile.mkdtemp()

def text(filter_graph):
    out = f"{tmp}/p.wav"
    subprocess.run([FF, "-v", "error", "-y", "-i", f"{S}/audio.wav", "-filter_complex", filter_graph,
                    out], check=True)
    r = subprocess.run([WH, "-m", MODEL, "-l", LANG, "-f", out, "-nt"], capture_output=True, text=True)
    return " ".join(r.stdout.split())

def piece(a, b):
    return text(f"[0]atrim={a:.3f}:{b:.3f},asetpts=N/SR/TB,apad=pad_dur=0.5")

def joined(a, b):
    return text(f"[0]atrim={a - CTX:.3f}:{a:.3f},asetpts=N/SR/TB[l];[0]atrim={b:.3f}:{b + CTX:.3f},"
                f"asetpts=N/SR/TB[r];[l][r]concat=n=2:v=0:a=1,apad=pad_dur=0.5")

w = wave.open(f"{S}/audio.wav"); sr = w.getframerate()
x = np.frombuffer(w.readframes(w.getnframes()), np.int16) / 32768

def env(t):
    n = int(0.02 * sr); i0 = int((t - 0.3) * sr)
    vals = [20 * np.log10(np.sqrt(np.mean(x[i:i + n] ** 2)) + 1e-9) for i in range(i0, i0 + int(0.6 * sr), n)]
    return " ".join(f"{v:.0f}" for v in vals)

args = [float(v) for v in sys.argv[1:]]
for A, B in zip(args[::2], args[1::2]):
    print(f"=== cut {A:.2f} .. {B:.2f}")
    print(f"  env around A ({A - 0.3:.2f}..{A + 0.3:.2f}, 20 ms): {env(A)}")
    print(f"  env around B ({B - 0.3:.2f}..{B + 0.3:.2f}, 20 ms): {env(B)}")
    for d in SHIFTS:
        print(f"  left  ..{A + d:.2f}: {piece(A - CTX, A + d)}")
    for d in SHIFTS:
        print(f"  right {B + d:.2f}..: {piece(B + d, B + CTX)}")
    print(f"  JOINED: {joined(A, B)}")
