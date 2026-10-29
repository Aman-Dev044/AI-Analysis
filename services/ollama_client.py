"""Thin client for an Ollama server (local or on a VPS) with streaming support."""

import json
import re
from typing import Callable, Iterator, Optional

import requests

from config import Config

_THINK_BLOCK = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)


class OllamaError(RuntimeError):
    pass


def _headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if Config.OLLAMA_API_KEY:
        headers["Authorization"] = f"Bearer {Config.OLLAMA_API_KEY}"
    return headers


def strip_thinking(text: str) -> str:
    """Remove <think> blocks that reasoning models (qwen3, deepseek-r1) may emit."""
    text = _THINK_BLOCK.sub("", text)
    # An unterminated block while streaming: hide everything after <think>.
    open_at = text.lower().find("<think>")
    return text[:open_at] if open_at != -1 else text


def health() -> dict:
    """Return reachability, version and installed models."""
    try:
        version = requests.get(f"{Config.OLLAMA_URL}/api/version", headers=_headers(), timeout=8)
        version.raise_for_status()
        tags = requests.get(f"{Config.OLLAMA_URL}/api/tags", headers=_headers(), timeout=8)
        tags.raise_for_status()
        models = sorted(m.get("name") for m in tags.json().get("models", []) if m.get("name"))
        return {
            "ok": True,
            "url": Config.OLLAMA_URL,
            "version": version.json().get("version"),
            "models": models,
            "default_model": Config.OLLAMA_MODEL,
            "default_model_installed": Config.OLLAMA_MODEL in models,
        }
    except requests.RequestException as exc:
        return {"ok": False, "url": Config.OLLAMA_URL, "error": str(exc), "models": [],
                "default_model": Config.OLLAMA_MODEL}


def _stream_request(payload: dict) -> Iterator[str]:
    try:
        resp = requests.post(
            f"{Config.OLLAMA_URL}/api/chat",
            headers=_headers(),
            data=json.dumps(payload),
            stream=True,
            timeout=(15, Config.OLLAMA_TIMEOUT),
        )
    except requests.ConnectionError as exc:
        raise OllamaError(f"Cannot reach Ollama at {Config.OLLAMA_URL}. Check OLLAMA_URL / VPS firewall.") from exc
    except requests.Timeout as exc:
        raise OllamaError("Ollama did not respond in time.") from exc

    if resp.status_code != 200:
        detail = resp.text[:400]
        try:
            detail = resp.json().get("error", detail)
        except ValueError:
            pass
        raise OllamaError(f"Ollama HTTP {resp.status_code}: {detail}")

    with resp:
        # Parse raw bytes: Ollama's NDJSON is UTF-8 but its Content-Type has no charset.
        for line in resp.iter_lines():
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except ValueError:
                continue
            if chunk.get("error"):
                raise OllamaError(chunk["error"])
            piece = (chunk.get("message") or {}).get("content", "")
            if piece:
                yield piece
            if chunk.get("done"):
                break


def chat(
    messages: list[dict],
    *,
    model: Optional[str] = None,
    temperature: float = 0.3,
    num_predict: int = -1,
    num_ctx: Optional[int] = None,
    on_token: Optional[Callable[[str], None]] = None,
) -> str:
    """Run a chat completion, streaming partial text to on_token(full_text_so_far)."""
    payload = {
        "model": model or Config.OLLAMA_MODEL,
        "messages": messages,
        "stream": True,
        "think": False,
        "keep_alive": Config.OLLAMA_KEEP_ALIVE,  # keep the model in RAM: reloading it costs seconds on CPU
        "options": {
            "temperature": temperature,
            "num_ctx": min(num_ctx or Config.OLLAMA_NUM_CTX, Config.OLLAMA_NUM_CTX),
            "num_predict": num_predict,
        },
    }
    raw = ""
    try:
        stream = _stream_request(payload)
        for piece in stream:
            raw += piece
            if on_token:
                on_token(strip_thinking(raw))
    except OllamaError as exc:
        # Older Ollama versions / non-thinking models reject the "think" flag.
        if "think" in str(exc).lower() and not raw:
            payload.pop("think", None)
            for piece in _stream_request(payload):
                raw += piece
                if on_token:
                    on_token(strip_thinking(raw))
        else:
            raise
    text = strip_thinking(raw).strip()
    if not text:
        raise OllamaError("The model returned an empty response.")
    return text


def vision_ocr(image_b64: str, model: str) -> str:
    """Transcribe an image with a vision model (e.g. qwen2.5vl, llava)."""
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": "Transcribe ALL text in this image exactly as written, preserving line breaks "
                       "and table rows. Output only the text, no commentary.",
            "images": [image_b64],
        }],
        "stream": True,
        "options": {"temperature": 0},
    }
    return strip_thinking("".join(_stream_request(payload))).strip()
