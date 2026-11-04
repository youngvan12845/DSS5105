from __future__ import annotations

import logging
from dataclasses import dataclass

from a_agent.models import ArticleChunk
from a_agent.services.article_text import chunk_text, html_to_text
from a_agent.services.embeddings import embed_provider, embed_text, embed_texts, embeddings_available
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

    vectors: list[list[float]] = []
    if do_embed:
        vectors = embed_texts([c[:2000] for c in chunks])

    new_chunks = []
    for index, content in enumerate(chunks):
        vector = vectors[index] if index < len(vectors) else []
        new_chunks.append(
            ArticleChunk(
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
        )
    if new_chunks:
        ArticleChunk.objects.bulk_create(new_chunks, batch_size=100)
    return len(new_chunks)


def remove_article_index(article_id: int) -> None:
    ArticleChunk.objects.filter(article_id=article_id).delete()


def index_all_articles(*, do_embed: bool = False) -> IndexStats:
    if do_embed and not embeddings_available():
        raise RuntimeError(f'Embeddings service ({embed_provider()}) is not available.')

    from django.db import transaction

    articles = list(ArticlePage.objects.live().prefetch_related('tags'))
    pending_records: list[ArticleChunk] = []

    for article in articles:
        plain = html_to_text(str(article.body))
        intro = article.intro or ''
        merged = f'{article.title}\n{intro}\n{plain}'.strip()
        chunks = chunk_text(merged) or [merged[:800]]
        tags = ', '.join(tag.name for tag in article.tags.all())
        url = article.url or ''

        for index, content in enumerate(chunks):
            pending_records.append(
                ArticleChunk(
                    article_id=article.pk,
                    article_title=article.title,
                    article_url=url,
                    chunk_index=index,
                    content=content,
                    is_free=article.is_free,
                    required_points=article.required_points,
                    tags=tags,
                    embedding=[],
                )
            )

    embedded = 0
    if do_embed and pending_records:
        vectors = embed_texts([r.content[:2000] for r in pending_records], batch_size=40)
        for idx, record in enumerate(pending_records):
            if idx < len(vectors) and vectors[idx]:
                record.embedding = vectors[idx]
                embedded += 1

    with transaction.atomic():
        ArticleChunk.objects.all().delete()
        if pending_records:
            ArticleChunk.objects.bulk_create(pending_records, batch_size=200)

    return IndexStats(articles=len(articles), chunks=len(pending_records), embedded=embedded)
