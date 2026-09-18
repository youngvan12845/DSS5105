"""Management command to configure series taxonomy, tags, like counts, and designate top-liked articles as member articles."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from a_blog.models import ArticlePage


ARTICLE_SERIES_CONFIG = {
    # Series: Python 與程式基礎 (Python & Algorithms)
    'python-basics-variables': {
        'tags': ['python', 'programming', 'basics'],
        'likes': 68,
        'is_free': True,
        'required_points': 0,
        'series': 'Python 與程式基礎',
    },
    'python-functions-modules': {
        'tags': ['python', 'programming', 'architecture'],
        'likes': 95,
        'is_free': True,
        'required_points': 0,
        'series': 'Python 與程式基礎',
    },
    'path-python-web': {
        'tags': ['python', 'webdev', 'roadmap'],
        'likes': 110,
        'is_free': True,
        'required_points': 0,
        'series': 'Python 與程式基礎',
    },
    'i-built-a-version-bump-tool-in-rust-that-is-1': {
        'tags': ['rust', 'python', 'tutorial', 'javascript'],
        'likes': 180,
        'is_free': True,
        'required_points': 0,
        'series': 'Python 與程式基礎',
    },
    'i-tried-to-beat-peter-norvig-and-accidentally': {
        'tags': ['algorithms', 'python', 'adventofcode', 'programming'],
        'likes': 342,
        'is_free': False,
        'required_points': 15,
        'series': 'Python 與程式基礎',
    },

    # Series: 機器學習與資料科學 (Machine Learning & Data Science)
    'path-ml-getting-started': {
        'tags': ['machine-learning', 'python', 'roadmap'],
        'likes': 88,
        'is_free': True,
        'required_points': 0,
        'series': '機器學習與資料科學',
    },
    'ml-supervised-unsupervised': {
        'tags': ['machine-learning', 'python', 'ai'],
        'likes': 125,
        'is_free': True,
        'required_points': 0,
        'series': '機器學習與資料科學',
    },
    'gradient-descent-intuition': {
        'tags': ['machine-learning', 'math', 'optimization'],
        'likes': 142,
        'is_free': True,
        'required_points': 0,
        'series': '機器學習與資料科學',
    },
    'linear-regression-practice': {
        'tags': ['machine-learning', 'python', 'data-science'],
        'likes': 268,
        'is_free': False,
        'required_points': 10,
        'series': '機器學習與資料科學',
    },
    'a-4-gb-laptop-gpu-beats-a-12-core-cpu-by-43x-': {
        'tags': ['machinelearning', 'gpu', 'benchmarking', 'python'],
        'likes': 315,
        'is_free': False,
        'required_points': 15,
        'series': '機器學習與資料科學',
    },

    # Series: 後端開發與系統架構 (Backend & System Architecture)
    'web-http-rest': {
        'tags': ['webdev', 'http', 'api'],
        'likes': 76,
        'is_free': True,
        'required_points': 0,
        'series': '後端開發與系統架構',
    },
    'django-project-structure': {
        'tags': ['django', 'webdev', 'python'],
        'likes': 105,
        'is_free': True,
        'required_points': 0,
        'series': '後端開發與系統架構',
    },
    'wagtail-quickstart': {
        'tags': ['wagtail', 'django', 'cms'],
        'likes': 89,
        'is_free': True,
        'required_points': 0,
        'series': '後端開發與系統架構',
    },
    'the-cicd-pipeline-that-was-lying-to-us-a-depl': {
        'tags': ['githubactions', 'docker', 'django', 'devops'],
        'likes': 165,
        'is_free': True,
        'required_points': 0,
        'series': '後端開發與系統架構',
    },
    'fixing-delicate-cache-mismatches-in-a-brownfi': {
        'tags': ['webdev', 'architecture', 'webperf', 'caching'],
        'likes': 286,
        'is_free': False,
        'required_points': 15,
        'series': '後端開發與系統架構',
    },
    'nginx-silently-rejects-the-new-http-query-met': {
        'tags': ['nginx', 'django', 'fastapi', 'http'],
        'likes': 298,
        'is_free': False,
        'required_points': 20,
        'series': '後端開發與系統架構',
    },

    # Series: 人工智能與 Agent 系統 (AI & Agent Systems)
    'what-is-rag': {
        'tags': ['ai', 'rag', 'machine-learning'],
        'likes': 150,
        'is_free': True,
        'required_points': 0,
        'series': '人工智能與 Agent 系統',
    },
    '20-agentic-ai-terms-every-developer-should-kn': {
        'tags': ['ai', 'agents', 'mcp', 'beginners'],
        'likes': 138,
        'is_free': True,
        'required_points': 0,
        'series': '人工智能與 Agent 系統',
    },
    'vibe-coding-isnt-the-problem-calling-it-engin': {
        'tags': ['ai', 'machinelearning', 'coding', 'development'],
        'likes': 172,
        'is_free': True,
        'required_points': 0,
        'series': '人工智能與 Agent 系統',
    },
    'ai-is-already-better-at-coding-than-most-soft': {
        'tags': ['discuss', 'ai', 'webdev', 'programming'],
        'likes': 320,
        'is_free': False,
        'required_points': 15,
        'series': '人工智能與 Agent 系統',
    },
    'agent-tool-design': {
        'tags': ['ai', 'agents', 'architecture', 'security'],
        'likes': 380,
        'is_free': False,
        'required_points': 15,
        'series': '人工智能與 Agent 系統',
    },

    # Series: 社群與平台討論 (Community & Platform)
    '5-devto-features-i-wish-existed-3-im-genuinel': {
        'tags': ['discuss', 'meta', 'forem', 'webdev'],
        'likes': 210,
        'is_free': False,
        'required_points': 10,
        'series': '社群與平台討論',
    },
}


class Command(BaseCommand):
    help = 'Setup article series taxonomy, realistic likes, and designate top-liked articles as member articles.'

    def handle(self, *args, **options):
        updated_count = 0
        premium_count = 0
        free_count = 0

        for slug, cfg in ARTICLE_SERIES_CONFIG.items():
            try:
                article = ArticlePage.objects.get(slug=slug)
            except ArticlePage.DoesNotExist:
                self.stderr.write(self.style.WARNING(f'Article "{slug}" not found, skipping.'))
                continue

            with transaction.atomic():
                article.likes = cfg['likes']
                article.is_free = cfg['is_free']
                article.required_points = cfg['required_points']

                # Update tags
                article.tags.clear()
                for tag_name in cfg['tags']:
                    article.tags.add(tag_name)

                article.save(update_fields=['likes', 'is_free', 'required_points'])
                revision = article.save_revision()
                revision.publish()

            tier = "PREMIUM (會員)" if not cfg['is_free'] else "FREE (免費)"
            if cfg['is_free']:
                free_count += 1
            else:
                premium_count += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ [{cfg["series"]}] {article.title[:40]:40s} | {tier:15s} | 讚數: {cfg["likes"]:3d} | 點數: {cfg["required_points"]:2d}'
                )
            )
            updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'\n完成配置：共更新 {updated_count} 篇文章（免費: {free_count} 篇，會員專屬: {premium_count} 篇）。'
            )
        )
