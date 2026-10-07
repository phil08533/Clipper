"""App settings, campaign defaults and built-in prompt templates."""
import json

from . import db

DEFAULT_SETTINGS = {
    "autopilot": False,
    # Language model (script writing)
    "llm_provider": "ollama",            # ollama | openai (any OpenAI-compatible server: LM Studio, llama.cpp, vLLM)
    "llm_url": "http://127.0.0.1:11434",
    "llm_model": "llama3.1:8b",
    "llm_temperature": 0.9,
    # Images
    "image_engine": "cards",             # cards (no AI, styled backgrounds) | comfyui | a1111 — start simple, switch once ComfyUI is installed
    "image_url": "http://127.0.0.1:8188",
    "comfy_checkpoint": "sd_xl_base_1.0.safetensors",
    "comfy_workflow_path": "",           # optional custom API-format workflow JSON
    "image_width": 768,
    "image_height": 1344,
    "image_steps": 25,
    "negative_prompt": "text, watermark, logo, signature, blurry, low quality, deformed, extra fingers",
    # Animation (image-to-video through ComfyUI)
    "animate_mode": "off",               # off | hook (first scene only) | all
    "video_model": "ltx",                # ltx (fast) | wan22 (better, slower)
    "video_url": "http://127.0.0.1:8188",
    "ltx_checkpoint": "ltx-video-2b-v0.9.5.safetensors",
    "ltx_text_encoder": "t5xxl_fp8_e4m3fn_scaled.safetensors",
    "wan_model": "wan2.2_ti2v_5B_fp16.safetensors",
    "wan_text_encoder": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
    "wan_vae": "wan2.2_vae.safetensors",
    "video_workflow_path": "",           # optional custom API-format image-to-video workflow
    # Voice
    "tts_engine": "kokoro",              # kokoro | piper | system | none
    "kokoro_voice": "am_michael",
    "piper_model": "",                   # path to a Piper .onnx voice
    "tts_speed": 1.05,
    # Video
    "ffmpeg_path": "ffmpeg",
    "ffprobe_path": "ffprobe",
    "caption_font": "Arial",
    "fps": 30,
    # Posting
    "browser_channel": "chrome",         # chrome | msedge | chromium
    "headless": False,
    "max_posts_per_account": 6,          # safety cap: posts per account per day
    "parallel_uploads": 2,               # accounts that may upload at the same time
    "session_check_hours": 12,           # re-check each account's sign-in this often (0 = only when posting)
    "delete_after_days": 14,             # delete video files this long after posting (0 = keep)
    "open_browser_on_start": True,
}

DEFAULT_CAMPAIGN = {
    "niche": "",
    "prompt_id": None,
    "topics": [],                        # empty = the model picks fresh topics in the niche
    "duration": 45,                      # target seconds
    "scenes": 6,
    "visual_style": "cinematic, dramatic lighting, highly detailed, 35mm photo",
    "caption_words": 3,
    "caption_position": "middle",        # middle | lower
    "caption_uppercase": True,
    "music_dir": "",
    "music_volume": 0.12,
    "accounts": [],                      # account ids to post to
    "schedule_mode": "random",           # random | even
    "posts_per_day": 2,                  # even mode
    "posts_min": 1,                      # random mode: posts per day varies between min and max
    "posts_max": 3,
    "min_gap_minutes": 120,              # random mode: minimum spacing between posts
    "window_start": 9,                   # local hour
    "window_end": 21,
    "days": [0, 1, 2, 3, 4, 5, 6],       # Monday = 0
    "jitter_minutes": 20,
    "review": True,                      # hold videos for approval before posting
    "buffer": 2,                         # videos to keep generated ahead of schedule
    "youtube_visibility": "public",      # public | unlisted | private
    "ai_label": True,                    # tick each platform's AI-generated disclosure
    "extra_hashtags": "",
    "voice": "",                         # Kokoro voice for this campaign ("" = the one in Settings)
    "series_bible": "",                  # non-empty = episodic series; previous episodes are fed back in
    "preset": "",                        # which ready-made workflow this campaign started from
}

DEFAULT_PROMPTS = [
    ("Surprising facts", """Write a short-form video script about one surprising, little-known fact related to {niche}.
Open with a hook in the first sentence that makes the viewer stop scrolling.
Explain the fact clearly, add one vivid detail, and end with a question that invites comments.
Tone: curious, confident, conversational. No filler, no "in this video"."""),
    ("Mini story", """Write a gripping micro-story set in the world of {niche}.
Start in the middle of the action. Build tension quickly and land a twist in the last scene.
Use plain, punchy sentences that read well out loud."""),
    ("History in 45 seconds", """Tell a true, specific story from history related to {niche}.
Name the people, place and year. Hook first, then the events in order, then why it still matters today.
Stay factual; do not invent quotes or numbers."""),
    ("Quick tips", """Give three practical, specific tips about {niche} that most people don't know.
Hook with the problem the tips solve. Each tip gets its own scene. Finish with a one-line takeaway."""),
]


def get_all():
    out = dict(DEFAULT_SETTINGS)
    for row in db.query("SELECT key, value FROM settings"):
        if row["key"] in DEFAULT_SETTINGS:
            out[row["key"]] = json.loads(row["value"])
    return out


def get(key):
    return get_all()[key]


def update(values):
    for k, v in values.items():
        if k not in DEFAULT_SETTINGS:
            continue
        default = DEFAULT_SETTINGS[k]
        # Coerce to the default's type so the UI can send strings safely.
        if isinstance(default, bool):
            v = v in (True, "true", "1", 1, "on")
        elif isinstance(default, int):
            v = int(float(v))
        elif isinstance(default, float):
            v = float(v)
        else:
            v = "" if v is None else str(v)
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (k, json.dumps(v)))
    return get_all()


def campaign_config(raw):
    cfg = dict(DEFAULT_CAMPAIGN)
    cfg.update({k: v for k, v in (raw or {}).items() if k in DEFAULT_CAMPAIGN})
    return cfg


def seed():
    if not db.one("SELECT id FROM prompts LIMIT 1"):
        for name, body in DEFAULT_PROMPTS:
            db.execute("INSERT INTO prompts (name, body, created_at, updated_at) VALUES (?,?,?,?)",
                       (name, body, db.now(), db.now()))
