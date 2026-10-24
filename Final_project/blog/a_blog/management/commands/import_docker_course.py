"""
Management command to crawl and import the complete Docker Basics course
from https://d-libro.com/course/docker-basics/ into CheeseO Wagtail CMS,
uploading all technical diagrams and covers to Supabase S3 storage.
"""

from __future__ import annotations

import io
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.images import ImageFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from wagtail.images.models import Image
from wagtail.models import Page, Site

from a_blog.models import ArticlePage, BlogPage

COURSE_URL = "https://d-libro.com/course/docker-basics/"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
SUPABASE_PROJECT_REF = "gkucyoqzaudzmscgvmmh"
PUBLIC_MEDIA_BASE = f"https://{SUPABASE_PROJECT_REF}.supabase.co/storage/v1/object/public/media"


def fetch_url(url: str, retries: int = 3, timeout: int = 15) -> Optional[bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.getcode() == 200:
                    return resp.read()
        except Exception:
            time.sleep(1 + attempt)
    return None


class Command(BaseCommand):
    help = "Crawl and import Docker Basics course topics from d-libro.com into Wagtail and Supabase S3."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Limit number of topics to import (0 = all 27 topics).",
        )
        parser.add_argument(
            "--chapter",
            type=int,
            default=0,
            help="Import only a specific chapter (1 to 6).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-import and update existing articles even if slug exists.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        target_chapter = options["chapter"]
        force = options["force"]

        self.stdout.write(self.style.SUCCESS("=" * 70))
        self.stdout.write(self.style.SUCCESS("  Docker Basics Course Importer (d-libro.com -> Supabase S3)"))
        self.stdout.write(self.style.SUCCESS("=" * 70))

        # 1. Ensure series parent page exists under Home
        series_page = self._get_or_create_series_parent()
        self.stdout.write(f"Series parent page: id={series_page.id}, title='{series_page.title}', url={series_page.url}")

        # 2. Scrape course index curriculum
        self.stdout.write("Fetching Docker course curriculum index...")
        html_bytes = fetch_url(COURSE_URL)
        if not html_bytes:
            self.stdout.write(self.style.ERROR(f"Failed to fetch course index: {COURSE_URL}"))
            return

        soup = BeautifulSoup(html_bytes.decode("utf-8"), "html.parser")
        chapters = self._parse_curriculum(soup)
        self.stdout.write(f"Found {len(chapters)} chapters in curriculum.")

        total_imported = 0
        total_skipped = 0
        uploaded_images_count = 0

        user = get_user_model().objects.filter(is_superuser=True).first() or get_user_model().objects.first()
        fallback_cover = Image.objects.first()

        for ch_idx, (ch_title, topics) in enumerate(chapters, start=1):
            if target_chapter and ch_idx != target_chapter:
                continue

            self.stdout.write(self.style.MIGRATE_HEADING(f"\n[{ch_title}] ({len(topics)} topics)"))

            for t_idx, topic in enumerate(topics, start=1):
                if limit and total_imported >= limit:
                    break

                topic_url = topic["url"]
                topic_title = topic["title"]
                cover_src = topic.get("cover_src")

                # Derive clean unique slug
                raw_slug = topic_url.strip("/").split("/")[-1]
                slug = f"docker-{raw_slug}" if not raw_slug.startswith("docker-") else raw_slug

                # Check if already exists
                existing = ArticlePage.objects.filter(slug=slug).first()
                if existing and not force:
                    self.stdout.write(f"  [{t_idx}/{len(topics)}] Skip existing: {topic_title} ({slug})")
                    total_skipped += 1
                    continue

                self.stdout.write(f"  [{t_idx}/{len(topics)}] Fetching: {topic_title} -> {topic_url}")
                page_bytes = fetch_url(topic_url)
                if not page_bytes:
                    self.stdout.write(self.style.WARNING(f"    Failed to download page: {topic_url}"))
                    continue

                # Parse topic page content
                t_soup = BeautifulSoup(page_bytes.decode("utf-8"), "html.parser")
                parsed_data = self._parse_topic_content(t_soup, topic_title, slug)
                if not parsed_data:
                    self.stdout.write(self.style.WARNING(f"    No editor-content found for: {topic_title}"))
                    continue

                final_title = parsed_data["title"]
                intro = parsed_data["intro"]
                clean_intro = (intro or final_title).strip()[:80]
                body_html = parsed_data["body_html"]
                in_body_images = parsed_data["images"]

                # Process in-body technical diagrams (upload to Supabase S3)
                for orig_src in in_body_images:
                    new_s3_url = self._upload_image_to_supabase(orig_src, slug)
                    if new_s3_url:
                        body_html = body_html.replace(orig_src, new_s3_url)
                        uploaded_images_count += 1

                # Process cover image
                cover_image_obj = None
                if cover_src:
                    cover_image_obj = self._create_wagtail_image(cover_src, final_title, slug)
                if not cover_image_obj:
                    cover_image_obj = fallback_cover

                # Designate advanced chapters (e.g. Chapter 4 Networking/Volumes, Chapter 6 Production Deployment) with points
                is_free = True
                required_points = 0
                if ch_idx in (4, 6) or any(kw in slug for kw in ("networking", "storage", "compose", "production", "persistent")):
                    is_free = False
                    required_points = 30

                # Create or update ArticlePage under series_page
                if existing:
                    existing.title = final_title
                    existing.intro = clean_intro
                    existing.body = body_html
                    if cover_image_obj:
                        existing.image = cover_image_obj
                    elif not existing.image:
                        existing.image = fallback_cover
                    existing.is_free = is_free
                    existing.required_points = required_points
                    existing.series_slug = "docker"
                    existing.series_title = "Docker Basics Course"
                    existing.chapter_number = ch_idx
                    existing.chapter_title = ch_name
                    existing.save()
                    existing.save_revision().publish()
                    self.stdout.write(self.style.SUCCESS(f"    Updated: {final_title} ({slug})"))
                else:
                    new_article = ArticlePage(
                        title=final_title,
                        slug=slug,
                        intro=clean_intro,
                        body=body_html,
                        date=date.today(),
                        image=cover_image_obj,
                        is_free=is_free,
                        required_points=required_points,
                        series_slug="docker",
                        series_title="Docker Basics Course",
                        chapter_number=ch_idx,
                        chapter_title=ch_name,
                        owner=user,
                    )
                    series_page.add_child(instance=new_article)
                    new_article.save_revision().publish()

                    # Add taxonomy tags (excluding chapter - chapter is now a model field)
                    new_article.tags.add(
                        "docker",
                        "container",
                        "devops",
                        "deployment",
                        "docker-series"
                    )
                    new_article.save()
                    self.stdout.write(self.style.SUCCESS(f"    Created & Published: {final_title} ({slug})"))

                total_imported += 1
                time.sleep(0.2)  # Respectful crawl delay

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 70))
        self.stdout.write(self.style.SUCCESS(f"  Docker Import Completed: {total_imported} imported, {total_skipped} skipped"))
        self.stdout.write(self.style.SUCCESS(f"  Uploaded {uploaded_images_count} diagrams to Supabase S3"))
        self.stdout.write(self.style.SUCCESS("=" * 70))

    def _get_or_create_series_parent(self) -> BlogPage:
        """Find or create the 'series' BlogPage container under the Home page."""
        site = Site.objects.get(is_default_site=True)
        home = site.root_page

        series_page = BlogPage.objects.filter(slug="series").first()
        if not series_page:
            series_page = BlogPage(
                title="Engineering Series Learning Tracks",
                slug="series",
                body="Structured hands-on engineering curricula covering Git, Docker, DevOps, and cloud deployment with interactive architecture diagrams.",
            )
            home.add_child(instance=series_page)
            series_page.save_revision().publish()
        else:
            # Update title to reflect multi-series learning tracks
            if series_page.title == "Git & GitHub Master Course":
                series_page.title = "Engineering Series Learning Tracks"
                series_page.body = "Structured hands-on engineering curricula covering Git, Docker, DevOps, and cloud deployment with interactive architecture diagrams."
                series_page.save()
                series_page.save_revision().publish()
        return series_page

    def _parse_curriculum(self, soup: BeautifulSoup) -> List[Tuple[str, List[Dict[str, str]]]]:
        """Parse chapter names and topic cards from d-libro course index."""
        chapters = []
        for ch_idx, ch_div in enumerate(soup.find_all("div", class_="chapter-container"), start=1):
            acc = ch_div.find("div", class_="accordion-root")
            if acc:
                parts = acc.get_text(" | ", strip=True).split(" | ")
                ch_name = parts[0].strip() if parts else f"Chapter {ch_idx}"
            else:
                ch_name_el = ch_div.find("div", class_="chapter-name-div")
                ch_name = ch_name_el.get_text(strip=True) if ch_name_el else f"Chapter {ch_idx}"

            topics = []
            for card in ch_div.find_all("div", class_="chapter-card"):
                a_tag = card.find("a")
                if not a_tag or not a_tag.get("href"):
                    continue
                href = a_tag["href"]
                if href.startswith("/"):
                    href = "https://d-libro.com" + href

                img_tag = card.find("img")
                title = img_tag.get("alt", "").strip() if img_tag else ""
                cover_src = ""
                if img_tag:
                    raw_src = img_tag.get("src", "")
                    if "url=" in raw_src:
                        parsed_url = urllib.parse.parse_qs(urllib.parse.urlsplit(raw_src).query).get("url")
                        cover_src = parsed_url[0] if parsed_url else raw_src
                    else:
                        cover_src = raw_src

                if href not in [t["url"] for t in topics]:
                    topics.append({
                        "url": href,
                        "title": title or href.strip("/").split("/")[-1].replace("-", " ").title(),
                        "cover_src": cover_src,
                    })

            if topics:
                chapters.append((ch_name, topics))

        return chapters

    def _parse_topic_content(self, soup: BeautifulSoup, fallback_title: str, slug: str) -> Optional[Dict[str, Any]]:
        """Extract H1 title, meta intro, and cleaned editor-content."""
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else fallback_title

        meta_desc = soup.find("meta", attrs={"name": "description"})
        intro = meta_desc.get("content", "").strip() if meta_desc else ""

        editor = soup.find("div", class_="editor-content")
        if not editor:
            return None

        # Clean out promotional ads and Amazon Kindle links
        for a in editor.find_all("a"):
            if "amzn.to" in a.get("href", "") or "Amazon" in str(a):
                a.decompose()
        for img in editor.find_all("img"):
            src = img.get("src") or ""
            if "Amazon_Kindle" in src or "bloovee-round" in src:
                img.decompose()
        for p in editor.find_all("p"):
            p_text = p.get_text(strip=True)
            if "learn this topic offline" in p_text or "Amazon" in p_text:
                p.decompose()

        if not intro:
            p1 = editor.find("p")
            intro = p1.get_text(strip=True) if p1 else title

        # Collect embedded technical diagram URLs
        images = []
        for img in editor.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            if src.startswith("http") and ("static.d-libro.com/01-course-content-images" in src or "static.d-libro.com" in src):
                images.append(src)

        return {
            "title": title,
            "intro": intro,
            "body_html": str(editor),
            "images": images,
        }

    def _upload_image_to_supabase(self, image_url: str, topic_slug: str) -> Optional[str]:
        """Download remote diagram and upload to Supabase S3 bucket."""
        try:
            data = fetch_url(image_url)
            if not data:
                return None

            filename = os.path.basename(urllib.parse.urlparse(image_url).path)
            s3_path = f"images/docker/{topic_slug}_{filename}"

            # Save via Django default_storage (configured with S3 backend)
            saved_name = default_storage.save(s3_path, ContentFile(data))
            return default_storage.url(saved_name)
        except Exception:
            return None

    def _create_wagtail_image(self, cover_url: str, title: str, topic_slug: str) -> Optional[Image]:
        """Download cover image and create a Wagtail Image model instance."""
        try:
            data = fetch_url(cover_url)
            if not data:
                return None

            filename = f"cover_docker_{topic_slug}.webp"
            img_file = ImageFile(io.BytesIO(data), name=filename)
            wagtail_img = Image.objects.create(
                title=f"Cover: {title}",
                file=img_file,
            )
            return wagtail_img
        except Exception:
            return None
