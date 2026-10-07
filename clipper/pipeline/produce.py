"""Runs one video through the full pipeline: script -> images -> voice -> render."""
import json
import random
import shutil

from .. import db, settings as settings_mod
from . import images, render, script, tts


def _template(cfg):
    row = None
    if cfg.get("prompt_id"):
        row = db.one("SELECT body FROM prompts WHERE id=?", (cfg["prompt_id"],))
    row = row or db.one("SELECT body FROM prompts ORDER BY name LIMIT 1")
    return row["body"] if row else settings_mod.DEFAULT_PROMPTS[0][1]


def _next_topic(campaign, cfg):
    topics = [t.strip() for t in cfg["topics"] if t.strip()]
    if not topics:
        return ""
    idx = campaign["topic_cursor"] % len(topics)
    db.execute("UPDATE campaigns SET topic_cursor=topic_cursor+1 WHERE id=?", (campaign["id"],))
    return topics[idx]


def _series(campaign, cfg, video_id):
    """Previous episodes for an episodic campaign, so the model continues the same story."""
    if not cfg["series_bible"].strip():
        return None
    eps = db.query("SELECT title, script FROM videos WHERE campaign_id=? AND id<? AND script IS NOT NULL "
                   "AND status NOT IN ('failed','rejected') ORDER BY id", (campaign["id"], video_id))
    recent = []
    for e in eps[-6:]:
        scenes = db.loads(e["script"], {}).get("scenes") or []
        synopsis = " … ".join(sc["narration"] for sc in scenes[:1] + scenes[-2:])[:400]
        recent.append((e["title"], synopsis))
    return {"bible": cfg["series_bible"], "number": len(eps) + 1, "episodes": recent}


def produce(video_id):
    video = db.one("SELECT * FROM videos WHERE id=?", (video_id,))
    campaign = db.one("SELECT * FROM campaigns WHERE id=?", (video["campaign_id"],)) if video else None
    if not campaign:
        db.execute("UPDATE videos SET status='failed', error=? WHERE id=?", ("Campaign no longer exists", video_id))
        return
    cfg = settings_mod.campaign_config(db.loads(campaign["config"], {}))
    s = settings_mod.get_all()
    workdir = db.VIDEOS_DIR / str(video_id)
    shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir(parents=True)

    def stage(msg):
        db.execute("UPDATE videos SET error=?, updated_at=? WHERE id=?", (msg, db.now(), video_id))

    db.execute("UPDATE videos SET status='generating', error=NULL, updated_at=? WHERE id=?", (db.now(), video_id))
    try:
        stage("Writing script")
        recent = [r["title"] for r in db.query(
            "SELECT title FROM videos WHERE campaign_id=? AND title!='' ORDER BY id DESC LIMIT 30", (campaign["id"],))]
        topic = video["topic"] or _next_topic(campaign, cfg)
        sc = script.generate(s, _template(cfg), cfg["niche"], topic, int(cfg["scenes"]), int(cfg["duration"]), recent,
                             series=_series(campaign, cfg, video_id))
        tags = sc["hashtags"] + [t.lstrip("#") for t in cfg["extra_hashtags"].replace(",", " ").split() if t.strip("#")]
        db.execute("UPDATE videos SET title=?, description=?, hashtags=?, topic=?, script=?, updated_at=? WHERE id=?",
                   (sc["title"], sc["description"], json.dumps(list(dict.fromkeys(tags))), sc["topic"] or topic,
                    json.dumps(sc), db.now(), video_id))

        timed, scene_files, t = [], [], 0.0
        motions = ["in", "out", "left", "right"]
        random.shuffle(motions)
        n = len(sc["scenes"])
        for i, scene in enumerate(sc["scenes"]):
            stage(f"Scene {i + 1} of {n}: image")
            img = workdir / f"scene_{i}.png"
            images.generate(s, f"{scene['visual']}, {cfg['visual_style']}", img)

            stage(f"Scene {i + 1} of {n}: voice")
            raw, voice = workdir / f"voice_{i}_raw.wav", workdir / f"voice_{i}.wav"
            if tts.synthesize(s, scene["narration"], raw):
                render.adjust_voice(s, raw, voice)
                speech = render.probe_duration(s, voice)
            else:
                voice, speech = None, max(2.5, len(scene["narration"].split()) / 2.6)
            dur = speech + 0.35
            timed.append((t, speech, scene["narration"]))

            stage(f"Scene {i + 1} of {n}: animating")
            clip = workdir / f"scene_{i}.mp4"
            render.render_scene(s, img, voice, dur, clip, motions[i % 4])
            scene_files.append(clip)
            t += dur

        stage("Final render")
        render.build_captions(s, cfg, timed, workdir / "captions.ass")
        render.finalize(s, cfg, workdir, scene_files, t)
        for p in workdir.glob("voice_*_raw.wav"):
            p.unlink()
        status = "needs_review" if cfg["review"] else "ready"
        db.execute("UPDATE videos SET status=?, duration=?, error=NULL, updated_at=? WHERE id=?",
                   (status, round(t, 1), db.now(), video_id))
        db.log("info", "generator", f"Video ready: {sc['title']} ({t:.0f}s)", video_id)
    except Exception as e:  # noqa: BLE001 — any failure marks the video failed and is shown in the UI
        db.execute("UPDATE videos SET status='failed', error=?, updated_at=? WHERE id=?", (str(e)[:2000], db.now(), video_id))
        db.log("error", "generator", f"Generation failed: {e}", video_id)
