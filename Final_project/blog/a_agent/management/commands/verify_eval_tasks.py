"""Check the eval set against the article corpus before trusting its scores."""

from __future__ import annotations

import collections
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from a_agent.eval.grading import fact_present
from a_agent.eval.runner import default_tasks_path, load_tasks
from a_agent.services.article_text import html_to_text
from a_blog.models import ArticlePage

# Course spec minimums for the evaluation set.
MIN_TASKS = 30
MIN_ADVERSARIAL = 5
MIN_ACTION = 5


class Command(BaseCommand):
    help = (
        'Verify that every gold fact in the eval set appears in its source article '
        'and is not simply echoed from the question.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--tasks', type=str, default='', help='Path to the eval JSON file.')

    def handle(self, *args, **options):
        tasks_path = Path(options['tasks']) if options['tasks'] else default_tasks_path()
        if not tasks_path.exists():
            raise CommandError(f'Eval tasks file not found: {tasks_path}')

        tasks = load_tasks(tasks_path)
        problems: list[str] = []
        checked_facts = 0

        for task in tasks:
            task_id = task.get('id', '?')
            facts = task.get('expects', {}).get('facts', [])
            slug = task.get('gold_source', '')
            corpus_facts = [fact for fact in facts if not fact.get('behaviour')]

            if corpus_facts and not slug:
                problems.append(f'{task_id}: has facts but no gold_source article')
                continue

            article_text = self._article_text(slug) if slug else ''
            if slug and not article_text:
                problems.append(f'{task_id}: gold_source "{slug}" is not a live article')
                continue

            for fact in facts:
                checked_facts += 1
                name = fact.get('name', '?')
                variants = fact.get('any_of', [])
                # Behaviour facts describe how the assistant should respond
                # (e.g. name the paywall), so there is no article to check them against.
                if not fact.get('behaviour') and not fact_present(article_text, variants):
                    problems.append(
                        f'{task_id}: fact "{name}" is not supported by article "{slug}"'
                    )
                if fact_present(task.get('query', ''), variants):
                    problems.append(
                        f'{task_id}: fact "{name}" already appears in the question — '
                        'the agent can pass by repeating the question'
                    )

        self._report_composition(tasks)
        self.stdout.write(f'Checked {checked_facts} facts across {len(tasks)} tasks.')

        if problems:
            self.stdout.write(self.style.ERROR(f'{len(problems)} problems:'))
            for problem in problems:
                self.stdout.write(f'  - {problem}')
            raise CommandError('Eval set verification failed.')

        self.stdout.write(self.style.SUCCESS('All gold facts are grounded in the corpus.'))

    def _article_text(self, slugs) -> str:
        """Title, intro and body of one slug or a list of slugs, joined."""
        if isinstance(slugs, str):
            slugs = [slugs]
        parts = []
        for slug in slugs:
            article = ArticlePage.objects.filter(slug=slug).live().first()
            if article is None:
                return ''
            parts += [article.title, article.intro or '', html_to_text(str(article.body))]
        return ' '.join(parts)

    def _report_composition(self, tasks: list[dict]) -> None:
        categories = collections.Counter(task.get('category', 'uncategorized') for task in tasks)
        splits = collections.Counter(task.get('split', 'unassigned') for task in tasks)
        human = sum(1 for task in tasks if task.get('human_review'))

        self.stdout.write('Categories: ' + ', '.join(f'{k}={v}' for k, v in sorted(categories.items())))
        self.stdout.write('Splits: ' + ', '.join(f'{k}={v}' for k, v in sorted(splits.items())))
        self.stdout.write(f'Tasks needing human review: {human}')

        for label, count, minimum in (
            ('tasks', len(tasks), MIN_TASKS),
            ('adversarial tasks', categories.get('adversarial', 0), MIN_ADVERSARIAL),
            ('action tasks', categories.get('action', 0), MIN_ACTION),
        ):
            if count < minimum:
                self.stdout.write(self.style.WARNING(
                    f'Below the spec minimum: {count} {label} (need {minimum}).'
                ))
