"""Image-to-video: turns a scene's still image into a short moving clip with ComfyUI.

Two built-in models, both supported by ComfyUI's own nodes (no custom nodes needed):
  ltx    LTX-Video 2B  — fast (~1 min per clip on an 8 GB card), decent motion
  wan22  Wan 2.2 5B    — slower (several minutes per clip), noticeably better motion
A custom API-format workflow can replace either; see README for its placeholders.
"""
import json
import random
from pathlib import Path

import httpx

from .images import _fill, comfy_fetch, comfy_run


class AnimateError(RuntimeError):
    pass


NEGATIVE = ("low quality, worst quality, deformed, distorted, disfigured, motion smear, motion artifacts, "
            "blurry, jittery, flickering, morphing, extra limbs, text, watermark")

MODELS = {
    "ltx": {
        "name": "LTX-Video", "width": 512, "height": 896, "length": 97, "fps": 24,
        "nodes": ["CheckpointLoaderSimple", "CLIPLoader", "LTXVImgToVideo", "LTXVConditioning",
                  "LTXVScheduler", "SamplerCustom", "KSamplerSelect"],
        "files": [("CheckpointLoaderSimple", "ckpt_name", "ltx_checkpoint", "models/checkpoints"),
                  ("CLIPLoader", "clip_name", "ltx_text_encoder", "models/text_encoders")],
        "timeout": 1200,
    },
    "wan22": {
        "name": "Wan 2.2 5B", "width": 480, "height": 832, "length": 81, "fps": 24,
        "nodes": ["UNETLoader", "CLIPLoader", "VAELoader", "ModelSamplingSD3", "Wan22ImageToVideoLatent", "KSampler"],
        "files": [("UNETLoader", "unet_name", "wan_model", "models/diffusion_models"),
                  ("CLIPLoader", "clip_name", "wan_text_encoder", "models/text_encoders"),
                  ("VAELoader", "vae_name", "wan_vae", "models/vae")],
        "timeout": 3600,
    },
}


def _ltx_graph(s, v):
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": s["ltx_checkpoint"]}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": s["ltx_text_encoder"], "type": "ltxv"}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": v["prompt"], "clip": ["2", 0]}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": v["negative"], "clip": ["2", 0]}},
        "5": {"class_type": "LoadImage", "inputs": {"image": v["image"]}},
        "6": {"class_type": "LTXVImgToVideo", "inputs": {
            "positive": ["3", 0], "negative": ["4", 0], "vae": ["1", 2], "image": ["5", 0],
            "width": v["width"], "height": v["height"], "length": v["length"], "batch_size": 1, "strength": 1.0}},
        "7": {"class_type": "LTXVConditioning", "inputs": {"positive": ["6", 0], "negative": ["6", 1], "frame_rate": v["fps"]}},
        "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "9": {"class_type": "LTXVScheduler", "inputs": {
            "steps": 30, "max_shift": 2.05, "base_shift": 0.95, "stretch": True, "terminal": 0.1, "latent": ["6", 2]}},
        "10": {"class_type": "SamplerCustom", "inputs": {
            "model": ["1", 0], "add_noise": True, "noise_seed": v["seed"], "cfg": 3.0,
            "positive": ["7", 0], "negative": ["7", 1], "sampler": ["8", 0], "sigmas": ["9", 0], "latent_image": ["6", 2]}},
        "11": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["1", 2]}},
        "12": {"class_type": "PreviewImage", "inputs": {"images": ["11", 0]}},  # temp files: nothing piles up in output/
    }


