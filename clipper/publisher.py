"""Posting videos to accounts and managing those accounts."""
import datetime
import json
import re
import shutil
import threading

from . import db, settings as settings_mod
from .uploaders import PLATFORMS, base

MAX_ATTEMPTS = 3
FINAL = ("posted", "unconfirmed", "skipped")
HOLD_SECONDS = 1800               # how often a post held for a signed-out account is looked at again
_hold_logged = set()              # (video, account) holds already reported, to keep the log readable


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


# ---------- accounts ----------

def get_account(account_id):
    return db.one("SELECT * FROM accounts WHERE id=?", (account_id,))


def create_account(platform, label):
    if platform not in PLATFORMS:
        raise ValueError("Unknown platform")
    label = (label or "").strip()[:80] or db.PLATFORM_NAMES[platform]
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:30] or platform
    aid = db.execute("INSERT INTO accounts (platform, label, profile, created_at) VALUES (?,?,?,?)",
                     (platform, label, f"tmp-{db.now()}", db.now()))
    db.execute("UPDATE accounts SET profile=? WHERE id=?", (f"{platform}-{aid}-{slug}", aid))
    return get_account(aid)


def account_status(account_id, status, note=None):
    db.execute("UPDATE accounts SET status=?, note=?, checked_at=? WHERE id=?", (status, note, db.now(), account_id))


def check_account(account_id, background=False):
    """Opens the account's profile and confirms it is still signed in. Returns True when it is."""
    acct = get_account(account_id)
    if not acct:
        return False
    was = acct["status"]
    account_status(account_id, "checking", acct["note"])
    try:
        with base.session(settings_mod.get_all(), acct, headless=True if background else None) as page:
            ok = PLATFORMS[acct["platform"]].is_logged_in(page)
    except Exception as e:  # noqa: BLE001
        account_status(account_id, "error", f"Sign-in check failed: {str(e)[:400]}")
        db.log("error", acct["platform"], f"{acct['label']}: sign-in check failed: {e}")
        return False
    if ok:
        account_status(account_id, "connected", None)
        # Release anything held while it was signed out.
        db.execute("UPDATE posts SET next_attempt_at=NULL, error=NULL WHERE account_id=? AND status='pending'", (account_id,))
        if was != "connected" and background:
            db.log("info", acct["platform"], f"{acct['label']}: signed in again — held posts will go out")
        return True
    account_status(account_id, "not_connected", "Signed out — click Reconnect. Posts to this account are on hold.")
    if was == "connected":
        db.log("error", acct["platform"], f"{acct['label']}: signed out. Posts to it are on hold until you reconnect it on the Accounts page.")
    return False


def connect_account(account_id):
    acct = get_account(account_id)
    if not acct:
        return
    account_status(account_id, "login_open", "Sign in, then close the browser window")
    try:
        base.open_login_window(settings_mod.get_all(), acct, PLATFORMS[acct["platform"]].LOGIN_URL)
    except Exception as e:  # noqa: BLE001
        account_status(account_id, "error", str(e)[:500])
        db.log("error", acct["platform"], f"{acct['label']}: could not open the sign-in window: {e}")
        return
    check_account(account_id)


def disconnect_account(account_id):
    acct = get_account(account_id)
    if not acct:
        return
    with base.lock_for(acct):
        shutil.rmtree(base.profile_dir(acct), ignore_errors=True)
    account_status(account_id, "not_connected", "Signed out")


def delete_account(account_id):
    acct = get_account(account_id)
    if not acct:
        return
    disconnect_account(account_id)
    db.execute("DELETE FROM accounts WHERE id=?", (account_id,))
    for camp in db.query("SELECT id, config FROM campaigns"):
        cfg = db.loads(camp["config"], {})
        if account_id in cfg.get("accounts", []):
            cfg["accounts"] = [a for a in cfg["accounts"] if a != account_id]
            db.execute("UPDATE campaigns SET config=? WHERE id=?", (json.dumps(cfg), camp["id"]))


