"""Synthesize a quiet lo-fi background bed -> music.wav (48k stereo, ~-20 LUFS).

usage: python music.py <reel length in seconds>
Soft pads + muted e-piano arpeggio + sine bass over Am9 - Fmaj7 - Cmaj7 - G6, 76 bpm.
No drums: it sits under speech. build.py ducks it under the voice.
"""
import os, subprocess, sys, wave
import numpy as np

S = os.path.dirname(os.path.abspath(__file__))
FF = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
TOTAL = float(sys.argv[1]) if len(sys.argv) > 1 else 150.0
SR = 48000
BPM = 76
BEAT = 60 / BPM
BAR = 4 * BEAT
rng = np.random.default_rng(7)

def hz(m):
    return 440 * 2 ** ((m - 69) / 12)

# midi notes: (pad voicing, bass root, arpeggio tones)
CHORDS = [
    ([57, 60, 64, 67, 71], 45, [69, 72, 76, 79, 71]),   # Am9
    ([53, 57, 60, 64, 67], 41, [65, 69, 72, 76, 67]),   # Fmaj7(9)
    ([48, 52, 55, 59, 62], 48, [64, 67, 71, 74, 72]),   # Cmaj7(9)
    ([55, 59, 62, 64, 69], 43, [67, 71, 74, 76, 74]),   # G6(9)
]
n = int((TOTAL + 1) * SR)
L = np.zeros(n); R = np.zeros(n)

def add(sig, start, pan=0.0):
    i = int(start * SR)
    if i >= n:
        return
    sig = sig[: n - i]
    L[i:i + len(sig)] += sig * np.sqrt(0.5 * (1 - pan))
    R[i:i + len(sig)] += sig * np.sqrt(0.5 * (1 + pan))

def env(dur, att, rel):
    t = np.arange(int(dur * SR)) / SR
    e = np.minimum(1, t / att) * np.minimum(1, np.maximum(0, (dur - t) / rel))
    return t, e

bars = int(TOTAL / BAR) + 2
for b in range(bars):
    pad, root, arp = CHORDS[b % 4]
    t0 = b * BAR
    # pad: three slightly detuned sines per note, slow swell, overlaps into the next bar
    t, e = env(BAR + 1.2, 0.9, 1.4)
    for k, m in enumerate(pad):
        f = hz(m)
        s = sum(np.sin(2 * np.pi * f * (1 + d) * t + rng.uniform(0, 6.28)) for d in (-0.0025, 0, 0.0025))
        s += 0.15 * np.sin(2 * np.pi * 2 * f * t)
        add(0.045 * s * e, t0, pan=(k - 2) * 0.25)
    # bass: soft sine on beats 1 and 3
    for beat in (0, 2):
        t, e = env(BEAT * 1.9, 0.02, 0.6)
        s = np.sin(2 * np.pi * hz(root) * t) * np.exp(-0.9 * t)
        add(0.16 * s * e, t0 + beat * BEAT)
    # e-piano: sparse 8th-note arpeggio, some steps skipped, gentle velocity
    pattern = [0, 2, 1, 3, 4, 2, 1, 3]
    for step, idx in enumerate(pattern):
        if step in (3, 7) and rng.random() < 0.5:
            continue
        f = hz(arp[idx])
        t, e = env(1.6, 0.005, 0.5)
        s = (np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-6 * t)) * np.exp(-3.2 * t)
        vel = 0.05 * rng.uniform(0.7, 1.0)
        add(vel * s * e, t0 + step * BEAT / 2 + rng.uniform(0, 0.012), pan=rng.uniform(-0.5, 0.5))

x = np.stack([L, R], 1)[: int(TOTAL * SR)]
# fade in 2 s, out 3 s
f = np.ones(len(x)); a, z = int(2 * SR), int(3 * SR)
f[:a] = np.linspace(0, 1, a); f[-z:] = np.linspace(1, 0, z)
x *= f[:, None]
x /= np.abs(x).max() / 0.7
raw = f"{S}/music_raw.wav"
with wave.open(raw, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((x * 32767).astype(np.int16).tobytes())
# warm it up (lowpass, slight tape-ish saturation), add a roomy echo, level to -20 LUFS
subprocess.run([FF, "-v", "error", "-y", "-i", raw, "-af",
                "lowpass=f=4200,highpass=f=45,aecho=0.8:0.6:180|310:0.25|0.18,"
                "loudnorm=I=-20:TP=-3:LRA=7", "-ar", str(SR), f"{S}/music.wav"], check=True)
os.remove(raw)
print("music.wav", TOTAL, "s")
