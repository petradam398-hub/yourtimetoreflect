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

from make_post import make, make_reel, make_story, is_readable, readability

API = "https://graph.instagram.com/v23.0"
REPO = os.environ.get("GITHUB_REPOSITORY", "petradam398-hub/yourtimetoreflect")
CATCH_UP = timedelta(hours=3)  # a slot missed by more than this is skipped, not posted late
LOOKAHEAD = timedelta(minutes=55)  # GitHub starts scheduled runs late, so start early and wait

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


def fail(msg):
    print(f"::error::{msg}", flush=True)
    sys.exit(msg)


def note(msg):
    print(f"::notice::{msg}", flush=True)


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
        fail(f"Instagram API error {e.code} on {path}: {body}")


RUN_ID = os.environ.get("GITHUB_RUN_ID", "local")


def posted_slots(text=None):
    """Slots already posted ("YYYY-MM-DD HH:MM"); log lines may carry a run id after it."""
    rows = text.splitlines() if text is not None else lines("posted_log.txt")
    return {" ".join(r.split()[:2]) for r in rows if r.strip()}


def due_slots(cfg, now):
    posted = posted_slots()
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


def next_slot(cfg, now):
    """The next not-yet-posted slot starting within LOOKAHEAD (to wait for), or None."""
    posted = posted_slots()
    for t in sorted(cfg["times"]):
        h, m = map(int, t.split(":"))
        at = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if f"{now.date().isoformat()} {t}" not in posted and now < at <= now + LOOKAHEAD:
            return at
    return None


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
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if r.returncode:
        fail(f"git {' '.join(args[:2])} failed: {(r.stderr or r.stdout).strip()[-400:]}")


def claim(slot):
    """Push the bookkeeping commit as a lock: only the run whose push lands first may
    publish this slot. A rejected push means something changed on GitHub meanwhile;
    if that was another run taking this slot, we stop, otherwise rebase and retry."""
    for _ in range(5):
        if subprocess.run(["git", "push", "-q", "origin", "HEAD"], capture_output=True).returncode == 0:
            return True
        git("fetch", "-q", "origin", "main")
        theirs = subprocess.run(["git", "show", "origin/main:posted_log.txt"],
                                capture_output=True, text=True).stdout
        if slot in posted_slots(theirs):
            git("reset", "-q", "--hard", "origin/main")
            return False
        git("rebase", "-q", "origin/main")
        if slot not in posted_slots():  # our record got dropped - never publish without one
            git("reset", "-q", "--hard", "origin/main")
            return False
    fail(f"could not push the post record for {slot}")


def publish_one(slot, cfg):
    queue = load("queue.json", [])
    if not queue:
        fail("queue.json is empty - add new quotes before the next post")
    entry = queue[0]
    date, hhmm = slot.split()
    # entries written for a specific photo keep it; others get a readable random one
    bg = entry.get("background")
    if not bg or not os.path.exists(f"backgrounds/{bg}"):
        bg = pick_background(cfg, entry["quote"])
    out = f"posts/{date}-{hhmm.replace(':', '')}.jpg"
    make(entry["quote"], out, f"backgrounds/{bg}", entry.get("spot"))
    as_reel = hhmm in cfg.get("reel_times", []) or os.environ.get("AS_REEL") == "1"
    reel = out.replace(".jpg", ".mp4") if as_reel else None
    story = out.replace(".jpg", "-story.jpg") if (cfg.get("stories") or reel) else None
    if story:
        make_story(out, f"backgrounds/{bg}", story)
    if reel:  # the reel is the 9:16 story frame, slowly zooming in, with music
        make_reel(story, reel)
    print(f"[{slot}] {entry['quote']}  ({bg}) -> {reel or out}" + (f" + {story}" if story else ""))
    if DRY:
        return

    # make sure Instagram accepts us before touching the queue (a blocked app or an
    # expired token must not use up posts)
    me = api("GET", "me", fields="user_id,username")
    ig_id = me["user_id"]

    # record first, so a crash after publishing can never post the same entry twice
    tracked = ["queue.json", "quotes_used.txt", "backgrounds_used.txt", "posted_log.txt"]
    snapshot = {f: open(f).read() if os.path.exists(f) else "" for f in tracked}
    save("queue.json", queue[1:])
    append("quotes_used.txt", entry["quote"].rstrip("."))
    append("backgrounds_used.txt", f"{date} {bg}")
    append("posted_log.txt", f"{slot} {RUN_ID}")
    git("add", "-A")
    git("commit", "-qm", f"Post {slot}")
    if not claim(slot):
        note(f"{slot} was already posted by another run - skipping")
        return
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    image_url = f"https://raw.githubusercontent.com/{REPO}/{sha}/{reel or out}"
    try:
        new_post = upload(ig_id, me, slot, entry, image_url, is_reel=bool(reel))
    except SystemExit:
        # not published: give the entry back so it goes out at the next time slot
        for f, text in snapshot.items():
            with open(f, "w") as fh:
                fh.write(text)
        git("add", "-A")
        git("commit", "-qm", f"Undo failed post {slot}")
        git("pull", "-q", "--rebase", "origin", "main")
        git("push", "-q", "origin", "HEAD")
        raise
    if story and cfg.get("stories") and new_post:  # the feed post is out; a failed story only warns, it never undoes the post
        share_story(ig_id, slot, f"https://raw.githubusercontent.com/{REPO}/{sha}/{story}")


