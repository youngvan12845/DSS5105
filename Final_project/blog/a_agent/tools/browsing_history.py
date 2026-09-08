from __future__ import annotations

from dataclasses import asdict, dataclass

from django.contrib.auth.models import AnonymousUser, User

from a_users.models import BrowsingHistory


@dataclass
class HistoryItem:
    article_id: int
    article_title: str
    article_url: str
    viewed_at: str


def get_browsing_history(
    user: User | AnonymousUser,
    *,
    limit: int = 5,
) -> list[HistoryItem]:
    if not user.is_authenticated:
        return []

    rows = BrowsingHistory.objects.filter(user=user).order_by('-viewed_at')[:limit]
    return [
        HistoryItem(
            article_id=row.article_id,
            article_title=row.article_title,
            article_url=row.article_url,
            viewed_at=row.viewed_at.isoformat(),
        )
        for row in rows
    ]


def history_to_dicts(items: list[HistoryItem]) -> list[dict]:
    return [asdict(item) for item in items]
