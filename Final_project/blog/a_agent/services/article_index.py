from __future__ import annotations

import logging
from dataclasses import dataclass

from a_agent.models import ArticleChunk
from a_agent.services.article_text import chunk_text, html_to_text
from a_agent.services.embeddings import embed_text, embeddings_available
from a_blog.models import ArticlePage

logger = logging.getLogger(__name__)


@dataclass
class IndexStats:
    articles: int
    chunks: int
    embedded: int


def index_article(article: ArticlePage, *, do_embed: bool | None = None) -> int:
    """Rebuild retrieval chunks for one article. Returns chunk count (0 if unpublished)."""

    ArticleChunk.objects.filter(article_id=article.pk).delete()
    if not article.live:
        return 0

    if do_embed is None:
        do_embed = embeddings_available()

    plain = html_to_text(str(article.body))
    intro = article.intro or ''
    merged = f'{article.title}\n{intro}\n{plain}'.strip()
    chunks = chunk_text(merged) or [merged[:800]]
    tags = ', '.join(tag.name for tag in article.tags.all())
    url = article.url or ''

    created = 0
    for index, content in enumerate(chunks):
        vector: list[float] = []
        if do_embed:
            vector = embed_text(content[:2000]) or []

        ArticleChunk.objects.create(
            article_id=article.pk,
            article_title=article.title,
            article_url=url,
            chunk_index=index,
            content=content,
            is_free=article.is_free,
            required_points=article.required_points,
            tags=tags,
            embedding=vector,
        )
        created += 1
    return created


def remove_article_index(article_id: int) -> None:
    ArticleChunk.objects.filter(article_id=article_id).delete()


def index_all_articles(*, do_embed: bool = False) -> IndexStats:
    if do_embed and not embeddings_available():
        raise RuntimeError('Ollama is not running.')

    total_chunks = 0
    embedded = 0
    articles = ArticlePage.objects.live()

    for article in articles:
        chunk_count = index_article(article, do_embed=do_embed)
        total_chunks += chunk_count
        if do_embed:
            embedded += ArticleChunk.objects.filter(article_id=article.pk).exclude(embedding=[]).count()

    return IndexStats(articles=articles.count(), chunks=total_chunks, embedded=embedded)
