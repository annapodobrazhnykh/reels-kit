"""Synthesize a minimal techno / deep house bed -> music.wav (48k stereo, ~-20 LUFS).

usage: python music_minimal.py <reel length in seconds>
v8: v7 was inaudible -> hats/stab/bass overtones back up a little, sub trimmed.
v7 (v6 fought the voice): no clap or ghost hats, darker quieter hats, no kick click.
122 bpm: soft four-on-the-floor kick, off-beat hats, rolling 16th bassline with a slow filter
sweep, one dub chord stab with a dotted-8th echo, kick pumps the bass and stab. Few mids,
so it stays out of the voice; build.py ducks it under the voice on top of that.
"""
import os, subprocess, sys, wave
import numpy as np
from scipy.signal import butter, sosfilt

S = os.path.dirname(os.path.abspath(__file__))
FF = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
TOTAL = float(sys.argv[1]) if len(sys.argv) > 1 else 77.0
SR = 48000
BPM = 122
BEAT = 60 / BPM
BAR = 4 * BEAT
S16 = BEAT / 4
rng = np.random.default_rng(3)
n = int((TOTAL + 2) * SR)
bars = int(TOTAL / BAR) + 2

def hz(m):
    return 440 * 2 ** ((m - 69) / 12)

def bus():
    return np.zeros((n, 2))

def place(buf, sig, t, pan=0.0, gain=1.0):
    i = int(t * SR)
    if i >= n:
        return
    sig = sig[: n - i] * gain
    buf[i:i + len(sig), 0] += sig * np.sqrt(0.5 * (1 - pan))
    buf[i:i + len(sig), 1] += sig * np.sqrt(0.5 * (1 + pan))

def filt(x, kind, f, order=2):
    return sosfilt(butter(order, f, kind, fs=SR, output="sos"), x)

# arrangement: which parts play in which bar
def part(b):
    kick = b < 16 or b >= 18               # v9: no hats-only intro (it ticked under the hook); 2-bar break mid-way
    stab = b >= 4 and not (16 <= b < 18 and b % 2)
    clap = b >= 6 and b != 17
    return kick, stab, clap

kick_b, hat_b, clap_b, bass_b, stab_b = bus(), bus(), bus(), bus(), bus()
pump = np.ones(n)

# kick: pitch-dropping sine, short click
t = np.arange(int(0.45 * SR)) / SR
f = 45 + 70 * np.exp(-t * 28)
kick = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7.5)
kick = filt(kick, "lowpass", 140)   # v7: no click, just a soft thump
# closed hat / ghost hat: high-passed noise bursts
def hat(dur, dec):
    t = np.arange(int(dur * SR)) / SR
    return filt(filt(rng.standard_normal(len(t)), "highpass", 6000), "lowpass", 10000) * np.exp(-t * dec)
# clap/rim: band-passed noise with a double hit
t = np.arange(int(0.2 * SR)) / SR
clap = filt(rng.standard_normal(len(t)), "bandpass", [1200, 3500]) * (np.exp(-t * 30) + 0.6 * np.exp(-np.maximum(t - 0.012, 0) * 30) * (t > 0.012))

BASS = [33, 33, 33, 36]                    # A1 x3, C2: one change every 4th bar
BASS_STEPS = [2, 3, 6, 7, 10, 11, 14, 15]  # rolling off-beat 16ths
STAB = [57, 60, 64, 67, 71]                # Am9 voicing, played as a short dub chord

for b in range(bars):
    t0 = b * BAR
    k_on, s_on, c_on = part(b)
    for q in range(4):
        if k_on:
            place(kick_b, kick, t0 + q * BEAT, gain=0.7)
            i = int((t0 + q * BEAT) * SR)
            env = 1 - 0.55 * np.exp(-np.arange(int(BEAT * SR)) / SR * 9)
            pump[i:i + len(env)] = np.minimum(pump[i:i + len(env)], env[: max(0, min(len(env), n - i))])
        place(hat_b, hat(0.05, 70), t0 + q * BEAT + BEAT / 2, pan=0.2, gain=0.16)      # off-beat hat
        if b >= 1:
            for g in (1, 3):
                if rng.random() < 0.7:
                    pass   # v7: no ghost hats
        if c_on and q in (1, 3):
            pass   # v7: no clap, it fought the voice
    # bass: saw-ish (additive harmonics), cutoff swept slowly over 16 bars
    root = BASS[b % 4]
    cut = 320 + 700 * (0.5 - 0.5 * np.cos(2 * np.pi * b / 16))
    for st in BASS_STEPS:
        fq = hz(root + (12 if st in (7, 15) and b % 2 else 0))
        t = np.arange(int(S16 * 0.9 * SR)) / SR
        sig = np.zeros(len(t))
        for h in range(1, 14):
            if fq * h > cut * 2.5:
                break
            sig += np.sin(2 * np.pi * fq * h * t) / h / (1 + (fq * h / cut) ** 4)
        sig *= np.exp(-t * 14) * np.minimum(1, t / 0.003)
        place(bass_b, sig, t0 + st * S16, gain=0.32)
    # dub stab on the "and" of 2, every bar; echo builds the groove
    if s_on:
        t = np.arange(int(0.35 * SR)) / SR
        sig = sum(np.sin(2 * np.pi * hz(m) * t + rng.uniform(0, 6.28)) + 0.3 * np.sin(2 * np.pi * 2 * hz(m) * t) for m in STAB)
        sig = filt(sig * np.exp(-t * 16), "lowpass", 900 + 500 * np.sin(b / 3))
        when = t0 + 1.5 * BEAT if b % 2 == 0 else t0 + 2.75 * BEAT
        for e in range(4):                                        # dotted-8th echo, ping-pong
            place(stab_b, sig, when + e * 0.75 * BEAT, pan=(-0.6 if e % 2 else 0.6), gain=0.05 * 0.5 ** e)

mix = kick_b + hat_b + clap_b + (bass_b + stab_b) * pump[:, None]
x = mix[: int(TOTAL * SR)]
f = np.ones(len(x)); a, z = int(2 * SR), int(3 * SR)
f[:a] = np.linspace(0, 1, a); f[-z:] = np.linspace(1, 0, z)
x *= f[:, None]
x /= np.abs(x).max() / 0.8
raw = f"{S}/music_raw.wav"
with wave.open(raw, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((x * 32767).astype(np.int16).tobytes())
subprocess.run([FF, "-v", "error", "-y", "-i", raw, "-af",
                "highpass=f=55,loudnorm=I=-20:TP=-3:LRA=7", "-ar", str(SR), f"{S}/music.wav"], check=True)
os.remove(raw)
print("music.wav", TOTAL, "s")
