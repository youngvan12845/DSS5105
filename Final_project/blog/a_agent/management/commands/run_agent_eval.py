from __future__ import annotations

import json
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from a_agent.eval.runner import (
    ALL_VARIANTS,
    compare_report_to_dict,
    default_tasks_path,
    load_tasks,
    report_to_dict,
    run_compare_eval,
    run_eval,
)


class Command(BaseCommand):
    help = 'Run the agent eval task set (full agent or baselines A/B/C).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tasks',
            type=str,
            default='',
            help='Path to eval JSON file (default: a_agent/data/eval_tasks.json).',
        )
        parser.add_argument(
            '--username',
            type=str,
            default='',
            help='Django user to run eval as (default: first superuser).',
        )
        parser.add_argument(
            '--variant',
            type=str,
            default='full',
            choices=[*ALL_VARIANTS, 'all'],
            help='full | baseline_a | baseline_b | baseline_c | all (compare every variant).',
        )
        parser.add_argument(
            '--model',
            type=str,
            default='',
            help='Optional LLM model override passed to the agent.',
        )
        parser.add_argument(
            '--output',
            type=str,
            default='',
            help='Optional path to write full JSON results.',
        )
        parser.add_argument(
            '--fail-fast',
            action='store_true',
            help='Stop printing details after the first failing task.',
        )
        parser.add_argument(
            '--no-fail-exit',
            action='store_true',
            help='Always exit 0 even when tasks fail (useful for baseline sweeps).',
        )

    def handle(self, *args, **options):
        tasks_path = Path(options['tasks']) if options['tasks'] else default_tasks_path()
        if not tasks_path.exists():
            raise CommandError(f'Eval tasks file not found: {tasks_path}')

        user = self._get_user(options['username'])
        tasks = load_tasks(tasks_path)
        if not tasks:
            raise CommandError('No tasks found in eval file.')

        model = options['model'] or None

        if options['variant'] == 'all':
            compare = run_compare_eval(tasks, user, model=model)
            compare.tasks_file = str(tasks_path)
            self._print_compare_summary(compare, tasks_path)
            if options['output']:
                output_path = Path(options['output'])
                output_path.write_text(
                    json.dumps(compare_report_to_dict(compare), indent=2, ensure_ascii=False) + '\n',
                    encoding='utf-8',
                )
                self.stdout.write(self.style.SUCCESS(f'Wrote compare report to {output_path}'))
            return

        report = run_eval(tasks, user, model=model, variant=options['variant'])
        report.tasks_file = str(tasks_path)
        self._print_report(report, tasks_path, options)
        if options['output']:
            output_path = Path(options['output'])
            output_path.write_text(
                json.dumps(report_to_dict(report), indent=2, ensure_ascii=False) + '\n',
                encoding='utf-8',
            )
            self.stdout.write(self.style.SUCCESS(f'Wrote report to {output_path}'))

        if report.failed and not options['no_fail_exit']:
            raise CommandError(f'{report.failed} eval task(s) failed.')

    def _print_compare_summary(self, compare, tasks_path) -> None:
        self.stdout.write(
            self.style.MIGRATE_HEADING(f'Agent eval compare — user={compare.username}')
        )
        self.stdout.write(f'Tasks file: {tasks_path}')
        self.stdout.write('')
        self.stdout.write(f'{"Variant":<14} {"Passed":>8} {"Failed":>8} {"Rate":>8}')
        self.stdout.write('-' * 42)
        for variant in ALL_VARIANTS:
            report = compare.variants[variant]
            rate = (report.passed / report.total * 100) if report.total else 0
            self.stdout.write(
                f'{variant:<14} {report.passed:>8} {report.failed:>8} {rate:>7.1f}%'
            )
        self.stdout.write('')
        for variant in ALL_VARIANTS:
            report = compare.variants[variant]
            self.stdout.write(self.style.MIGRATE_HEADING(variant))
            for category, stats in sorted(report.by_category.items()):
                self.stdout.write(
                    f'  {category}: {stats["passed"]}/{stats["total"]} passed'
                )
            self.stdout.write('')

    def _print_report(self, report, tasks_path, options) -> None:
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f'Agent eval — variant={report.variant} user={report.username}'
            )
        )
        self.stdout.write(f'Tasks file: {tasks_path}')
        self.stdout.write(
            f'Total: {report.total}  Passed: {report.passed}  Failed: {report.failed}'
        )
        self.stdout.write('')

        for category, stats in sorted(report.by_category.items()):
            self.stdout.write(
                f'  {category}: {stats["passed"]}/{stats["total"]} passed'
            )

        self.stdout.write('')
        for result in report.results:
            style = self.style.SUCCESS if result.passed else self.style.ERROR
            mark = 'PASS' if result.passed else 'FAIL'
            self.stdout.write(style(f'[{mark}] {result.task_id} ({result.category})'))
            self.stdout.write(f'  Q: {result.query}')
            self.stdout.write(f'  A: {result.reply_preview}')
            if not result.passed:
                for check in result.checks:
                    if not check.passed:
                        self.stdout.write(f'    - {check.name}: {check.detail}')
                if options['fail_fast']:
                    break
            self.stdout.write('')

    def _get_user(self, username: str) -> User:
        if username:
            return User.objects.get(username=username)

        user = User.objects.filter(is_superuser=True).order_by('id').first()
        if user is None:
            user = User.objects.filter(is_active=True).order_by('id').first()
        if user is None:
            raise CommandError('No active user found. Create a superuser first.')
        return user
