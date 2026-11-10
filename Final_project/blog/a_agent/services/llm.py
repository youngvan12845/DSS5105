from __future__ import annotations

import base64
import json
import logging
import mimetypes
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from a_agent.config import (
    ANTHROPIC_MODEL_IDS,
    CLOUDFLARE_MODEL_IDS,
    OLLAMA_MODEL_IDS,
    OPENAI_MODEL_IDS,
    default_anthropic_model,
    default_cloudflare_model,
    default_ollama_model,
    default_openai_model,
    is_vision_model,
    normalize_model,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMInfo:
    configured: bool
    provider: str
    model: str
    label: str
    vision: bool


_CF_ACCOUNT_EXHAUSTED_UNTIL: dict[str, float] = {}


def get_cloudflare_accounts() -> list[tuple[str, str]]:
    """Return configured (account_id, api_token) pairs with non-exhausted accounts first."""
    raw_pairs: list[tuple[str, str]] = []
    primary_id = getattr(settings, 'CLOUDFLARE_ACCOUNT_ID', '')
    primary_token = getattr(settings, 'CLOUDFLARE_API_TOKEN', '')
    if primary_id and primary_token:
        raw_pairs.append((primary_id, primary_token))

    for acc_id, tok in getattr(settings, 'CLOUDFLARE_ACCOUNTS', []):
        if acc_id and tok and (acc_id, tok) not in raw_pairs:
            raw_pairs.append((acc_id, tok))

    now = time.time()
    active = [pair for pair in raw_pairs if now >= _CF_ACCOUNT_EXHAUSTED_UNTIL.get(pair[0], 0.0)]
    return active


def has_any_cloudflare_account() -> bool:
    primary_id = getattr(settings, 'CLOUDFLARE_ACCOUNT_ID', '')
    primary_token = getattr(settings, 'CLOUDFLARE_API_TOKEN', '')
    if primary_id and primary_token:
        return True
    return bool(getattr(settings, 'CLOUDFLARE_ACCOUNTS', []))


def mark_cloudflare_account_exhausted(account_id: str, cooldown: float = 1800.0) -> None:
    _CF_ACCOUNT_EXHAUSTED_UNTIL[account_id] = time.time() + cooldown
    logger.warning(
        'Cloudflare account %s hit 10k neuron limit; switching to next fallback account for %.0fs.',
        account_id[:8],
        cooldown,
    )


def _provider(model: str | None = None) -> str:
    if model:
        if model in ANTHROPIC_MODEL_IDS or model.startswith('claude-'):
            return 'anthropic'
        if model in OPENAI_MODEL_IDS or model.startswith(('gpt-', 'o1-', 'o3-')):
            return 'openai'
        if model in CLOUDFLARE_MODEL_IDS or model.startswith('@cf/'):
            return 'cloudflare'
        if model in OLLAMA_MODEL_IDS:
            return 'ollama'

    provider = getattr(settings, 'AGENT_LLM_PROVIDER', 'cloudflare').lower()
    if provider == 'ollama' and not ollama_reachable():
        if has_any_cloudflare_account():
            return 'cloudflare'
        if getattr(settings, 'AGENT_OPENAI_API_KEY', ''):
            return 'openai'
        if getattr(settings, 'ANTHROPIC_API_KEY', ''):
            return 'anthropic'
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


def llm_configured(model: str | None = None) -> bool:
    provider = _provider(model)
    if provider == 'anthropic':
        return bool(getattr(settings, 'ANTHROPIC_API_KEY', ''))
    if provider == 'openai':
        return bool(getattr(settings, 'AGENT_OPENAI_API_KEY', ''))
    if provider == 'ollama':
        return ollama_reachable()
    if provider == 'cloudflare':
        return has_any_cloudflare_account()
    return False


def get_llm_info(model: str | None = None) -> LLMInfo:
    selected = normalize_model(model)
    provider = _provider(selected)

    if provider == 'anthropic':
        api_key = getattr(settings, 'ANTHROPIC_API_KEY', '')
        if api_key:
            return LLMInfo(
                configured=True,
                provider='anthropic',
                model=selected,
                label=f'Claude · {selected}',
                vision=is_vision_model(selected),
            )
        return LLMInfo(
            configured=False,
            provider='fallback',
            model='',
            label='Claude offline (ANTHROPIC_API_KEY missing)',
            vision=False,
        )

    if provider == 'openai':
        api_key = getattr(settings, 'AGENT_OPENAI_API_KEY', '')
        if api_key:
            return LLMInfo(
                configured=True,
                provider='openai',
                model=selected,
                label=f'ChatGPT · {selected}',
                vision=is_vision_model(selected),
            )
        return LLMInfo(
            configured=False,
            provider='fallback',
            model='',
            label='OpenAI offline (OPENAI_API_KEY missing)',
            vision=False,
        )

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
        cf_model = selected if selected.startswith('@cf/') else getattr(settings, 'CLOUDFLARE_AI_MODEL', default_cloudflare_model())
        if has_any_cloudflare_account():
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

    return LLMInfo(
        configured=False,
        provider='fallback',
        model='',
        label='Rule-based retrieval (no LLM)',
        vision=False,
    )


def _read_image_base64(image_file) -> tuple[str, str]:
    """Extract (base64_data, mime_type) from Django FieldFile."""
    if not image_file:
        return '', ''
    try:
        with image_file.open('rb') as fh:
            data = fh.read()
        mime, _ = mimetypes.guess_type(getattr(image_file, 'name', 'image.jpg'))
        mime = mime or 'image/jpeg'
        encoded = base64.b64encode(data).decode('ascii')
        return encoded, mime
    except Exception as exc:
        logger.warning('Could not read uploaded image; answering without it. %s', exc)
        return '', ''


def _build_openai_user_message(user_prompt: str, image_file) -> str | list[dict]:
    encoded, mime = _read_image_base64(image_file)
    if not encoded:
        return user_prompt
    return [
        {'type': 'text', 'text': user_prompt},
        {'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{encoded}'}},
    ]


