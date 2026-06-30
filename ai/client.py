"""Gemini REST client with automatic model fallback on rate limits. Free tier."""
import json
import os
import time

import requests

_last_call = 0.0

# 2.5-flash first — it's the model that has free-tier quota on this key.
MODEL_FALLBACK = [
    "gemini-2.5-flash",
    "gemini-flash-lite-latest",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]


def generate(prompt: str, model: str = "", rate_limit: float = 7.0) -> dict:
    """Call Gemini, auto-falling back across models on 429/404. Returns JSON or {}."""
    global _last_call

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return {}

    elapsed = time.time() - _last_call
    if elapsed < rate_limit:
        time.sleep(rate_limit - elapsed)

    models = [model] + [m for m in MODEL_FALLBACK if m != model] if model else MODEL_FALLBACK
    _last_call = time.time()

    for m in models:
        # Key goes in a header, NOT the URL query string, so it can't leak into
        # logs/tracebacks (which include the request URL on connection errors).
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.4,
                "maxOutputTokens": 8192,
            },
        }
        try:
            resp = requests.post(url, headers={"x-goog-api-key": api_key}, json=payload, timeout=30)
            if resp.status_code == 200:
                return _parse(resp)
            if resp.status_code in (429, 404):
                time.sleep(1)
                continue
            print(f"[gemini] {m} -> HTTP {resp.status_code}")
            return {}
        except requests.RequestException as exc:
            print(f"[gemini] {m} request error: {type(exc).__name__}")
            return {}

    return {}


def _parse(resp) -> dict:
    try:
        text = (
            resp.json()
            .get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
            .strip()
        )
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
        return json.loads(text)
    except (json.JSONDecodeError, KeyError, IndexError):
        return {}
