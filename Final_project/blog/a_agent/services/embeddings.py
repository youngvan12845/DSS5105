from __future__ import annotations

import json
import math
import urllib.error
import urllib.request

from django.conf import settings

from a_agent.services.llm import _ollama_base_host, ollama_reachable


def embed_model() -> str:
    return getattr(settings, 'AGENT_OLLAMA_EMBED_MODEL', 'nomic-embed-text')


def embeddings_available() -> bool:
    return ollama_reachable()


def embed_text(text: str) -> list[float] | None:
    if not text.strip() or not ollama_reachable():
        return None

    payload = json.dumps({'model': embed_model(), 'input': text}).encode('utf-8')
    request = urllib.request.Request(
        f'{_ollama_base_host()}/api/embed',
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode('utf-8'))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None

    if data.get('error'):
        return None

    embeddings = data.get('embeddings') or data.get('embedding')
    if isinstance(embeddings, list) and embeddings and isinstance(embeddings[0], list):
        return [float(x) for x in embeddings[0]]
    if isinstance(embeddings, list):
        return [float(x) for x in embeddings]
    return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
