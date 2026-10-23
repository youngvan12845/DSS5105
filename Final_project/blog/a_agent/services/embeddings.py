from __future__ import annotations

import json
import logging
import math
import urllib.error
import urllib.request
from typing import Sequence

from django.conf import settings

from a_agent.services.llm import _ollama_base_host, ollama_reachable

logger = logging.getLogger(__name__)


def embed_provider() -> str:
    return getattr(settings, 'AGENT_LLM_PROVIDER', 'ollama').lower()


def embed_model() -> str:
    provider = embed_provider()
    if provider == 'cloudflare':
        return getattr(settings, 'CLOUDFLARE_EMBED_MODEL', '@cf/baai/bge-m3')
    if provider == 'openai':
        return getattr(settings, 'OPENAI_EMBED_MODEL', 'text-embedding-3-small')
    return getattr(settings, 'AGENT_OLLAMA_EMBED_MODEL', 'nomic-embed-text')


def embeddings_available() -> bool:
    provider = embed_provider()
    if provider == 'cloudflare':
        return bool(getattr(settings, 'CLOUDFLARE_ACCOUNT_ID', '')) and bool(
            getattr(settings, 'CLOUDFLARE_API_TOKEN', '')
        )
    if provider == 'openai':
        return bool(getattr(settings, 'AGENT_OPENAI_API_KEY', ''))
    return ollama_reachable()


def _embed_texts_cloudflare(texts: Sequence[str]) -> list[list[float]]:
    account_id = getattr(settings, 'CLOUDFLARE_ACCOUNT_ID', '')
    token = getattr(settings, 'CLOUDFLARE_API_TOKEN', '')
    model = embed_model()
    if not account_id or not token:
        return []

    url = f'https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}'
    payload = json.dumps({'text': list(texts)}).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as exc:
        logger.warning('Cloudflare embedding failed: %s', exc)
        return []

    raw_data = data.get('result', {}).get('data', [])
    results: list[list[float]] = []
    for item in raw_data:
        if isinstance(item, list):
            results.append([float(x) for x in item])
    return results


def _embed_texts_openai(texts: Sequence[str]) -> list[list[float]]:
    try:
        from openai import OpenAI
    except ImportError:
        logger.warning('OpenAI package not installed')
        return []

    api_key = getattr(settings, 'AGENT_OPENAI_API_KEY', '')
    base_url = getattr(settings, 'AGENT_OPENAI_BASE_URL', None) or None
    if not api_key:
        return []

    client = OpenAI(api_key=api_key, base_url=base_url)
    try:
        resp = client.embeddings.create(input=list(texts), model=embed_model())
        return [list(item.embedding) for item in resp.data]
    except Exception as exc:
        logger.warning('OpenAI embedding failed: %s', exc)
        return []


def _embed_texts_ollama(texts: Sequence[str]) -> list[list[float]]:
    if not ollama_reachable():
        return []

    payload = json.dumps({'model': embed_model(), 'input': list(texts)}).encode('utf-8')
    req = urllib.request.Request(
        f'{_ollama_base_host()}/api/embed',
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as exc:
        logger.warning('Ollama embedding failed: %s', exc)
        return []

    raw = data.get('embeddings') or data.get('embedding')
    if isinstance(raw, list):
        if raw and isinstance(raw[0], list):
            return [[float(x) for x in row] for row in raw]
        if raw and isinstance(raw[0], (int, float)):
            return [[float(x) for x in raw]]
    return []


def embed_texts(texts: Sequence[str], *, batch_size: int = 40) -> list[list[float]]:
    """Generate embeddings for multiple texts, automatically batching requests."""
    clean_texts = [t.strip() for t in texts]
    if not clean_texts or not embeddings_available():
        return []

    provider = embed_provider()
    results: list[list[float]] = []

    for i in range(0, len(clean_texts), batch_size):
        batch = clean_texts[i : i + batch_size]
        if provider == 'cloudflare':
            batch_vectors = _embed_texts_cloudflare(batch)
        elif provider == 'openai':
            batch_vectors = _embed_texts_openai(batch)
        else:
            batch_vectors = _embed_texts_ollama(batch)

        results.extend(batch_vectors)

    return results


def embed_text(text: str) -> list[float] | None:
    """Generate an embedding vector for a single text."""
    if not text.strip():
        return None
    vectors = embed_texts([text])
    return vectors[0] if vectors else None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
