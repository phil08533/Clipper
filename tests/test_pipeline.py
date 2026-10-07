"""End-to-end pipeline tests with a fake ComfyUI and a fake script model. Needs ffmpeg; skipped otherwise.

Run: python -m pytest -q
"""
import io
import json
import shutil
import subprocess
import sys
import threading
import types
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
from PIL import Image

from clipper import db, settings
from clipper.pipeline import animate, llm, produce, tts

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")

SCRIPT = {"topic": "Octopus hearts", "title": "Octopuses Have Three Hearts", "description": "Why octopus blood is blue.",
          "hashtags": ["octopus", "ocean"],
          "scenes": [{"narration": "An octopus has three hearts, and one stops when it swims.", "visual": "octopus on a reef",
                      "motion": "tentacles drift, camera pushes in"},
                     {"narration": "Its blood is blue because it uses copper.", "visual": "blue water swirling"}]}


class FakeComfy(BaseHTTPRequestHandler):
    graphs, uploads, fail = [], [], False
    frames = 33

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/upload/image":
            FakeComfy.uploads.append(data)
            return self._json({"name": "clipper_upload.png", "subfolder": "", "type": "input"})
        if self.path == "/prompt":
            FakeComfy.graphs.append(json.loads(data)["prompt"])
            return self._json({"prompt_id": "p1"})
        return self._json({})

    def do_GET(self):
        url = urlparse(self.path)
        if url.path.startswith("/history/"):
            if FakeComfy.fail:
                return self._json({"p1": {"status": {"status_str": "error", "completed": False, "messages": [
                    ["execution_error", {"node_type": "SamplerCustom", "exception_message": "CUDA out of memory"}]]}}})
            imgs = [{"filename": f"f{i}.png", "subfolder": "", "type": "temp"} for i in range(FakeComfy.frames)]
            return self._json({"p1": {"status": {"status_str": "success", "completed": True}, "outputs": {"12": {"images": imgs}}}})
        if url.path == "/view":
            i = int(parse_qs(url.query)["filename"][0][1:-4])
            buf = io.BytesIO()
            Image.new("RGB", (512, 896), (i * 7 % 255, 80, 160)).save(buf, "PNG")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(buf.getvalue())
            return
        if url.path == "/object_info":
            files = {"ckpt_name": [["ltx-video-2b-v0.9.5.safetensors"]], "clip_name": [["t5xxl_fp8_e4m3fn_scaled.safetensors"], {}]}
            info = {n: {"input": {"required": {}}} for n in animate.MODELS["ltx"]["nodes"]}
            info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"] = files["ckpt_name"]
            info["CLIPLoader"]["input"]["required"]["clip_name"] = ["COMBO", {"options": files["clip_name"][0]}]
            return self._json(info)
        self._json({}, 404)

    def log_message(self, *a):
        pass