def _wan_graph(s, v):
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": s["wan_model"], "weight_dtype": "fp8_e4m3fn"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": s["wan_text_encoder"], "type": "wan"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": s["wan_vae"]}},
        "4": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8.0}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": v["prompt"], "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": v["negative"], "clip": ["2", 0]}},
        "7": {"class_type": "LoadImage", "inputs": {"image": v["image"]}},
        "8": {"class_type": "Wan22ImageToVideoLatent", "inputs": {
            "vae": ["3", 0], "width": v["width"], "height": v["height"], "length": v["length"], "batch_size": 1,
            "start_image": ["7", 0]}},
        "9": {"class_type": "KSampler", "inputs": {
            "model": ["4", 0], "seed": v["seed"], "steps": 20, "cfg": 5.0, "sampler_name": "uni_pc", "scheduler": "simple",
            "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["8", 0], "denoise": 1.0}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["3", 0]}},
        "11": {"class_type": "PreviewImage", "inputs": {"images": ["10", 0]}},
    }


def wanted(settings, scene_index):
    mode = settings["animate_mode"]
    return mode == "all" or (mode == "hook" and scene_index == 0)


def _upload(base, image_path, name):
    with open(image_path, "rb") as f:
        r = httpx.post(f"{base}/upload/image", files={"image": (name, f, "image/png")},
                       data={"overwrite": "true", "type": "input"}, timeout=60)
    r.raise_for_status()
    d = r.json()
    return f"{d['subfolder']}/{d['name']}" if d.get("subfolder") else d["name"]


def animate(settings, image_path, prompt, frames_dir, name, seed=None):
    """Writes the clip's frames as frames_dir/f_00001.png… and returns its frame rate."""
    model = MODELS.get(settings["video_model"])
    if not model:
        raise AnimateError(f"Unknown animation model {settings['video_model']!r}")
    base = settings["video_url"].rstrip("/")
    try:
        uploaded = _upload(base, image_path, name)
    except httpx.HTTPError as e:
        raise AnimateError(f"Cannot reach ComfyUI at {base}: {e}") from e
    values = {"image": uploaded, "prompt": prompt, "negative": NEGATIVE, "seed": seed or random.randint(1, 2**31 - 1),
              "width": model["width"], "height": model["height"], "length": model["length"], "fps": model["fps"]}
    wf = settings["video_workflow_path"]
    if wf:
        graph = _fill(json.loads(Path(wf).expanduser().read_text(encoding="utf-8")), values)
    else:
        graph = (_ltx_graph if settings["video_model"] == "ltx" else _wan_graph)(settings, values)
    frames = comfy_run(base, graph, model["timeout"], AnimateError)
    if len(frames) < 8:
        raise AnimateError(f"ComfyUI returned only {len(frames)} frame(s) — is the workflow saving every frame?")
    out = Path(frames_dir)
    out.mkdir(parents=True, exist_ok=True)
    try:
        for i, img in enumerate(frames, 1):
            (out / f"f_{i:05d}.png").write_bytes(comfy_fetch(base, img))
    except httpx.HTTPError as e:
        raise AnimateError(f"Cannot download frames from ComfyUI: {e}") from e
    return model["fps"]


def _options(info, node, field):
    """Values ComfyUI offers for a dropdown, across old and new /object_info formats."""
    spec = info.get(node, {}).get("input", {})
    spec = {**spec.get("required", {}), **spec.get("optional", {})}.get(field)
    if not spec:
        return []
    if isinstance(spec[0], list):
        return spec[0]
    if len(spec) > 1 and isinstance(spec[1], dict):
        return spec[1].get("options", [])
    return []


def check(settings):
    if settings["animate_mode"] == "off":
        return True, "Off — scenes use still images with a slow zoom"
    model = MODELS.get(settings["video_model"])
    if not model:
        return False, "Unknown animation model"
    base = settings["video_url"].rstrip("/")
    try:
        info = httpx.get(f"{base}/object_info", timeout=10).json()
    except (httpx.HTTPError, ValueError):
        return False, f"ComfyUI not reachable at {base}"
    missing_nodes = [n for n in model["nodes"] if n not in info]
    if missing_nodes:
        return False, f"Your ComfyUI is too old for {model['name']} (missing {', '.join(missing_nodes)}). Update ComfyUI."
    if settings["video_workflow_path"]:
        return True, f"{model['name']} via your custom workflow"
    for node, field, key, folder in model["files"]:
        if settings[key] not in _options(info, node, field):
            return False, f"{settings[key]} not found in ComfyUI/{folder}"
    return True, f"{model['name']} · {'first scene' if settings['animate_mode'] == 'hook' else 'every scene'}"
