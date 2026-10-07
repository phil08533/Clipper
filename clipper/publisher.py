"""Posting videos to platforms and managing signed-in accounts."""
import datetime
import shutil
import threading

from . import db, settings as settings_mod
from .uploaders import PLATFORMS, base

MAX_ATTEMPTS = 3
FINAL = ("posted", "unconfirmed", "skipped")


def build_post(video, cfg, platform):
    tags = db.loads(video["hashtags"], [])
    hashtags = " ".join("#" + t for t in tags)
    post = {
        "file": str(db.VIDEOS_DIR / str(video["id"]) / "final.mp4"),
        "title": video["title"],
        "ai_label": bool(cfg["ai_label"]),
        "visibility": cfg["youtube_visibility"],
    }
    if platform == "youtube":
        post["description"] = f"{video['description']}\n\n{hashtags} #Shorts".strip()
    elif platform == "tiktok":
        post["caption"] = f"{video['title']} {hashtags}".strip()
    else:
        post["caption"] = f"{video['title']}\n\n{video['description']}\n\n{hashtags}".strip()
    return post


def posted_today():
    midnight = datetime.datetime.combine(datetime.date.today(), datetime.time()).timestamp()
    return db.one("SELECT COUNT(*) n FROM posts WHERE status='posted' AND updated_at>=?", (midnight,))["n"]


def _set_post(video_id, platform, **fields):
    fields["updated_at"] = db.now()
    cols = ", ".join(f"{k}=?" for k in fields)
    db.execute(f"UPDATE posts SET {cols} WHERE video_id=? AND platform=?", (*fields.values(), video_id, platform))


def refresh_video_status(video_id):
    rows = db.query("SELECT status, attempts FROM posts WHERE video_id=?", (video_id,))
    if not rows:
        return
    st = [r["status"] for r in rows]
    retryable = any(r["status"] in ("failed", "pending") and r["attempts"] < MAX_ATTEMPTS for r in rows)
    if any(s == "posting" for s in st):
        status = "posting"
    elif all(s in ("posted", "skipped") for s in st):
        status = "posted"
    elif retryable:
        status = "retrying"
    elif all(s in FINAL for s in st):
        status = "check"          # at least one platform couldn't confirm success
    elif any(s in ("posted", "unconfirmed") for s in st):
        status = "partial"
    else:
        status = "post_failed"
    posted_at = db.now() if status in ("posted", "partial", "check") else None
    db.execute("UPDATE videos SET status=?, posted_at=COALESCE(posted_at, ?), updated_at=? WHERE id=?",
               (status, posted_at, db.now(), video_id))


def publish(video_id, platforms=None, manual=False):
    video = db.one("SELECT * FROM videos WHERE id=?", (video_id,))
    if not video:
        return
    camp = db.one("SELECT config FROM campaigns WHERE id=?", (video["campaign_id"],))
    cfg = settings_mod.campaign_config(db.loads(camp["config"], {}) if camp else {})
    s = settings_mod.get_all()
    if not (db.VIDEOS_DIR / str(video_id) / "final.mp4").is_file():
        db.log("error", "publisher", "Video file is missing; cannot post", video_id)
        return
    for p in platforms or cfg["platforms"]:
        if p not in PLATFORMS:
            continue
        db.execute("INSERT OR IGNORE INTO posts (video_id, platform, status, updated_at) VALUES (?,?,'pending',?)",
                   (video_id, p, db.now()))
        row = db.one("SELECT * FROM posts WHERE video_id=? AND platform=?", (video_id, p))
        if row["status"] in FINAL:
            continue
        if not manual and posted_today() >= s["max_posts_per_day"]:
            db.log("warn", "publisher", f"Daily safety cap of {s['max_posts_per_day']} posts reached; holding the rest", video_id)
            break
        attempts = row["attempts"] + 1
        _set_post(video_id, p, status="posting", attempts=attempts, error=None)
        refresh_video_status(video_id)
        mod = PLATFORMS[p]
        db.log("info", p, f"Posting “{video['title']}” (attempt {attempts})", video_id)
        try:
            with base.session(s, p) as page:
                url = mod.upload(page, build_post(video, cfg, p))
            _set_post(video_id, p, status="posted", url=url, error=None)
            db.log("info", p, f"Posted “{video['title']}”" + (f" — {url}" if url else ""), video_id)
        except base.Unconfirmed as e:
            _set_post(video_id, p, status="unconfirmed", error=str(e))
            db.log("warn", p, f"{e}. Check the account and mark it posted or retry from the Library.", video_id)
        except base.NotLoggedIn as e:
            _set_post(video_id, p, status="failed", attempts=MAX_ATTEMPTS, error=str(e))
            db.execute("UPDATE accounts SET status='not_connected', note=?, checked_at=? WHERE platform=?", (str(e), db.now(), p))
            db.log("error", p, str(e), video_id)
        except Exception as e:  # noqa: BLE001
            retry_at = db.now() + 900 * attempts if attempts < MAX_ATTEMPTS else None
            _set_post(video_id, p, status="failed", error=str(e)[:1500], next_attempt_at=retry_at)
            db.log("error", p, f"Post failed: {e}" + (" — will retry" if retry_at else ""), video_id)
    refresh_video_status(video_id)


# ---------- accounts ----------

def account_status(platform, status, note=None):
    db.execute("INSERT INTO accounts (platform, status, note, checked_at) VALUES (?,?,?,?) "
               "ON CONFLICT(platform) DO UPDATE SET status=excluded.status, note=excluded.note, checked_at=excluded.checked_at",
               (platform, status, note, db.now()))


def check_account(platform):
    account_status(platform, "checking")
    try:
        with base.session(settings_mod.get_all(), platform) as page:
            ok = PLATFORMS[platform].is_logged_in(page)
        account_status(platform, "connected" if ok else "not_connected", None if ok else "Not signed in")
    except Exception as e:  # noqa: BLE001
        account_status(platform, "error", str(e)[:500])
        db.log("error", platform, f"Account check failed: {e}")


def connect_account(platform):
    account_status(platform, "login_open", "Sign in, then close the browser window")
    try:
        base.open_login_window(settings_mod.get_all(), platform, PLATFORMS[platform].LOGIN_URL)
    except Exception as e:  # noqa: BLE001
        account_status(platform, "error", str(e)[:500])
        db.log("error", platform, f"Could not open the sign-in window: {e}")
        return
    check_account(platform)


def disconnect_account(platform):
    with base.LOCKS[platform]:
        shutil.rmtree(base.profile_dir(platform), ignore_errors=True)
    account_status(platform, "not_connected", "Signed out")


def run_in_thread(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()
