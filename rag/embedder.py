"""Sprint 30 — Ollama-backed embedder for RAG."""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Callable, Optional, Sequence

from agent.tracing import trace_subsystem

EMBED_DIM = 768
DEFAULT_MODEL = "nomic-embed-text"


class EmbedderError(RuntimeError):
    pass


def _ollama_url() -> str:
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    return host + "/api/embeddings"


def _default_call(payload: dict) -> dict:
    req = urllib.request.Request(
        _ollama_url(),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


@trace_subsystem("rag")
def embed_text(
    text: str,
    *,
    model: str = DEFAULT_MODEL,
    _call: Optional[Callable[[dict], dict]] = None,
) -> list[float]:
    text = (text or "").strip()
    if not text:
        raise EmbedderError("empty input")
    call = _call or _default_call
    resp = call({"model": model, "prompt": text})
    emb = resp.get("embedding") or []
    if len(emb) != EMBED_DIM:
        raise EmbedderError(f"unexpected embedding dim {len(emb)} != {EMBED_DIM}")
    return [float(x) for x in emb]


@trace_subsystem("rag")
def embed_batch(
    texts: Sequence[str],
    *,
    model: str = DEFAULT_MODEL,
    _call: Optional[Callable[[dict], dict]] = None,
) -> list[list[float]]:
    return [embed_text(t, model=model, _call=_call) for t in texts]
