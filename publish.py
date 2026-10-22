"""Publish due quote posts straight to Instagram (no Metricool).

Runs from GitHub Actions every 30 minutes. For each time in config.json that is
due today and not yet posted, it takes the next entry from queue.json, renders
the image, pushes it to this repo (so Instagram can download it from a public
URL) and publishes it through the Instagram API.

Env:
  IG_ACCESS_TOKEN  Instagram API token (Instagram Login)  - required unless DRY_RUN
  DRY_RUN=1        render and log only, no push, no Instagram call
  FORCE=1          post one entry now, ignoring the schedule (for testing)
"""
import json, os, random, subprocess, sys, time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib import request, parse, error

from make_post import make, is_readable, readability

API = "https://graph.instagram.com/v23.0"
REPO = os.environ.get("GITHUB_REPOSITORY", "petradam398-hub/yourtimetoreflect")
CATCH_UP = timedelta(hours=3)  # a slot missed by more than this is skipped, not posted late

DRY = os.environ.get("DRY_RUN") == "1"
FORCE = os.environ.get("FORCE") == "1"


def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def lines(path):
    try:
        with open(path) as f:
            return [l.rstrip("\n") for l in f if l.strip()]
    except FileNotFoundError:
        return []


def append(path, text):
    with open(path, "a") as f:
        f.write(text + "\n")


def api(method, path, **params):
    params["access_token"] = os.environ["IG_ACCESS_TOKEN"]
    data = parse.urlencode(params).encode()
    url = f"{API}/{path}"
    if method == "GET":
        req = request.Request(url + "?" + data.decode())
    else:
        req = request.Request(url, data=data, method="POST")
    try:
        with request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except error.HTTPError as e:
        body = e.read().decode(errors="replace").replace(os.environ["IG_ACCESS_TOKEN"], "***")
        sys.exit(f"Instagram API error {e.code} on {path}: {body}")


def due_slots(cfg, now):
    posted = set(lines("posted_log.txt"))
    today = now.date().isoformat()
    slots = []
    for t in sorted(cfg["times"]):
        h, m = map(int, t.split(":"))
        at = now.replace(hour=h, minute=m, second=0, microsecond=0)
        key = f"{today} {t}"
        if key in posted:
            continue
        if at <= now <= at + CATCH_UP:
            slots.append(key)
    return slots


def pick_background(cfg, quote):
    """Random background that was not used recently AND keeps the white text readable."""
    names = sorted(f for f in os.listdir("backgrounds") if f.lower().endswith((".jpg", ".jpeg", ".png")))
    recent = [l.split()[-1] for l in lines("backgrounds_used.txt")][-cfg.get("background_cooldown", 5):]
    fresh = [n for n in names if n not in recent]
    random.shuffle(fresh)
    for n in fresh:
        if is_readable(quote, f"backgrounds/{n}"):
            return n
    # nothing fresh works: fall back to the most readable background that is not yesterday's
    pool = [n for n in names if n != (recent[-1] if recent else None)] or names
    return min(pool, key=lambda n: readability(quote, f"backgrounds/{n}"))


def git(*args):
    subprocess.run(["git", *args], check=True)


def publish_one(slot, cfg):
    queue = load("queue.json", [])
    if not queue:
        sys.exit("queue.json is empty - add new quotes before the next post")
    entry = queue[0]
    date, hhmm = slot.split()
    bg = pick_background(cfg, entry["quote"])
    out = f"posts/{date}-{hhmm.replace(':', '')}.jpg"
    make(entry["quote"], out, f"backgrounds/{bg}")
    print(f"[{slot}] {entry['quote']}  ({bg}) -> {out}")
    if DRY:
        return

    # record first, so a crash after publishing can never post the same entry twice
    save("queue.json", queue[1:])
    append("quotes_used.txt", entry["quote"].rstrip("."))
    append("backgrounds_used.txt", f"{date} {bg}")
    append("posted_log.txt", slot)
    git("add", "-A")
    git("commit", "-qm", f"Post {slot}")
    git("push", "-q", "origin", "HEAD")
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    image_url = f"https://raw.githubusercontent.com/{REPO}/{sha}/{out}"

    me = api("GET", "me", fields="user_id,username")
    ig_id = me["user_id"]
    container = api("POST", f"{ig_id}/media", image_url=image_url, caption=entry["caption"])["id"]
    for _ in range(30):  # Instagram downloads and processes the image first
        status = api("GET", container, fields="status_code").get("status_code")
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            sys.exit(f"Instagram could not process the image ({status}) for {image_url}")
        time.sleep(5)
    post = api("POST", f"{ig_id}/media_publish", creation_id=container)
    print(f"Published to @{me.get('username')}: media id {post['id']}")


def check():
    """Verify token and publish permission without posting anything: a container is
    created and processed but never published (Instagram discards it after 24 h)."""
    me = api("GET", "me", fields="user_id,username,account_type")
    print(f"Token OK for @{me.get('username')} ({me.get('account_type')})")
    url = f"https://raw.githubusercontent.com/{REPO}/main/backgrounds/hoodie-teal.jpg"
    container = api("POST", f"{me['user_id']}/media", image_url=url, caption="test")["id"]
    for _ in range(30):
        status = api("GET", container, fields="status_code").get("status_code")
        if status == "FINISHED":
            print("Publish permission OK - Instagram downloaded and accepted a test image (not published)")
            return
        if status in ("ERROR", "EXPIRED"):
            sys.exit(f"Instagram rejected the test image ({status})")
        time.sleep(5)
    sys.exit("Instagram did not finish processing the test image in time")


def main():
    cfg = load("config.json", {})
    if os.environ.get("CHECK") == "1":
        return check()
    if not DRY and not os.environ.get("IG_ACCESS_TOKEN"):
        print("IG_ACCESS_TOKEN secret is not set yet - nothing published")
        return
    if not cfg.get("enabled", True) and not FORCE:
        print("Posting is disabled in config.json")
        return
    now = datetime.now(ZoneInfo(cfg.get("timezone", "Europe/Prague")))
    if FORCE:
        slots = [now.strftime("%Y-%m-%d %H:%M")]
    else:
        posted_today = [l for l in lines("posted_log.txt") if l.startswith(now.date().isoformat())]
        room = max(0, int(cfg.get("max_posts_per_day", 25)) - len(posted_today))
        slots = due_slots(cfg, now)[:room]
    if not slots:
        print(f"{now:%Y-%m-%d %H:%M} nothing due")
        return
    for slot in slots:
        publish_one(slot, cfg)


if __name__ == "__main__":
    main()
