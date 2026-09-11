from __future__ import annotations

import base64
import json
import logging
import mimetypes
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from a_agent.config import default_ollama_model, normalize_model

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMInfo:
    configured: bool
    provider: str
    model: str
    label: str
    vision: bool


def _provider() -> str:
    return getattr(settings, 'AGENT_LLM_PROVIDER', 'ollama').lower()


def _ollama_base_host() -> str:
    base_url = getattr(settings, 'AGENT_OLLAMA_BASE_URL', 'http://127.0.0.1:11434/v1')
    host = base_url.rstrip('/')
    if host.endswith('/v1'):
        host = host[:-3]
    return host


def ollama_reachable() -> bool:
    try:
        with urllib.request.urlopen(f'{_ollama_base_host()}/api/tags', timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def llm_configured() -> bool:
    provider = _provider()
    if provider == 'ollama':
        return ollama_reachable()
    return bool(getattr(settings, 'AGENT_OPENAI_API_KEY', ''))


def get_llm_info(model: str | None = None) -> LLMInfo:
    from a_agent.config import is_vision_model

    selected = normalize_model(model)
    provider = _provider()
    if provider == 'ollama':
        if ollama_reachable():
            return LLMInfo(
                configured=True,
                provider='ollama',
                model=selected,
                label=f'Ollama · {selected} (local)',
                vision=is_vision_model(selected),
            )
        return LLMInfo(
            configured=False,
            provider='fallback',
            model='',
            label='Ollama offline · rule-based fallback',
            vision=False,
        )

    api_key = getattr(settings, 'AGENT_OPENAI_API_KEY', '')
    openai_model = getattr(settings, 'AGENT_OPENAI_MODEL', 'gpt-4o-mini')
    if api_key:
        return LLMInfo(
            configured=True,
            provider='openai',
            model=openai_model,
            label=f'OpenAI · {openai_model}',
            vision=False,
        )

    return LLMInfo(
        configured=False,
        provider='fallback',
        model='',
        label='Rule-based retrieval (no LLM)',
        vision=False,
    )


def _build_user_message(user_prompt: str, image_file) -> str | list[dict]:
    """Attach an uploaded image (a Django FieldFile) to the user message.

    Reads through the storage backend rather than a filesystem path, so it
    works with local media and with remote storage such as Supabase.
    """
    if not image_file:
        return user_prompt

    try:
        with image_file.open('rb') as fh:
            data = fh.read()
    except Exception:
        logger.warning('Could not read uploaded image %s; answering without it.', image_file.name)
        return user_prompt

    mime, _ = mimetypes.guess_type(image_file.name)
    mime = mime or 'image/jpeg'
    encoded = base64.b64encode(data).decode('ascii')
    return [
        {'type': 'text', 'text': user_prompt},
        {'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{encoded}'}},
    ]


def generate_answer(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    image_file=None,
) -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError('openai package is not installed') from exc

    provider = _provider()
    if provider == 'ollama':
        if not ollama_reachable():
            raise RuntimeError('Ollama is not running')
        base_url = getattr(settings, 'AGENT_OLLAMA_BASE_URL', 'http://127.0.0.1:11434/v1')
        selected_model = normalize_model(model)
        client = OpenAI(base_url=base_url, api_key='ollama')
    else:
        api_key = getattr(settings, 'AGENT_OPENAI_API_KEY', '')
        if not api_key:
            raise RuntimeError('OPENAI_API_KEY is not configured')
        selected_model = getattr(settings, 'AGENT_OPENAI_MODEL', 'gpt-4o-mini')
        client = OpenAI(api_key=api_key)

    user_content = _build_user_message(user_prompt, image_file)
    response = client.chat.completions.create(
        model=selected_model,
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_content},
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content or ''


def dumps_context(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)
