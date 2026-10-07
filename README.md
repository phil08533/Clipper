# Clipper

Clipper is a desktop app that makes short vertical videos with AI running on your own PC and posts them to
YouTube Shorts, TikTok and Instagram Reels on a schedule. You set it up once in a web dashboard. After that
it runs on its own: it writes the script, generates images and voiceover, renders with captions and music,
then posts.

- **Local AI only.** Scripts come from [Ollama](https://ollama.com) or any OpenAI-compatible local server
  (LM Studio, llama.cpp). Images come from [ComfyUI](https://github.com/comfyanonymous/ComfyUI) or
  Stable Diffusion WebUI / Forge. Voices come from [Piper](https://github.com/rhasspy/piper).
  No cloud keys and no per-video cost.
- **Ready-made workflows.** Pick one and every setting is filled in: niche, prompt, topic list, visual
  style, captions, length and schedule. You only choose which accounts it posts to.

  | Workflow | What it makes |
  |---|---|
  | Mythology & Folklore | Traditional myths retold as short stories (40 legends included) |
  | Short Horror Stories | Original first-person horror with a twist (30 story seeds) |
  | What If…? | Science hypotheticals told second by second, then year by year (30 questions) |
  | A Day in History (POV) | "You are a Roman legionary…": immersive days from history (30 roles) |
  | Insects & Bugs | One creature's strangest real ability, in macro-photo style (36 topics) |
  | Animal Kingdom | Astonishing animal abilities, told like a wildlife documentary (39 topics) |
  | Original Story Series | An ongoing fantasy saga; each video is the next episode, with the story so far fed back in |
  | Start from scratch | Your own niche and prompt |

- **Many campaigns, many accounts.**
  - Add as many accounts as you like, including several per platform. Each keeps its own sign-in.
  - Each campaign posts to any mix of accounts.
  - Campaigns run side by side.
  - Different accounts upload in parallel. How many at once is set in Settings.
- **Random or even schedules.**
  - *Random*: a different number of posts each day (e.g. 1–3) at random times, with a minimum gap
    between posts.
  - *Even*: a fixed number per day, spaced out with a small random offset.
  - Both modes use a daily time window and chosen days of the week.
- **Prompts you control.** You write the creative direction yourself and can test it against your model
  before using it. Clipper adds the output format, length and repeat-avoidance rules automatically.
- **Review or full autopilot.** Videos can wait for your approval, or post with no human in the loop.
- **Safe defaults.**
  - A per-account daily cap holds extra posts until the next day.
  - While autopilot runs, each account's sign-in is re-checked in the background (every 12 hours by
    default). If an account has signed out, its posts are held, not failed, and a banner tells you which
    account to reconnect. Held posts go out once it's back.
  - Failed posts retry with back-off.
  - Uploads that can't be confirmed are never retried automatically, so nothing gets double-posted.
  - Failures save a screenshot.
  - Each platform's AI-content disclosure is ticked by default.

## Before you start: read this

- **Automation and platform rules.** Posting through a browser automates your account. TikTok, YouTube and
  Instagram restrict automated activity, and accounts that post like bots can be limited or banned. Use
  accounts you own, keep the posting frequency modest, and start with review mode on.
- **AI disclosure.** All three platforms require you to label realistic AI-generated media. Clipper ticks
  the label for you. Leave **Label posts as AI-generated** on.
- **Monetisation.** YouTube's Partner Program excludes mass-produced, repetitive ("inauthentic") content,
  and TikTok/Instagram suppress it. Channels that earn have a clear niche, real value per video and varied
  prompts. Volume alone doesn't earn.
- **Music.** Only put tracks you have rights to in your music folder.

## Requirements

| Piece | What to install |
|---|---|
| Python 3.10+ | [python.org](https://www.python.org/downloads/). On Windows, tick "Add to PATH". |
| ffmpeg | Windows: `winget install Gyan.FFmpeg` · macOS: `brew install ffmpeg` · Linux: your package manager. Must include libass (all of these do). |
| Script model | [Ollama](https://ollama.com), then `ollama pull llama3.1:8b` (or `qwen2.5:14b` if you have the VRAM). |
| Image model | [ComfyUI](https://github.com/comfyanonymous/ComfyUI) with an SDXL or SD 1.5 checkpoint, **or** Forge/AUTOMATIC1111 started with `--api`. No GPU? Pick **Styled backgrounds** in Settings. |
| Voice | A Piper voice: download a `.onnx` file **and** its `.onnx.json` from [piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US) (e.g. `ryan/high`). Or use the system voice. |
| Browser | Google Chrome or Microsoft Edge (recommended for signing in). |

A GPU with 8 GB+ VRAM is comfortable for SDXL. With SD 1.5, 4–6 GB is enough. A 45-second, 6-scene video
usually takes 1–5 minutes on a mid-range GPU.

## Optional: animated scenes (image-to-video)

Settings → **Animation** turns still scenes into short AI clips through ComfyUI. **First scene only** is
recommended: the hook gets motion and the render stays fast. Download one model set into your ComfyUI folder:

**LTX-Video 2B** (fast, about 1 minute per clip on an 8 GB card):
```bash
cd ~/ComfyUI/models
wget -P checkpoints    https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltx-video-2b-v0.9.5.safetensors
wget -P text_encoders  https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn_scaled.safetensors
```

**Wan 2.2 5B** (better motion, several minutes per clip):
```bash
cd ~/ComfyUI/models
wget -P diffusion_models https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors
wget -P text_encoders    https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors
wget -P vae              https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan2.2_vae.safetensors
```

Restart ComfyUI after downloading. The Overview's *System check → Animation* line confirms the files are found.
If a clip fails, for example because the GPU runs out of memory, that scene falls back to the still image and the
video still completes. Both models use ComfyUI's built-in nodes; keep ComfyUI up to date (`git pull` in its folder).

## Voices

**Kokoro** is the default voice engine and sounds far more natural than Piper. `run.sh` / `run.bat` install it
automatically. It runs on the CPU, so it never competes with ComfyUI for the GPU. The voice model (~330 MB)
downloads on first use. Pick a default voice in Settings, and a different one per campaign if you like; each
ready-made workflow comes with a matching narrator. Kokoro needs Python 3.10–3.12; on other versions Clipper falls
back to Piper.

## Install and run

**Windows:** double-click `run.bat`. **macOS/Linux:** `./run.sh`.

The first launch creates a virtual environment and installs everything. Then the dashboard opens at
<http://127.0.0.1:8765>. The dashboard only listens on your own machine.

## First-time setup (about 10 minutes)

1. **Settings.** Point Clipper at your script model, image engine and Piper voice. The Overview page's
   *System check* turns green when each piece is reachable.
2. **Accounts.** Add each channel you want to post to, for example "Myths TikTok" and "Horror TikTok".
   Then click **Connect** on each one. A normal browser window opens for that account only. Sign in as
   usual (2FA included), then close the window. Each account's session lives in its own folder under
   `data/browser_profiles/`. Clipper never sees or stores your password. If one Google login owns several
   YouTube channels, add one account per channel and switch to the right channel before closing the
   window.
3. **Prompts (optional).** Workflows come with their own prompts. To write your own, use the Prompts
   page, where **Test this prompt** shows what your model produces.
4. **Campaigns.** Click **New campaign**, pick a workflow, tick the accounts it should post to, and
   create it. Then press **Generate a video now** and watch it render in the **Library**. Repeat for as
   many campaigns as you want.
5. **Autopilot.** Flip the switch in the sidebar. Clipper keeps each campaign's buffer of videos generated
   ahead and posts at the scheduled times. Turn off **Hold videos for my approval** in a campaign when
   you're happy with its output.

### Start with your PC

- **Windows:** press `Win+R`, type `shell:startup`, and put a shortcut to `run.bat` in that folder. To skip
  opening the dashboard each time, set the shortcut's target to `run.bat --no-browser`, or turn the option
  off in Settings.
- **macOS:** System Settings → General → Login Items → add `run.sh`.
- **Linux:** add `run.sh --no-browser` to your session's autostart.

Clipper must be running, and the PC awake, for posts to go out on time. A missed slot posts as soon as it's
running again.

**Throughput.** Videos are generated one at a time, because the GPU is shared. So total output across
all campaigns is limited by render speed. At about 3 minutes per video, that's roughly 20 videos an hour.
Uploads to different accounts run in parallel.

## When something breaks

- **A post failed.** Open the video in the Library to see the error. Every failure also writes a screenshot
  of the browser to `data/screenshots/`, linked from the Activity page.
- **Platforms change their upload pages.** If an upload step stops working, the selectors live in one file
  per platform: `clipper/uploaders/youtube.py`, `tiktok.py`, `instagram.py`.
- **"Unconfirmed" posts.** Clipper clicked Post but couldn't see a success message. Check the account, then
  click **It posted** or **Retry** in the video's panel.
- **Signed out.** When a session expires, posts to that account are put on hold, not failed. The
  account shows *Not connected* and the Overview shows a banner. Click **Reconnect**; held posts then go
  out automatically.

## Project layout

```
clipper/
  __main__.py       entry point (python -m clipper)
  server.py         local HTTP API + dashboard
  scheduler.py      autopilot: buffers, posting slots, retries, clean-up
  publisher.py      posting state machine, account connect/check
  pipeline/         script (LLM) → images → voice → ffmpeg render
  uploaders/        Playwright flows for YouTube, TikTok, Instagram
  web/              dashboard (plain HTML/CSS/JS, no build step)
data/               database, videos, browser profiles, screenshots (created on first run, git-ignored)
tests/              python -m pytest -q
```