def _call_anthropic(system_prompt: str, user_prompt: str, model: str, image_file=None) -> str:
    """Call Anthropic Messages API (Claude 3.5 Sonnet / Haiku / Opus) via httpx."""
    import httpx

    api_key = getattr(settings, 'ANTHROPIC_API_KEY', '')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY is not configured in settings or environment')
    base_url = getattr(settings, 'AGENT_ANTHROPIC_BASE_URL', 'https://api.anthropic.com/v1').rstrip('/')

    content_blocks = []
    encoded, mime = _read_image_base64(image_file)
    if encoded:
        content_blocks.append({
            'type': 'image',
            'source': {
                'type': 'base64',
                'media_type': mime,
                'data': encoded,
            },
        })
    content_blocks.append({'type': 'text', 'text': user_prompt})

    headers = {
        'x-api-key': api_key,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json',
    }
    payload: dict[str, Any] = {
        'model': model,
        'max_tokens': 1200,
        'temperature': 0.1,
        'messages': [
            {'role': 'user', 'content': content_blocks},
        ],
    }
    if system_prompt:
        payload['system'] = system_prompt

    with httpx.Client(timeout=35.0) as client:
        resp = client.post(f'{base_url}/messages', headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        texts = [block['text'] for block in data.get('content', []) if block.get('type') == 'text']
        return ''.join(texts).strip()


def _call_openai(system_prompt: str, user_prompt: str, model: str, image_file=None) -> str:
    """Call OpenAI API (ChatGPT: GPT-4o, GPT-4o-mini, o3-mini, etc.)."""
    from openai import OpenAI

    api_key = getattr(settings, 'AGENT_OPENAI_API_KEY', '')
    if not api_key:
        raise RuntimeError('OPENAI_API_KEY is not configured in settings or environment')
    base_url = getattr(settings, 'AGENT_OPENAI_BASE_URL', None) or None
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=35.0)

    user_content = _build_openai_user_message(user_prompt, image_file)
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_content},
    ]

    kwargs: dict[str, Any] = {'model': model, 'messages': messages}
    if model.startswith(('o1', 'o3')):
        kwargs['max_completion_tokens'] = 1200
    else:
        kwargs['temperature'] = 0.1
        kwargs['max_tokens'] = 1200

    response = client.chat.completions.create(**kwargs)
    return (response.choices[0].message.content or '').strip()


