"""Autopilot: keeps each campaign's buffer of generated videos topped up and posts on schedule.

Two worker threads (generation, posting) take jobs from queues so a slow render never
blocks a scheduled post, and a tick thread decides what should happen next.
"""
import datetime
import queue
import random
import shutil
import threading
import time

from . import db, publisher, settings as settings_mod
from .pipeline import produce

TICK_SECONDS = 20
gen_q, post_q = queue.Queue(), queue.Queue()
_queued_gen, _queued_post = set(), set()
_qlock = threading.Lock()
_notified = set()                # one-off log messages already shown
state = {"generating": None, "posting": None, "last_tick": None}


# ---------- queues ----------

def enqueue_generation(video_id):
    with _qlock:
        if video_id in _queued_gen:
            return
        _queued_gen.add(video_id)
    gen_q.put(video_id)


def enqueue_post(video_id, platforms=None, manual=False):
    with _qlock:
        if video_id in _queued_post:
            return
        _queued_post.add(video_id)
    post_q.put((video_id, platforms, manual))


def new_video(campaign_id, topic=""):
    vid = db.execute("INSERT INTO videos (campaign_id, status, topic, created_at, updated_at) VALUES (?, 'queued', ?, ?, ?)",
                     (campaign_id, topic, db.now(), db.now()))
    enqueue_generation(vid)
    return vid


def _gen_worker():
    while True:
        vid = gen_q.get()
        state["generating"] = vid
        try:
            produce.produce(vid)
        finally:
            state["generating"] = None
            with _qlock:
                _queued_gen.discard(vid)


def _post_worker():
    while True:
        vid, platforms, manual = post_q.get()
        state["posting"] = vid
        try:
            publisher.publish(vid, platforms, manual)
        except Exception as e:  # noqa: BLE001
            db.log("error", "publisher", f"Unexpected posting error: {e}", vid)
        finally:
            state["posting"] = None
            with _qlock:
                _queued_post.discard(vid)


# ---------- schedule maths ----------

def next_slot(cfg, after):
    """Next posting time after `after` (epoch secs): posts spread evenly across the daily window, with jitter."""
    n = max(1, int(cfg["posts_per_day"]))
    start, end = int(cfg["window_start"]), int(cfg["window_end"])
    if end <= start:
        end = 24
    days = set(cfg["days"]) or set(range(7))
    span = (end - start) * 3600
    jitter = max(0, int(cfg["jitter_minutes"])) * 60
    today = datetime.date.fromtimestamp(after)
    for offset in range(0, 8):
        d = today + datetime.timedelta(days=offset)
        if d.weekday() not in days:
            continue
        base = datetime.datetime.combine(d, datetime.time(start)).timestamp()
        for i in range(n):
            slot = base + span * (i + 0.5) / n
            j = min(jitter, span / n / 2 - 60) if n > 1 else min(jitter, span / 2 - 60)
            slot += random.uniform(-j, j) if j > 0 else 0
            if slot > after + 60:
                return slot
    return after + 86400


# ---------- tick ----------

def _once(key, level, msg, video_id=None):
    if key not in _notified:
        _notified.add(key)
        db.log(level, "autopilot", msg, video_id)


def tick():
    state["last_tick"] = db.now()
    s = settings_mod.get_all()
    if not s["autopilot"]:
        return
    now = db.now()
    for camp in db.query("SELECT * FROM campaigns WHERE enabled=1"):
        cfg = settings_mod.campaign_config(db.loads(camp["config"], {}))
        cid = camp["id"]

        # 1. Keep the buffer full, one generation at a time per campaign.
        counts = db.one("SELECT SUM(status IN ('queued','generating')) busy, "
                        "SUM(status IN ('queued','generating','ready','needs_review','approved')) pending "
                        "FROM videos WHERE campaign_id=?", (cid,))
        if not counts["busy"] and (counts["pending"] or 0) < max(1, int(cfg["buffer"])):
            new_video(cid)

        # 2. Post when a slot arrives.
        if camp["next_post_at"] is None:
            nxt = next_slot(cfg, now)
            db.execute("UPDATE campaigns SET next_post_at=? WHERE id=?", (nxt, cid))
            continue
        if now < camp["next_post_at"]:
            continue
        wanted = "('approved')" if cfg["review"] else "('ready','approved')"
        video = db.one(f"SELECT id, title FROM videos WHERE campaign_id=? AND status IN {wanted} ORDER BY id LIMIT 1", (cid,))
        if not video:
            hint = "approve videos in the Library" if cfg["review"] else "waiting for generation"
            _once(f"empty-{cid}-{camp['next_post_at']}", "warn", f"“{camp['name']}”: a post is due but nothing is ready ({hint}).")
            continue
        if publisher.posted_today() >= s["max_posts_per_day"]:
            _once(f"cap-{datetime.date.today()}", "warn", f"Daily cap of {s['max_posts_per_day']} posts reached. Posting resumes tomorrow.")
            continue
        enqueue_post(video["id"])
        db.execute("UPDATE campaigns SET next_post_at=? WHERE id=?", (next_slot(cfg, now), cid))

    # 3. Retry failed posts whose back-off has elapsed.
    if publisher.posted_today() < s["max_posts_per_day"]:
        for row in db.query("SELECT DISTINCT p.video_id FROM posts p JOIN videos v ON v.id=p.video_id "
                            "WHERE v.status='retrying' AND p.status IN ('failed','pending') AND p.attempts<? "
                            "AND (p.next_attempt_at IS NULL OR p.next_attempt_at<=?)", (publisher.MAX_ATTEMPTS, now)):
            enqueue_post(row["video_id"])


def housekeeping():
    days = settings_mod.get("delete_after_days")
    if days <= 0:
        return
    cutoff = db.now() - days * 86400
    for v in db.query("SELECT id FROM videos WHERE status IN ('posted','partial','check') AND posted_at<? AND files_deleted=0", (cutoff,)):
        shutil.rmtree(db.VIDEOS_DIR / str(v["id"]), ignore_errors=True)
        db.execute("UPDATE videos SET files_deleted=1 WHERE id=?", (v["id"],))


def _loop():
    last_house = 0
    while True:
        try:
            tick()
            if time.time() - last_house > 3600:
                housekeeping()
                last_house = time.time()
        except Exception as e:  # noqa: BLE001
            db.log("error", "autopilot", f"Scheduler error: {e}")
        time.sleep(TICK_SECONDS)


def recover():
    """After a crash/restart: resume interrupted generations; never blindly re-post interrupted uploads."""
    for v in db.query("SELECT id FROM videos WHERE status IN ('queued','generating')"):
        db.execute("UPDATE videos SET status='queued' WHERE id=?", (v["id"],))
        enqueue_generation(v["id"])
    for p in db.query("SELECT video_id, platform FROM posts WHERE status='posting'"):
        db.execute("UPDATE posts SET status='unconfirmed', error='App stopped while posting — check the account' "
                   "WHERE video_id=? AND platform=?", (p["video_id"], p["platform"]))
        publisher.refresh_video_status(p["video_id"])


def start():
    recover()
    for target in (_gen_worker, _post_worker, _loop):
        threading.Thread(target=target, daemon=True).start()
