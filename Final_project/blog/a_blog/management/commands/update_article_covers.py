"""Management command to replace default/ugly thumbnails with curated, topic-specific 1200x675 tech cover images."""

from __future__ import annotations

import io
import urllib.request
from typing import Optional

from django.core.files.images import ImageFile
from django.core.management.base import BaseCommand
from django.db import transaction
from wagtail.images.models import Image

from a_blog.models import ArticlePage


USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'

ARTICLE_COVERS = {
    'python-basics-variables': {
        'title': 'Cover: Python Basics - Variables and Data Types',
        'url': 'https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=1200&h=675&fit=crop&q=85',
        'filename': 'cover_python_basics_variables.jpg',
    },
    'python-functions-modules': {
        'title': 'Cover: Python Functions and Modular Architecture',
        'url': 'https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=1200&h=675&fit=crop&q=85',
        'filename': 'cover_python_functions_modules.jpg',
    },
    'ml-supervised-unsupervised': {
        'title': 'Cover: Machine Learning - Supervised and Unsupervised',
        'url': 'https://images.unsplash.com/photo-1620712943543-bcc4688e7485?w=1200&h=675&fit=crop&q=85',
        'filename': 'cover_ml_supervised_unsupervised.jpg',
    },
    'gradient-descent-intuition': {
        'title': 'Cover: Gradient Descent Optimization and Loss Landscapes',
        'url': 'https://images.unsplash.com/photo-1635070041078-e363dbe005cb?w=1200&h=675&fit=crop&q=85',
        'filename': 'cover_gradient_descent_intuition.jpg',
    },
    'linear-regression-practice': {
        'title': 'Cover: Linear Regression in Practice and Diagnostics',
        'url': 'https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=1200&h=675&fit=crop&q=85',
        'filename': 'cover_linear_regression_practice.jpg',
    },
    'web-http-rest': {
        'title': 'Cover: Web Development Protocols - HTTP and REST APIs',
        'url': 'https://images.unsplash.com/photo-1544197150-b99a580bb7a8?w=1200&h=675&fit=crop&q=85',
        'filename': 'cover_web_http_rest.jpg',
    },
    'django-project-structure': {
        'title': 'Cover: Django Project Architecture and Engineering',
        'url': 'https://images.unsplash.com/photo-1507238691740-187a5b1d37b8?w=1200&h=675&fit=crop&q=85',
        'filename': 'cover_django_project_structure.jpg',
    },
    'wagtail-quickstart': {
        'title': 'Cover: Wagtail CMS Quickstart and Digital Publishing',
        'url': 'https://images.unsplash.com/photo-1499750310107-5fef28a66643?w=1200&h=675&fit=crop&q=85',
        'filename': 'cover_wagtail_quickstart.jpg',
    },
    'what-is-rag': {
        'title': 'Cover: What Is RAG - Retrieval-Augmented Generation',
        'url': 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=1200&h=675&fit=crop&q=85',
        'filename': 'cover_what_is_rag.jpg',
    },
    'agent-tool-design': {
        'title': 'Cover: Autonomous Agent Tool Design and Execution',
        'url': 'https://images.unsplash.com/photo-1485827404703-89b55fcc595e?w=1200&h=675&fit=crop&q=85',
        'filename': 'cover_agent_tool_design.jpg',
    },
    'path-ml-getting-started': {
        'title': 'Cover: Machine Learning Getting Started Roadmap',
        'url': 'https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=1200&h=675&fit=crop&q=85',
        'filename': 'cover_path_ml_getting_started.jpg',
    },
    'path-python-web': {
        'title': 'Cover: Python Web Developer Learning Journey',
        'url': 'https://images.unsplash.com/photo-1498050108023-c5249f4df085?w=1200&h=675&fit=crop&q=85',
        'filename': 'cover_path_python_web.jpg',
    },
    'nginx-silently-rejects-the-new-http-query-met': {
        'title': 'Cover: Nginx HTTP QUERY Rejection and Reverse Proxying',
        'url': 'https://images.unsplash.com/photo-1558494949-ef010cbdcc31?w=1200&h=675&fit=crop&q=85',
        'filename': 'cover_nginx_http_query.jpg',
    },
    'fixing-delicate-cache-mismatches-in-a-brownfi': {
        'title': 'Cover: Distributed Caching and Cache Invalidation',
        'url': 'https://images.unsplash.com/photo-1518770660439-4636190af475?w=1200&h=675&fit=crop&q=85',
        'filename': 'cover_cache_mismatches.jpg',
    },
}


class Command(BaseCommand):
    help = 'Replace default/ugly article covers with topic-specific 1200x675 tech imagery.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-download and update even if article already has a custom cover.',
        )
        parser.add_argument(
            '--slug',
            type=str,
            default='',
            help='Update only a specific article by slug.',
        )

    def _fetch_and_create_image(self, title: str, url: str, filename: str) -> Optional[Image]:
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            return Image.objects.create(
                title=title,
                file=ImageFile(io.BytesIO(data), name=filename),
            )
        except Exception as exc:
            self.stderr.write(self.style.WARNING(f'Failed to fetch image {url}: {exc}'))
            return None

    def handle(self, *args, **options):
        force = options['force']
        target_slug = options['slug']

        items = ARTICLE_COVERS.items()
        if target_slug:
            if target_slug not in ARTICLE_COVERS:
                self.stderr.write(self.style.ERROR(f'Slug "{target_slug}" not configured in ARTICLE_COVERS.'))
                return
            items = [(target_slug, ARTICLE_COVERS[target_slug])]

        success_count = 0
        skip_count = 0

        for slug, meta in items:
            try:
                article = ArticlePage.objects.get(slug=slug)
            except ArticlePage.DoesNotExist:
                self.stderr.write(self.style.WARNING(f'Article with slug "{slug}" not found in database.'))
                continue

            # Check if article currently uses Default cover (id 1 or cheese.png)
            is_default = (
                article.image is None
                or article.image.id == 1
                or 'cheese' in (article.image.file.name or '').lower()
                or 'default' in (article.image.title or '').lower()
            )

            if not is_default and not force:
                self.stdout.write(f'Skipping "{slug}" (already has custom cover: {article.image.title})')
                skip_count += 1
                continue

            self.stdout.write(f'Updating cover for "{slug}"...')

            # Reuse existing Image model if already created with this exact title
            existing_img = Image.objects.filter(title=meta['title']).first()
            if existing_img and not force:
                img_obj = existing_img
            else:
                img_obj = self._fetch_and_create_image(
                    title=meta['title'],
                    url=meta['url'],
                    filename=meta['filename'],
                )

            if not img_obj:
                self.stderr.write(self.style.ERROR(f'Could not obtain image for "{slug}".'))
                continue

            with transaction.atomic():
                article.image = img_obj
                article.save(update_fields=['image'])
                # Also update Wagtail revision and publish live
                revision = article.save_revision()
                revision.publish()

            self.stdout.write(self.style.SUCCESS(f'✓ Updated "{slug}" -> {img_obj.title} ({img_obj.width}x{img_obj.height})'))
            success_count += 1

        self.stdout.write(self.style.SUCCESS(f'\nFinished updating covers: {success_count} updated, {skip_count} skipped.'))
