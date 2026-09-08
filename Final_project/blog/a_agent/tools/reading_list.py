from __future__ import annotations

from dataclasses import asdict, dataclass

from django.contrib.auth.models import User

from a_agent.models import AgentActionLog, ReadingListItem
from a_blog.models import ArticlePage

from .access import get_article_access


@dataclass
class ReadingListEntry:
    article_id: int
    title: str
    url: str
    is_free: bool


def get_reading_list(user: User, *, limit: int = 20) -> list[ReadingListEntry]:
    rows = ReadingListItem.objects.filter(user=user).order_by('-added_at')[:limit]
    return [
        ReadingListEntry(
            article_id=row.article_id,
            title=row.article_title,
            url=row.article_url,
            is_free=row.is_free,
        )
        for row in rows
    ]


def reading_list_to_dicts(items: list[ReadingListEntry]) -> list[dict]:
    return [asdict(item) for item in items]


def propose_add_to_reading_list(
    user: User,
    article_ids: list[int],
    *,
    request=None,
) -> AgentActionLog | None:
    unique_ids = []
    seen: set[int] = set()
    for article_id in article_ids:
        if article_id in seen:
            continue
        seen.add(article_id)
        unique_ids.append(article_id)
    if not unique_ids:
        return None

    articles = []
    for article_id in unique_ids:
        article = ArticlePage.objects.filter(pk=article_id).live().first()
        if article is None:
            continue
        access = get_article_access(user, article, request=request)
        articles.append(
            {
                'article_id': article.pk,
                'title': article.title,
                'url': access.url,
                'is_free': article.is_free,
            }
        )
    if not articles:
        return None

    return AgentActionLog.objects.create(
        user=user,
        action_type='add_to_reading_list',
        payload={'articles': articles},
        confirmed=False,
        executed=False,
    )


def execute_add_to_reading_list(action: AgentActionLog) -> list[ReadingListItem]:
    if action.action_type != 'add_to_reading_list':
        raise ValueError('Unsupported action type')

    created: list[ReadingListItem] = []
    for item in action.payload.get('articles', []):
        row, was_created = ReadingListItem.objects.get_or_create(
            user=action.user,
            article_id=item['article_id'],
            defaults={
                'article_title': item['title'],
                'article_url': item['url'],
                'is_free': item.get('is_free', True),
            },
        )
        if was_created:
            created.append(row)
    return created


def _resolve_remove_article_ids(
    user: User,
    article_ids: list[int],
    *,
    query: str = '',
) -> list[int]:
    if article_ids:
        return article_ids

    q = query.lower().strip()
    if not q:
        return []

    rows = ReadingListItem.objects.filter(user=user)
    matched: list[int] = []
    for row in rows:
        title = row.article_title.lower()
        if title in q or q in title:
            matched.append(row.article_id)
    return matched


def propose_remove_from_reading_list(
    user: User,
    article_ids: list[int],
    *,
    query: str = '',
) -> AgentActionLog | None:
    unique_ids = _resolve_remove_article_ids(user, article_ids, query=query)
    if not unique_ids:
        return None

    articles = []
    for article_id in unique_ids:
        row = ReadingListItem.objects.filter(user=user, article_id=article_id).first()
        if row is None:
            continue
        articles.append(
            {
                'article_id': row.article_id,
                'title': row.article_title,
                'url': row.article_url,
                'is_free': row.is_free,
            }
        )
    if not articles:
        return None

    return AgentActionLog.objects.create(
        user=user,
        action_type='remove_from_reading_list',
        payload={'articles': articles},
        confirmed=False,
        executed=False,
    )


def execute_remove_from_reading_list(action: AgentActionLog) -> int:
    if action.action_type != 'remove_from_reading_list':
        raise ValueError('Unsupported action type')

    removed = 0
    for item in action.payload.get('articles', []):
        deleted, _ = ReadingListItem.objects.filter(
            user=action.user,
            article_id=item['article_id'],
        ).delete()
        removed += deleted
    return removed
