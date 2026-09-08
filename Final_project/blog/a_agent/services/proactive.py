from __future__ import annotations

from datetime import datetime

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from django.utils.timesince import timesince

from a_agent.models import ChatMessage, ChatSession
from a_agent.tools.browsing_history import HistoryItem, get_browsing_history
from a_agent.tools.recommend import recommend_articles


def _format_viewed_at(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace('Z', '+00:00'))
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return f'{timesince(dt)} ago'
    except (ValueError, TypeError):
        return 'recently'


def build_continue_reading_nudge(
    history: list[HistoryItem],
    user: User,
    *,
    request=None,
) -> tuple[str, list[dict], list[dict]]:
    latest = history[0]
    lines = [
        f'Welcome back! You were reading **{latest.article_title}** ({_format_viewed_at(latest.viewed_at)}).',
        '',
        f'[Continue reading →]({latest.article_url})',
    ]

    if len(history) > 1:
        lines.extend(['', '**Recently viewed:**'])
        for item in history[1:]:
            lines.append(f'- [{item.article_title}]({item.article_url})')

    history_ids = {item.article_id for item in history}
    recs = [
        hit
        for hit in recommend_articles(user, limit=4, request=request)
        if hit.article_id not in history_ids
    ][:2]
    if recs:
        lines.extend(['', '**You might also like:**'])
        for hit in recs:
            lines.append(f'- [{hit.title}]({hit.url}) — _{hit.reason}_')

    lines.extend(['', 'Ask me anything, or use the shortcuts below.'])

    citations = [
        {
            'article_id': item.article_id,
            'title': item.article_title,
            'url': item.article_url,
            'source': 'browsing_history',
        }
        for item in history
    ]
    for hit in recs:
        citations.append(
            {
                'article_id': hit.article_id,
                'title': hit.title,
                'url': hit.url,
                'source': 'recommendation',
            }
        )

    tool_trace = [
        {
            'tool': 'proactive_continue_reading',
            'article_id': latest.article_id,
            'article_title': latest.article_title,
            'article_url': latest.article_url,
        }
    ]
    return '\n'.join(lines), citations[:5], tool_trace


def ensure_session_continue_nudge(
    session: ChatSession,
    user: User,
    *,
    request=None,
) -> ChatMessage | None:
    if not user.is_authenticated:
        return None
    if session.title.startswith('📄'):
        return None

    with transaction.atomic():
        locked = ChatSession.objects.select_for_update().get(pk=session.pk)
        if locked.messages.exists():
            return None

        history = get_browsing_history(user, limit=3)
        if not history:
            return None

        content, citations, tool_trace = build_continue_reading_nudge(
            history,
            user,
            request=request,
        )
        return ChatMessage.objects.create(
            session=locked,
            role=ChatMessage.ROLE_ASSISTANT,
            content=content,
            citations=citations,
            tool_trace=tool_trace,
        )
