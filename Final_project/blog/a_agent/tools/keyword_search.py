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
