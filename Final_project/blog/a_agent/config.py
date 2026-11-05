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


def _active_provider() -> str:
    return getattr(settings, 'AGENT_LLM_PROVIDER', 'cloudflare').lower()


def get_model_options() -> list[dict]:
    if _active_provider() == 'cloudflare':
        return CLOUDFLARE_MODEL_OPTIONS
    return OLLAMA_MODEL_OPTIONS


def default_ollama_model() -> str:
    return getattr(settings, 'AGENT_OLLAMA_MODEL', 'qwen2.5vl:7b')


def default_cloudflare_model() -> str:
    return getattr(settings, 'CLOUDFLARE_AI_MODEL', '@cf/qwen/qwen2.5-coder-32b-instruct')


def is_vision_model(model: str) -> bool:
    for option in CLOUDFLARE_MODEL_OPTIONS + OLLAMA_MODEL_OPTIONS:
        if option['id'] == model:
            return bool(option.get('vision'))
    return 'vl' in model.lower() or 'vision' in model.lower() or 'scout' in model.lower()


def normalize_model(model: str | None) -> str:
    if _active_provider() == 'cloudflare':
        if model and model in CLOUDFLARE_MODEL_IDS:
            return model
        if model and model in OLLAMA_MODEL_IDS:
            return default_cloudflare_model()
        if model and model.startswith('@cf/'):
            return model
        return default_cloudflare_model()
    if model and model in OLLAMA_MODEL_IDS:
        return model
    return default_ollama_model()
