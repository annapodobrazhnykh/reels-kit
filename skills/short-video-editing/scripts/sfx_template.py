"""Synthesize sound effects and lay them on the reel's timeline -> sfx.wav (48k stereo).

Copy to <reel>/work/sfx.py, edit EVENTS, run before build.py (build.py mixes sfx.wav under the voice).
"""
import os, subprocess, sys

# usage: python3 sfx.py [reel length in seconds]; writes sfx.wav next to this script
S = os.path.dirname(os.path.abspath(__file__))
TOTAL = float(sys.argv[1]) if len(sys.argv) > 1 else 58.7
FF = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
D = f"{S}/sfx"
subprocess.run(["mkdir", "-p", D])

def gen(name, graph, dur):
    subprocess.run([FF, "-v", "error", "-y", "-f", "lavfi", "-i", graph, "-t", str(dur),
                    "-ar", "48000", "-ac", "2", f"{D}/{name}.wav"], check=True)

# airy whoosh: pink noise swelling and dying, band-limited
gen("whoosh", "anoisesrc=color=pink:d=0.5:a=0.6,highpass=f=400,lowpass=f=5000,"
              "afade=t=in:d=0.32:curve=exp,afade=t=out:st=0.32:d=0.18", 0.5)
# short swish for zoom snaps
gen("swish", "anoisesrc=color=white:d=0.2:a=0.35,highpass=f=1800,lowpass=f=9000,"
             "afade=t=in:d=0.12:curve=exp,afade=t=out:st=0.12:d=0.08", 0.2)
# camera shutter: two clicks with a little body
gen("shutter", "aevalsrc='(random(0)-0.5)*1.6*(exp(-180*t)+exp(-180*max(t-0.065,0))*gte(t,0.065))"
               "+0.4*sin(2*PI*700*t)*exp(-90*t)':s=48000:d=0.16,highpass=f=1200", 0.16)
# pop: pitch-dropping blip
gen("pop", "aevalsrc='0.8*sin(2*PI*(520*t-1600*t*t))*exp(-28*t)':s=48000:d=0.15", 0.15)
# low boom: sub hit with a falling pitch
gen("boom", "aevalsrc='0.9*sin(2*PI*(70*t-12*t*t))*exp(-3.2*t)+0.3*sin(2*PI*140*t)*exp(-9*t)':s=48000:d=1.3,"
            "lowpass=f=220", 1.3)
# ka-ching bell for "дорого"
gen("ding", "aevalsrc='0.45*(sin(2*PI*1760*t)+0.6*sin(2*PI*2637*t)+0.3*sin(2*PI*3520*t))*exp(-5*t)':s=48000:d=0.9", 0.9)

# "wrong" buzzer: two short square-ish low tones
gen("buzz", "aevalsrc='0.5*tanh(4*sin(2*PI*150*t))*(lt(t,0.16)+between(t,0.22,0.42))':s=48000:d=0.45,"
            "lowpass=f=1800,afade=t=out:st=0.38:d=0.07", 0.45)

# === CONFIG: sound events, reel seconds (example values are london1's) ===
# (time, sound, gain dB). whooshes start early so their peak lands on the cut
EVENTS = [
    (6.33, "swish", -14),     # zoom
    (11.86, "whoosh", -11),   # into the telegram scroll
    (13.16, "whoosh", -12),   # cut to the stage
    (14.66, "pop", -10),      # timeweb
    (15.17, "whoosh", -12),   # conference prep video
    (17.19, "pop", -10),      # smart500
    (18.77, "pop", -10),      # course site
    (22.83, "swish", -14),    # zoom
    (24.16, "pop", -10),      # approval chat
    (39.86, "swish", -14),    # zoom
    (57.36, "swish", -14),    # zoom
    (59.90, "whoosh", -11),   # speaker selfie
    (64.43, "swish", -14),    # zoom
    (74.78, "boom", -13),     # final zoom
]
# raw synth peaks differ a lot (whoosh ~-18 dB, boom ~-3 dB); level them before the event gains
TRIM = {"whoosh": 14, "swish": 10, "shutter": 0, "pop": 0, "boom": 0, "ding": 4, "buzz": 0}
EVENTS = [(t, snd, g + TRIM[snd]) for t, snd, g in EVENTS]
cmd = [FF, "-v", "error", "-y"]
for _, snd, _ in EVENTS:
    cmd += ["-i", f"{D}/{snd}.wav"]
fc = []
for i, (t, _, g) in enumerate(EVENTS):
    ms = int(t * 1000)
    fc.append(f"[{i}:a]volume={g}dB,adelay={ms}|{ms}[e{i}]")
fc.append("".join(f"[e{i}]" for i in range(len(EVENTS))) +
          f"amix=inputs={len(EVENTS)}:normalize=0:duration=longest,apad,atrim=0:{TOTAL}[out]")
cmd += ["-filter_complex", ";".join(fc), "-map", "[out]", "-ar", "48000", f"{S}/sfx.wav"]
subprocess.run(cmd, check=True)
print("events", len(EVENTS))
