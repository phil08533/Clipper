"""Turns a prompt template into a structured video script using the local LLM."""
import datetime

from . import llm

SYSTEM = """You write scripts for vertical short-form videos (TikTok, YouTube Shorts, Instagram Reels).
Reply with ONLY a JSON object, no commentary, in exactly this shape:
{
  "topic": "the specific topic you chose",
  "title": "catchy title, under 80 characters, no hashtags",
  "description": "one or two sentences for the post description",
  "hashtags": ["5 to 8 relevant hashtags without the # sign"],
  "scenes": [
    {"narration": "what the voiceover says in this scene (1-3 short sentences)",
     "visual": "a concrete visual description for an image generator: subject, setting, composition. No text or words in the image."}
  ]
}
Rules: write narration to be spoken aloud; no emojis, stage directions or scene labels in narration;
every scene needs a different visual; the first scene's narration is the hook."""

USER = """{template}

Requirements:
- Niche: {niche}
- Topic: {topic_line}
- Exactly {scenes} scenes. Total narration about {words} words (~{duration} seconds spoken).
- Each scene's narration must be {per_scene_lo}-{per_scene_hi} words (two or three full sentences). Short scenes make the video too short.
- Today is {date}.
{avoid}{series}"""


def series_block(series):
    """series = {"bible": str, "number": int, "episodes": [(title, synopsis), ...] oldest first}."""
    if not series or not series.get("bible"):
        return ""
    lines = ["", "STORY WORLD (canon — never contradict it):", series["bible"].strip(), ""]
    if series.get("episodes"):
        lines.append("PREVIOUS EPISODES (oldest first):")
        lines += [f"- {t}: {syn}" for t, syn in series["episodes"]]
    else:
        lines.append("This is the very first episode: introduce the main character and the central mystery.")
    lines.append(f"Write episode {series['number']}. Continue directly from the last episode.")
    return "\n".join(lines)


def render_user_prompt(template, niche, topic, scenes, duration, recent_titles, series=None):
    words = int(duration * 2.5)
    avoid = ""
    if recent_titles and not (series and series.get("bible")):
        avoid = "- Do NOT repeat or closely resemble these recent videos:\n" + "\n".join(f"  * {t}" for t in recent_titles[:30])
    return USER.format(
        template=template.replace("{niche}", niche or "general interest")
                         .replace("{topic}", topic or "a fresh topic of your choice"),
        niche=niche or "general interest",
        topic_line=topic or "choose a fresh, specific topic that fits the niche",
        scenes=scenes, words=words, duration=duration,
        per_scene_lo=max(8, int(words / scenes * 0.85)), per_scene_hi=max(12, int(words / scenes * 1.2)),
        date=datetime.date.today().strftime("%B %d, %Y"),
        avoid=avoid,
        series=series_block(series),
    )


def validate(data, scenes_wanted):
    if not isinstance(data, dict):
        raise ValueError("model did not return a JSON object")
    scenes = [s for s in data.get("scenes") or [] if isinstance(s, dict) and str(s.get("narration", "")).strip()]
    if len(scenes) < max(2, scenes_wanted // 2):
        raise ValueError(f"only {len(scenes)} usable scenes")
    title = str(data.get("title") or "").strip().strip('"')
    if not title:
        raise ValueError("missing title")
    tags = data.get("hashtags") or []
    if isinstance(tags, str):
        tags = tags.replace(",", " ").split()
    tags = [str(t).strip().lstrip("#").replace(" ", "") for t in tags if str(t).strip()]
    return {
        "topic": str(data.get("topic") or "").strip(),
        "title": title[:95],
        "description": str(data.get("description") or "").strip(),
        "hashtags": tags[:10],
        "scenes": [{"narration": str(s["narration"]).strip(),
                    "visual": str(s.get("visual") or s["narration"]).strip()} for s in scenes[:12]],
    }


def generate(settings, template, niche, topic, scenes, duration, recent_titles=(), attempts=3, series=None):
    user = render_user_prompt(template, niche, topic, scenes, duration, list(recent_titles), series)
    last = None
    for _ in range(attempts):
        try:
            raw = llm.chat(settings, SYSTEM, user, json_mode=True)
            return validate(llm.parse_json(raw), scenes)
        except llm.LLMError:
            raise
        except (ValueError, KeyError, TypeError) as e:
            last = e
    raise llm.LLMError(f"Model returned an unusable script after {attempts} tries: {last}")
