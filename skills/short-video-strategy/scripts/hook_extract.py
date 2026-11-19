"""Pull the hook out of reference videos: first ~8 s via yt-dlp, a strip of frames at
0 / 0.5 / 1 / 1.5 / 2.5 / 3.5 s (read it yourself — on-screen hook text, the face, the shot),
and a Whisper transcript of the first 6 s.

Usage:
  python hook_extract.py ranked.json --top 40 --out _strategy/trends/2026-10-27/hooks
  python hook_extract.py --urls URL [URL ...] --out ...
Writes <out>/<n>_strip.jpg and <out>/hooks.json (url, strip, transcript_6s, views, ...).
Reference footage is for studying the mechanic only: never reuse it in posts.
"""
import argparse, json, os, re, subprocess, sys

FF = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
YTDLP = "/opt/homebrew/bin/yt-dlp"
WHISPER = "/opt/homebrew/bin/whisper-cli"
MODEL = os.path.expanduser("~/Desktop/shortVideos/_system/tools/ggml-large-v3-turbo.bin")
TIMES = [0.0, 0.5, 1.0, 1.5, 2.5, 3.5]


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ranked", nargs="?")
    ap.add_argument("--urls", nargs="*")
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lang", default="auto")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--full", action="store_true", help="download whole video, add transcript_full + duration (structure analysis)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    items = [{"url": u} for u in (a.urls or [])]
    if a.ranked:
        items += [v for v in json.load(open(a.ranked)) if v.get("ideation_eligible", True)][: a.top]

    out = []
    for n, v in enumerate(items, 1):
        tag = f"{n:03d}"
        clip = f"{a.out}/{tag}.mp4"
        if os.path.exists(v["url"]):  # a local file (own drafts, a downloaded reference)
            r = run([FF, "-v", "error", "-y", "-i", v["url"], "-t", "8", "-c:v", "libx264", "-c:a", "aac", clip])
        else:
            src = v.get("video_url") or v["url"]  # Instagram needs a direct CDN url (from the Apify row)
            part = [] if a.full else ["--download-sections", "*0-8", "--force-keyframes-at-cuts"]
            r = run([YTDLP, "-q", "--no-playlist", "--ffmpeg-location", os.path.dirname(FF),
                     "-f", "b[height<=720]/bv*[height<=720]+ba/b", *part, "-o", clip, src])
        if not os.path.exists(clip):
            print(f"{tag} skip (download failed): {v['url']} {r.stderr.strip()[-120:]}"); continue
        strip = f"{a.out}/{tag}_strip.jpg"
        ins, flt = [], []
        for i, t in enumerate(TIMES):
            ins += ["-ss", str(t), "-i", clip]
            flt.append(f"[{i}:v]scale=200:-2,setsar=1,drawtext=text='{t}s':fontfile=/System/Library/Fonts/Supplemental/Arial.ttf:"
                       f"fontsize=18:fontcolor=yellow:x=4:y=4,trim=end_frame=1[f{i}]")
        run([FF, "-v", "error", "-y", *ins, "-filter_complex",
             ";".join(flt) + ";" + "".join(f"[f{i}]" for i in range(len(TIMES))) + f"hstack={len(TIMES)}",
             "-frames:v", "1", strip])
        wav = f"{a.out}/{tag}.wav"
        run([FF, "-v", "error", "-y", "-i", clip, "-t", "6", "-ac", "1", "-ar", "16000", wav])
        tr = run([WHISPER, "-m", a.model, "-l", a.lang, "-nt", "-f", wav]).stdout if os.path.exists(wav) else ""
        tr = re.sub(r"\s+", " ", tr).strip()
        full = ""
        if a.full:
            fw = f"{a.out}/{tag}_full.wav"
            run([FF, "-v", "error", "-y", "-i", clip, "-ac", "1", "-ar", "16000", fw])
            full = re.sub(r"\s+", " ", run([WHISPER, "-m", a.model, "-l", a.lang, "-f", fw]).stdout).strip()
            os.remove(fw)
        if re.search(r"^\[?(music|музыка)\]?$|продолжение следует", tr, re.I):
            tr = "[no speech]"
        for f in (clip, wav):
            if os.path.exists(f):
                os.remove(f)
        row = {k: v.get(k) for k in ("url", "platform", "handle", "views", "followers", "engagement_score",
                                     "attribution", "created", "text")}
        row.update({"n": tag, "strip": strip, "transcript_6s": tr})
        if a.full:
            row.update({"transcript_full": full, "duration": v.get("duration")})
        out.append(row)
        print(f"{tag} ok {v.get('views')} {v['url']} | {tr[:70]}")
    json.dump(out, open(f"{a.out}/hooks.json", "w"), ensure_ascii=False, indent=1)
    print(f"-> {a.out}/hooks.json ({len(out)} videos). Now look at each *_strip.jpg and label the hook.")


if __name__ == "__main__":
    main()
