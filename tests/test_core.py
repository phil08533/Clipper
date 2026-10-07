"""Core logic tests: scheduling, script validation, captions, posting state machine.

Run: python -m pytest -q
"""
import contextlib
import datetime
import json
import types

import pytest

from clipper import db, publisher, scheduler, settings
from clipper.pipeline import render, script
from clipper.uploaders import base


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "VIDEOS_DIR", tmp_path / "videos")
    monkeypatch.setattr(db, "PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(db, "SHOTS_DIR", tmp_path / "shots")
    db.init()
    settings.seed()
    scheduler._queued_gen.clear()
    scheduler._queued_check.clear()
    publisher._hold_logged.clear()
    while not scheduler.check_q.empty():
        scheduler.check_q.get_nowait()
    scheduler._queued_post.clear()
    scheduler._notified.clear()
    while not scheduler.gen_q.empty():
        scheduler.gen_q.get_nowait()
    while not scheduler.post_q.empty():
        scheduler.post_q.get_nowait()
    yield


def make_account(platform="youtube", label=None, status="connected"):
    aid = publisher.create_account(platform, label or platform)["id"]
    publisher.account_status(aid, status)
    return aid


def make_campaign(**cfg):
    full = settings.campaign_config(cfg)
    return db.execute("INSERT INTO campaigns (name, enabled, config, created_at, updated_at) VALUES ('C',1,?,?,?)",
                      (json.dumps(full), db.now(), db.now()))


def make_video(cid, status="ready"):
    vid = db.execute("INSERT INTO videos (campaign_id, status, title, hashtags, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                     (cid, status, "A title", '["one","two"]', db.now(), db.now()))
    (db.VIDEOS_DIR / str(vid)).mkdir(parents=True)
    (db.VIDEOS_DIR / str(vid) / "final.mp4").write_bytes(b"x")
    return vid


# ---------- scheduling ----------

def ts(y, m, d, hh, mm=0):
    return datetime.datetime(y, m, d, hh, mm).timestamp()


def test_next_slot_spreads_posts_in_window():
    cfg = settings.campaign_config({"schedule_mode": "even", "posts_per_day": 3, "window_start": 9, "window_end": 21, "jitter_minutes": 0})
    after = ts(2026, 10, 5, 0)  # a Monday
    slots, t = [], after
    for _ in range(4):
        t, _plan = scheduler.next_slot(cfg, t)
        slots.append(datetime.datetime.fromtimestamp(t))
    assert [(s.day, s.hour) for s in slots] == [(5, 11), (5, 15), (5, 19), (6, 11)]


def test_next_slot_respects_days_and_jitter_bounds():
    cfg = settings.campaign_config({"schedule_mode": "even", "posts_per_day": 1, "window_start": 10, "window_end": 12, "days": [5], "jitter_minutes": 600})
    slot = datetime.datetime.fromtimestamp(scheduler.next_slot(cfg, ts(2026, 10, 5, 0))[0])
    assert slot.weekday() == 5
    assert 10 <= slot.hour < 12  # jitter is clamped inside the window


# ---------- script validation ----------

def test_validate_cleans_model_output():
    raw = {"title": '"Big title"', "hashtags": "#a, #b c", "scenes": [{"narration": "One."}, {"narration": "Two.", "visual": "v"}, {"narration": " "}]}
    out = script.validate(raw, 2)
    assert out["title"] == "Big title"
    assert out["hashtags"] == ["a", "b", "c"]
    assert [s["narration"] for s in out["scenes"]] == ["One.", "Two."]
    assert out["scenes"][0]["visual"] == "One."


def test_validate_rejects_thin_scripts():
    with pytest.raises(ValueError):
        script.validate({"title": "x", "scenes": [{"narration": "only one"}]}, 6)


def test_prompt_template_braces_are_safe():
    text = script.render_user_prompt("Talk about {niche}. Use {curly} braces {topic}.", "cats", "", 4, 30, ["Old"])
    assert "Talk about cats" in text and "{curly}" in text and "Old" in text


# ---------- captions ----------

def test_captions_cover_speech_and_escape(tmp_path):
    cfg = settings.campaign_config({"caption_words": 2, "caption_uppercase": True})
    out = tmp_path / "c.ass"
    render.build_captions(settings.get_all(), cfg, [(0.0, 2.0, "hello {there} big world"), (2.5, 1.0, "bye")], out)
    lines = [l for l in out.read_text().splitlines() if l.startswith("Dialogue")]
    assert len(lines) == 3
    assert "(THERE)" in lines[0] and "{there}" not in lines[0].lower().split("}", 1)[-1]
    assert lines[1].split(",")[2] == "0:00:02.00"  # second chunk ends exactly at speech end


# ---------- posting ----------

class FakePlatform(types.SimpleNamespace):
    def upload(self, page, post):
        self.calls.append(post)
        if self.behaviour == "ok":
            return "https://example.com/v"
        if self.behaviour == "unconfirmed":
            raise base.Unconfirmed("no confirmation")
        if self.behaviour == "logged_out":
            raise base.NotLoggedIn("expired")
        raise RuntimeError("selector missing")


@pytest.fixture
def fakes(monkeypatch):
    sessions = []

    @contextlib.contextmanager
    def session(_settings, account, **_k):
        sessions.append(account["profile"])
        yield object()
    monkeypatch.setattr(publisher.base, "session", session)
    plats = {p: FakePlatform(NAME=p, calls=[], behaviour="ok") for p in ("youtube", "tiktok", "instagram")}
    monkeypatch.setattr(publisher, "PLATFORMS", plats)
    plats["sessions"] = sessions
    return plats


def post_rows(vid):
    return {r["account_id"]: r for r in db.query("SELECT * FROM posts WHERE video_id=?", (vid,))}


def test_publish_all_ok(fakes):
    yt, tt = make_account("youtube"), make_account("tiktok")
    vid = make_video(make_campaign(accounts=[yt, tt]))
    publisher.publish(vid)
    assert db.one("SELECT status FROM videos WHERE id=?", (vid,))["status"] == "posted"
    assert post_rows(vid)[yt]["url"] == "https://example.com/v"
    post = fakes["youtube"].calls[0]
    assert "#Shorts" in post["description"] and post["ai_label"] is True
    assert fakes["tiktok"].calls[0]["caption"] == "A title #one #two"


def test_two_accounts_same_platform_use_separate_profiles(fakes):
    a, b = make_account("tiktok", "Myths"), make_account("tiktok", "Horror")
    vid = make_video(make_campaign(accounts=[a, b]))
    publisher.publish(vid)
    assert len(fakes["tiktok"].calls) == 2
    assert len(set(fakes["sessions"])) == 2
    assert {r["status"] for r in post_rows(vid).values()} == {"posted"}


def test_publish_failure_retries_then_gives_up(fakes):
    fakes["tiktok"].behaviour = "boom"
    yt, tt = make_account("youtube"), make_account("tiktok")
    vid = make_video(make_campaign(accounts=[yt, tt]))
    publisher.publish(vid)
    assert db.one("SELECT status FROM videos WHERE id=?", (vid,))["status"] == "retrying"
    for _ in range(2):
        publisher.publish(vid)
    rows = post_rows(vid)
    assert rows[tt]["attempts"] == 3 and rows[tt]["status"] == "failed"
    assert len(fakes["youtube"].calls) == 1  # posted accounts are never re-posted
    assert db.one("SELECT status FROM videos WHERE id=?", (vid,))["status"] == "partial"


def test_unconfirmed_is_not_retried(fakes):
    fakes["instagram"].behaviour = "unconfirmed"
    ig = make_account("instagram")
    vid = make_video(make_campaign(accounts=[ig]))
    publisher.publish(vid)
    publisher.publish(vid)
    assert len(fakes["instagram"].calls) == 1
    assert db.one("SELECT status FROM videos WHERE id=?", (vid,))["status"] == "check"


def test_signed_out_during_post_holds_without_using_attempts(fakes):
    fakes["youtube"].behaviour = "logged_out"
    yt = make_account("youtube")
    vid = make_video(make_campaign(accounts=[yt]))
    publisher.publish(vid)
    assert db.one("SELECT status FROM accounts WHERE id=?", (yt,))["status"] == "not_connected"
    row = post_rows(vid)[yt]
    assert row["status"] == "pending" and row["attempts"] == 0 and row["next_attempt_at"] > db.now()
    assert db.one("SELECT status FROM videos WHERE id=?", (vid,))["status"] == "retrying"


def test_known_signed_out_account_is_skipped_not_attempted(fakes):
    yt = make_account("youtube", status="not_connected")
    tt = make_account("tiktok")
    vid = make_video(make_campaign(accounts=[yt, tt]))
    publisher.publish(vid)
    assert fakes["youtube"].calls == [] and len(fakes["tiktok"].calls) == 1
    assert "On hold" in post_rows(vid)[yt]["error"]


def test_reconnect_releases_held_posts(fakes, monkeypatch):
    yt = make_account("youtube", status="not_connected")
    vid = make_video(make_campaign(accounts=[yt]))
    publisher.publish(vid)
    assert post_rows(vid)[yt]["next_attempt_at"] is not None
    monkeypatch.setattr(fakes["youtube"], "is_logged_in", lambda page: True, raising=False)
    assert publisher.check_account(yt, background=True) is True
    assert post_rows(vid)[yt]["next_attempt_at"] is None
    publisher.publish(vid)
    assert len(fakes["youtube"].calls) == 1


def test_check_sessions_only_queues_stale_accounts_in_active_campaigns():
    used, unused, fresh = make_account("youtube"), make_account("tiktok"), make_account("instagram")
    db.execute("UPDATE accounts SET checked_at=? WHERE id IN (?,?)", (db.now() - 13 * 3600, used, unused))
    make_campaign(accounts=[used, fresh])  # fresh was checked just now by make_account
    assert scheduler.check_sessions() == 1
    assert scheduler.check_q.get_nowait() == used
    scheduler._queued_check.clear()
    assert scheduler.check_sessions(force=True) == 3


def test_recover_resets_interrupted_checks():
    aid = make_account("youtube", status="checking")
    scheduler.recover()
    row = db.one("SELECT status, checked_at FROM accounts WHERE id=?", (aid,))
    assert row["status"] == "error" and row["checked_at"] is None


def test_per_account_cap_holds_until_tomorrow(fakes):
    settings.update({"max_posts_per_account": 1})
    yt = make_account("youtube")
    cid = make_campaign(accounts=[yt])
    first, second = make_video(cid), make_video(cid)
    publisher.publish(first)
    publisher.publish(second)
    assert len(fakes["youtube"].calls) == 1
    held = post_rows(second)[yt]
    assert held["status"] == "pending" and held["next_attempt_at"] > db.now() + 3600
    publisher.publish(second, manual=True)  # manual "Post now" ignores the cap
    assert len(fakes["youtube"].calls) == 2


def test_deleting_account_removes_it_from_campaigns(fakes):
    a, b = make_account("youtube"), make_account("tiktok")
    cid = make_campaign(accounts=[a, b])
    publisher.delete_account(a)
    cfg = json.loads(db.one("SELECT config FROM campaigns WHERE id=?", (cid,))["config"])
    assert cfg["accounts"] == [b]


# ---------- autopilot tick ----------

def test_tick_does_nothing_when_paused():
    make_campaign()
    scheduler.tick()
    assert db.query("SELECT * FROM videos") == []


def test_tick_fills_buffer_and_posts_when_due():
    settings.update({"autopilot": True})
    a, b = make_account("youtube"), make_account("tiktok")
    cid = make_campaign(review=False, buffer=2, accounts=[a, b])
    scheduler.tick()
    assert db.one("SELECT COUNT(*) n FROM videos WHERE status='queued'")["n"] == 1  # one at a time
    assert db.one("SELECT next_post_at FROM campaigns WHERE id=?", (cid,))["next_post_at"] is not None

    db.execute("DELETE FROM videos")
    vid = make_video(cid, "ready")
    db.execute("UPDATE campaigns SET next_post_at=? WHERE id=?", (db.now() - 5, cid))
    scheduler.tick()
    jobs = {scheduler.post_q.get_nowait()[:2] for _ in range(2)}
    assert jobs == {(vid, a), (vid, b)}  # one job per account, so they upload in parallel
    assert db.one("SELECT next_post_at FROM campaigns WHERE id=?", (cid,))["next_post_at"] > db.now()


def test_review_mode_only_posts_approved():
    settings.update({"autopilot": True})
    cid = make_campaign(review=True, buffer=1, accounts=[make_account()])
    make_video(cid, "needs_review")
    db.execute("UPDATE campaigns SET next_post_at=? WHERE id=?", (db.now() - 5, cid))
    scheduler.tick()
    assert scheduler.post_q.empty()
    approved = make_video(cid, "approved")
    scheduler.tick()
    assert scheduler.post_q.get_nowait()[0] == approved


def test_recover_never_reposts_interrupted_uploads():
    cid = make_campaign()
    vid = make_video(cid, "posting")
    aid = make_account("tiktok")
    db.execute("INSERT INTO posts (video_id, account_id, platform, status, attempts, updated_at) VALUES (?, ?, 'tiktok', 'posting', 1, ?)",
               (vid, aid, db.now()))
    scheduler.recover()
    assert post_rows(vid)[aid]["status"] == "unconfirmed"
    assert scheduler.post_q.empty()


# ---------- random schedule ----------

def walk_random(cfg, start, days):
    """Simulate the scheduler: repeatedly take the next slot, carrying the stored plan forward."""
    t, plan, out = start, None, []
    end = start + days * 86400
    while True:
        t, plan = scheduler.next_slot(cfg, t, plan)
        if t >= end:
            return out
        out.append(datetime.datetime.fromtimestamp(t))


def test_random_schedule_respects_count_gap_window_and_days():
    cfg = settings.campaign_config({"schedule_mode": "random", "posts_min": 1, "posts_max": 4, "min_gap_minutes": 90,
                                    "window_start": 10, "window_end": 22, "days": [0, 1, 2, 3, 4]})
    slots = walk_random(cfg, ts(2026, 10, 5, 0), 28)  # four weeks from a Monday
    per_day = {}
    for s in slots:
        per_day.setdefault(s.date(), []).append(s)
    assert all(d.weekday() < 5 for d in per_day)
    assert all(1 <= len(v) <= 4 for v in per_day.values())
    assert len({len(v) for v in per_day.values()}) > 1, "daily count should vary"
    for v in per_day.values():
        assert all(10 <= s.hour < 22 for s in v)
        assert all((b - a).total_seconds() >= 90 * 60 for a, b in zip(v, v[1:]))


def test_random_schedule_never_replans_the_same_day():
    cfg = settings.campaign_config({"schedule_mode": "random", "posts_min": 2, "posts_max": 2, "min_gap_minutes": 30,
                                    "window_start": 9, "window_end": 21})
    for _ in range(20):
        slots = walk_random(cfg, ts(2026, 10, 5, 0), 3)
        counts = {}
        for s in slots:
            counts[s.date()] = counts.get(s.date(), 0) + 1
        assert set(counts.values()) == {2}


def test_random_schedule_squeezes_gap_when_window_is_small():
    cfg = settings.campaign_config({"schedule_mode": "random", "posts_min": 5, "posts_max": 5, "min_gap_minutes": 120,
                                    "window_start": 10, "window_end": 14})
    times = scheduler.plan_day(cfg, datetime.date(2026, 10, 5))
    assert len(times) == 3  # only three posts fit 2h apart in a 4h window
    assert all(b - a >= 7200 for a, b in zip(times, times[1:]))


# ---------- presets & series ----------

def test_every_preset_produces_a_valid_campaign(monkeypatch):
    from clipper import presets, server
    for p in presets.PRESETS:
        out = server.apply_preset(p["key"])
        cfg = out["config"]
        assert cfg["prompt_id"] and cfg["preset"] == p["key"] and cfg["schedule_mode"] == "random"
        assert p["key"] == "series" or len(cfg["topics"]) >= 30
        assert db.one("SELECT name FROM prompts WHERE id=?", (cfg["prompt_id"],))["name"] == p["prompt_name"]
    assert {"insects", "animals"} <= {p["key"] for p in presets.PRESETS} and presets.PRESETS[-1]["key"] == "series"
    server.apply_preset("mythology")  # applying twice reuses the prompt
    assert db.one("SELECT COUNT(*) n FROM prompts WHERE name='Mythology & Folklore'")["n"] == 1


def test_series_prompt_includes_world_and_previous_episodes():
    series = {"bible": "A kingdom inside a tree.", "number": 3, "episodes": [("Part 1: Whispers", "Wren hears it…"), ("Part 2: The Order", "They come…")]}
    text = script.render_user_prompt("Next episode in {niche}.", "the Hollow Kingdom", "", 6, 50, ["Part 2: The Order"], series)
    assert "A kingdom inside a tree." in text and "Part 1: Whispers" in text and "episode 3" in text
    assert "Do NOT repeat" not in text  # series continue the story instead of avoiding it


def test_produce_feeds_previous_episodes(monkeypatch, tmp_path):
    from clipper.pipeline import produce
    cid = make_campaign(series_bible="World bible", scenes=2)
    for i in (1, 2):
        db.execute("INSERT INTO videos (campaign_id, status, title, script, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                   (cid, "posted", f"Part {i}", json.dumps({"scenes": [{"narration": f"n{i}"}]}), db.now(), db.now()))
    vid = make_video(cid, "queued")
    camp = db.one("SELECT * FROM campaigns WHERE id=?", (cid,))
    ser = produce._series(camp, settings.campaign_config(json.loads(camp["config"])), vid)
    assert ser["number"] == 3 and [t for t, _ in ser["episodes"]] == ["Part 1", "Part 2"]


# ---------- migration from v1 ----------

def test_v1_database_migrates_accounts_posts_and_campaigns(tmp_path, monkeypatch):
    import sqlite3
    path = tmp_path / "v1.db"
    c = sqlite3.connect(path)
    c.executescript("""
      CREATE TABLE accounts (platform TEXT PRIMARY KEY, status TEXT NOT NULL, note TEXT, checked_at REAL);
      CREATE TABLE posts (id INTEGER PRIMARY KEY AUTOINCREMENT, video_id INTEGER NOT NULL, platform TEXT NOT NULL, status TEXT NOT NULL,
        url TEXT, error TEXT, attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at REAL, updated_at REAL NOT NULL, UNIQUE(video_id, platform));
      CREATE TABLE campaigns (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0, config TEXT NOT NULL,
        next_post_at REAL, topic_cursor INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL, updated_at REAL NOT NULL);
      INSERT INTO accounts VALUES ('youtube', 'connected', NULL, 1), ('tiktok', 'not_connected', NULL, 1);
      INSERT INTO posts (video_id, platform, status, url, updated_at) VALUES (1, 'youtube', 'posted', 'u', 1);
      INSERT INTO campaigns (name, config, created_at, updated_at) VALUES ('Old', '{"platforms": ["youtube", "tiktok"]}', 1, 1);
    """)
    c.commit()
    c.close()
    monkeypatch.setattr(db, "DB_PATH", path)
    db.init()
    accts = {a["platform"]: a for a in db.query("SELECT * FROM accounts")}
    assert accts["youtube"]["status"] == "connected" and accts["youtube"]["profile"] == "youtube"  # keeps the old sign-in folder
    post = db.one("SELECT * FROM posts")
    assert post["account_id"] == accts["youtube"]["id"] and post["status"] == "posted"
    cfg = json.loads(db.one("SELECT config FROM campaigns")["config"])
    assert sorted(cfg["accounts"]) == sorted([accts["youtube"]["id"], accts["tiktok"]["id"]]) and "platforms" not in cfg
    db.init()  # idempotent
    assert len(db.query("SELECT * FROM accounts")) == 2
