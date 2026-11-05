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
    provider = getattr(settings, 'AGENT_LLM_PROVIDER', 'cloudflare').lower()
    if provider == 'ollama' and not ollama_reachable():
        if getattr(settings, 'CLOUDFLARE_API_TOKEN', ''):
            return 'cloudflare'
        if getattr(settings, 'AGENT_OPENAI_API_KEY', ''):
            return 'openai'
    return provider


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
    if provider == 'cloudflare':
        return bool(getattr(settings, 'CLOUDFLARE_API_TOKEN', ''))
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

    if provider == 'cloudflare':
        token = getattr(settings, 'CLOUDFLARE_API_TOKEN', '')
        cf_model = selected if selected.startswith('@cf/') else getattr(settings, 'CLOUDFLARE_AI_MODEL', '@cf/qwen/qwen2.5-coder-32b-instruct')
        if token:
            display_name = cf_model.split('/')[-1]
            return LLMInfo(
                configured=True,
                provider='cloudflare',
                model=cf_model,
                label=f'Cloudflare AI · {display_name}',
                vision=is_vision_model(cf_model),
            )
        return LLMInfo(
            configured=False,
            provider='fallback',
            model='',
            label='Cloudflare AI offline · rule-based fallback',
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


_CF_LLM_QUOTA_EXHAUSTED_UNTIL: float = 0.0


def generate_answer(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    image_file=None,
) -> str:
    global _CF_LLM_QUOTA_EXHAUSTED_UNTIL
    import time

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError('openai package is not installed') from exc

    provider = _provider()
    if provider == 'cloudflare' and time.time() < _CF_LLM_QUOTA_EXHAUSTED_UNTIL:
        raise RuntimeError('Cloudflare daily free neuron quota temporarily exhausted')
    if provider == 'ollama':
        if not ollama_reachable():
            raise RuntimeError('Ollama is not running')
        base_url = getattr(settings, 'AGENT_OLLAMA_BASE_URL', 'http://127.0.0.1:11434/v1')
        selected_model = normalize_model(model)
        client = OpenAI(base_url=base_url, api_key='ollama', timeout=25.0)
    elif provider == 'cloudflare':
        account_id = getattr(settings, 'CLOUDFLARE_ACCOUNT_ID', '')
        token = getattr(settings, 'CLOUDFLARE_API_TOKEN', '')
        if not token:
            raise RuntimeError('CLOUDFLARE_API_TOKEN is not configured')
        base_url = f'https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1'
        if model and model.startswith('@cf/'):
            selected_model = model
        else:
            selected_model = getattr(settings, 'CLOUDFLARE_AI_MODEL', '@cf/qwen/qwen2.5-coder-32b-instruct')
        if image_file and 'scout' not in selected_model and 'vision' not in selected_model:
            selected_model = getattr(settings, 'CLOUDFLARE_VISION_MODEL', '@cf/meta/llama-4-scout-17b-16e-instruct')
        client = OpenAI(base_url=base_url, api_key=token, timeout=25.0)
    else:
        api_key = getattr(settings, 'AGENT_OPENAI_API_KEY', '')
        if not api_key:
            raise RuntimeError('OPENAI_API_KEY is not configured')
        base_url = getattr(settings, 'AGENT_OPENAI_BASE_URL', None) or None
        if model and (model.startswith('gpt-') or model.startswith('o1') or model.startswith('o3')):
            selected_model = model
        else:
            selected_model = getattr(settings, 'AGENT_OPENAI_MODEL', 'gpt-4o-mini')
        client = OpenAI(base_url=base_url, api_key=api_key, timeout=25.0)

    user_content = _build_user_message(user_prompt, image_file)
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_content},
    ]

    candidate_models = [selected_model]
    if provider == 'cloudflare':
        fallback_cf = (
            ['@cf/meta/llama-4-scout-17b-16e-instruct']
            if image_file
            else [
                '@cf/qwen/qwen2.5-coder-32b-instruct',
                '@cf/meta/llama-3.3-70b-instruct-fp8-fast',
                '@cf/meta/llama-4-scout-17b-16e-instruct',
            ]
        )
        for m in fallback_cf:
            if m not in candidate_models:
                candidate_models.append(m)

    last_exc = None
    for cand_model in candidate_models:
        for attempt in range(2):
            try:
                response = client.chat.completions.create(
                    model=cand_model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=900,
                )
                text = response.choices[0].message.content or ''
                if text.strip():
                    return text
            except Exception as exc:
                last_exc = exc
                err_str = str(exc)
                if '4006' in err_str or 'daily free allocation' in err_str:
                    _CF_LLM_QUOTA_EXHAUSTED_UNTIL = time.time() + 120.0
                    raise exc
                if ('429' in err_str or '502' in err_str or '503' in err_str) and attempt == 0:
                    time.sleep(0.8)
                    continue
                break
    if last_exc:
        raise last_exc
    return ''


def dumps_context(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)
