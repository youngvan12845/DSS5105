from __future__ import annotations

import logging

from django.dispatch import receiver
from wagtail.signals import page_published, page_unpublished

from a_agent.services.article_index import index_article, remove_article_index
from a_blog.models import ArticlePage

logger = logging.getLogger(__name__)


def _is_article_page(instance) -> bool:
    return isinstance(instance, ArticlePage)


@receiver(page_published)
def rebuild_article_index_on_publish(sender, instance, **kwargs):
    if not _is_article_page(instance):
        return

    try:
        chunk_count = index_article(instance)
        logger.info('Indexed article %s (%s chunks) after publish.', instance.pk, chunk_count)
    except Exception:
        logger.exception('Failed to index article %s after publish.', instance.pk)


@receiver(page_unpublished)
def remove_article_index_on_unpublish(sender, instance, **kwargs):
    if not _is_article_page(instance):
        return

    try:
        remove_article_index(instance.pk)
        logger.info('Removed index for unpublished article %s.', instance.pk)
    except Exception:
        logger.exception('Failed to remove index for article %s.', instance.pk)
