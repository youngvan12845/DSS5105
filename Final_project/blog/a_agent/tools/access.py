from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth.models import AnonymousUser, User

from a_blog.models import ArticlePage


@dataclass
class ArticleAccess:
    article_id: int
    title: str
    url: str
    is_free: bool
    can_read_full: bool
    required_points: int
    reason: str


def _session_has_article_access(request, article_id: int) -> bool:
    if request is None:
        return False
    return bool(request.session.get(f'article_access_{article_id}', False))


def can_user_read_full(
    user: User | AnonymousUser,
    article: ArticlePage,
    *,
    request=None,
) -> tuple[bool, str]:
    if article.is_free:
        return True, 'free'

    if not user.is_authenticated:
        return False, 'login_required'

    profile = user.profile
    if profile.has_valid_subscription():
        return True, 'subscription'

    if _session_has_article_access(request, article.pk):
        return True, 'purchased'

    return False, 'paywall'


def get_article_access(user: User | AnonymousUser, article: ArticlePage, request=None) -> ArticleAccess:
    url = article.get_url(request) if request else (article.url or '')
    can_read, reason = can_user_read_full(user, article, request=request)
    return ArticleAccess(
        article_id=article.pk,
        title=article.title,
        url=url,
        is_free=article.is_free,
        can_read_full=can_read,
        required_points=article.required_points,
        reason=reason,
    )