@pytest.fixture
def env(tmp_path, monkeypatch):
    for name, sub in [("DATA_DIR", ""), ("VIDEOS_DIR", "videos"), ("PROFILES_DIR", "profiles"), ("SHOTS_DIR", "shots")]:
        monkeypatch.setattr(db, name, tmp_path / sub if sub else tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init()
    settings.seed()
    monkeypatch.setattr(llm, "chat", lambda *a, **k: json.dumps(SCRIPT))
    srv = HTTPServer(("127.0.0.1", 0), FakeComfy)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    FakeComfy.graphs, FakeComfy.uploads, FakeComfy.fail = [], [], False
    settings.update({"image_engine": "cards", "tts_engine": "none", "animate_mode": "hook",
                     "video_url": f"http://127.0.0.1:{srv.server_port}", "image_width": 256, "image_height": 448})
    cid = db.execute("INSERT INTO campaigns (name, enabled, config, created_at, updated_at) VALUES ('C',1,?,?,?)",
                     (json.dumps(settings.campaign_config({"scenes": 2, "review": False})), db.now(), db.now()))
    yield cid
    srv.shutdown()


def make_video(cid):
    return db.execute("INSERT INTO videos (campaign_id, status, created_at, updated_at) VALUES (?, 'queued', ?, ?)",
                      (cid, db.now(), db.now()))


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout
    return float(out)


def test_hook_scene_is_animated_with_ltx(env):
    vid = make_video(env)
    produce.produce(vid)
    v = db.one("SELECT * FROM videos WHERE id=?", (vid,))
    assert v["status"] == "ready", v["error"]
    assert len(FakeComfy.graphs) == 1 and len(FakeComfy.uploads) == 1  # only the first scene is animated
    g = FakeComfy.graphs[0]
    by_type = {n["class_type"]: n["inputs"] for n in g.values()}
    assert by_type["LoadImage"]["image"] == "clipper_upload.png"
    assert by_type["LTXVImgToVideo"]["length"] == 97 and by_type["LTXVImgToVideo"]["width"] % 32 == 0
    assert by_type["CLIPLoader"]["type"] == "ltxv"
    positive = g[by_type["LTXVImgToVideo"]["positive"][0]]["inputs"]["text"]
    assert "tentacles drift" in positive and "octopus on a reef" in positive  # the scene's motion line drives the clip
    final = db.VIDEOS_DIR / str(vid) / "final.mp4"
    assert final.is_file() and abs(duration(final) - v["duration"]) < 0.5
    assert not list((db.VIDEOS_DIR / str(vid)).glob("anim_*"))  # frames cleaned up


def test_wan_graph_shape(env):
    settings.update({"video_model": "wan22", "animate_mode": "all"})
    vid = make_video(env)
    produce.produce(vid)
    assert db.one("SELECT status FROM videos WHERE id=?", (vid,))["status"] == "ready"
    assert len(FakeComfy.graphs) == 2
    by_type = {n["class_type"]: n["inputs"] for n in FakeComfy.graphs[0].values()}
    assert by_type["Wan22ImageToVideoLatent"]["length"] % 4 == 1
    assert by_type["UNETLoader"]["weight_dtype"] == "fp8_e4m3fn"  # fits an 8 GB card
    assert by_type["CLIPLoader"]["type"] == "wan"


def test_failed_animation_falls_back_to_still(env):
    FakeComfy.fail = True
    vid = make_video(env)
    produce.produce(vid)
    assert db.one("SELECT status FROM videos WHERE id=?", (vid,))["status"] == "ready"
    warn = db.one("SELECT message FROM logs WHERE level='warn' AND video_id=?", (vid,))
    assert "CUDA out of memory" in warn["message"] and "still image" in warn["message"]


def test_animation_check_reads_comfy_model_lists(env):
    ok, detail = animate.check(settings.get_all())
    assert ok, detail
    settings.update({"ltx_checkpoint": "missing.safetensors"})
    ok, detail = animate.check(settings.get_all())
    assert not ok and "missing.safetensors" in detail


def test_kokoro_voice_writes_wav(tmp_path, monkeypatch):
    np = pytest.importorskip("numpy")
    calls = []

    class Audio:
        def __init__(self, a):
            self.a = a

        def detach(self):
            return self

        def cpu(self):
            return self

        def numpy(self):
            return self.a

    class KPipeline:
        def __init__(self, lang_code, repo_id=None, device=None):
            calls.append((lang_code, device))

        def __call__(self, text, voice=None, speed=1):
            for _ in range(2):
                yield types.SimpleNamespace(audio=Audio(np.full(12000, 0.25, dtype="float32")))

    monkeypatch.setitem(sys.modules, "kokoro", types.SimpleNamespace(KPipeline=KPipeline))
    monkeypatch.setattr(tts, "_kokoro_cache", {})
    out = tmp_path / "v.wav"
    assert tts.synthesize({"tts_engine": "kokoro", "kokoro_voice": "bm_george", "piper_model": ""}, "Hello there.", out)
    with wave.open(str(out)) as w:
        assert w.getframerate() == 24000 and w.getnframes() == 24000
    assert calls == [("b", "cpu")]  # British voice -> British G2P, on the CPU
