"""HTTP API + static UI. Bound to localhost only."""
import datetime
import json
import shutil
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db, health, presets, publisher, scheduler, settings as settings_mod
from .pipeline import llm, script

WEB = Path(__file__).resolve().parent / "web"
app = FastAPI(title="Clipper", docs_url=None, redoc_url=None)


def _404(what="Not found"):
    raise HTTPException(404, what)


def _video_out(v):
    v = dict(v)
    v["hashtags"] = db.loads(v["hashtags"], [])
    v["script"] = db.loads(v.get("script"), None)
    has_file = (db.VIDEOS_DIR / str(v["id"]) / "final.mp4").is_file()
    stamp = int(v["updated_at"])
    v["video_url"] = f"/media/{v['id']}/final.mp4?v={stamp}" if has_file else None
    v["thumb_url"] = f"/media/{v['id']}/thumb.jpg?v={stamp}" if has_file else None
    return v


def _accounts_brief(ids):
    if not ids:
        return []
    rows = {a["id"]: a for a in db.query(f"SELECT id, platform, label, status FROM accounts WHERE id IN ({','.join('?' * len(ids))})", ids)}
    return [rows[i] for i in ids if i in rows]


def _campaign_out(c):
    c = dict(c)
    c["config"] = settings_mod.campaign_config(db.loads(c["config"], {}))
    c["accounts"] = _accounts_brief(c["config"]["accounts"])
    plan = db.loads(c.pop("schedule_plan", None), None) or {}
    c["upcoming"] = ([c["next_post_at"]] if c["next_post_at"] else []) + plan.get("times", [])
    c["counts"] = {r["status"]: r["n"] for r in db.query(
        "SELECT status, COUNT(*) n FROM videos WHERE campaign_id=? GROUP BY status", (c["id"],))}
    return c


def _attention():
    """Accounts used by active campaigns that can't post right now."""
    in_use = scheduler.accounts_in_use()
    return [a for a in db.query("SELECT id, platform, label, status, note FROM accounts WHERE status IN ('not_connected','error') ORDER BY label")
            if a["id"] in in_use]


# ---------- overview ----------

@app.get("/api/overview")
def overview():
    s = settings_mod.get_all()
    day = db.now() - 86400
    week = db.now() - 7 * 86400
    stat = lambda sql, *a: db.one(sql, a)["n"]  # noqa: E731
    return {
        "autopilot": s["autopilot"],
        "worker": scheduler.state,
        "posted_today": stat("SELECT COUNT(*) n FROM posts WHERE status='posted' AND updated_at>=?",
                             datetime.datetime.combine(datetime.date.today(), datetime.time()).timestamp()),
        "account_cap": s["max_posts_per_account"],
        "accounts": db.one("SELECT COUNT(*) n FROM accounts")["n"],
        "attention": _attention(),
        "stats": {
            "posted_7d": stat("SELECT COUNT(*) n FROM posts WHERE status='posted' AND updated_at>=?", week),
            "ready": stat("SELECT COUNT(*) n FROM videos WHERE status IN ('ready','approved')"),
            "review": stat("SELECT COUNT(*) n FROM videos WHERE status='needs_review'"),
            "failed_24h": stat("SELECT COUNT(*) n FROM logs WHERE level='error' AND ts>=?", day),
        },
        "campaigns": [{"id": c["id"], "name": c["name"], "enabled": c["enabled"], "next_post_at": c["next_post_at"],
                       "accounts": c["accounts"], "schedule_mode": c["config"]["schedule_mode"]}
                      for c in map(_campaign_out, db.query("SELECT * FROM campaigns ORDER BY name"))],
        "recent": [_video_out(v) for v in db.query("SELECT * FROM videos ORDER BY id DESC LIMIT 6")],
        "activity": db.query("SELECT * FROM logs ORDER BY id DESC LIMIT 12"),
    }


@app.get("/api/health")
def get_health():
    return health.run()


