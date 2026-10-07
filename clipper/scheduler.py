"""Autopilot: keeps each campaign's buffer of generated videos topped up and posts on schedule.

One generation worker (the GPU does one video at a time), a pool of posting workers (different
accounts upload in parallel; one account never runs two browsers), and a tick thread that decides
what should happen next.
"""
import datetime
import json
import queue
import random
import shutil
import threading
import time

from . import db, publisher, settings as settings_mod
from .pipeline import produce

TICK_SECONDS = 20
gen_q, post_q, check_q = queue.Queue(), queue.Queue(), queue.Queue()
_queued_gen, _queued_post, _queued_check = set(), set(), set()
_qlock = threading.Lock()
_notified = set()                # one-off log messages already shown
state = {"generating": None, "posting": [], "last_tick": None}


# ---------- queues ----------

def enqueue_generation(video_id):
    with _qlock:
        if video_id in _queued_gen:
            return
        _queued_gen.add(video_id)
    gen_q.put(video_id)


def enqueue_post(video_id, account_ids=None, manual=False):
    """Queues one job per account so a video goes to all its accounts in parallel."""
    if account_ids is None:
        video = db.one("SELECT campaign_id FROM videos WHERE id=?", (video_id,))
        account_ids = publisher.campaign_for(video)["accounts"] if video else []
    if not account_ids:
        db.log("warn", "publisher", "No accounts selected for this campaign; nothing to post to", video_id)
    for aid in account_ids:
        with _qlock:
            if (video_id, aid) in _queued_post:
                continue
            _queued_post.add((video_id, aid))
        post_q.put((video_id, aid, manual))


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
        except Exception as e:  # noqa: BLE001
            db.log("error", "generator", f"Unexpected generation error: {e}", vid)
        finally:
            state["generating"] = None
            with _qlock:
                _queued_gen.discard(vid)


def enqueue_check(account_id):
    with _qlock:
        if account_id in _queued_check:
            return
        _queued_check.add(account_id)
    check_q.put(account_id)


def _check_worker():
    """Background sign-in checks, one browser at a time so they never compete with uploads for resources."""
    while True:
        aid = check_q.get()
        try:
            publisher.check_account(aid, background=True)
        except Exception as e:  # noqa: BLE001
            db.log("error", "accounts", f"Sign-in check crashed: {e}")
        finally:
            with _qlock:
                _queued_check.discard(aid)


def accounts_in_use():
    ids = set()
    for camp in db.query("SELECT config FROM campaigns WHERE enabled=1"):
        ids.update(db.loads(camp["config"], {}).get("accounts", []))
    return ids


def check_sessions(force=False):
    """Queues a sign-in check for each account used by an active campaign whose last check is too old."""
    hours = settings_mod.get("session_check_hours")
    if hours <= 0 and not force:
        return 0
    cutoff = db.now() - hours * 3600
    queued, in_use = 0, accounts_in_use()
    for a in db.query("SELECT id, status, checked_at FROM accounts"):
        if a["id"] not in in_use and not force:
            continue
        if a["status"] in ("checking", "login_open"):
            continue
        if force or a["checked_at"] is None or a["checked_at"] < cutoff:
            enqueue_check(a["id"])
            queued += 1
    return queued


def _post_worker():
    while True:
        vid, aid, manual = post_q.get()
        state["posting"].append(vid)
        try:
            publisher.publish(vid, [aid], manual)
        except Exception as e:  # noqa: BLE001
            db.log("error", "publisher", f"Unexpected posting error: {e}", vid)
        finally:
            state["posting"].remove(vid)
            with _qlock:
                _queued_post.discard((vid, aid))


# ---------- schedule maths ----------

def _window(cfg):
    start, end = int(cfg["window_start"]), int(cfg["window_end"])
    return start, (24 if end <= start else end)


def _even_slot(cfg, after):
    """Posts spread evenly across the daily window, each nudged by a random offset."""
    n = max(1, int(cfg["posts_per_day"]))
    start, end = _window(cfg)
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
            j = min(jitter, span / n / 2 - 60)
            slot = base + span * (i + 0.5) / n + (random.uniform(-j, j) if j > 0 else 0)
            if slot > after + 60:
                return slot
    return after + 86400


