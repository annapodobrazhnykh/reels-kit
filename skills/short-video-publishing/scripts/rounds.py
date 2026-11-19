"""Reach diagnosis per account and platform: distribution rounds R0-R4, throttled vs content failing,
spam / automation signals, a 0-100 "shadowban probability" (own implementation of the method published
in tiktok-shadowban-check; the round bands come from TikTok and are an approximation for Reels/Shorts).

Input: JSON list of posts (Upload-Post analytics or Apify profile rows), fields (aliases accepted):
  platform, account, url, created, views, likes, comments, shares, saves, caption, hashtags
Usage: python rounds.py posts.json [--out _published/health-2026-10-27.md]
"""
import argparse, json, re, statistics, sys
from collections import Counter, defaultdict
from datetime import datetime

ROUNDS = [("R0 не вышел из стартовой выборки", 0, 200), ("R1 показали, хук не удержал", 200, 500),
          ("R2 одна волна", 500, 2000), ("R3 рекомендации", 2000, 20000), ("R4 вирус", 20000, 10**12)]


def g(p, *keys, default=None):
    for k in keys:
        if p.get(k) not in (None, ""):
            return p[k]
    return default


def rnd(v):
    return next(n for n, lo, hi in ROUNDS if lo <= v < hi)


def analyse(posts):
    posts = sorted(posts, key=lambda p: str(g(p, "created", "createTimeISO", "timestamp", default="")))
    views = [int(g(p, "views", "playCount", "videoPlayCount", "viewCount", default=0)) for p in posts]
    n = len(views)
    tot = sum(views) or 1
    inter = sum(int(g(p, "likes", "diggCount", "likesCount", default=0)) + int(g(p, "comments", "commentCount", default=0))
                + int(g(p, "shares", "shareCount", default=0)) for p in posts)
    eng = inter / tot * 100
    med = statistics.median(views)
    rounds = Counter(rnd(v) for v in views)
    r0 = rounds[ROUNDS[0][0]] / n
    zero = sum(v == 0 for v in views) / n
    times = []
    for p in posts:
        c = str(g(p, "created", "createTimeISO", "timestamp", default=""))
        try:
            times.append(datetime.fromisoformat(c.replace("Z", "+00:00")))
        except ValueError:
            pass
    bursts = sum((b - a).total_seconds() < 3600 for a, b in zip(times, times[1:]))
    per_day = Counter(t.date() for t in times)
    heavy_days = sum(k > 3 for k in per_day.values())
    caps = [re.sub(r"#\S+", "", str(g(p, "caption", "text", default=""))).strip().lower() for p in posts]
    dup = n - len(set(c for c in caps if c)) - caps.count("")
    tagsets = Counter(tuple(sorted(re.findall(r"#\S+", str(g(p, "caption", "text", default="")).lower())
                                   + [t.lower() for t in g(p, "hashtags", default=[])])) for p in posts)
    top_tag_share = max(tagsets.values()) / n if tagsets and max(tagsets) else 0
    trend = None
    if n >= 20:
        trend = statistics.median(views[-10:]) / (statistics.median(views[-20:-10]) or 1)

    score = min(40, r0 * 40 / 0.6) + (20 if med < 300 else 0) + min(20, zero * 100) \
        + (10 if bursts >= 3 or heavy_days else 0) + (10 if dup >= 2 or top_tag_share >= 0.6 else 0)
    if med >= 500:
        verdict = "охваты нормальные — масштабировать то, что выше медианы"
    elif eng >= 1:
        verdict = ("ПОХОЖЕ НА ОГРАНИЧЕНИЕ: кто видит — реагирует (≥1 %), но платформа не раздаёт. "
                   "Пауза 48–72 ч, затем 1 пост в день с большими интервалами; менять КАК постишь, не ЧТО")
    else:
        verdict = ("КОНТЕНТ НЕ ПРОХОДИТ ПЕРВЫЙ ТЕСТ (<1 % реакций): чинить первые 1,5 с, "
                   "брать формат, который уже работает в нише")
    signals = []
    if bursts >= 3: signals.append(f"{bursts} пары постов с интервалом < 1 ч")
    if heavy_days: signals.append(f"{heavy_days} дн. с >3 постами")
    if dup >= 2: signals.append(f"{dup} повторяющихся подписей")
    if top_tag_share >= 0.6: signals.append(f"один набор хэштегов на {top_tag_share:.0%} постов")
    if zero: signals.append(f"{zero:.0%} постов с нулём просмотров — проверить статус аккаунта")
    best = sorted(zip(views, posts), key=lambda x: -x[0])[:3]
    return {"n": n, "median": med, "engagement_pct": round(eng, 2), "rounds": rounds, "score": round(score),
            "verdict": verdict, "signals": signals, "trend_last10_vs_prev10": trend,
            "best": [(v, g(p, "url", default="")) for v, p in best]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("posts")
    ap.add_argument("--out")
    a = ap.parse_args()
    groups = defaultdict(list)
    for p in json.load(open(a.posts)):
        groups[(g(p, "platform", default="?"), g(p, "account", "handle", default="?"))].append(p)
    lines = []
    for (pl, acc), posts in groups.items():
        r = analyse(posts)
        lines += [f"## {pl} · {acc} — вероятность ограничения {r['score']}/100",
                  f"- постов {r['n']}, медиана {r['median']:.0f}, реакции {r['engagement_pct']} %"
                  + (f", тренд последних 10 к предыдущим ×{r['trend_last10_vs_prev10']:.2f}" if r['trend_last10_vs_prev10'] else ""),
                  "- раунды: " + ", ".join(f"{name} — {r['rounds'].get(name, 0)}" for name, _, _ in ROUNDS),
                  f"- вывод: {r['verdict']}",
                  "- сигналы: " + ("; ".join(r["signals"]) if r["signals"] else "нет"),
                  "- лучшие: " + "; ".join(f"{v} {u}" for v, u in r["best"]), ""]
    text = "\n".join(lines)
    print(text)
    if a.out:
        open(a.out, "w").write(text)


if __name__ == "__main__":
    main()
