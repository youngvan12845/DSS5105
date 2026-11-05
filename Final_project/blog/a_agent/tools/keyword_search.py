from __future__ import annotations

from dataclasses import asdict, dataclass

from django.contrib.auth.models import AnonymousUser, User

from a_blog.models import ArticlePage

from .access import get_article_access
from .chunk_search import STOPWORDS, _extract_terms_and_phrases, _word_match


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
    terms, _phrases = _extract_terms_and_phrases(query)
    cleaned_query = ' '.join(terms)
    search_target = cleaned_query if cleaned_query else query.strip()

    articles = list(ArticlePage.objects.live().autocomplete(search_target)[:limit])
    if not articles:
        articles = list(ArticlePage.objects.live().search(search_target)[:limit])

    if len(articles) < limit and cleaned_query and len(terms) > 1:
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
        tag_names = [t.name for t in article.tags.all()]
        if terms:
            t_low = (article.title or '').lower()
            tags_low = ' '.join(tag_names).lower()
            body_low = f'{article.intro or ""} {article.body or ""}'.lower()
            title_tag_match = any(_word_match(t, t_low) or _word_match(t, tags_low) for t in terms)
            body_match_count = sum(1 for t in terms if _word_match(t, body_low))
            if not title_tag_match and body_match_count < min(2, len(terms)):
                continue

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
                tags=tag_names,
                is_free=article.is_free,
                can_read_full=access.can_read_full,
                access_reason=access.reason,
            )
        )
    return hits


def hits_to_dicts(hits: list[SearchHit]) -> list[dict]:
    return [asdict(hit) for hit in hits]
