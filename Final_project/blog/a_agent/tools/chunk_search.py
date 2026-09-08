from __future__ import annotations

from dataclasses import asdict, dataclass

from django.contrib.auth.models import AnonymousUser, User
from django.db.models import Q

from a_agent.models import ArticleChunk

from .access import can_user_read_full
from a_blog.models import ArticlePage


@dataclass
class ChunkHit:
    article_id: int
    article_title: str
    article_url: str
    chunk_index: int
    content: str
    tags: str
    is_free: bool
    can_read_full: bool


def search_article_chunks(
    query: str,
    user: User | AnonymousUser,
    *,
    limit: int = 5,
    request=None,
) -> list[ChunkHit]:
    if not query.strip():
        return []

    chunks = (
        ArticleChunk.objects.filter(
            Q(content__icontains=query)
            | Q(article_title__icontains=query)
            | Q(tags__icontains=query)
        )
        .order_by('article_id', 'chunk_index')[: limit * 3]
    )

    hits: list[ChunkHit] = []
    seen_articles: set[int] = set()
    for chunk in chunks:
        if chunk.article_id in seen_articles and len(hits) >= limit:
            continue
        try:
            article = ArticlePage.objects.get(pk=chunk.article_id)
        except ArticlePage.DoesNotExist:
            continue

        can_read, _ = can_user_read_full(user, article, request=request)
        content = chunk.content
        if not can_read and not chunk.is_free:
            content = f'[Paid content] {chunk.article_title} — subscribe or purchase to read the full article.'

        url = article.get_url(request) if request else chunk.article_url
        hits.append(
            ChunkHit(
                article_id=chunk.article_id,
                article_title=chunk.article_title,
                article_url=url or chunk.article_url,
                chunk_index=chunk.chunk_index,
                content=content[:500],
                tags=chunk.tags,
                is_free=chunk.is_free,
                can_read_full=can_read,
            )
        )
        seen_articles.add(chunk.article_id)
        if len(hits) >= limit:
            break
    return hits


def chunk_hits_to_dicts(hits: list[ChunkHit]) -> list[dict]:
    return [asdict(hit) for hit in hits]
