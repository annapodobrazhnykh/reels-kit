"""Rank reference videos the way trendwatch / ugc-hooks reason about them (own implementation of the
published method): normalize Apify / yt-dlp rows from TikTok, Instagram, YouTube Shorts and X, score
engagement, freshness and whether the FORMAT or the CREATOR carried the views.

Pure compute, no network.
Usage:
  python rank.py raw1.json [raw2.json ...] --out ranked [--min-views 50000] [--max-duration 90]
                 [--window 180] [--now 2026-10-27]
Writes ranked.json and ranked.csv (best first) and prints a short summary.
"""
import argparse, csv, json, statistics, sys
from collections import defaultdict
from datetime import datetime, timezone


def dig(d, path):
    for k in path.split("."):
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def first(d, *paths):
    for p in paths:
        v = dig(d, p)
        if v not in (None, ""):
            return v
    return None


def num(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def secs(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    parts = str(v).split(":")  # "0:45" / "1:02:03"
    try:
        out = 0.0
        for p in parts:
            out = out * 60 + float(p)
        return out
    except ValueError:
        return None


def when(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, timezone.utc)
    s = str(v).replace("Z", "+00:00")
    for fmt in (None, "%a %b %d %H:%M:%S %z %Y", "%Y%m%d"):
        try:
            d = datetime.fromisoformat(s) if fmt is None else datetime.strptime(s, fmt)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def platform_of(r):
    url = str(first(r, "webVideoUrl", "url", "twitterUrl", "webpage_url") or "")
    for key, name in (("tiktok", "tiktok"), ("instagram", "instagram"), ("youtu", "youtube"),
                      ("x.com", "x"), ("twitter", "x")):
        if key in url:
            return name
    return "unknown"


def normalize(r):
    return {
        "platform": platform_of(r),
        "url": first(r, "webVideoUrl", "url", "twitterUrl", "webpage_url"),
        "handle": first(r, "authorMeta.name", "ownerUsername", "channelName", "author.userName",
                        "uploader_id", "channel"),
        "followers": num(first(r, "authorMeta.fans", "followersCount", "ownerFollowersCount",
                               "numberOfSubscribers", "author.followers", "channel_follower_count")),
        "views": num(first(r, "playCount", "videoPlayCount", "videoViewCount", "viewCount", "view_count")),
        "likes": num(first(r, "diggCount", "likesCount", "likes", "likeCount", "like_count")) or 0,
        "comments": num(first(r, "commentCount", "commentsCount", "replyCount", "comment_count")) or 0,
        "shares": num(first(r, "shareCount", "sharesCount", "retweetCount", "repost_count")) or 0,
        "saves": num(first(r, "collectCount", "savesCount", "bookmarkCount")),
        "created": when(first(r, "createTimeISO", "timestamp", "date", "createdAt", "upload_date",
                              "timestamp_unix")),
        "duration": secs(first(r, "videoMeta.duration", "videoDuration", "duration")),
        "text": (first(r, "text", "caption", "title", "fullText", "description") or "")[:300],
        "is_ad": bool(first(r, "isAd", "isSponsored", "isPaidPartnership")),
        "is_slideshow": bool(first(r, "isSlideshow")),
    }


def bucket(f):
    if f is None:
        return "unknown"
    if f < 10_000:
        return "<10k"
    if f < 250_000:
        return "10k-250k PRIME"
    if f < 500_000:
        return "250k-500k"
    if f < 1_000_000:
        return "500k-1M gray"
    return ">1M drop"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", default="ranked")
    ap.add_argument("--min-views", type=int, default=0)
    ap.add_argument("--max-duration", type=float, default=90)
    ap.add_argument("--window", type=float, default=180, help="days; recency weight hits 0.1 here")
    ap.add_argument("--now")
    a = ap.parse_args()
    now = when(a.now) if a.now else datetime.now(timezone.utc)

    rows = []
    for f in a.files:
        data = json.load(open(f))
        if isinstance(data, dict):
            data = data.get("items") or data.get("videos") or data.get("entries") or [data]
        rows += [normalize(r) for r in data if isinstance(r, dict)]

    seen, vids, dropped = set(), [], defaultdict(int)
    for v in rows:
        if not v["url"] or v["url"] in seen:
            dropped["duplicate/no url"] += 1; continue
        seen.add(v["url"])
        if v["is_ad"]:
            dropped["ad/sponsored"] += 1; continue
        if v["is_slideshow"]:
            dropped["slideshow"] += 1; continue
        if v["views"] is None or v["views"] < a.min_views:
            dropped["below min views"] += 1; continue
        if v["duration"] and v["duration"] > a.max_duration:
            dropped["too long"] += 1; continue
        vids.append(v)

    by_handle = defaultdict(list)
    for v in vids:
        by_handle[v["handle"]].append(v["views"])
    for v in vids:
        views = v["views"]
        w = v["likes"] + 2 * v["comments"] + 3 * (v["saves"] or 0) + 5 * v["shares"]
        v["engagement_score"] = round(w / views, 5) if views else 0
        v["save_rate"] = round(v["saves"] / views, 5) if views and v["saves"] is not None else None
        age = (now - v["created"]).days if v["created"] else None
        v["age_days"] = age
        v["freshness"] = ("unknown" if age is None else "rising" if age < 14 else "peak" if age < 30
                          else "declining" if age < 60 else "evergreen-structure-only")
        v["recency_weight"] = 0.5 if age is None else round(max(0.1, 1 - age / a.window), 3)
        same = by_handle[v["handle"]]
        med = statistics.median(same) if len(same) >= 3 else None
        v["vs_account_median"] = round(views / med, 2) if med else None
        v["engagement_ratio"] = round(views / v["followers"], 3) if v["followers"] else None
        v["size_bucket"] = bucket(v["followers"])
        vm, er = v["vs_account_median"], v["engagement_ratio"]
        if v["size_bucket"] == ">1M drop":
            attr = "creator-attributable"
        elif vm is not None:
            attr = "format-attributable" if vm >= 2 else "creator-attributable" if vm <= 1.2 else "mixed"
        elif er is not None:
            attr = "format-attributable" if er >= 0.5 else "creator-attributable" if er < 0.1 else "mixed"
        else:
            attr = "unknown"
        v["attribution"] = attr
        v["ideation_eligible"] = attr in ("format-attributable", "mixed", "unknown")
        v["rank_score"] = round(v["engagement_score"] * v["recency_weight"] * (1 if v["ideation_eligible"] else 0.2), 6)
        v["created"] = v["created"].date().isoformat() if v["created"] else None

    vids.sort(key=lambda v: v["rank_score"], reverse=True)
    json.dump(vids, open(f"{a.out}.json", "w"), ensure_ascii=False, indent=1)
    cols = ["platform", "url", "handle", "followers", "size_bucket", "views", "engagement_score", "save_rate",
            "vs_account_median", "engagement_ratio", "attribution", "created", "age_days", "freshness",
            "duration", "rank_score", "text"]
    with open(f"{a.out}.csv", "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore"); wr.writeheader(); wr.writerows(vids)
    elig = sum(v["ideation_eligible"] for v in vids)
    print(f"{len(rows)} rows -> {len(vids)} kept ({elig} ideation-eligible); dropped: {dict(dropped)}")
    print(f"-> {a.out}.json / {a.out}.csv")
    for v in vids[:10]:
        print(f"  {v['rank_score']:.4f} {v['platform']:9} {v['views']:>9} {v['attribution']:22} {v['url']}")


if __name__ == "__main__":
    main()
