"""Management command to automatically import high-quality open-source technical articles from Dev.to."""

from __future__ import annotations

import io
import json
import logging
import random
import re
import urllib.error
import urllib.request
from datetime import date
from typing import Any

from django.contrib.auth import get_user_model
from django.core.files.images import ImageFile
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from wagtail.images.models import Image
from wagtail.models import Site

from a_blog.models import ArticlePage, BlogPage

logger = logging.getLogger(__name__)

USER_AGENT = 'Mozilla/5.0 (compatible; CheeseOBlog/1.0; +https://rqaistudio.com)'


def clean_html(raw_html: str) -> str:
    """Sanitize and clean up raw HTML from Dev.to."""
    if not raw_html:
        return ''

    # Remove script and style tags
    cleaned = re.sub(r'<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>', '', raw_html, flags=re.IGNORECASE)
    cleaned = re.sub(r'<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>', '', cleaned, flags=re.IGNORECASE)
    # Remove iframe embeds
    cleaned = re.sub(r'<iframe\b[^<]*(?:(?!<\/iframe>)<[^<]*)*<\/iframe>', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


class Command(BaseCommand):
    help = 'Import high-quality technical articles from Dev.to into the CheeseO blog.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tags',
            nargs='+',
            default=['python', 'machinelearning', 'ai', 'django', 'webdev'],
            help='Dev.to tags to search for (e.g., --tags python ai django).',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=2,
            help='Number of articles to import per tag (default: 2).',
        )
        parser.add_argument(
            '--paid-ratio',
            type=float,
            default=0.25,
            help='Fraction of articles to designate as paid/point-locked (default: 0.25).',
        )

    def _site_parent(self):
        site = Site.objects.get(is_default_site=True)
        return site.root_page

    def _get_default_image(self) -> Image | None:
        return Image.objects.first()

    def _fetch_image(self, image_url: str, title: str) -> Image | None:
        """Download remote cover image and save to Wagtail Image model."""
        if not image_url or not image_url.startswith('http'):
            return None

        try:
            req = urllib.request.Request(image_url, headers={'User-Agent': USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
                filename = f"devto_{slugify(title)[:30]}.jpg"
                return Image.objects.create(
                    title=f"Cover: {title[:50]}",
                    file=ImageFile(io.BytesIO(data), name=filename),
                )
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"Could not download cover image from {image_url}: {exc}"))
            return None

    def _fetch_json(self, url: str) -> Any:
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode('utf-8'))

    def handle(self, *args, **options):
        User = get_user_model()
        owner = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if owner is None:
            self.stderr.write(self.style.ERROR('No user found. Create a superuser first.'))
            return

        site_root = self._site_parent()
        blog = BlogPage.objects.child_of(site_root).first()
        if blog is None:
            blog = BlogPage.objects.first()

        if blog is None:
            self.stderr.write(self.style.ERROR('BlogPage parent not found.'))
            return

        default_image = self._get_default_image()
        tags_to_query = options['tags']
        limit_per_tag = options['limit']
        paid_ratio = options['paid_ratio']

        imported_count = 0
        seen_ids = set()

        for tag in tags_to_query:
            self.stdout.write(f'Fetching top articles for tag "#{tag}"...')
            list_url = f'https://dev.to/api/articles?tag={tag}&per_page={limit_per_tag * 2}&top=30'

            try:
                articles_list = self._fetch_json(list_url)
            except Exception as exc:
                self.stderr.write(self.style.WARNING(f'Failed to fetch tag #{tag}: {exc}'))
                continue

            tag_imported = 0
            for item in articles_list:
                if tag_imported >= limit_per_tag:
                    break

                article_id = item.get('id')
                title = item.get('title', '').strip()
                if not article_id or not title or article_id in seen_ids:
                    continue

                seen_ids.add(article_id)

                # Generate a clean, unique slug
                base_slug = slugify(title)[:45]
                slug = base_slug or f'article-{article_id}'
                if ArticlePage.objects.filter(slug=slug).exists():
                    slug = f'{slug[:40]}-{article_id}'

                if ArticlePage.objects.filter(title=title).exists():
                    self.stdout.write(f'  Skipping duplicate title: "{title[:40]}..."')
                    continue

                # Fetch full article detail for body_html
                detail_url = f'https://dev.to/api/articles/{article_id}'
                try:
                    detail = self._fetch_json(detail_url)
                except Exception as exc:
                    self.stderr.write(self.style.WARNING(f'  Failed to fetch detail for {article_id}: {exc}'))
                    continue

                body_html = clean_html(detail.get('body_html', ''))
                if len(body_html) < 200:
                    continue

                # Decide if paid
                is_free = random.random() > paid_ratio
                required_points = 0 if is_free else random.choice([10, 15, 20])

                # Cover image
                cover_url = detail.get('cover_image') or item.get('cover_image')
                article_image = self._fetch_image(cover_url, title) if cover_url else None
                if not article_image:
                    article_image = default_image

                # Description / Intro (Wagtail CharField max 80)
                raw_intro = (detail.get('description') or item.get('description') or title).strip()
                intro = (raw_intro[:77] + '...') if len(raw_intro) > 80 else raw_intro

                author_name = detail.get('user', {}).get('name', 'Community Author')
                caption = f'Source: Dev.to by {author_name}'[:80]

                # Create Wagtail ArticlePage
                article_page = ArticlePage(
                    title=title,
                    slug=slug,
                    intro=intro,
                    body=body_html,
                    date=date.today(),
                    image=article_image,
                    caption=caption,
                    owner=owner,
                    is_free=is_free,
                    required_points=required_points,
                )

                blog.add_child(instance=article_page)

                # Add tags
                dev_tags = detail.get('tags', [])
                if isinstance(dev_tags, list):
                    for t in dev_tags[:4]:
                        t_clean = slugify(str(t))
                        if t_clean:
                            article_page.tags.add(t_clean)

                revision = article_page.save_revision()
                revision.publish()

                tag_imported += 1
                imported_count += 1
                tier = 'FREE' if is_free else f'PAID ({required_points} pts)'
                self.stdout.write(
                    self.style.SUCCESS(f'  [+] [{tier}] Imported: {title} ({slug})')
                )

        self.stdout.write(
            self.style.SUCCESS(f'\nDone! Successfully imported {imported_count} articles from Dev.to.')
        )
