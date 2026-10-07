"""HTTP API + static UI. Bound to localhost only."""
import json
import shutil
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db, health, publisher, scheduler, settings as settings_mod
from .pipeline import llm, script
from .uploaders import PLATFORMS

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


def _campaign_out(c):
    c = dict(c)
    c["config"] = settings_mod.campaign_config(db.loads(c["config"], {}))
    c["counts"] = {r["status"]: r["n"] for r in db.query(
        "SELECT status, COUNT(*) n FROM videos WHERE campaign_id=? GROUP BY status", (c["id"],))}
    return c


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
        "posted_today": publisher.posted_today(),
        "daily_cap": s["max_posts_per_day"],
        "stats": {
            "posted_7d": stat("SELECT COUNT(*) n FROM posts WHERE status='posted' AND updated_at>=?", week),
            "ready": stat("SELECT COUNT(*) n FROM videos WHERE status IN ('ready','approved')"),
            "review": stat("SELECT COUNT(*) n FROM videos WHERE status='needs_review'"),
            "failed_24h": stat("SELECT COUNT(*) n FROM logs WHERE level='error' AND ts>=?", day),
        },
        "campaigns": [{"id": c["id"], "name": c["name"], "enabled": bool(c["enabled"]), "next_post_at": c["next_post_at"],
                       "platforms": settings_mod.campaign_config(db.loads(c["config"], {}))["platforms"]}
                      for c in db.query("SELECT * FROM campaigns ORDER BY name")],
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
        db.execute("UPDATE campaigns SET next_post_at=NULL")  # schedule fresh from now
    db.log("info", "autopilot", "Autopilot started" if on else "Autopilot paused")
    return {"autopilot": on}


# ---------- campaigns ----------

@app.get("/api/campaigns")
def list_campaigns():
    return [_campaign_out(c) for c in db.query("SELECT * FROM campaigns ORDER BY name")]


@app.get("/api/campaigns/defaults")
def campaign_defaults():
    return settings_mod.DEFAULT_CAMPAIGN


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
    db.execute("UPDATE campaigns SET name=?, enabled=?, config=?, next_post_at=NULL, updated_at=? WHERE id=?",
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
    out["posts"] = db.query("SELECT * FROM posts WHERE video_id=? ORDER BY platform", (vid,))
    c = db.one("SELECT name, config FROM campaigns WHERE id=?", (v["campaign_id"],))
    out["campaign_name"] = c["name"] if c else "(deleted)"
    out["platforms"] = settings_mod.campaign_config(db.loads(c["config"], {}) if c else {})["platforms"]
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
    v = db.one("SELECT * FROM videos WHERE id=?", (vid,)) or _404()
    if action == "approve":
        db.execute("UPDATE videos SET status='approved', updated_at=? WHERE id=?", (db.now(), vid))
    elif action == "reject":
        db.execute("UPDATE videos SET status='rejected', updated_at=? WHERE id=?", (db.now(), vid))
    elif action == "regenerate":
        db.execute("DELETE FROM posts WHERE video_id=?", (vid,))
        db.execute("UPDATE videos SET status='queued', title='', error=NULL, posted_at=NULL, updated_at=? WHERE id=?", (db.now(), vid))
        scheduler.enqueue_generation(vid)
    elif action == "post":
        platforms = [p for p in body.get("platforms") or [] if p in PLATFORMS] or None
        if platforms:  # an explicit re-post of a platform resets its attempts
            for p in platforms:
                db.execute("UPDATE posts SET status='pending', attempts=0, error=NULL WHERE video_id=? AND platform=? AND status!='posted'", (vid, p))
        scheduler.enqueue_post(vid, platforms, manual=True)
    elif action == "mark_posted":
        p = body.get("platform")
        db.execute("UPDATE posts SET status='posted', error=NULL, updated_at=? WHERE video_id=? AND platform=?", (db.now(), vid, p))
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

@app.get("/api/accounts")
def accounts():
    rows = {a["platform"]: a for a in db.query("SELECT * FROM accounts")}
    out = []
    for key, mod in PLATFORMS.items():
        a = rows.get(key, {"status": "not_connected", "note": None, "checked_at": None})
        out.append({"platform": key, "name": mod.NAME, "status": a["status"], "note": a["note"], "checked_at": a["checked_at"],
                    "posted": db.one("SELECT COUNT(*) n FROM posts WHERE platform=? AND status='posted'", (key,))["n"]})
    return out


@app.post("/api/accounts/{platform}/{action}")
def account_action(platform: str, action: str):
    if platform not in PLATFORMS:
        _404()
    fn = {"connect": publisher.connect_account, "check": publisher.check_account,
          "disconnect": publisher.disconnect_account}.get(action) or _404("Unknown action")
    publisher.run_in_thread(fn, platform)
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
