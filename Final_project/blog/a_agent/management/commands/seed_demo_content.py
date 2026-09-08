from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.files.images import ImageFile
from django.core.management.base import BaseCommand
from django.db import transaction
from wagtail.images.models import Image
from wagtail.models import Site

from a_blog.models import ArticlePage, BlogPage


DEMO_ARTICLES = [
    {
        'title': 'Python Basics: Variables and Data Types',
        'slug': 'python-basics-variables',
        'intro': 'Your first lesson in Python syntax',
        'tags': ['python', 'programming'],
        'is_free': True,
        'body': '<p>Python uses dynamic typing. Common types include int, float, str, list, and dict.</p><p>Variables do not need type declarations — assign a value directly.</p>',
    },
    {
        'title': 'Python Functions and Modules',
        'slug': 'python-functions-modules',
        'intro': 'How to organize Python code',
        'tags': ['python', 'programming'],
        'is_free': True,
        'body': '<p>Functions are defined with def. Modules split code across files and are imported with import.</p><p>Good module structure helps maintenance and testing.</p>',
    },
    {
        'title': 'Machine Learning Overview: Supervised vs Unsupervised',
        'slug': 'ml-supervised-unsupervised',
        'intro': 'Understanding the two main ML paradigms',
        'tags': ['machine-learning', 'python'],
        'is_free': True,
        'body': '<p>Supervised learning trains on labeled data for tasks like classification and regression.</p><p>Unsupervised learning finds structure in unlabeled data, such as clustering.</p>',
    },
    {
        'title': 'Gradient Descent Intuition',
        'slug': 'gradient-descent-intuition',
        'intro': 'Introduction to optimization',
        'tags': ['machine-learning', 'math'],
        'is_free': True,
        'body': '<p>Gradient descent updates parameters along the negative gradient of the loss to reduce error step by step.</p><p>The learning rate controls how large each step is.</p>',
    },
    {
        'title': 'Linear Regression in Practice',
        'slug': 'linear-regression-practice',
        'intro': 'Your first ML model',
        'tags': ['machine-learning', 'python'],
        'is_free': False,
        'required_points': 10,
        'body': '<p>Linear regression assumes a linear relationship between features and targets. You can train quickly with sklearn.</p><p>Common metrics include MSE and R².</p>',
    },
    {
        'title': 'Web Development Basics: HTTP and REST',
        'slug': 'web-http-rest',
        'intro': 'Backend development fundamentals',
        'tags': ['web-dev'],
        'is_free': True,
        'body': '<p>HTTP is the protocol for web communication. REST uses resource-oriented URLs and verbs like GET, POST, PUT, and DELETE.</p>',
    },
    {
        'title': 'Django Project Structure Explained',
        'slug': 'django-project-structure',
        'intro': 'Understanding the Django layout',
        'tags': ['web-dev', 'python'],
        'is_free': True,
        'body': '<p>A Django project contains one project config and multiple apps. settings, urls, models, and views are the core pieces.</p>',
    },
    {
        'title': 'Wagtail CMS Quick Start',
        'slug': 'wagtail-quickstart',
        'intro': 'Getting started with a CMS',
        'tags': ['web-dev'],
        'is_free': True,
        'body': '<p>Wagtail builds on Django with a page tree and a friendly admin editing experience.</p>',
    },
    {
        'title': 'What Is RAG?',
        'slug': 'what-is-rag',
        'intro': 'Retrieval-augmented generation basics',
        'tags': ['machine-learning', 'web-dev'],
        'is_free': True,
        'body': '<p>RAG retrieves relevant documents first, then lets the LLM answer from those results — helping reduce hallucinations.</p>',
    },
    {
        'title': 'Agent Tool Design Principles',
        'slug': 'agent-tool-design',
        'intro': 'Capstone agent design reference',
        'tags': ['machine-learning', 'programming'],
        'is_free': False,
        'required_points': 15,
        'body': '<p>Tools should have a single responsibility, clear inputs/outputs, and be auditable. The LLM orchestrates; tools provide facts and computation.</p>',
    },
    {
        'title': 'Reading Path: Machine Learning Getting Started',
        'slug': 'path-ml-getting-started',
        'intro': 'Recommended learning order',
        'tags': ['machine-learning'],
        'is_free': True,
        'body': '<p>Suggested order: ML overview → gradient descent intuition → linear regression in practice.</p>',
    },
    {
        'title': 'Reading Path: Python Web Development',
        'slug': 'path-python-web',
        'intro': 'Recommended learning order',
        'tags': ['python', 'web-dev'],
        'is_free': True,
        'body': '<p>Suggested order: Python basics → Django project structure → Wagtail quick start → HTTP and REST.</p>',
    },
]


class Command(BaseCommand):
    help = 'Seed demo articles under the Wagtail site root (optional dev helper).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--replace-orphans',
            action='store_true',
            help='Delete articles that sit outside the site tree before seeding.',
        )

    def _site_parent(self):
        site = Site.objects.get(is_default_site=True)
        return site.root_page

    def _get_default_image(self) -> Image:
        existing = Image.objects.first()
        if existing:
            return existing

        from django.conf import settings

        image_path = settings.BASE_DIR / 'static' / 'images' / 'cheese.png'
        with open(image_path, 'rb') as handle:
            return Image.objects.create(
                title='Default cover',
                file=ImageFile(handle, name='cheese.png'),
            )

    def _cleanup_orphans(self, site_root):
        """Remove BlogPage/articles attached to Wagtail Root instead of site home."""
        from wagtail.models import Page

        true_root = Page.get_first_root_node()
        orphan_blog = BlogPage.objects.filter(path__startswith=true_root.path).exclude(
            path__startswith=site_root.path
        )
        count = 0
        for blog in orphan_blog:
            for article in blog.get_children().specific():
                article.delete()
                count += 1
            blog.delete()
            count += 1
        if count:
            self.stdout.write(f'Removed {count} orphan page(s) outside site tree.')

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        owner = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if owner is None:
            self.stderr.write('No user found. Create a superuser first: createsuperuser')
            return

        site_root = self._site_parent()
        if options['replace_orphans']:
            self._cleanup_orphans(site_root)

        blog = BlogPage.objects.child_of(site_root).first()
        if blog is None:
            blog = BlogPage(title='Articles', slug='articles', body='<p>Capstone article list</p>')
            site_root.add_child(instance=blog)
            revision = blog.save_revision()
            revision.publish()
            self.stdout.write(f'Created BlogPage under site root: {blog.url}')

        created = 0
        default_image = self._get_default_image()
        for item in DEMO_ARTICLES:
            if ArticlePage.objects.filter(slug=item['slug']).exists():
                continue

            article = ArticlePage(
                title=item['title'],
                slug=item['slug'],
                intro=item['intro'],
                body=item['body'],
                image=default_image,
                is_free=item.get('is_free', True),
                required_points=item.get('required_points', 0),
                owner=owner,
            )
            blog.add_child(instance=article)
            revision = article.save_revision()
            revision.publish()

            for tag in item.get('tags', []):
                article.tags.add(tag)

            created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Seed complete. Created {created} articles '
                f'(total live: {ArticlePage.objects.live().count()}).'
            )
        )
        sample = ArticlePage.objects.filter(slug='python-basics-variables').first()
        if sample:
            self.stdout.write(f'Sample URL: {sample.url}')
        self.stdout.write(
            'Tip: for production content, add articles in Wagtail admin (/blog/cms/) instead.'
        )
        self.stdout.write('Next: python manage.py build_article_index')