@app.post("/api/autopilot")
def set_autopilot(body: dict = Body(...)):
    on = bool(body.get("on"))
    settings_mod.update({"autopilot": on})
    if on:
        db.execute("UPDATE campaigns SET next_post_at=NULL, schedule_plan=NULL")  # schedule fresh from now
    db.log("info", "autopilot", "Autopilot started" if on else "Autopilot paused")
    return {"autopilot": on}


# ---------- campaigns ----------

@app.get("/api/campaigns")
def list_campaigns():
    return [_campaign_out(c) for c in db.query("SELECT * FROM campaigns ORDER BY name")]


@app.get("/api/campaigns/defaults")
def campaign_defaults():
    return settings_mod.DEFAULT_CAMPAIGN


@app.get("/api/presets")
def list_presets():
    return presets.summary()


@app.post("/api/presets/{key}/apply")
def apply_preset(key: str):
    """Full campaign config for a preset, creating its prompt if it doesn't exist yet."""
    p = next((x for x in presets.summary() if x["key"] == key), None) or _404("Unknown preset")
    row = db.one("SELECT id FROM prompts WHERE name=?", (p["prompt_name"],))
    pid = row["id"] if row else db.execute("INSERT INTO prompts (name, body, created_at, updated_at) VALUES (?,?,?,?)",
                                           (p["prompt_name"], p["prompt"], db.now(), db.now()))
    cfg = settings_mod.campaign_config({**p["config"], "prompt_id": pid, "preset": key})
    return {"name": p["name"], "config": cfg}


@app.post("/api/campaigns")
def create_campaign(body: dict = Body(...)):
    name = str(body.get("name") or "Untitled campaign").strip()[:120]
    cfg = settings_mod.campaign_config(body.get("config"))
    if not cfg["prompt_id"]:
        first = db.one("SELECT id FROM prompts ORDER BY name LIMIT 1")
        cfg["prompt_id"] = first["id"] if first else None
    cid = db.execute("INSERT INTO campaigns (name, enabled, config, created_at, updated_at) VALUES (?,?,?,?,?)",
                     (name, int(bool(body.get("enabled"))), json.dumps(cfg), db.now(), db.now()))
    return _campaign_out(db.one("SELECT * FROM campaigns WHERE id=?", (cid,)))


@app.get("/api/campaigns/{cid}")
def get_campaign(cid: int):
    return _campaign_out(db.one("SELECT * FROM campaigns WHERE id=?", (cid,)) or _404())


@app.put("/api/campaigns/{cid}")
def update_campaign(cid: int, body: dict = Body(...)):
    c = db.one("SELECT * FROM campaigns WHERE id=?", (cid,)) or _404()
    name = str(body.get("name", c["name"])).strip()[:120] or c["name"]
    cfg = settings_mod.campaign_config(body["config"]) if "config" in body else db.loads(c["config"], {})
    enabled = int(bool(body.get("enabled", c["enabled"])))
    db.execute("UPDATE campaigns SET name=?, enabled=?, config=?, next_post_at=NULL, schedule_plan=NULL, updated_at=? WHERE id=?",
               (name, enabled, json.dumps(cfg), db.now(), cid))
    return _campaign_out(db.one("SELECT * FROM campaigns WHERE id=?", (cid,)))


@app.delete("/api/campaigns/{cid}")
def delete_campaign(cid: int):
    db.execute("DELETE FROM campaigns WHERE id=?", (cid,))
    return {"ok": True}


@app.post("/api/campaigns/{cid}/generate")
def generate_now(cid: int, body: dict = Body(default={})):
    db.one("SELECT id FROM campaigns WHERE id=?", (cid,)) or _404()
    vid = scheduler.new_video(cid, str(body.get("topic") or "").strip())
    return {"video_id": vid}


# ---------- prompts ----------

@app.get("/api/prompts")
def list_prompts():
    return db.query("SELECT * FROM prompts ORDER BY name")


@app.post("/api/prompts")
def create_prompt(body: dict = Body(...)):
    pid = db.execute("INSERT INTO prompts (name, body, created_at, updated_at) VALUES (?,?,?,?)",
                     (str(body.get("name") or "New prompt")[:120], str(body.get("body") or ""), db.now(), db.now()))
    return db.one("SELECT * FROM prompts WHERE id=?", (pid,))


