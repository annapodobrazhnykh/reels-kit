"""Permanent link for a reel cover: a secret GitHub gist (not on her profile, link-only), deleted after the reel is out.

Upload-Post keeps the Custom Cover URL as a link and Instagram fetches it at publish time; its own media_url dies in ~6 h,
so a post scheduled further ahead lost its cover. A gist raw link serves image/jpeg directly (checked 2026-11-11).

usage:
  python3 cover_gist.py upload COVER.jpg "серия 5" 2026-11-12T10:00Z   -> prints the raw URL (checked: 200 + image/jpeg)
  python3 cover_gist.py due [--hours 24]                                -> covers whose reel went out > N h ago
  python3 cover_gist.py delete GIST_ID [GIST_ID ...]

Every gist is described "reel-cover · <label> · выход <UTC ISO>", so `due` needs no separate ledger.
Deleting removes the file at once; the raw CDN copy may live up to 5 min (cache-control max-age=300).
"""
import datetime as dt, json, os, shutil, subprocess, sys, tempfile, urllib.request

PREFIX = "reel-cover"
GH = shutil.which("gh") or os.path.expanduser("~/.local/bin/gh")

def _login():
    return subprocess.run([GH, "api", "user", "-q", ".login"], check=True, capture_output=True, text=True).stdout.strip()

def gh(*args):
    return subprocess.run([GH, *args], check=True, capture_output=True, text=True).stdout.strip()

def git(cwd, *args):
    LOGIN = _login()
    # https + gh as credential helper: the gist ssh host key is not trusted on this Mac
    subprocess.run(["git", "-c", "credential.helper=", "-c", f"credential.helper=!{GH} auth git-credential",
                    "-c", f"user.name={LOGIN}", "-c", f"user.email={LOGIN}@users.noreply.github.com",
                    *args], cwd=cwd, check=True, capture_output=True, text=True)

def parse_when(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(dt.timezone.utc)

def upload(path, label, when):
    when = parse_when(when).strftime("%Y-%m-%dT%H:%MZ")
    tmp = tempfile.mkdtemp()
    readme = os.path.join(tmp, "README.md")
    open(readme, "w").write("reel cover\n")
    url = gh("gist", "create", readme, "-d", f"{PREFIX} · {label} · выход {when}").splitlines()[-1]   # secret by default
    gid = url.rstrip("/").split("/")[-1]
    repo = os.path.join(tmp, "g")
    git(tmp, "clone", "-q", f"https://gist.github.com/{gid}.git", repo)
    shutil.copy(path, os.path.join(repo, "cover.jpg"))
    git(repo, "add", "cover.jpg"); git(repo, "commit", "-qm", "cover"); git(repo, "push", "-q")
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
    user = gh("api", "user", "--jq", ".login")
    raw = f"https://gist.githubusercontent.com/{user}/{gid}/raw/{sha}/cover.jpg"
    with urllib.request.urlopen(raw) as r:
        ok = r.status == 200 and r.headers.get("Content-Type") == "image/jpeg" and r.read() == open(path, "rb").read()
    shutil.rmtree(tmp)
    if not ok:
        sys.exit(f"gist {gid}: raw link does not serve the cover as image/jpeg — do not use it")
    print(json.dumps({"gist_id": gid, "cover_url": raw, "publish_utc": when}, ensure_ascii=False))

def due(hours):
    gists = json.loads(gh("api", "gists", "--paginate"))
    now = dt.datetime.now(dt.timezone.utc)
    for g in gists:
        d = g.get("description") or ""
        if not d.startswith(PREFIX) or "выход " not in d:
            continue
        when = parse_when(d.split("выход ")[-1].strip())
        print(json.dumps({"gist_id": g["id"], "description": d, "due": now - when > dt.timedelta(hours=hours)}, ensure_ascii=False))

cmd = sys.argv[1:] or ["-h"]
if cmd[0] == "upload" and len(cmd) == 4:
    upload(*cmd[1:])
elif cmd[0] == "due":
    due(float(cmd[2]) if len(cmd) > 2 and cmd[1] == "--hours" else 24)
elif cmd[0] == "delete" and len(cmd) > 1:
    for gid in cmd[1:]:
        gh("gist", "delete", gid, "--yes"); print("deleted", gid)
else:
    print(__doc__)
