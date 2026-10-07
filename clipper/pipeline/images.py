"""Scene images from ComfyUI, AUTOMATIC1111/Forge, or a no-AI styled background."""
import base64
import json
import random
import time
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter


class ImageError(RuntimeError):
    pass


# Minimal API-format txt2img graph. Works with SD 1.5 and SDXL checkpoints.
DEFAULT_COMFY_WORKFLOW = {
    "3": {"class_type": "KSampler", "inputs": {
        "seed": "{{seed}}", "steps": "{{steps}}", "cfg": 6.5, "sampler_name": "dpmpp_2m", "scheduler": "karras",
        "denoise": 1, "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
    "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "{{checkpoint}}"}},
    "5": {"class_type": "EmptyLatentImage", "inputs": {"width": "{{width}}", "height": "{{height}}", "batch_size": 1}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}", "clip": ["4", 1]}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{negative}}", "clip": ["4", 1]}},
    "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
    "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "clipper", "images": ["8", 0]}},
}


def _fill(node, values):
    """Replace "{{name}}" placeholders anywhere in a workflow, keeping numbers numeric."""
    if isinstance(node, dict):
        return {k: _fill(v, values) for k, v in node.items()}
    if isinstance(node, list):
        return [_fill(v, values) for v in node]
    if isinstance(node, str):
        for k, v in values.items():
            if node == "{{" + k + "}}":
                return v
            node = node.replace("{{" + k + "}}", str(v))
    return node


def _comfy(settings, prompt, out, seed):
    base = settings["image_url"].rstrip("/")
    wf_path = settings["comfy_workflow_path"]
    workflow = json.loads(Path(wf_path).expanduser().read_text(encoding="utf-8")) if wf_path else DEFAULT_COMFY_WORKFLOW
    graph = _fill(workflow, {
        "prompt": prompt, "negative": settings["negative_prompt"], "seed": seed,
        "steps": settings["image_steps"], "width": settings["image_width"], "height": settings["image_height"],
        "checkpoint": settings["comfy_checkpoint"],
    })
    try:
        r = httpx.post(f"{base}/prompt", json={"prompt": graph, "client_id": "clipper"}, timeout=30)
        if r.status_code >= 400:
            raise ImageError(f"ComfyUI rejected the workflow: {r.text[:500]}")
        pid = r.json()["prompt_id"]
        deadline = time.time() + 900
        while time.time() < deadline:
            time.sleep(1.5)
            h = httpx.get(f"{base}/history/{pid}", timeout=30).json().get(pid)
            if not h:
                continue
            status = h.get("status", {})
            if status.get("status_str") == "error":
                raise ImageError("ComfyUI reported an error while generating")
            for node_out in h.get("outputs", {}).values():
                for img in node_out.get("images", []):
                    data = httpx.get(f"{base}/view", params={
                        "filename": img["filename"], "subfolder": img.get("subfolder", ""), "type": img.get("type", "output")},
                        timeout=60).content
                    Path(out).write_bytes(data)
                    return
        raise ImageError("ComfyUI timed out")
    except httpx.HTTPError as e:
        raise ImageError(f"Cannot reach ComfyUI at {base}: {e}") from e


def _a1111(settings, prompt, out, seed):
    base = settings["image_url"].rstrip("/")
    try:
        r = httpx.post(f"{base}/sdapi/v1/txt2img", timeout=900, json={
            "prompt": prompt, "negative_prompt": settings["negative_prompt"], "seed": seed,
            "steps": settings["image_steps"], "width": settings["image_width"], "height": settings["image_height"],
            "cfg_scale": 6.5, "sampler_name": "DPM++ 2M"})
        r.raise_for_status()
        Path(out).write_bytes(base64.b64decode(r.json()["images"][0].split(",", 1)[-1]))
    except httpx.HTTPError as e:
        raise ImageError(f"Image request to {base} failed: {e}") from e


PALETTES = [
    ((16, 24, 40), (52, 78, 120)), ((30, 20, 24), (120, 54, 48)), ((14, 34, 30), (40, 110, 92)),
    ((28, 26, 36), (88, 76, 120)), ((22, 22, 22), (90, 90, 96)), ((36, 26, 14), (150, 104, 48)),
]


def _cards(settings, out, seed):
    """Non-AI fallback: a soft gradient with grain, so the pipeline works without a GPU."""
    rnd = random.Random(seed)
    w, h = settings["image_width"], settings["image_height"]
    top, bottom = rnd.choice(PALETTES)
    img = Image.new("RGB", (w, h))
    px = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        px.line([(0, y), (w, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    glow = Image.new("L", (w, h), 0)
    gd = ImageDraw.Draw(glow)
    for _ in range(3):
        cx, cy, r = rnd.randint(0, w), rnd.randint(0, h), rnd.randint(w // 3, w)
        gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=rnd.randint(30, 70))
    glow = glow.filter(ImageFilter.GaussianBlur(w // 6))
    img = Image.composite(Image.new("RGB", (w, h), (255, 255, 255)), img, glow)
    noise = Image.effect_noise((w, h), 18).convert("RGB")
    Image.blend(img, noise, 0.05).save(out)


def generate(settings, prompt, out, seed=None):
    seed = seed if seed is not None else random.randint(1, 2**31 - 1)
    engine = settings["image_engine"]
    if engine == "comfyui":
        _comfy(settings, prompt, out, seed)
    elif engine == "a1111":
        _a1111(settings, prompt, out, seed)
    else:
        _cards(settings, out, seed)
    # Normalise to RGB PNG so ffmpeg always gets the same input.
    with Image.open(out) as im:
        im.convert("RGB").save(out, "PNG")


def release(settings):
    """Ask ComfyUI to unload its model so the script model has the GPU for the next video."""
    if settings["image_engine"] != "comfyui":
        return
    try:
        httpx.post(settings["image_url"].rstrip("/") + "/free", json={"unload_models": True, "free_memory": True}, timeout=10)
    except httpx.HTTPError:
        pass


def check(settings):
    engine = settings["image_engine"]
    if engine == "cards":
        return True, "Styled backgrounds (no image AI)"
    base = settings["image_url"].rstrip("/")
    try:
        path = "/system_stats" if engine == "comfyui" else "/sdapi/v1/sd-models"
        httpx.get(base + path, timeout=4).raise_for_status()
        return True, f"{'ComfyUI' if engine == 'comfyui' else 'Stable Diffusion WebUI'} at {base}"
    except httpx.HTTPError:
        return False, f"Not reachable at {base}"
