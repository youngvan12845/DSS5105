from __future__ import annotations

from dataclasses import asdict, dataclass

from django.contrib.auth.models import AnonymousUser, User

from a_blog.models import ArticlePage

from .access import get_article_access


@dataclass
class SearchHit:
    article_id: int
    title: str
    url: str
    intro: str
    snippet: str
    tags: list[str]
    is_free: bool
    can_read_full: bool
    access_reason: str


import re

STOPWORDS = {
    'a', 'about', 'an', 'and', 'are', 'article', 'articles', 'as', 'at', 'be',
    'by', 'can', 'cover', 'covers', 'discuss', 'discussing', 'do', 'does', 'for',
    'from', 'how', 'i', 'in', 'is', 'it', 'me', 'my', 'of', 'on', 'or', 'our',
    'please', 'recommend', 'related', 'site', 'suggest', 'tell', 'that', 'the',
    'their', 'there', 'these', 'this', 'to', 'topics', 'was', 'what', 'when',
    'where', 'which', 'who', 'why', 'will', 'with', 'you',
}


def keyword_search_articles(
    query: str,
    user: User | AnonymousUser,
    *,
    limit: int = 5,
    request=None,
) -> list[SearchHit]:
    """Baseline B: Wagtail keyword/autocomplete search."""

    if not query.strip():
        return []

    hits: list[SearchHit] = []
    articles = list(ArticlePage.objects.live().autocomplete(query)[:limit])
    if not articles:
        articles = list(ArticlePage.objects.live().search(query)[:limit])

    if len(articles) < limit:
        cleaned_words = [
            w for w in re.findall(r'[a-zA-Z0-9_\-]+', query) if w.lower() not in STOPWORDS
        ]
        cleaned_query = ' '.join(cleaned_words)
        if cleaned_query and cleaned_query.lower() != query.lower().strip():
            fallback_articles = list(
                ArticlePage.objects.live().search(cleaned_query, operator='or')[:limit]
            )
            existing_ids = {a.pk for a in articles}
            for a in fallback_articles:
                if a.pk not in existing_ids:
                    articles.append(a)
                    existing_ids.add(a.pk)
                if len(articles) >= limit:
                    break

    for article in articles:
        access = get_article_access(user, article, request=request)
        body_text = article.body or ''
        snippet_source = article.intro or body_text
        snippet = snippet_source[:240]
        if not access.can_read_full and not access.is_free:
            snippet = f'[Paid preview] {article.intro or article.title}'

        hits.append(
            SearchHit(
                article_id=article.pk,
                title=article.title,
                url=access.url,
                intro=article.intro,
                snippet=snippet,
                tags=[t.name for t in article.tags.all()],
                is_free=article.is_free,
                can_read_full=access.can_read_full,
                access_reason=access.reason,
            )
        )
    return hits


def hits_to_dicts(hits: list[SearchHit]) -> list[dict]:
    return [asdict(hit) for hit in hits]
