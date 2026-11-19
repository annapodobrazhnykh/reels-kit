"""Synthesize a quiet lo-fi background bed -> music.wav (48k stereo, ~-20 LUFS).

usage: python music.py <reel length in seconds>
ep5 variant: brighter D major, 88 bpm, Dmaj9 - Bm9 - Gmaj7 - A6sus; kalimba-like plucks + soft shaker.
No drums: it sits under speech. build.py ducks it under the voice.
"""
import os, subprocess, sys, wave
import numpy as np

S = os.path.dirname(os.path.abspath(__file__))
FF = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
TOTAL = float(sys.argv[1]) if len(sys.argv) > 1 else 150.0
SR = 48000
BPM = 88
BEAT = 60 / BPM
BAR = 4 * BEAT
rng = np.random.default_rng(21)

def hz(m):
    return 440 * 2 ** ((m - 69) / 12)

# midi notes: (pad voicing, bass root, arpeggio tones)
CHORDS = [
    ([50, 54, 57, 61, 64], 38, [66, 69, 73, 76, 78]),   # Dmaj9
    ([47, 50, 54, 57, 61], 35, [62, 66, 69, 73, 74]),   # Bm9
    ([43, 47, 50, 54, 57], 43, [62, 66, 67, 71, 74]),   # Gmaj7
    ([45, 50, 52, 54, 57], 45, [64, 66, 69, 71, 76]),   # A6sus
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
    pattern = [(0, 0), (3, 2), (6, 1), (8, 4), (10, 2), (13, 3), (14, 1)]   # (16th step, arp tone)
    for step, idx in pattern:
        if step in (13, 14) and rng.random() < 0.4:
            continue
        f = hz(arp[idx])
        t, e = env(1.2, 0.003, 0.4)
        s = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 5.4 * f * t) * np.exp(-25 * t)) * np.exp(-4.5 * t)
        vel = 0.055 * rng.uniform(0.7, 1.0)
        add(vel * s * e, t0 + step * BEAT / 4 + rng.uniform(0, 0.01), pan=rng.uniform(-0.6, 0.6))
    # soft shaker on 8ths, accent on the off-beats
    for k in range(8):
        t, e = env(0.09, 0.01, 0.07)
        s = rng.standard_normal(len(t)) * np.exp(-40 * t)
        add((0.010 if k % 2 == 0 else 0.016) * s * e, t0 + k * BEAT / 2, pan=0.3)

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
                "lowpass=f=6500,highpass=f=50,aecho=0.8:0.6:180|310:0.25|0.18,"
                "loudnorm=I=-20:TP=-3:LRA=7", "-ar", str(SR), f"{S}/music.wav"], check=True)
os.remove(raw)
print("music.wav", TOTAL, "s")