_CF_LLM_QUOTA_EXHAUSTED_UNTIL: float = 0.0


def generate_answer(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    image_file=None,
) -> str:
    global _CF_LLM_QUOTA_EXHAUSTED_UNTIL

    selected_provider = _provider(model)

    # 1. Anthropic (Claude)
    if selected_provider == 'anthropic':
        selected_model = model or getattr(settings, 'AGENT_ANTHROPIC_MODEL', default_anthropic_model())
        return _call_anthropic(system_prompt, user_prompt, selected_model, image_file=image_file)

    # 2. OpenAI (ChatGPT)
    if selected_provider == 'openai':
        selected_model = model or getattr(settings, 'AGENT_OPENAI_MODEL', default_openai_model())
        return _call_openai(system_prompt, user_prompt, selected_model, image_file=image_file)

    # 3. Ollama (Local)
    if selected_provider == 'ollama':
        from openai import OpenAI

        if not ollama_reachable():
            raise RuntimeError('Ollama is not running')
        base_url = getattr(settings, 'AGENT_OLLAMA_BASE_URL', 'http://127.0.0.1:11434/v1')
        selected_model = normalize_model(model)
        client = OpenAI(base_url=base_url, api_key='ollama', timeout=30.0)
        user_content = _build_openai_user_message(user_prompt, image_file)
        response = client.chat.completions.create(
            model=selected_model,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_content},
            ],
            temperature=0.1,
            max_tokens=900,
        )
        return (response.choices[0].message.content or '').strip()

    # 4. Cloudflare Workers AI (with automatic multi-account rotation on HTTP 429 / Code 4006)
    if time.time() < _CF_LLM_QUOTA_EXHAUSTED_UNTIL:
        raise RuntimeError('Cloudflare daily free neuron quota temporarily exhausted across all accounts')

    from openai import OpenAI

    cf_accounts = get_cloudflare_accounts()
    if not cf_accounts:
        if not has_any_cloudflare_account():
            raise RuntimeError('CLOUDFLARE_API_TOKEN is not configured')
        raise RuntimeError('Cloudflare daily free neuron quota temporarily exhausted across all accounts')

    if model and model.startswith('@cf/'):
        selected_model = model
    else:
        selected_model = getattr(settings, 'CLOUDFLARE_AI_MODEL', default_cloudflare_model())

    if image_file and 'scout' not in selected_model and 'vision' not in selected_model:
        selected_model = getattr(settings, 'CLOUDFLARE_VISION_MODEL', '@cf/meta/llama-4-scout-17b-16e-instruct')

    user_content = _build_openai_user_message(user_prompt, image_file)
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_content},
    ]

    candidate_models = [selected_model]
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
    for account_id, token in cf_accounts:
        base_url = f'https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1'
        client = OpenAI(base_url=base_url, api_key=token, timeout=25.0)
        account_exhausted = False
        for cand_model in candidate_models:
            if account_exhausted:
                break
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
                        return text.strip()
                except Exception as exc:
                    last_exc = exc
                    err_str = str(exc)
                    if '4006' in err_str or 'daily free allocation' in err_str:
                        mark_cloudflare_account_exhausted(account_id)
                        account_exhausted = True
                        break
                    if ('429' in err_str or '502' in err_str or '503' in err_str) and attempt == 0:
                        time.sleep(0.8)
                        continue
                    break
        if not account_exhausted:
            break

    if not get_cloudflare_accounts():
        _CF_LLM_QUOTA_EXHAUSTED_UNTIL = time.time() + 120.0
    if last_exc:
        raise last_exc
    return ''


def dumps_context(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)
