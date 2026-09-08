from __future__ import annotations

from dataclasses import asdict, dataclass

from django.contrib.auth.models import AnonymousUser, User

from a_agent.models import ArticleChunk
from a_agent.services.embeddings import cosine_similarity, embed_text
from a_blog.models import ArticlePage

from .access import can_user_read_full
from .chunk_search import ChunkHit


@dataclass
class VectorHit(ChunkHit):
    score: float = 0.0


def search_article_vectors(
    query: str,
    user: User | AnonymousUser,
    *,
    limit: int = 5,
    request=None,
) -> list[VectorHit]:
    if not query.strip():
        return []

    query_embedding = embed_text(query)
    if query_embedding is None:
        return []

    scored: list[tuple[float, ArticleChunk]] = []
    for chunk in ArticleChunk.objects.exclude(embedding=[]).iterator():
        if not chunk.embedding:
            continue
        score = cosine_similarity(query_embedding, chunk.embedding)
        if score <= 0:
            continue
        scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)

    hits: list[VectorHit] = []
    seen_articles: set[int] = set()
    for score, chunk in scored:
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
            VectorHit(
                article_id=chunk.article_id,
                article_title=chunk.article_title,
                article_url=url or chunk.article_url,
                chunk_index=chunk.chunk_index,
                content=content[:500],
                tags=chunk.tags,
                is_free=chunk.is_free,
                can_read_full=can_read,
                score=round(score, 4),
            )
        )
        seen_articles.add(chunk.article_id)
        if len(hits) >= limit:
            break
    return hits


def vector_hits_to_dicts(hits: list[VectorHit]) -> list[dict]:
    return [asdict(hit) for hit in hits]