@app.put("/api/prompts/{pid}")
def update_prompt(pid: int, body: dict = Body(...)):
    db.one("SELECT id FROM prompts WHERE id=?", (pid,)) or _404()
    db.execute("UPDATE prompts SET name=?, body=?, updated_at=? WHERE id=?",
               (str(body.get("name") or "Untitled")[:120], str(body.get("body") or ""), db.now(), pid))
    return db.one("SELECT * FROM prompts WHERE id=?", (pid,))


@app.delete("/api/prompts/{pid}")
def delete_prompt(pid: int):
    db.execute("DELETE FROM prompts WHERE id=?", (pid,))
    return {"ok": True}


@app.post("/api/prompts/test")
def test_prompt(body: dict = Body(...)):
    try:
        return script.generate(settings_mod.get_all(), str(body.get("body") or ""), str(body.get("niche") or ""),
                               str(body.get("topic") or ""), int(body.get("scenes") or 5), int(body.get("duration") or 40))
    except llm.LLMError as e:
        raise HTTPException(502, str(e)) from e


# ---------- videos ----------

@app.get("/api/videos")
def list_videos(status: str = "", campaign_id: int = 0, limit: int = 200):
    sql, args = "SELECT * FROM videos WHERE 1=1", []
    if status:
        sql += f" AND status IN ({','.join('?' * len(status.split(',')))})"
        args += status.split(",")
    if campaign_id:
        sql += " AND campaign_id=?"
        args.append(campaign_id)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(min(limit, 1000))
    return [_video_out(v) for v in db.query(sql, args)]


@app.get("/api/videos/{vid}")
def get_video(vid: int):
    v = db.one("SELECT * FROM videos WHERE id=?", (vid,)) or _404()
    out = _video_out(v)
    out["posts"] = db.query("SELECT * FROM posts WHERE video_id=?", (vid,))
    c = db.one("SELECT name, config FROM campaigns WHERE id=?", (v["campaign_id"],))
    out["campaign_name"] = c["name"] if c else "(deleted)"
    targets = settings_mod.campaign_config(db.loads(c["config"], {}) if c else {})["accounts"]
    # Show every account the campaign posts to, plus any account it already posted to before a change.
    extra = [p["account_id"] for p in out["posts"] if p["account_id"] not in targets]
    out["targets"] = _accounts_brief(targets + extra)
    return out


@app.put("/api/videos/{vid}")
def update_video(vid: int, body: dict = Body(...)):
    v = db.one("SELECT * FROM videos WHERE id=?", (vid,)) or _404()
    tags = body.get("hashtags", db.loads(v["hashtags"], []))
    if isinstance(tags, str):
        tags = tags.replace(",", " ").split()
    tags = [t.lstrip("#") for t in tags if t.strip("#")]
    db.execute("UPDATE videos SET title=?, description=?, hashtags=?, updated_at=? WHERE id=?",
               (str(body.get("title", v["title"]))[:100], str(body.get("description", v["description"])),
                json.dumps(tags), db.now(), vid))
    return get_video(vid)


@app.post("/api/videos/{vid}/{action}")
def video_action(vid: int, action: str, body: dict = Body(default={})):
    db.one("SELECT id FROM videos WHERE id=?", (vid,)) or _404()
    if action == "approve":
        db.execute("UPDATE videos SET status='approved', updated_at=? WHERE id=?", (db.now(), vid))
    elif action == "reject":
        db.execute("UPDATE videos SET status='rejected', updated_at=? WHERE id=?", (db.now(), vid))
    elif action == "regenerate":
        db.execute("DELETE FROM posts WHERE video_id=?", (vid,))
        db.execute("UPDATE videos SET status='queued', title='', error=NULL, posted_at=NULL, updated_at=? WHERE id=?", (db.now(), vid))
        scheduler.enqueue_generation(vid)
    elif action == "post":
        ids = [int(a) for a in body.get("accounts") or []] or None
        if ids:  # an explicit re-post to an account resets its attempts
            for aid in ids:
                db.execute("UPDATE posts SET status='pending', attempts=0, error=NULL, next_attempt_at=NULL "
                           "WHERE video_id=? AND account_id=? AND status!='posted'", (vid, aid))
        scheduler.enqueue_post(vid, ids, manual=True)
    elif action == "mark_posted":
        db.execute("UPDATE posts SET status='posted', error=NULL, updated_at=? WHERE video_id=? AND account_id=?",
                   (db.now(), vid, int(body.get("account_id") or 0)))
        publisher.refresh_video_status(vid)
    else:
        _404("Unknown action")
    return get_video(vid)


