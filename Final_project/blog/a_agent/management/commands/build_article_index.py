from __future__ import annotations

from django.core.management.base import BaseCommand

from a_agent.services.article_index import index_all_articles
from a_agent.services.embeddings import (
    embed_model,
    embed_provider,
    embed_text,
    embeddings_available,
)


class Command(BaseCommand):
    help = 'Build searchable article chunks from Wagtail articles (optional vector embeddings).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--embed',
            action='store_true',
            help='Compute embeddings for vector search (Ollama, Cloudflare, or OpenAI).',
        )

    def handle(self, *args, **options):
        do_embed = options['embed']
        if do_embed:
            provider = embed_provider()
            if not embeddings_available():
                self.stderr.write(
                    self.style.ERROR(f'Embedding provider "{provider}" is not configured or reachable.')
                )
                return

            model_name = embed_model()
            probe = embed_text('health check')
            if probe is None:
                self.stderr.write(
                    self.style.ERROR(
                        f'Embedding model "{model_name}" ({provider}) failed health check.'
                    )
                )
                return

        try:
            stats = index_all_articles(do_embed=do_embed)
        except RuntimeError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return

        message = f'Indexed {stats.articles} articles into {stats.chunks} chunks.'
        if do_embed:
            message += f' Embeddings: {stats.embedded}/{stats.chunks}.'
        self.stdout.write(self.style.SUCCESS(message))