def share_story(ig_id, slot, url):
    try:
        container = api("POST", f"{ig_id}/media", image_url=url, media_type="STORIES")["id"]
        for _ in range(30):
            status = api("GET", container, fields="status_code").get("status_code")
            if status == "FINISHED":
                break
            if status in ("ERROR", "EXPIRED"):
                raise SystemExit(f"story image {status}")
            time.sleep(5)
        else:
            raise SystemExit("story still processing after 150 s")
        story = api("POST", f"{ig_id}/media_publish", creation_id=container)
        note(f"Story for {slot} published: media id {story['id']}")
    except SystemExit as e:
        print(f"::warning::Post is out, but the story for {slot} failed: {e}", flush=True)


def wait_ready(container, url, tries=30, pause=5):
    """Instagram downloads and processes the file before it can be published."""
    status = None
    for _ in range(tries):
        info = api("GET", container, fields="status_code,status")
        status = info.get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            fail(f"Instagram could not process {url} ({status}: {info.get('status', '')})")
        time.sleep(pause)
    fail(f"Instagram was still processing {url} after {tries * pause} s ({status})")


def already_live(ig_id, caption, hours=12):
    """True if a post with this exact caption went out in the last hours (e.g. a run
    that got an error back although Instagram published it anyway)."""
    recent = api("GET", f"{ig_id}/media", fields="caption,timestamp", limit="15").get("data", [])
    cutoff = datetime.now(ZoneInfo("UTC")) - timedelta(hours=hours)
    for m in recent:
        ts = datetime.strptime(m.get("timestamp", "1970-01-01T00:00:00+0000"), "%Y-%m-%dT%H:%M:%S%z")
        if ts >= cutoff and (m.get("caption") or "").strip() == caption.strip():
            return True
    return False


def upload(ig_id, me, slot, entry, image_url, is_reel=False):
    if already_live(ig_id, entry["caption"]):
        note(f"{slot}: this post is already on Instagram - not posting it again")
        return False
    if is_reel:
        params = dict(media_type="REELS", video_url=image_url, share_to_feed="true")
    else:
        params = dict(image_url=image_url)
    container = api("POST", f"{ig_id}/media", caption=entry["caption"], **params)["id"]
    wait_ready(container, image_url, tries=60 if is_reel else 30, pause=10 if is_reel else 5)
    try:
        post = api("POST", f"{ig_id}/media_publish", creation_id=container)
    except SystemExit:
        time.sleep(20)
        if already_live(ig_id, entry["caption"], hours=1):
            note(f"{slot}: Instagram reported an error but the post is live - keeping it")
            return True
        raise
    note(f"Published {slot} to @{me.get('username')}: media id {post['id']}")
    return True


def check():
    """Verify token and publish permission without posting anything: a container is
    created and processed but never published (Instagram discards it after 24 h)."""
    me = api("GET", "me", fields="user_id,username,account_type")
    note(f"Token OK for @{me.get('username')} ({me.get('account_type')})")
    recent = api("GET", f"{me['user_id']}/media", fields="caption,timestamp", limit="3").get("data", [])
    note(f"Duplicate guard OK - can read the {len(recent)} latest posts")
    url = f"https://raw.githubusercontent.com/{REPO}/main/backgrounds/hoodie-teal.jpg"
    container = api("POST", f"{me['user_id']}/media", image_url=url, caption="test")["id"]
    for _ in range(30):
        status = api("GET", container, fields="status_code").get("status_code")
        if status == "FINISHED":
            note("Publish permission OK - test image accepted (not published)")
            break
        if status in ("ERROR", "EXPIRED"):
            fail(f"Instagram rejected the test image ({status})")
        time.sleep(5)
    else:
        fail("Instagram did not finish processing the test image in time")
    if os.path.exists("tests/reel-test.mp4"):
        url = f"https://raw.githubusercontent.com/{REPO}/main/tests/reel-test.mp4"
        c = api("POST", f"{me['user_id']}/media", media_type="REELS", video_url=url, caption="test")["id"]
        wait_ready(c, url, tries=60, pause=10)
        note("Reel OK - test video accepted (not published)")


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
        posted_today = [p for p in posted_slots() if p.startswith(now.date().isoformat())]
        room = max(0, int(cfg.get("max_posts_per_day", 25)) - len(posted_today))
        slots = due_slots(cfg, now)[:room]
        if not slots and room and not DRY:
            at = next_slot(cfg, now)
            if at:
                wait = (at - now).total_seconds()
                print(f"Waiting {wait / 60:.0f} min to post exactly at {at:%H:%M}")
                time.sleep(max(0, wait))
                now = datetime.now(now.tzinfo)
                slots = due_slots(cfg, now)[:room]
    if not slots:
        print(f"{now:%Y-%m-%d %H:%M} nothing due")
        return
    for slot in slots:
        publish_one(slot, cfg)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # anything unexpected still shows up as a readable error
        fail(f"Unexpected error: {e!r}")