@app.delete("/api/videos/{vid}")
def delete_video(vid: int):
    shutil.rmtree(db.VIDEOS_DIR / str(vid), ignore_errors=True)
    db.execute("DELETE FROM posts WHERE video_id=?", (vid,))
    db.execute("DELETE FROM videos WHERE id=?", (vid,))
    return {"ok": True}


# ---------- accounts ----------

def _account_out(a):
    a = dict(a)
    a["posted"] = db.one("SELECT COUNT(*) n FROM posts WHERE account_id=? AND status='posted'", (a["id"],))["n"]
    a["posted_today"] = publisher.posted_today(a["id"])
    a["campaigns"] = [c["name"] for c in db.query("SELECT name, config FROM campaigns ORDER BY name")
                      if a["id"] in db.loads(c["config"], {}).get("accounts", [])]
    return a


@app.get("/api/accounts")
def accounts():
    return [_account_out(a) for a in db.query("SELECT * FROM accounts ORDER BY platform, label")]


@app.post("/api/accounts")
def add_account(body: dict = Body(...)):
    try:
        return _account_out(publisher.create_account(str(body.get("platform")), str(body.get("label") or "")))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.put("/api/accounts/{aid}")
def rename_account(aid: int, body: dict = Body(...)):
    publisher.get_account(aid) or _404()
    label = str(body.get("label") or "").strip()[:80]
    if label:
        db.execute("UPDATE accounts SET label=? WHERE id=?", (label, aid))
    return _account_out(publisher.get_account(aid))


@app.delete("/api/accounts/{aid}")
def remove_account(aid: int):
    publisher.get_account(aid) or _404()
    publisher.delete_account(aid)
    return {"ok": True}


@app.post("/api/accounts/check-all")
def check_all_accounts():
    return {"queued": scheduler.check_sessions(force=True)}


@app.post("/api/accounts/{aid}/{action}")
def account_action(aid: int, action: str):
    publisher.get_account(aid) or _404()
    fn = {"connect": publisher.connect_account, "check": publisher.check_account,
          "disconnect": publisher.disconnect_account}.get(action) or _404("Unknown action")
    publisher.run_in_thread(fn, aid)
    return {"ok": True}


# ---------- logs & settings ----------

@app.get("/api/logs")
def logs(level: str = "", limit: int = 300, video_id: int = 0):
    sql, args = "SELECT * FROM logs WHERE 1=1", []
    if level:
        sql += " AND level=?"
        args.append(level)
    if video_id:
        sql += " AND video_id=?"
        args.append(video_id)
    return db.query(sql + " ORDER BY id DESC LIMIT ?", (*args, min(limit, 2000)))


@app.get("/api/settings")
def get_settings():
    return settings_mod.get_all()


@app.put("/api/settings")
def put_settings(body: dict = Body(...)):
    body.pop("autopilot", None)
    try:
        return settings_mod.update(body)
    except (TypeError, ValueError) as e:
        raise HTTPException(400, f"Invalid value: {e}") from e


@app.get("/api/voices")
def voices():
    from .pipeline import tts
    return [{"id": v, "label": label} for v, label in tts.KOKORO_VOICES]


@app.get("/api/llm/models")
def llm_models():
    try:
        return llm.list_models(settings_mod.get_all())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, str(e)) from e


# ---------- static ----------

db.init()
app.mount("/media", StaticFiles(directory=db.VIDEOS_DIR), name="media")
app.mount("/screenshots", StaticFiles(directory=db.SHOTS_DIR), name="screenshots")
app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")
