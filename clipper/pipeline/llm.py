"""Local language model client: Ollama or any OpenAI-compatible server."""
import json
import re

import httpx


class LLMError(RuntimeError):
    pass


def chat(settings, system, user, json_mode=True, timeout=600):
    provider = settings["llm_provider"]
    base = settings["llm_url"].rstrip("/")
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        if provider == "ollama":
            body = {"model": settings["llm_model"], "messages": msgs, "stream": False,
                    "options": {"temperature": settings["llm_temperature"]}}
            if json_mode:
                body["format"] = "json"
            r = httpx.post(f"{base}/api/chat", json=body, timeout=timeout)
            r.raise_for_status()
            return r.json()["message"]["content"]
        body = {"model": settings["llm_model"], "messages": msgs, "temperature": settings["llm_temperature"]}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        url = base if base.endswith("/v1") else base + "/v1"
        r = httpx.post(f"{url}/chat/completions", json=body, timeout=timeout)
        if r.status_code == 400 and json_mode:
            # Some servers reject response_format; the prompt already demands JSON.
            body.pop("response_format")
            r = httpx.post(f"{url}/chat/completions", json=body, timeout=timeout)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except httpx.HTTPError as e:
        raise LLMError(f"Language model request failed ({base}): {e}") from e


def parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except ValueError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise


def list_models(settings, timeout=5):
    base = settings["llm_url"].rstrip("/")
    if settings["llm_provider"] == "ollama":
        r = httpx.get(f"{base}/api/tags", timeout=timeout)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    url = base if base.endswith("/v1") else base + "/v1"
    r = httpx.get(f"{url}/models", timeout=timeout)
    r.raise_for_status()
    return [m["id"] for m in r.json().get("data", [])]
