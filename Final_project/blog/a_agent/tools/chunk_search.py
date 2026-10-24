from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from django.contrib.auth.models import AnonymousUser, User
from django.db.models import Q

from a_agent.models import ArticleChunk

from .access import can_user_read_full
from a_blog.models import ArticlePage

STOPWORDS = {
    'a', 'about', 'an', 'and', 'are', 'article', 'articles', 'as', 'at', 'be',
    'by', 'can', 'cover', 'covers', 'discuss', 'discussing', 'do', 'does', 'explain',
    'explains', 'find', 'for', 'from', 'give', 'help', 'how', 'i', 'in', 'is', 'it',
    'know', 'learn', 'master', 'me', 'my', 'need', 'of', 'on', 'or', 'our', 'please',
    'recommend', 'related', 'show', 'site', 'suggest', 'tell', 'that', 'the', 'their',
    'there', 'these', 'this', 'to', 'topics', 'use', 'used', 'using', 'want', 'was',
    'what', 'when', 'where', 'which', 'who', 'why', 'will', 'with', 'you',
}


def _extract_terms_and_phrases(query: str) -> tuple[list[str], list[str]]:
    raw_words = re.findall(r'[a-zA-Z0-9_\-\.]+', query.lower())
    terms = [w for w in raw_words if len(w) > 1 and w not in STOPWORDS]
    phrases = []
    for i in range(len(raw_words) - 1):
        w1, w2 = raw_words[i], raw_words[i + 1]
        if len(w1) > 1 and len(w2) > 1 and w1 not in STOPWORDS and w2 not in STOPWORDS:
            phrases.append(f'{w1} {w2}')
    return terms, phrases


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

    exact_chunks = list(
        ArticleChunk.objects.filter(
            Q(content__icontains=query)
            | Q(article_title__icontains=query)
            | Q(tags__icontains=query)
        ).order_by('article_id', 'chunk_index')[: limit * 3]
    )

    combined_chunks = list(exact_chunks)
    if len(combined_chunks) < limit:
        terms, phrases = _extract_terms_and_phrases(query)
        if terms or phrases:
            high_q = Q()
            for p in phrases:
                high_q |= Q(content__icontains=p) | Q(article_title__icontains=p)
            for t in terms:
                high_q |= Q(article_title__icontains=t) | Q(tags__icontains=t)

            high_candidates = list(ArticleChunk.objects.filter(high_q)[:limit * 10])

            broad_candidates = []
            if len(high_candidates) < limit * 3:
                term_q = Q()
                for t in terms:
                    term_q |= Q(content__icontains=t)
                broad_candidates = list(ArticleChunk.objects.filter(term_q)[:limit * 10])

            candidates = high_candidates + broad_candidates

            def score_chunk(c: ArticleChunk) -> int:
                score = 0
                t_low = c.article_title.lower()
                c_low = c.content.lower()
                tags_low = c.tags.lower()
                for p in phrases:
                    if p in t_low:
                        score += 30
                    if p in c_low:
                        score += 15
                for t in terms:
                    if t in t_low:
                        score += 10
                    if t in tags_low:
                        score += 6
                    if t in c_low:
                        score += 1
                return score

            candidates.sort(key=score_chunk, reverse=True)
            existing_ids = {c.pk for c in combined_chunks}
            for c in candidates:
                if c.pk not in existing_ids and score_chunk(c) > 0:
                    combined_chunks.append(c)
                    existing_ids.add(c.pk)

    hits: list[ChunkHit] = []
    seen_articles: set[int] = set()
    for chunk in combined_chunks:
        if chunk.article_id in seen_articles:
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
