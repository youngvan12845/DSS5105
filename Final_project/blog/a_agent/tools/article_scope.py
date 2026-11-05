from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from bs4 import BeautifulSoup
from django.contrib.auth.models import AnonymousUser, User
from django.db.models import Q

from a_agent.models import ArticleChunk
from a_agent.services.embeddings import cosine_similarity, embed_text
from a_agent.tools.access import get_article_access
from a_agent.tools.chunk_search import (
    ChunkHit,
    _extract_terms_and_phrases,
    chunk_hits_to_dicts,
)
from a_agent.tools.keyword_search import SearchHit
from a_blog.models import ArticlePage

from .access import can_user_read_full

SUMMARY_QUERY_HINTS = (
    'summarize',
    'summary',
    'five bullet',
    'bullet points',
    'overview',
    'tl;dr',
    'tldr',
    '總結',
    '摘要',
    '重點',
    '大綱',
)


def is_summary_query(query: str) -> bool:
    q = (query or '').lower()
    return any(h in q for h in SUMMARY_QUERY_HINTS)


@dataclass
class ArticleScope:
    article_id: int
    title: str
    url: str
    intro: str
    is_free: bool
    can_read_full: bool
    access_reason: str
    slug: str = ''


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
        url=article.url or '',
        intro=article.intro or '',
        is_free=access.is_free,
        can_read_full=access.can_read_full,
        access_reason=access.reason,
        slug=article.slug or '',
    )


def article_scope_to_dict(scope: ArticleScope | None) -> dict | None:
    if scope is None:
        return None
    return asdict(scope)


def _extract_article_headings(html: str) -> list[str]:
    if not html:
        return []
    try:
        soup = BeautifulSoup(html, 'html.parser')
        headings = []
        for tag in soup.find_all(['h1', 'h2', 'h3', 'h4']):
            text = tag.get_text(' ', strip=True)
            if text and text not in headings:
                headings.append(text)
        return headings
    except Exception:
        return []


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

    if scope.can_read_full or scope.is_free:
        headings = _extract_article_headings(body_text)
        if headings:
            outline = ' | '.join(headings[:25])
            snippet = f'{snippet}\n[Article Section Outline]: {outline}'
    else:
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
        content=content[:950],
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
    limit: int = 8,
    request=None,
) -> list[ChunkHit]:
    all_chunks = list(ArticleChunk.objects.defer('embedding').filter(article_id=article_id).order_by('chunk_index'))
    if not all_chunks:
        return []

    if len(all_chunks) <= limit:
        selected = all_chunks
    else:
        chosen_indices: set[int] = {0, len(all_chunks) - 1}
        # Prioritize chunks with explicit section definitions, numbered headings, or key config analysis
        for idx, c in enumerate(all_chunks):
            if len(chosen_indices) >= limit:
                break
            c_text = c.content
            if re.search(r'(?:^|\n)\d+\.\s+[A-Z0-9]', c_text) and (
                ':' in c_text or 'What is it?' in c_text
            ):
                chosen_indices.add(idx)
            elif any(kw in c_text.lower() for kw in ('limit_except', 'proxy_pass', 'model context protocol', 'what to do about it')):
                chosen_indices.add(idx)

        # Fill remaining slots evenly across the full article span
        if len(chosen_indices) < limit:
            step = max(1, (len(all_chunks) - 1) / max(1, limit - 1))
            for i in range(limit):
                if len(chosen_indices) >= limit:
                    break
                idx = min(len(all_chunks) - 1, int(round(i * step)))
                chosen_indices.add(idx)

        # If still under limit, fill sequentially
        for idx in range(len(all_chunks)):
            if len(chosen_indices) >= limit:
                break
            chosen_indices.add(idx)

        selected = [all_chunks[i] for i in sorted(chosen_indices)[:limit]]

    hits: list[ChunkHit] = []
    for chunk in selected:
        hit = _chunk_to_hit(chunk, user, request=request)
        if hit:
            hits.append(hit)
    return hits


def search_scoped_article_chunks(
    article_id: int,
    query: str,
    user: User | AnonymousUser,
    *,
    limit: int = 8,
    request=None,
) -> list[ChunkHit]:
    if not query.strip() or is_summary_query(query):
        return get_baseline_article_chunks(
            article_id, user, limit=max(limit, 12) if is_summary_query(query) else limit, request=request
        )

    all_chunks = list(ArticleChunk.objects.defer('embedding').filter(article_id=article_id).order_by('chunk_index'))
    if not all_chunks:
        return []

    q_lower = query.strip().lower()
    terms, phrases = _extract_terms_and_phrases(query)

    scored: list[tuple[int, int, ArticleChunk]] = []
    for chunk in all_chunks:
        c_low = chunk.content.lower()
        t_low = chunk.article_title.lower()
        tags_low = chunk.tags.lower()
        score = 0

        if q_lower in c_low:
            score += 50
        for p in phrases:
            if p in c_low:
                score += 25
            if p in t_low:
                score += 15
        for t in terms:
            # Exact word boundary match
            word_matches = len(re.findall(rf'\b{re.escape(t)}\b', c_low))
            if word_matches:
                score += 12 + min(word_matches, 5) * 4
                # Bonus if term appears in a heading or definition line (e.g. "8. MCP: Model Context Protocol")
                if re.search(rf'(?:^|\n)[^\n]*\b{re.escape(t)}\b\s*[:\-—]', c_low):
                    score += 40
                if 'what is it' in c_low or 'is an open protocol' in c_low or 'stands for' in c_low:
                    score += 20
            elif t in c_low:
                score += 5
            if t in tags_low:
                score += 4

        if score > 0:
            scored.append((score, -chunk.chunk_index, chunk))

    if not scored:
        return get_baseline_article_chunks(article_id, user, limit=limit, request=request)

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    hits: list[ChunkHit] = []
    for _, _, chunk in scored[:limit]:
        hit = _chunk_to_hit(chunk, user, request=request)
        if hit:
            hits.append(hit)
    return hits


def search_scoped_article_vectors(
    article_id: int,
    query: str,
    user: User | AnonymousUser,
    *,
    limit: int = 8,
    request=None,
) -> list:
    from a_agent.tools.vector_search import VectorHit

    if is_summary_query(query):
        baseline = get_baseline_article_chunks(article_id, user, limit=max(limit, 12), request=request)
        return [VectorHit(**asdict(hit), score=1.0) for hit in baseline]

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

    if query.strip() and not is_summary_query(query):
        return []

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
