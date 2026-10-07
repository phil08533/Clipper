"""Voiceover: Kokoro (most natural), Piper (lighter), or the operating system's built-in voice."""
import subprocess
import sys
import wave
from pathlib import Path

_piper_cache = {}
_kokoro_cache = {}

# Kokoro-82M voices worth using for narration (first letter: a = American, b = British; second: f/m).
KOKORO_VOICES = [
    ("am_michael", "Michael — American male, warm narrator"),
    ("am_fenrir", "Fenrir — American male, deep and dramatic"),
    ("am_puck", "Puck — American male, upbeat"),
    ("af_heart", "Heart — American female, natural and warm"),
    ("af_bella", "Bella — American female, expressive"),
    ("af_nicole", "Nicole — American female, soft and close"),
    ("bm_george", "George — British male, documentary"),
    ("bm_fable", "Fable — British male, storyteller"),
    ("bm_lewis", "Lewis — British male, deep"),
    ("bf_emma", "Emma — British female, clear"),
    ("bf_isabella", "Isabella — British female, warm"),
]
KOKORO_RATE = 24000


class TTSError(RuntimeError):
    pass


def voice_path(setting):
    """The .onnx voice file; accepts the path to its .onnx.json too, since both sit side by side."""
    if not setting:
        return None
    # Paths copied from a terminal often carry shell quotes (e.g. Documents/"GitHub Projects"/...); drop them.
    p = Path(setting.strip().replace('"', "").replace("'", "")).expanduser()
    return p.with_suffix("") if p.name.endswith(".onnx.json") else p


def _piper(text, out, model_path):
    model_path = str(voice_path(model_path) or "")
    if not model_path or not Path(model_path).is_file():
        raise TTSError("Piper voice model not found. Set the .onnx path in Settings > Voice.")
    try:
        from piper.voice import PiperVoice  # type: ignore
    except ImportError as e:
        raise TTSError("piper-tts is not installed (pip install piper-tts).") from e
    voice = _piper_cache.get(model_path)
    if voice is None:
        voice = _piper_cache[model_path] = PiperVoice.load(model_path)
    with wave.open(str(out), "wb") as wf:
        if hasattr(voice, "synthesize_wav"):   # piper-tts >= 1.3
            voice.synthesize_wav(text, wf)
        else:                                  # piper-tts 1.2
            voice.synthesize(text, wf)


def _system(text, out):
    # pyttsx3 is unreliable inside worker threads, so run it in its own process.
    code = ("import sys, pyttsx3; e = pyttsx3.init(); "
            "e.save_to_file(open(sys.argv[1], encoding='utf-8').read(), sys.argv[2]); e.runAndWait()")
    txt = Path(out).with_suffix(".txt")
    txt.write_text(text, encoding="utf-8")
    try:
        r = subprocess.run([sys.executable, "-c", code, str(txt), str(out)], capture_output=True, text=True, timeout=300)
    finally:
        txt.unlink(missing_ok=True)
    if r.returncode != 0 or not Path(out).exists():
        raise TTSError("System voice failed (pip install pyttsx3; on Linux also install espeak-ng): " + r.stderr[-400:])


def _kokoro(text, out, voice):
    try:
        import numpy as np
        from kokoro import KPipeline  # type: ignore
    except ImportError as e:
        raise TTSError("Kokoro is not installed. Restart Clipper with ./run.sh to install it.") from e
    voice = voice or "am_michael"
    lang = voice[0] if voice[:1] in ("a", "b") else "a"
    pipe = _kokoro_cache.get(lang)
    if pipe is None:
        # CPU keeps the graphics card free for image/video generation; Kokoro is fast enough there.
        pipe = _kokoro_cache[lang] = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M", device="cpu")
    chunks = [r.audio.detach().cpu().numpy() for r in pipe(text, voice=voice, speed=1.0) if r.audio is not None]
    if not chunks:
        raise TTSError("Kokoro produced no audio for this text")
    pcm = (np.clip(np.concatenate(chunks), -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(KOKORO_RATE)
        wf.writeframes(pcm.tobytes())


def synthesize(settings, text, out):
    """Writes speech to `out` (wav). Returns False when TTS is disabled."""
    engine = settings["tts_engine"]
    if engine == "none":
        return False
    if engine == "kokoro":
        try:
            _kokoro(text, out, settings["kokoro_voice"])
        except TTSError:
            # Kokoro unavailable (e.g. not installable on this Python): use Piper if one is set up rather than fail.
            piper = voice_path(settings["piper_model"])
            if not (piper and piper.is_file()):
                raise
            _piper(text, out, settings["piper_model"])
    elif engine == "piper":
        _piper(text, out, settings["piper_model"])
    elif engine == "system":
        _system(text, out)
    else:
        raise TTSError(f"Unknown voice engine {engine!r}")
    return True


def check(settings):
    engine = settings["tts_engine"]
    if engine == "none":
        return True, "Voiceover disabled — videos use music and captions only"
    if engine == "kokoro":
        try:
            import kokoro  # noqa: F401  # type: ignore
        except ImportError:
            return False, "Kokoro not installed — restart Clipper with ./run.sh to install it"
        label = dict(KOKORO_VOICES).get(settings["kokoro_voice"], settings["kokoro_voice"])
        return True, f"Kokoro · {label.split(' —')[0]} (first use downloads the voice model, ~330 MB)"
    if engine == "piper":
        try:
            import piper.voice  # noqa: F401  # type: ignore
        except ImportError:
            return False, "piper-tts not installed"
        model = voice_path(settings["piper_model"])
        if not model or not model.is_file():
            return False, "Piper voice file not found — check the path in Settings > Voice"
        if not model.with_name(model.name + ".json").is_file():
            return False, f"Missing {model.name}.json next to the voice file"
        return True, model.name
    try:
        import pyttsx3  # noqa: F401
    except ImportError:
        return False, "pyttsx3 not installed"
    return True, "System voice"
