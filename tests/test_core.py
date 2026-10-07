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
    scheduler._queued_post.clear()
    scheduler._notified.clear()
    while not scheduler.gen_q.empty():
        scheduler.gen_q.get_nowait()
    while not scheduler.post_q.empty():
        scheduler.post_q.get_nowait()
    yield


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
    cfg = settings.campaign_config({"posts_per_day": 3, "window_start": 9, "window_end": 21, "jitter_minutes": 0})
    after = ts(2026, 10, 5, 0)  # a Monday
    slots, t = [], after
    for _ in range(4):
        t = scheduler.next_slot(cfg, t)
        slots.append(datetime.datetime.fromtimestamp(t))
    assert [(s.day, s.hour) for s in slots] == [(5, 11), (5, 15), (5, 19), (6, 11)]


def test_next_slot_respects_days_and_jitter_bounds():
    cfg = settings.campaign_config({"posts_per_day": 1, "window_start": 10, "window_end": 12, "days": [5], "jitter_minutes": 600})
    slot = datetime.datetime.fromtimestamp(scheduler.next_slot(cfg, ts(2026, 10, 5, 0)))
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
    @contextlib.contextmanager
    def session(*_a, **_k):
        yield object()
    monkeypatch.setattr(publisher.base, "session", session)
    plats = {p: FakePlatform(NAME=p, calls=[], behaviour="ok") for p in ("youtube", "tiktok", "instagram")}
    monkeypatch.setattr(publisher, "PLATFORMS", plats)
    return plats


def post_rows(vid):
    return {r["platform"]: r for r in db.query("SELECT * FROM posts WHERE video_id=?", (vid,))}


def test_publish_all_ok(fakes):
    vid = make_video(make_campaign(platforms=["youtube", "tiktok"]))
    publisher.publish(vid)
    assert db.one("SELECT status FROM videos WHERE id=?", (vid,))["status"] == "posted"
    assert post_rows(vid)["youtube"]["url"] == "https://example.com/v"
    yt = fakes["youtube"].calls[0]
    assert "#Shorts" in yt["description"] and yt["ai_label"] is True
    assert fakes["tiktok"].calls[0]["caption"] == "A title #one #two"


def test_publish_failure_retries_then_gives_up(fakes):
    fakes["tiktok"].behaviour = "boom"
    vid = make_video(make_campaign(platforms=["youtube", "tiktok"]))
    publisher.publish(vid)
    assert db.one("SELECT status FROM videos WHERE id=?", (vid,))["status"] == "retrying"
    for _ in range(2):
        publisher.publish(vid)
    rows = post_rows(vid)
    assert rows["tiktok"]["attempts"] == 3 and rows["tiktok"]["status"] == "failed"
    assert len(fakes["youtube"].calls) == 1  # posted platforms are never re-posted
    assert db.one("SELECT status FROM videos WHERE id=?", (vid,))["status"] == "partial"


def test_unconfirmed_is_not_retried(fakes):
    fakes["instagram"].behaviour = "unconfirmed"
    vid = make_video(make_campaign(platforms=["instagram"]))
    publisher.publish(vid)
    publisher.publish(vid)
    assert len(fakes["instagram"].calls) == 1
    assert db.one("SELECT status FROM videos WHERE id=?", (vid,))["status"] == "check"


def test_logged_out_marks_account_and_stops(fakes):
    fakes["youtube"].behaviour = "logged_out"
    publisher.account_status("youtube", "connected")
    vid = make_video(make_campaign(platforms=["youtube"]))
    publisher.publish(vid)
    assert db.one("SELECT status FROM accounts WHERE platform='youtube'")["status"] == "not_connected"
    assert db.one("SELECT status FROM videos WHERE id=?", (vid,))["status"] == "post_failed"


def test_daily_cap_holds_automatic_posts(fakes):
    settings.update({"max_posts_per_day": 1})
    vid = make_video(make_campaign(platforms=["youtube", "tiktok"]))
    publisher.publish(vid)
    assert len(fakes["tiktok"].calls) == 0
    publisher.publish(vid, manual=True)  # manual "Post now" ignores the cap
    assert len(fakes["tiktok"].calls) == 1


# ---------- autopilot tick ----------

def test_tick_does_nothing_when_paused():
    make_campaign()
    scheduler.tick()
    assert db.query("SELECT * FROM videos") == []


def test_tick_fills_buffer_and_posts_when_due():
    settings.update({"autopilot": True})
    cid = make_campaign(review=False, buffer=2)
    scheduler.tick()
    assert db.one("SELECT COUNT(*) n FROM videos WHERE status='queued'")["n"] == 1  # one at a time
    assert db.one("SELECT next_post_at FROM campaigns WHERE id=?", (cid,))["next_post_at"] is not None

    db.execute("DELETE FROM videos")
    vid = make_video(cid, "ready")
    db.execute("UPDATE campaigns SET next_post_at=? WHERE id=?", (db.now() - 5, cid))
    scheduler.tick()
    assert scheduler.post_q.get_nowait()[0] == vid
    assert db.one("SELECT next_post_at FROM campaigns WHERE id=?", (cid,))["next_post_at"] > db.now()


def test_review_mode_only_posts_approved():
    settings.update({"autopilot": True})
    cid = make_campaign(review=True, buffer=1)
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
    db.execute("INSERT INTO posts (video_id, platform, status, attempts, updated_at) VALUES (?, 'tiktok', 'posting', 1, ?)", (vid, db.now()))
    scheduler.recover()
    assert post_rows(vid)["tiktok"]["status"] == "unconfirmed"
    assert scheduler.post_q.empty()
