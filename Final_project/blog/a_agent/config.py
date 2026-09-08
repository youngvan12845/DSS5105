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


def default_ollama_model() -> str:
    return getattr(settings, 'AGENT_OLLAMA_MODEL', 'qwen2.5vl:7b')


def is_vision_model(model: str) -> bool:
    for option in OLLAMA_MODEL_OPTIONS:
        if option['id'] == model:
            return bool(option.get('vision'))
    return 'vl' in model.lower()


def normalize_model(model: str | None) -> str:
    if model and model in OLLAMA_MODEL_IDS:
        return model
    return default_ollama_model()
