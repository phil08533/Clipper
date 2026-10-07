"""System checks shown on the Overview page."""
import shutil
import subprocess

from . import db, settings as settings_mod
from .pipeline import animate, images, llm, tts


def _ffmpeg(s):
    exe = shutil.which(s["ffmpeg_path"]) or s["ffmpeg_path"]
    try:
        out = subprocess.run([exe, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False, "ffmpeg not found — install it and add it to PATH"
    if " subtitles " not in out:
        return False, "ffmpeg found but built without libass (captions). Use a full build."
    return True, "ffmpeg ready"


def _llm(s):
    try:
        models = llm.list_models(s)
    except Exception:  # noqa: BLE001
        return False, f"Not reachable at {s['llm_url']}"
    if s["llm_model"] not in models and not any(m.split(":")[0] == s["llm_model"] for m in models):
        return False, f"Model “{s['llm_model']}” not installed" + (f" (have: {', '.join(models[:4])})" if models else "")
    return True, s["llm_model"]


def _playwright():
    try:
        import playwright  # noqa: F401
        return True, "Playwright installed"
    except ImportError:
        return False, "pip install playwright"


def run():
    s = settings_mod.get_all()
    checks = [("Video engine", *_ffmpeg(s)), ("Script model", *_llm(s)), ("Image engine", *images.check(s)), ("Animation", *animate.check(s)),
              ("Voice", *tts.check(s)), ("Browser automation", *_playwright()), ("Accounts", *_accounts())]
    return {"checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks]}


def _accounts():
    rows = db.query("SELECT status FROM accounts")
    if not rows:
        return False, "No accounts added yet"
    ok = sum(r["status"] == "connected" for r in rows)
    return ok == len(rows), f"{ok} of {len(rows)} connected"
