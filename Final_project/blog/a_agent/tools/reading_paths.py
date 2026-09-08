from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from django.contrib.auth.models import AnonymousUser, User

from a_blog.models import ArticlePage

from .access import get_article_access


@dataclass
class PathStep:
    order: int
    article_id: int
    title: str
    url: str
    intro: str
    is_free: bool
    note: str


@dataclass
class ReadingPath:
    topic: str
    title: str
    steps: list[PathStep]


def _load_paths_config() -> dict:
    path = Path(__file__).resolve().parent.parent / 'data' / 'reading_paths.json'
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def find_reading_path(query: str) -> ReadingPath | None:
    q = query.lower()
    config = _load_paths_config()
    matched_topic = None
    for topic in config:
        if topic in q:
            matched_topic = topic
            break
    if matched_topic is None:
        for topic in config:
            tokens = topic.split()
            if all(token in q for token in tokens):
                matched_topic = topic
                break
    if matched_topic is None:
        return None

    entry = config[matched_topic]
    steps: list[PathStep] = []
    for index, step in enumerate(entry.get('steps', []), start=1):
        slug = step['slug']
        article = ArticlePage.objects.filter(slug=slug).live().first()
        if article is None:
            continue
        steps.append(
            PathStep(
                order=index,
                article_id=article.pk,
                title=article.title,
                url=article.url or '',
                intro=article.intro,
                is_free=article.is_free,
                note=step.get('note', ''),
            )
        )
    if not steps:
        return None
    return ReadingPath(topic=matched_topic, title=entry.get('title', matched_topic.title()), steps=steps)


def get_reading_path_for_user(
    query: str,
    user: User | AnonymousUser,
    *,
    request=None,
) -> ReadingPath | None:
    path = find_reading_path(query)
    if path is None:
        return None

    resolved_steps: list[PathStep] = []
    for step in path.steps:
        try:
            article = ArticlePage.objects.get(pk=step.article_id)
        except ArticlePage.DoesNotExist:
            continue
        access = get_article_access(user, article, request=request)
        resolved_steps.append(
            PathStep(
                order=step.order,
                article_id=step.article_id,
                title=step.title,
                url=access.url,
                intro=step.intro,
                is_free=step.is_free,
                note=step.note,
            )
        )
    if not resolved_steps:
        return None
    return ReadingPath(topic=path.topic, title=path.title, steps=resolved_steps)


def reading_path_to_dict(path: ReadingPath | None) -> dict | None:
    if path is None:
        return None
    return {
        'topic': path.topic,
        'title': path.title,
        'steps': [asdict(step) for step in path.steps],
    }
