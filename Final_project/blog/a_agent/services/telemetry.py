"""Langfuse Observability & LLM Tracing integration for CheeseO.

Configured via environment variables:
  LANGFUSE_PUBLIC_KEY=pk-lf-...
  LANGFUSE_SECRET_KEY=sk-lf-...
  LANGFUSE_HOST=https://jp.cloud.langfuse.com (Japan region)
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

_client = None


def get_langfuse_client():
    global _client
    if _client is not None:
        return _client

    public_key = getattr(settings, 'LANGFUSE_PUBLIC_KEY', '')
    secret_key = getattr(settings, 'LANGFUSE_SECRET_KEY', '')
    host = getattr(settings, 'LANGFUSE_HOST', 'https://jp.cloud.langfuse.com')

    if not public_key or not secret_key:
        return None

    try:
        from langfuse import Langfuse
        _client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
        return _client
    except Exception as exc:
        logger.warning('Failed to initialize Langfuse client: %s', exc)
        return None


@contextlib.contextmanager
def trace_agent(
    name: str = 'CheeseO-Agent',
    query: str = '',
    user=None,
    model: str | None = None,
    session_id: int | None = None,
    metadata: dict[str, Any] | None = None,
):
    """Context manager for root Agent trace."""
    client = get_langfuse_client()
    if client is None:
        yield None
        return

    meta = {
        'model': model or 'default',
        'session_id': session_id,
        'username': getattr(user, 'username', 'anonymous'),
        **(metadata or {}),
    }

    try:
        with client.start_as_current_observation(
            name=name,
            as_type='agent',
            input={'query': query},
            metadata=meta,
        ) as agent_obs:
            yield agent_obs
    except Exception as exc:
        logger.debug('Langfuse trace_agent observation error: %s', exc)
        yield None


@contextlib.contextmanager
def trace_retriever(name: str = 'Retrieval', query: str = '', metadata: dict[str, Any] | None = None):
    """Context manager for document retrieval (keyword + chunk + vector)."""
    client = get_langfuse_client()
    if client is None:
        yield None
        return

    try:
        with client.start_as_current_observation(
            name=name,
            as_type='retriever',
            input={'query': query},
            metadata=metadata or {},
        ) as ret_obs:
            yield ret_obs
    except Exception as exc:
        logger.debug('Langfuse trace_retriever observation error: %s', exc)
        yield None


@contextlib.contextmanager
def trace_llm_generation(
    name: str = 'LLM-Generation',
    model: str = '',
    system_prompt: str = '',
    user_prompt: str = '',
    metadata: dict[str, Any] | None = None,
):
    """Context manager for LLM answer generation."""
    client = get_langfuse_client()
    if client is None:
        yield None
        return

    try:
        with client.start_as_current_observation(
            name=name,
            as_type='generation',
            model=model,
            input={'system': system_prompt, 'user': user_prompt},
            metadata=metadata or {},
        ) as gen_obs:
            yield gen_obs
    except Exception as exc:
        logger.debug('Langfuse trace_llm_generation observation error: %s', exc)
        yield None


def flush_telemetry():
    """Flush pending traces to Langfuse backend."""
    client = get_langfuse_client()
    if client is not None:
        try:
            client.flush()
        except Exception:
            pass
