from django.conf import settings

OLLAMA_MODEL_OPTIONS = getattr(
    settings,
    'AGENT_OLLAMA_MODELS',
    [
        {'id': 'qwen2.5:7b', 'label': 'Qwen 2.5 7B (text)', 'vision': False},
        {'id': 'qwen2.5vl:7b', 'label': 'Qwen 2.5 VL 7B (multimodal)', 'vision': True},
    ],
)
OLLAMA_MODEL_IDS = {m['id'] for m in OLLAMA_MODEL_OPTIONS}

CLOUDFLARE_MODEL_OPTIONS = getattr(
    settings,
    'AGENT_CLOUDFLARE_MODELS',
    [
        {'id': '@cf/qwen/qwen2.5-coder-32b-instruct', 'label': 'Qwen 2.5 Coder 32B', 'vision': True},
        {'id': '@cf/meta/llama-3.3-70b-instruct-fp8-fast', 'label': 'Llama 3.3 70B Fast', 'vision': True},
        {'id': '@cf/meta/llama-4-scout-17b-16e-instruct', 'label': 'Llama 4 Scout 17B (Vision)', 'vision': True},
    ],
)
CLOUDFLARE_MODEL_IDS = {m['id'] for m in CLOUDFLARE_MODEL_OPTIONS}

OPENAI_MODEL_OPTIONS = getattr(
    settings,
    'AGENT_OPENAI_MODELS',
    [
        {'id': 'gpt-4o-mini', 'label': 'ChatGPT · GPT-4o Mini', 'vision': True},
        {'id': 'gpt-4o', 'label': 'ChatGPT · GPT-4o', 'vision': True},
        {'id': 'o3-mini', 'label': 'ChatGPT · o3-mini (Reasoning)', 'vision': False},
    ],
)
OPENAI_MODEL_IDS = {m['id'] for m in OPENAI_MODEL_OPTIONS}

ANTHROPIC_MODEL_OPTIONS = getattr(
    settings,
    'AGENT_ANTHROPIC_MODELS',
    [
        {'id': 'claude-3-5-sonnet-20241022', 'label': 'Claude 3.5 Sonnet', 'vision': True},
        {'id': 'claude-3-5-haiku-20241022', 'label': 'Claude 3.5 Haiku', 'vision': True},
    ],
)
ANTHROPIC_MODEL_IDS = {m['id'] for m in ANTHROPIC_MODEL_OPTIONS}


def _active_provider() -> str:
    return getattr(settings, 'AGENT_LLM_PROVIDER', 'cloudflare').lower()


def get_model_options() -> list[dict]:
    provider = _active_provider()
    if provider == 'cloudflare':
        return CLOUDFLARE_MODEL_OPTIONS
    if provider == 'openai':
        return OPENAI_MODEL_OPTIONS
    if provider == 'anthropic':
        return ANTHROPIC_MODEL_OPTIONS
    return OLLAMA_MODEL_OPTIONS


def default_ollama_model() -> str:
    return getattr(settings, 'AGENT_OLLAMA_MODEL', 'qwen2.5vl:7b')


def default_cloudflare_model() -> str:
    return getattr(settings, 'CLOUDFLARE_AI_MODEL', '@cf/qwen/qwen2.5-coder-32b-instruct')


def default_openai_model() -> str:
    return getattr(settings, 'AGENT_OPENAI_MODEL', 'gpt-4o-mini')


def default_anthropic_model() -> str:
    return getattr(settings, 'AGENT_ANTHROPIC_MODEL', 'claude-3-5-sonnet-20241022')


def is_vision_model(model: str) -> bool:
    all_options = CLOUDFLARE_MODEL_OPTIONS + OLLAMA_MODEL_OPTIONS + OPENAI_MODEL_OPTIONS + ANTHROPIC_MODEL_OPTIONS
    for option in all_options:
        if option['id'] == model:
            return bool(option.get('vision'))
    m_lower = model.lower()
    return (
        'vl' in m_lower
        or 'vision' in m_lower
        or 'scout' in m_lower
        or 'gpt-4o' in m_lower
        or 'claude-3' in m_lower
    )


def normalize_model(model: str | None) -> str:
    provider = _active_provider()
    if not model:
        if provider == 'cloudflare':
            return default_cloudflare_model()
        if provider == 'openai':
            return default_openai_model()
        if provider == 'anthropic':
            return default_anthropic_model()
        return default_ollama_model()

    # Provider-aware model validation:
    if provider == 'cloudflare':
        if model in CLOUDFLARE_MODEL_IDS or model.startswith('@cf/'):
            return model
        return default_cloudflare_model()

    if provider == 'openai':
        if model in OPENAI_MODEL_IDS or model.startswith(('gpt-', 'o1-', 'o3-')):
            return model
        return default_openai_model()

    if provider == 'anthropic':
        if model in ANTHROPIC_MODEL_IDS or model.startswith('claude-'):
            return model
        return default_anthropic_model()

    if model in OLLAMA_MODEL_IDS:
        return model
    return default_ollama_model()
