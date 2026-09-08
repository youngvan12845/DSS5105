from __future__ import annotations

from dataclasses import asdict, dataclass

from django.contrib.auth.models import AnonymousUser, User

from a_blog.models import ArticlePage

from .access import get_article_access
from .browsing_history import get_browsing_history


@dataclass
class RecommendHit:
    article_id: int
    title: str
    url: str
    intro: str
    reason: str
    is_free: bool


def recommend_articles(
    user: User | AnonymousUser,
    *,
    limit: int = 3,
    request=None,
) -> list[RecommendHit]:
    history = get_browsing_history(user, limit=1)
    hits: list[RecommendHit] = []
    seen: set[int] = set()

    if history:
        latest_id = history[0].article_id
        seen.add(latest_id)
        try:
            latest = ArticlePage.objects.get(pk=latest_id)
            tag_names = list(latest.tags.values_list('name', flat=True))
            if tag_names:
                related = (
                    ArticlePage.objects.live()
                    .filter(tags__name__in=tag_names)
                    .exclude(pk=latest_id)
                    .distinct()[:limit]
                )
                for article in related:
                    access = get_article_access(user, article, request=request)
                    hits.append(
                        RecommendHit(
                            article_id=article.pk,
                            title=article.title,
                            url=access.url,
                            intro=article.intro,
                            reason=f'Same topic as "{latest.title}"',
                            is_free=article.is_free,
                        )
                    )
                    seen.add(article.pk)
        except ArticlePage.DoesNotExist:
            pass

    if len(hits) < limit:
        for article in ArticlePage.objects.live().order_by('-date')[: limit * 2]:
            if article.pk in seen:
                continue
            access = get_article_access(user, article, request=request)
            hits.append(
                RecommendHit(
                    article_id=article.pk,
                    title=article.title,
                    url=access.url,
                    intro=article.intro,
                    reason='Latest articles',
                    is_free=article.is_free,
                )
            )
            seen.add(article.pk)
            if len(hits) >= limit:
                break

    return hits


def recommend_hits_to_dicts(hits: list[RecommendHit]) -> list[dict]:
    return [asdict(hit) for hit in hits]
