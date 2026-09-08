from __future__ import annotations

from dataclasses import asdict, dataclass

from django.contrib.auth.models import AnonymousUser, User
from django.db.models import Q

from a_agent.models import ArticleChunk
from a_agent.services.embeddings import cosine_similarity, embed_text
from a_agent.tools.access import get_article_access
from a_agent.tools.chunk_search import ChunkHit, chunk_hits_to_dicts
from a_agent.tools.keyword_search import SearchHit
from a_blog.models import ArticlePage

from .access import can_user_read_full


@dataclass
class ArticleScope:
    article_id: int
    title: str
    url: str
    intro: str
    is_free: bool
    can_read_full: bool
    access_reason: str


def get_article_scope(
    article_id: int,
    user: User | AnonymousUser,
    *,
    request=None,
) -> ArticleScope | None:
    try:
        article = ArticlePage.objects.live().get(pk=article_id)
    except ArticlePage.DoesNotExist:
        return None

    access = get_article_access(user, article, request=request)
    return ArticleScope(
        article_id=article.pk,
        title=article.title,
        url=access.url,
        intro=article.intro or '',
        is_free=article.is_free,
        can_read_full=access.can_read_full,
        access_reason=access.reason,
    )


def article_scope_to_dict(scope: ArticleScope | None) -> dict | None:
    if scope is None:
        return None
    return asdict(scope)


def scoped_keyword_hit(
    article_id: int,
    query: str,
    user: User | AnonymousUser,
    *,
    request=None,
) -> list[SearchHit]:
    scope = get_article_scope(article_id, user, request=request)
    if scope is None:
        return []

    try:
        article = ArticlePage.objects.live().get(pk=article_id)
    except ArticlePage.DoesNotExist:
        return []

    body_text = str(article.body or '')
    snippet_source = scope.intro or body_text
    snippet = snippet_source[:240]
    if query.strip():
        q = query.lower()
        haystack = f'{scope.title}\n{scope.intro}\n{body_text}'.lower()
        if q not in haystack:
            snippet = f'[Context from this article] {snippet[:180]}'

    if not scope.can_read_full and not scope.is_free:
        snippet = f'[Paid preview] {scope.intro or scope.title}'

    return [
        SearchHit(
            article_id=scope.article_id,
            title=scope.title,
            url=scope.url,
            intro=scope.intro,
            snippet=snippet,
            tags=[t.name for t in article.tags.all()],
            is_free=scope.is_free,
            can_read_full=scope.can_read_full,
            access_reason=scope.access_reason,
        )
    ]


def _chunk_to_hit(
    chunk: ArticleChunk,
    user: User | AnonymousUser,
    *,
    request=None,
    score: float = 0.0,
) -> ChunkHit | None:
    try:
        article = ArticlePage.objects.get(pk=chunk.article_id)
    except ArticlePage.DoesNotExist:
        return None

    can_read, _ = can_user_read_full(user, article, request=request)
    content = chunk.content
    if not can_read and not chunk.is_free:
        content = (
            f'[Paid content] {chunk.article_title} — '
            'subscribe or purchase to read the full article.'
        )

    url = article.get_url(request) if request else chunk.article_url
    hit = ChunkHit(
        article_id=chunk.article_id,
        article_title=chunk.article_title,
        article_url=url or chunk.article_url,
        chunk_index=chunk.chunk_index,
        content=content[:500],
        tags=chunk.tags,
        is_free=chunk.is_free,
        can_read_full=can_read,
    )
    if score:
        from a_agent.tools.vector_search import VectorHit

        return VectorHit(**asdict(hit), score=round(score, 4))
    return hit


def get_baseline_article_chunks(
    article_id: int,
    user: User | AnonymousUser,
    *,
    limit: int = 6,
    request=None,
) -> list[ChunkHit]:
    hits: list[ChunkHit] = []
    for chunk in ArticleChunk.objects.filter(article_id=article_id).order_by('chunk_index')[:limit]:
        hit = _chunk_to_hit(chunk, user, request=request)
        if hit:
            hits.append(hit)
    return hits


def search_scoped_article_chunks(
    article_id: int,
    query: str,
    user: User | AnonymousUser,
    *,
    limit: int = 6,
    request=None,
) -> list[ChunkHit]:
    if not query.strip():
        return get_baseline_article_chunks(article_id, user, limit=limit, request=request)

    chunks = (
        ArticleChunk.objects.filter(article_id=article_id)
        .filter(
            Q(content__icontains=query)
            | Q(article_title__icontains=query)
            | Q(tags__icontains=query)
        )
        .order_by('chunk_index')[:limit]
    )
    hits: list[ChunkHit] = []
    for chunk in chunks:
        hit = _chunk_to_hit(chunk, user, request=request)
        if hit:
            hits.append(hit)

    if not hits:
        return get_baseline_article_chunks(article_id, user, limit=limit, request=request)
    return hits


def search_scoped_article_vectors(
    article_id: int,
    query: str,
    user: User | AnonymousUser,
    *,
    limit: int = 6,
    request=None,
) -> list:
    from a_agent.tools.vector_search import VectorHit

    query_embedding = embed_text(query) if query.strip() else None
    article_chunks = list(
        ArticleChunk.objects.filter(article_id=article_id).exclude(embedding=[]).order_by('chunk_index')
    )

    if query_embedding and article_chunks:
        scored: list[tuple[float, ArticleChunk]] = []
        for chunk in article_chunks:
            if not chunk.embedding:
                continue
            score = cosine_similarity(query_embedding, chunk.embedding)
            if score <= 0:
                continue
            scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)

        hits: list[VectorHit] = []
        for score, chunk in scored[:limit]:
            hit = _chunk_to_hit(chunk, user, request=request, score=score)
            if isinstance(hit, VectorHit):
                hits.append(hit)
        if hits:
            return hits

    baseline = get_baseline_article_chunks(article_id, user, limit=limit, request=request)
    return [
        VectorHit(**asdict(hit), score=0.0)
        for hit in baseline
    ]


def scoped_context_to_dicts(
    scope: ArticleScope | None,
    keyword_hits,
    chunk_hits,
    vector_hits,
) -> dict:
    return {
        'article': article_scope_to_dict(scope),
        'keyword_hits': [asdict(h) for h in keyword_hits],
        'chunk_hits': chunk_hits_to_dicts(chunk_hits),
        'vector_hits': [asdict(h) for h in vector_hits],
    }
