# Clipper

Clipper is a desktop app that makes short vertical videos with AI running on your own PC and posts them to
YouTube Shorts, TikTok and Instagram Reels on a schedule. You set it up once in a web dashboard. After that
it runs on its own: it writes the script, generates images and voiceover, renders with captions and music,
then posts.

- **Local AI only.** Scripts come from [Ollama](https://ollama.com) or any OpenAI-compatible local server
  (LM Studio, llama.cpp). Images come from [ComfyUI](https://github.com/comfyanonymous/ComfyUI) or
  Stable Diffusion WebUI / Forge. Voices come from [Piper](https://github.com/rhasspy/piper).
  No cloud keys and no per-video cost.
- **Campaigns.** Each campaign is a content series with its own:
  - niche, prompt and topic list
  - visual style, caption style and music
  - platforms, posts per day, posting window, days of the week and random timing offset
- **Prompts you control.** You write the creative direction yourself and can test it against your model
  before using it. Clipper adds the output format, length and repeat-avoidance rules automatically.
- **Review or full autopilot.** Videos can wait for your approval, or post with no human in the loop.
- **Safe defaults.**
  - A daily cap limits how many posts go out across all campaigns.
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

## Install and run

**Windows:** double-click `run.bat`. **macOS/Linux:** `./run.sh`.

The first launch creates a virtual environment and installs everything. Then the dashboard opens at
<http://127.0.0.1:8765>. The dashboard only listens on your own machine.

## First-time setup (about 10 minutes)

1. **Settings.** Point Clipper at your script model, image engine and Piper voice. The Overview page's
   *System check* turns green when each piece is reachable.
2. **Accounts.** Click **Connect** for each platform. A normal browser window opens. Sign in as usual
   (2FA included), then close the window. Clipper keeps that browser profile in `data/browser_profiles/`.
   It never sees or stores your password.
3. **Prompts.** Edit the four starter prompts or write your own. Use **Test this prompt** to see what your
   model produces.
4. **Campaigns.** Create one. Pick a niche, prompt, platforms and schedule, then press
   **Generate a video now** and watch it render in the **Library**.
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

## When something breaks

- **A post failed.** Open the video in the Library to see the error. Every failure also writes a screenshot
  of the browser to `data/screenshots/`, linked from the Activity page.
- **Platforms change their upload pages.** If an upload step stops working, the selectors live in one file
  per platform: `clipper/uploaders/youtube.py`, `tiktok.py`, `instagram.py`.
- **"Unconfirmed" posts.** Clipper clicked Post but couldn't see a success message. Check the account, then
  click **It posted** or **Retry** in the video's panel.
- **Signed out.** When a session expires, posts to that platform stop and the account shows
  *Not connected*. Click **Reconnect**.

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
