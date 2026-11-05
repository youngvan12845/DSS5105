from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from django.contrib.auth.models import AnonymousUser, User
from django.db.models import Q

from a_agent.models import ArticleChunk

from .access import can_user_read_full
from a_blog.models import ArticlePage

STOPWORDS = {
    'a', 'about', 'according', 'add', 'all', 'an', 'and', 'any', 'are', 'article', 'articles',
    'as', 'ask', 'at', 'be', 'beginner', 'beginners', 'blog', 'both', 'bullet', 'by', 'can',
    'chapter', 'chart', 'charts', 'cite', 'citation', 'citations', 'citing', 'comment',
    'concepts', 'cook', 'cooking', 'course', 'cover', 'covers', 'define', 'defined',
    'definition', 'delete', 'deployment', 'deployments', 'discuss', 'discussing', 'do', 'does',
    'exact', 'exactly', 'expansion', 'explain', 'explains', 'find', 'finding', 'first', 'five',
    'for', 'from', 'getting', 'give', 'guide', 'have', 'help', 'how', 'i', 'in', 'into',
    'introduction', 'is', 'it', 'its', 'just', 'key', 'know', 'learn', 'leave', 'library',
    'link', 'links', 'list', 'main', 'master', 'me', 'mean', 'meaning', 'means', 'mention',
    'mentioned', 'mentioning', 'mentions', 'more', 'most', 'my', 'need', 'next', 'of', 'on',
    'one', 'only', 'or', 'ordered', 'other', 'our', 'overview', 'page', 'part', 'path', 'paths',
    'please', 'point', 'points', 'post', 'posts', 'question', 'questions', 'quote', 'read',
    'reading', 'recommend', 'recommended', 'related', 'remove', 'save', 'scratch', 'search',
    'second', 'section', 'sections', 'series', 'should', 'show', 'site', 'some', 'source',
    'sources', 'stand', 'stands', 'start', 'started', 'step', 'steps', 'structured', 'suggest',
    'summarize', 'summary', 'takeaway', 'takeaways', 'talk', 'talks', 'teach', 'teaching',
    'tell', 'that', 'the', 'their', 'them', 'there', 'these', 'third', 'this', 'those',
    'three', 'to', 'topic', 'topics', 'tutorial', 'tutorials', 'two', 'understand', 'use',
    'used', 'using', 'want', 'was', 'what', 'when', 'where', 'which', 'who', 'why', 'will',
    'with', 'write', 'you', 'your',
}

CJK_TOPIC_MAP = {
    '机器学习': ['machine', 'learning'],
    '機械學習': ['machine', 'learning'],
    '线性回归': ['linear', 'regression'],
    '線性回歸': ['linear', 'regression'],
    '梯度下降': ['gradient', 'descent'],
    '版本控制': ['version', 'control', 'git'],
    '分支冲突': ['branch', 'conflict', 'merge'],
    '分支衝突': ['branch', 'conflict', 'merge'],
    '容器': ['docker', 'container'],
    '智能体': ['agent', 'agentic'],
    '智能體': ['agent', 'agentic'],
    '检索增强': ['rag', 'retrieval'],
    '檢索增強': ['rag', 'retrieval'],
    '网页开发': ['web', 'http', 'rest'],
    '網頁開發': ['web', 'http', 'rest'],
    '缓存': ['cache', 'caching'],
    '快取': ['cache', 'caching'],
}


def _word_match(term: str, text: str) -> bool:
    return bool(re.search(rf'\b{re.escape(term)}\b', text))


def _extract_terms_and_phrases(query: str) -> tuple[list[str], list[str]]:
    raw_words = [w.strip('.-_') for w in re.findall(r'[a-zA-Z0-9_\-\.]+', query.lower())]
    raw_words = [w for w in raw_words if w]
    terms = [w for w in raw_words if len(w) > 1 and w not in STOPWORDS]
    phrases = []
    for i in range(len(raw_words) - 1):
        w1, w2 = raw_words[i], raw_words[i + 1]
        if len(w1) > 1 and len(w2) > 1 and w1 not in STOPWORDS and w2 not in STOPWORDS:
            phrases.append(f'{w1} {w2}')
    for cjk_key, eng_tokens in CJK_TOPIC_MAP.items():
        if cjk_key in query:
            for tok in eng_tokens:
                if tok not in terms:
                    terms.append(tok)
            if len(eng_tokens) >= 2:
                phrase = f'{eng_tokens[0]} {eng_tokens[1]}'
                if phrase not in phrases:
                    phrases.append(phrase)
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
        ArticleChunk.objects.defer('embedding').filter(
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

            high_candidates = list(ArticleChunk.objects.defer('embedding').filter(high_q)[:limit * 10])

            broad_candidates = []
            if len(high_candidates) < limit * 3:
                term_q = Q()
                for t in terms:
                    term_q |= Q(content__icontains=t)
                broad_candidates = list(ArticleChunk.objects.defer('embedding').filter(term_q)[:limit * 10])

            candidates = high_candidates + broad_candidates

            def score_chunk(c: ArticleChunk) -> int:
                score = 0
                t_low = c.article_title.lower()
                c_low = c.content.lower()
                tags_low = (c.tags or '').lower()
                title_or_tag_hits = 0
                body_hits = 0
                for p in phrases:
                    if p in t_low:
                        score += 30
                        title_or_tag_hits += 1
                    if p in c_low:
                        score += 15
                        body_hits += 1
                for t in terms:
                    if _word_match(t, t_low):
                        score += 10
                        title_or_tag_hits += 1
                    if _word_match(t, tags_low):
                        score += 6
                        title_or_tag_hits += 1
                    if _word_match(t, c_low):
                        score += 1
                        body_hits += 1
                if len(terms) >= 2 and title_or_tag_hits == 0 and body_hits < 2:
                    return 0
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
                content=content[:950],
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
