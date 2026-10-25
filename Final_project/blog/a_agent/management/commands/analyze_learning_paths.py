from django.conf import settings
from django.core.management.base import BaseCommand

from a_agent.services.learning_analysis import store_article_analysis
from a_agent.services.llm import generate_answer, llm_configured
from a_blog.models import ArticlePage


def _generate(system_prompt: str, user_prompt: str) -> str:
    provider = getattr(settings, 'AGENT_LLM_PROVIDER', 'ollama').lower()
    if provider == 'ollama':
        return generate_answer(system_prompt, user_prompt, model='qwen2.5:7b')
    return generate_answer(system_prompt, user_prompt)


class Command(BaseCommand):
    help = 'Analyze live articles for difficulty, article concepts, and prerequisite concepts.'

    def add_arguments(self, parser):
        parser.add_argument('--slug', default='', help='Analyze one article slug.')
        parser.add_argument('--limit', type=int, default=0, help='Stop after this many articles.')

    def handle(self, *args, **options):
        if not llm_configured():
            self.stderr.write('AI is not configured. No analysis was saved.')
            return

        articles = ArticlePage.objects.live().order_by('id')
        if options['slug']:
            articles = articles.filter(slug=options['slug'])
        if options['limit']:
            articles = articles[:options['limit']]

        catalog = [
            {'slug': item.slug, 'title': item.title}
            for item in ArticlePage.objects.live().only('slug', 'title')
        ]
        ready = unavailable = 0
        for article in articles:
            record = store_article_analysis(article, catalog, _generate)
            if record.get('status') == 'ready':
                ready += 1
                self.stdout.write(f'ready {article.slug}')
            else:
                unavailable += 1
                self.stdout.write(f'unavailable {article.slug}')
        self.stdout.write(self.style.SUCCESS(f'done ready={ready} unavailable={unavailable}'))