def run_in_thread(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()


# ---------- posting ----------

def posted_today(account_id):
    midnight = datetime.datetime.combine(datetime.date.today(), datetime.time()).timestamp()
    return db.one("SELECT COUNT(*) n FROM posts WHERE account_id=? AND status='posted' AND updated_at>=?",
                  (account_id, midnight))["n"]


def _set_post(video_id, account_id, **fields):
    fields["updated_at"] = db.now()
    cols = ", ".join(f"{k}=?" for k in fields)
    db.execute(f"UPDATE posts SET {cols} WHERE video_id=? AND account_id=?", (*fields.values(), video_id, account_id))


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
        status = "check"          # at least one account couldn't confirm success
    elif any(s in ("posted", "unconfirmed") for s in st):
        status = "partial"
    else:
        status = "post_failed"
    posted_at = db.now() if status in ("posted", "partial", "check") else None
    db.execute("UPDATE videos SET status=?, posted_at=COALESCE(posted_at, ?), updated_at=? WHERE id=?",
               (status, posted_at, db.now(), video_id))


def campaign_for(video):
    camp = db.one("SELECT config FROM campaigns WHERE id=?", (video["campaign_id"],))
    return settings_mod.campaign_config(db.loads(camp["config"], {}) if camp else {})


def publish(video_id, account_ids=None, manual=False):
    video = db.one("SELECT * FROM videos WHERE id=?", (video_id,))
    if not video:
        return
    cfg = campaign_for(video)
    s = settings_mod.get_all()
    if not (db.VIDEOS_DIR / str(video_id) / "final.mp4").is_file():
        db.log("error", "publisher", "Video file is missing; cannot post", video_id)
        return
    targets = account_ids or cfg["accounts"]
    if not targets:
        db.log("warn", "publisher", "This campaign has no accounts to post to", video_id)
        return
    for aid in targets:
        acct = get_account(aid)
        if not acct or acct["platform"] not in PLATFORMS:
            continue
        p, who = acct["platform"], acct["label"]
        db.execute("INSERT OR IGNORE INTO posts (video_id, account_id, platform, status, updated_at) VALUES (?,?,?,'pending',?)",
                   (video_id, aid, p, db.now()))
        row = db.one("SELECT * FROM posts WHERE video_id=? AND account_id=?", (video_id, aid))
        if row["status"] in FINAL:
            continue
        if not manual and acct["status"] == "not_connected":
            # Safe posting: don't burn retries (or trip platform defences) on an account we know is signed out.
            _set_post(video_id, aid, next_attempt_at=db.now() + HOLD_SECONDS, error="On hold: account is signed out — reconnect it")
            if (video_id, aid) not in _hold_logged:
                _hold_logged.add((video_id, aid))
                db.log("warn", p, f"{who}: signed out, so this post is on hold until you reconnect the account", video_id)
            continue
        if not manual and posted_today(aid) >= s["max_posts_per_account"]:
            tomorrow = datetime.datetime.combine(datetime.date.today() + datetime.timedelta(days=1), datetime.time(8)).timestamp()
            _set_post(video_id, aid, next_attempt_at=tomorrow)
            db.log("warn", p, f"{who}: daily cap of {s['max_posts_per_account']} posts reached; holding this post until tomorrow", video_id)
            continue
        attempts = row["attempts"] + 1
        _set_post(video_id, aid, status="posting", attempts=attempts, error=None)
        refresh_video_status(video_id)
        db.log("info", p, f"{who}: posting “{video['title']}” (attempt {attempts})", video_id)
        try:
            with base.session(s, acct) as page:
                url = PLATFORMS[p].upload(page, build_post(video, cfg, p))
            _set_post(video_id, aid, status="posted", url=url, error=None)
            db.log("info", p, f"{who}: posted “{video['title']}”" + (f" — {url}" if url else ""), video_id)
        except base.Unconfirmed as e:
            _set_post(video_id, aid, status="unconfirmed", error=str(e))
            db.log("warn", p, f"{who}: {e}. Check the account and mark it posted or retry from the Library.", video_id)
        except base.NotLoggedIn as e:
            # Not the video's fault: hold it (without using up an attempt) until the account is reconnected.
            _set_post(video_id, aid, status="pending", attempts=row["attempts"], next_attempt_at=db.now() + HOLD_SECONDS,
                      error="On hold: account is signed out — reconnect it")
            account_status(aid, "not_connected", "Signed out — click Reconnect. Posts to this account are on hold.")
            db.log("error", p, f"{who}: {e}. Posts to it are on hold until you reconnect it.", video_id)
        except Exception as e:  # noqa: BLE001
            retry_at = db.now() + 900 * attempts if attempts < MAX_ATTEMPTS else None
            _set_post(video_id, aid, status="failed", error=str(e)[:1500], next_attempt_at=retry_at)
            db.log("error", p, f"{who}: post failed: {e}" + (" — will retry" if retry_at else ""), video_id)
    refresh_video_status(video_id)
