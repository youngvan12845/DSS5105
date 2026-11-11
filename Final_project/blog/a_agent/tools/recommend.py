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
    history = get_browsing_history(user, limit=5)
    hits: list[RecommendHit] = []
    seen: set[int] = {item.article_id for item in history if getattr(item, 'article_id', None)}

    if history:
        latest_id = history[0].article_id
        try:
            latest = ArticlePage.objects.get(pk=latest_id)
            # 1. If latest article belongs to a structured learning path, recommend the next unread step(s)
            try:
                from .reading_paths import _load_paths_config
                paths_cfg = _load_paths_config()
                for path_entry in paths_cfg.values():
                    steps = path_entry.get('steps', [])
                    slugs = [s.get('slug') for s in steps]
                    if latest.slug in slugs:
                        for step in steps:
                            step_article = ArticlePage.objects.filter(slug=step.get('slug')).live().first()
                            if step_article is None or step_article.pk in seen:
                                continue
                            access = get_article_access(user, step_article, request=request)
                            hits.append(
                                RecommendHit(
                                    article_id=step_article.pk,
                                    title=step_article.title,
                                    url=access.url,
                                    intro=step_article.intro,
                                    reason=step.get('note') or f'Next step after "{latest.title}"',
                                    is_free=step_article.is_free,
                                )
                            )
                            seen.add(step_article.pk)
                            if len(hits) >= limit:
                                break
                        break
            except Exception:
                pass

            # 2. Same tags
            tag_names = list(latest.tags.values_list('name', flat=True))
            if tag_names and len(hits) < limit:
                related = (
                    ArticlePage.objects.live()
                    .filter(tags__name__in=tag_names)
                    .exclude(pk__in=seen)
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
                    if len(hits) >= limit:
                        break
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
