"""ffmpeg assembly: animated scenes + voice + captions + optional music -> 1080x1920 MP4."""
import math
import random
import subprocess
from pathlib import Path

W, H = 1080, 1920
AUDIO_ARGS = ["-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "160k"]


class RenderError(RuntimeError):
    pass


def run(settings, args, cwd=None, binary="ffmpeg_path"):
    cmd = [settings[binary]] + [str(a) for a in args]
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=1800)
    except FileNotFoundError as e:
        raise RenderError(f"{settings[binary]} not found. Install ffmpeg or set its path in Settings.") from e
    if r.returncode != 0:
        raise RenderError(f"{Path(cmd[0]).name} failed: {r.stderr.strip()[-800:]}")
    return r.stdout


def probe_duration(settings, path):
    out = run(settings, ["-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path],
              binary="ffprobe_path")
    return float(out.strip())


def video_args(settings):
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", settings["fps"]]


# ---------- captions ----------

def _ts(t):
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _clean(text):
    return text.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ")


def build_captions(settings, cfg, timed_scenes, path):
    """timed_scenes: [(start, speech_duration, narration)]."""
    align, margin = (5, 0) if cfg["caption_position"] == "middle" else (2, 480)
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{settings['caption_font']},86,&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,-1,0,0,0,100,100,1,0,1,7,3,{align},90,90,{margin},1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    n = max(1, int(cfg["caption_words"]))
    for start, dur, narration in timed_scenes:
        words = narration.split()
        chunks = [" ".join(words[i:i + n]) for i in range(0, len(words), n)]
        total = sum(len(c) + 2 for c in chunks) or 1
        t = start
        for c in chunks:
            d = dur * (len(c) + 2) / total
            text = _clean(c.upper() if cfg["caption_uppercase"] else c)
            lines.append(f"Dialogue: 0,{_ts(t)},{_ts(t + d)},Default,,0,0,0,,"
                         "{\\fscx88\\fscy88\\t(0,90,\\fscx100\\fscy100)}" + text)
            t += d
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------- scenes ----------

def _motion(kind, frames):
    f = max(frames, 1)
    centre = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    if kind == "in":
        return f"z='1+0.12*on/{f}':{centre}"
    if kind == "out":
        return f"z='1.12-0.12*on/{f}':{centre}"
    if kind == "left":
        return f"z='1.1':x='(iw-iw/zoom)*(1-on/{f})':y='ih/2-(ih/zoom/2)'"
    return f"z='1.1':x='(iw-iw/zoom)*on/{f}':y='ih/2-(ih/zoom/2)'"


def render_scene(settings, image, voice, duration, out, motion):
    fps = settings["fps"]
    frames = math.ceil(duration * fps)
    vf = (f"scale={int(W * 1.5)}:{int(H * 1.5)}:force_original_aspect_ratio=increase,"
          f"crop={int(W * 1.5)}:{int(H * 1.5)},"
          f"zoompan={_motion(motion, frames)}:d={frames}:s={W}x{H}:fps={fps},setsar=1")
    audio = ["-i", voice] if voice else ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    run(settings, ["-y", "-i", image, *audio, "-vf", vf, "-af", "apad", "-t", f"{duration:.3f}",
                   "-map", "0:v", "-map", "1:a", *video_args(settings), *AUDIO_ARGS, out])


def render_clip_scene(settings, frames_dir, clip_fps, voice, duration, out):
    """An animated scene: the AI clip (slowed slightly if short), then its last frame held, all under a gentle zoom
    so the hold never looks frozen. Upscales the clip to full 1080x1920."""
    fps = settings["fps"]
    n = len(list(Path(frames_dir).glob("f_*.png")))
    clip_len = n / clip_fps
    slow = min(1.35, max(1.0, duration / clip_len))
    frames = math.ceil(duration * fps)
    vf = (f"scale={int(W * 1.5)}:{int(H * 1.5)}:force_original_aspect_ratio=increase:flags=lanczos,"
          f"crop={int(W * 1.5)}:{int(H * 1.5)},setpts={slow:.3f}*PTS,fps={fps},"
          f"tpad=stop_mode=clone:stop_duration={duration:.3f},"
          f"zoompan=z='1+0.06*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps},setsar=1")
    audio = ["-i", voice] if voice else ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    run(settings, ["-y", "-framerate", clip_fps, "-i", Path(frames_dir) / "f_%05d.png", *audio, "-vf", vf, "-af", "apad",
                   "-t", f"{duration:.3f}", "-map", "0:v", "-map", "1:a", *video_args(settings), *AUDIO_ARGS, out])


def adjust_voice(settings, src, out):
    speed = min(max(float(settings["tts_speed"]), 0.5), 2.0)
    run(settings, ["-y", "-i", src, "-af", f"atempo={speed:.3f}", "-ar", "44100", "-ac", "2", out])


def pick_music(music_dir):
    if not music_dir:
        return None
    d = Path(music_dir).expanduser()
    if not d.is_dir():
        return None
    tracks = [p for p in d.iterdir() if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg", ".flac")]
    return random.choice(tracks) if tracks else None


def finalize(settings, cfg, workdir, scene_files, total):
    workdir = Path(workdir)
    (workdir / "scenes.txt").write_text("".join(f"file '{Path(f).name}'\n" for f in scene_files), encoding="utf-8")
    run(settings, ["-y", "-f", "concat", "-safe", "0", "-i", "scenes.txt", "-c", "copy", "body.mp4"], cwd=workdir)

    music = pick_music(cfg["music_dir"])
    # Captions file is referenced by relative name (cwd=workdir) to avoid Windows drive-letter escaping in filters.
    if music:
        vol = float(cfg["music_volume"])
        fade = max(total - 1.5, 0)
        fc = (f"[0:v]subtitles=captions.ass[v];"
              f"[1:a]volume={vol:.3f},afade=t=out:st={fade:.2f}:d=1.5[m];"
              f"[0:a][m]amix=inputs=2:duration=first,volume=2[a]")
        args = ["-y", "-i", "body.mp4", "-stream_loop", "-1", "-i", str(music.resolve()), "-filter_complex", fc,
                "-map", "[v]", "-map", "[a]"]
    else:
        args = ["-y", "-i", "body.mp4", "-vf", "subtitles=captions.ass", "-map", "0:v", "-map", "0:a"]
    run(settings, [*args, "-t", f"{total:.3f}", *video_args(settings), *AUDIO_ARGS,
                   "-movflags", "+faststart", "final.mp4"], cwd=workdir)
    run(settings, ["-y", "-ss", "0.8", "-i", "final.mp4", "-frames:v", "1", "-vf", "scale=360:-2", "thumb.jpg"], cwd=workdir)
    return workdir / "final.mp4"