def plan_day(cfg, day):
    """Random times for one day: a random count between min and max, at random times, at least min_gap apart."""
    start, end = _window(cfg)
    span = (end - start) * 3600
    lo = max(1, int(cfg["posts_min"]))
    hi = max(lo, int(cfg["posts_max"]))
    gap = max(0, int(cfg["min_gap_minutes"])) * 60
    n = random.randint(lo, hi)
    if gap:
        n = min(n, int(span // gap) + 1)
    free = max(0, span - (n - 1) * gap)
    # Uniform points in the leftover time, then re-insert the gaps: random but never closer than `gap`.
    offsets = sorted(random.uniform(0, free) for _ in range(n))
    base = datetime.datetime.combine(day, datetime.time(start)).timestamp()
    return [base + o + i * gap for i, o in enumerate(offsets)]


def next_slot(cfg, after, plan=None):
    """Returns (next post time, plan to store). Random mode keeps a per-day plan so the daily count holds."""
    if cfg["schedule_mode"] != "random":
        return _even_slot(cfg, after), None
    plan = plan or {}
    pending = [t for t in plan.get("times", []) if t > after + 60]
    if pending:
        return pending[0], {"day": plan["day"], "times": pending[1:]}
    days = set(cfg["days"]) or set(range(7))
    today = datetime.date.fromtimestamp(after)
    first = 0
    if plan.get("day"):
        # Today's plan is used up: never draw a second plan for the same day.
        first = max(0, (datetime.date.fromisoformat(plan["day"]) - today).days + 1)
    for offset in range(first, first + 8):
        d = today + datetime.timedelta(days=offset)
        if d.weekday() not in days:
            continue
        times = [t for t in plan_day(cfg, d) if t > after + 60]
        if times:
            return times[0], {"day": d.isoformat(), "times": times[1:]}
    return after + 86400, None


def _advance(camp, cfg, now):
    slot, plan = next_slot(cfg, now, db.loads(camp["schedule_plan"], None))
    db.execute("UPDATE campaigns SET next_post_at=?, schedule_plan=? WHERE id=?",
               (slot, json.dumps(plan) if plan else None, camp["id"]))


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
            _advance(camp, cfg, now)
            continue
        if now < camp["next_post_at"]:
            continue
        if not cfg["accounts"]:
            _once(f"noacct-{cid}", "warn", f"“{camp['name']}” has no accounts selected, so nothing will be posted.")
            continue
        wanted = "('approved')" if cfg["review"] else "('ready','approved')"
        video = db.one(f"SELECT id FROM videos WHERE campaign_id=? AND status IN {wanted} ORDER BY id LIMIT 1", (cid,))
        if not video:
            hint = "approve videos in the Library" if cfg["review"] else "waiting for generation"
            _once(f"empty-{cid}-{camp['next_post_at']}", "warn", f"“{camp['name']}”: a post is due but nothing is ready ({hint}).")
            continue
        enqueue_post(video["id"])
        _advance(camp, cfg, now)

    # 3. Retry failed or held posts whose back-off has elapsed.
    for row in db.query("SELECT p.video_id, p.account_id FROM posts p JOIN videos v ON v.id=p.video_id "
                        "WHERE v.status='retrying' AND p.status IN ('failed','pending') AND p.attempts<? "
                        "AND (p.next_attempt_at IS NULL OR p.next_attempt_at<=?)", (publisher.MAX_ATTEMPTS, now)):
        enqueue_post(row["video_id"], [row["account_id"]])


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
            if settings_mod.get("autopilot"):
                check_sessions()
            if time.time() - last_house > 3600:
                housekeeping()
                last_house = time.time()
        except Exception as e:  # noqa: BLE001
            db.log("error", "autopilot", f"Scheduler error: {e}")
        time.sleep(TICK_SECONDS)


def recover():
    """After a crash/restart: resume interrupted generations; never blindly re-post interrupted uploads."""
    db.execute("UPDATE accounts SET status='error', note='Sign-in check was interrupted — checking again', checked_at=NULL "
               "WHERE status IN ('checking','login_open')")
    for v in db.query("SELECT id FROM videos WHERE status IN ('queued','generating')"):
        db.execute("UPDATE videos SET status='queued' WHERE id=?", (v["id"],))
        enqueue_generation(v["id"])
    for p in db.query("SELECT video_id, account_id FROM posts WHERE status='posting'"):
        db.execute("UPDATE posts SET status='unconfirmed', error='App stopped while posting — check the account' "
                   "WHERE video_id=? AND account_id=?", (p["video_id"], p["account_id"]))
        publisher.refresh_video_status(p["video_id"])


def start():
    recover()
    workers = max(1, int(settings_mod.get("parallel_uploads")))
    for target in [_gen_worker, _check_worker, _loop] + [_post_worker] * workers:
        threading.Thread(target=target, daemon=True).start()
