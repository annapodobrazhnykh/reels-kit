"""Check a posting plan before anything goes to Upload-Post: anti-spam and cadence rules
(from the ugc-hooks posting kit, adapted to Instagram / YouTube Shorts / X).

Plan file (JSON list), one row per post:
  {"id": "london-ep1-ig", "video": "videos/2026-10-26_london-ep1/final/ig.mp4", "platform": "instagram",
   "at": "2026-10-28T19:00:00+00:00", "caption": "...", "hashtags": ["#london", "#relocation"],
   "pinned_comment": "...", "title": "(YouTube only)"}
Optional --history published.json (same shape) is included in uniqueness and cadence checks.
Usage: python post_check.py plan.json [--history _published/history.json] [--new-account]
Exit code 1 if any ERROR.
"""
import argparse, difflib, json, re, sys
from collections import defaultdict
from datetime import datetime

BANNED = ["ссылка в био", "ссылка в профиле", "подпишись", "подписывайся", "ставь лайк", "лайк если",
          "отметь друга", "link in bio", "follow for more", "like and follow", "tag a friend", "#fyp",
          "#viral", "#рекомендации"]
MAX_TAGS = {"instagram": 5, "tiktok": 5, "youtube": 3, "x": 2}
EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]")


def norm(s):
    return re.sub(r"[#@]\S+|\s+", " ", (s or "").lower()).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--history")
    ap.add_argument("--new-account", action="store_true", help="<=2 posts/day/platform, >=4 h apart")
    ap.add_argument("--min-gap-h", type=float, default=4)
    a = ap.parse_args()
    plan = json.load(open(a.plan))
    hist = json.load(open(a.history)) if a.history else []
    errs, warns = [], []
    E = lambda p, m: errs.append(f"ERROR {p.get('id')}: {m}")
    W = lambda p, m: warns.append(f"warn  {p.get('id')}: {m}")

    allposts = hist + plan
    for p in plan:
        pl = p.get("platform", "")
        cap = p.get("caption", "")
        low = cap.lower() + " " + " ".join(p.get("hashtags", [])).lower()
        for b in BANNED:
            if b in low:
                E(p, f"banned phrase «{b}» (engagement bait / spam signal)")
        if len(EMOJI.findall(cap)) > 1:
            E(p, "more than 1 emoji")
        if re.search(r"\b[A-ZА-ЯЁ]{5,}\b", cap):
            W(p, "caps-lock word in caption")
        if re.search(r"https?://", cap + (p.get("pinned_comment") or "")):
            W(p, "link in caption/comment ranks lower; name the thing instead")
        tags = [t.lower() for t in p.get("hashtags", [])]
        if len(tags) > MAX_TAGS.get(pl, 5):
            E(p, f"{len(tags)} hashtags > {MAX_TAGS.get(pl, 5)} for {pl}")
        if pl == "youtube" and len(p.get("title") or cap) > 100:
            E(p, "YouTube title over 100 characters")
        if pl == "x" and len(cap) > 280:
            E(p, "X text over 280 characters")
        if not cap.strip().endswith("?"):
            W(p, "no real question at the end of the caption")
        for q in allposts:
            if q is p:
                continue
            for field in ("caption", "pinned_comment"):
                x, y = norm(p.get(field)), norm(q.get(field))
                if x and y and difflib.SequenceMatcher(None, x, y).ratio() > 0.8:
                    E(p, f"{field} near-duplicate of {q.get('id')}")
            if q.get("platform") == pl and q.get("video") == p.get("video"):
                E(p, f"same video twice on {pl} (also {q.get('id')})")

    by_pl = defaultdict(list)
    for p in allposts:
        if p.get("at"):
            by_pl[p.get("platform")].append(p)
    for pl, ps in by_pl.items():
        ps.sort(key=lambda p: p["at"])
        for prev, cur in zip(ps, ps[1:]):
            gap = (datetime.fromisoformat(cur["at"]) - datetime.fromisoformat(prev["at"])).total_seconds() / 3600
            if gap < a.min_gap_h and cur in plan:
                E(cur, f"{gap:.1f} h after {prev.get('id')} on {pl} (min {a.min_gap_h} h)")
            if [t.lower() for t in cur.get("hashtags", [])] == [t.lower() for t in prev.get("hashtags", [])] \
                    and cur.get("hashtags") and cur in plan:
                E(cur, f"same hashtag set as previous {pl} post {prev.get('id')}")
        per_day = defaultdict(int)
        for p in ps:
            per_day[p["at"][:10]] += 1
        for d, k in per_day.items():
            if k > (2 if a.new_account else 3):
                errs.append(f"ERROR {pl} {d}: {k} posts in a day")
    # the same video on two platforms the same day: allowed, but variants should spread out
    by_video_day = defaultdict(set)
    for p in plan:
        if p.get("at"):
            by_video_day[(p.get("video"), p["at"][:10])].add(p.get("platform"))
    for (vid, d), pls in by_video_day.items():
        if len(pls) > 1:
            warns.append(f"warn  {vid}: {sorted(pls)} on the same day {d} (fine, but spread variants)")

    for line in errs + warns:
        print(line)
    print(f"{len(plan)} posts checked: {len(errs)} error(s), {len(warns)} warning(s)")
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
