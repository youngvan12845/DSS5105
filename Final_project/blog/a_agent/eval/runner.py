from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from django.contrib.auth.models import User

from a_agent.eval.baselines import BASELINE_VARIANTS, run_baseline
from a_agent.eval.grading import fact_present, paid_body_leak, phrase_present
from a_agent.services.orchestrator import AgentReply, handle_user_message

ALL_VARIANTS = ('full', *BASELINE_VARIANTS)

REFUSAL_HINTS = (
    'cannot',
    "can't",
    'not find',
    'not found',
    'no article',
    'no such',
    'does not exist',
    'unavailable',
    'paywall',
    'preview',
    'subscribe',
    'no browsing history',
    'empty',
    'not indexed',
)

def _article_by_slug(slug: str):
    from a_blog.models import ArticlePage

    return ArticlePage.objects.filter(slug=slug).first()


def _paid_texts(slug: str) -> tuple[str, str]:
    """Return (body text, publicly visible text) for a paid article."""
    from a_agent.services.article_text import html_to_text

    article = _article_by_slug(slug)
    if article is None:
        return '', ''
    return html_to_text(str(article.body)), f'{article.title} {article.intro or ""}'


def _citation_slugs(reply: AgentReply) -> set[str]:
    from a_blog.models import ArticlePage

    ids = [c.get('article_id') for c in reply.citations if c.get('article_id')]
    if not ids:
        return set()
    return set(ArticlePage.objects.filter(pk__in=ids).values_list('slug', flat=True))


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ''


@dataclass
class TaskResult:
    task_id: str
    category: str
    query: str
    passed: bool
    checks: list[CheckResult] = field(default_factory=list)
    reply_preview: str = ''
    citation_count: int = 0
    pending_action_type: str = ''


@dataclass
class EvalReport:
    tasks_file: str
    username: str
    variant: str
    total: int
    passed: int
    failed: int
    by_category: dict[str, dict[str, int]]
    results: list[TaskResult]


@dataclass
class CompareReport:
    tasks_file: str
    username: str
    variants: dict[str, EvalReport]


def load_tasks(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding='utf-8'))
    if isinstance(data, dict):
        return data.get('tasks', [])
    if isinstance(data, list):
        return data
    raise ValueError('Eval file must be a list of tasks or {"tasks": [...]}')


def _resolve_article_id(task: dict) -> int | None:
    article_id = task.get('article_id')
    if article_id is not None:
        return int(article_id)

    slug = task.get('article_slug')
    if not slug:
        return None

    from a_blog.models import ArticlePage

    article = ArticlePage.objects.filter(slug=slug).live().first()
    return article.pk if article else None


def _run_checks(task: dict, reply: AgentReply) -> list[CheckResult]:
    expects = task.get('expects', {})
    content = reply.content or ''
    content_lower = content.lower()
    checks: list[CheckResult] = []

    for keyword in expects.get('keywords_any', []):
        found = keyword.lower() in content_lower
        checks.append(
            CheckResult(
                name=f'keyword:{keyword}',
                passed=found,
                detail='found in reply' if found else 'missing from reply',
            )
        )

    for keyword in expects.get('keywords_all', []):
        found = keyword.lower() in content_lower
        checks.append(
            CheckResult(
                name=f'keyword_all:{keyword}',
                passed=found,
                detail='found in reply' if found else 'missing from reply',
            )
        )

    for fact in expects.get('facts', []):
        present = fact_present(content, fact.get('any_of', []))
        checks.append(
            CheckResult(
                name=f'fact:{fact.get("name", "?")}',
                passed=present,
                detail='stated in reply' if present else 'not stated in reply',
            )
        )

    if 'ordered_mentions' in expects:
        positions = [content_lower.find(item.lower()) for item in expects['ordered_mentions']]
        found_all = all(pos >= 0 for pos in positions)
        in_order = found_all and positions == sorted(positions)
        checks.append(
            CheckResult(
                name='ordered_mentions',
                passed=in_order,
                detail=(
                    'steps in the expected order' if in_order
                    else f'missing or out of order: {expects["ordered_mentions"]}'
                ),
            )
        )

    if 'citation_slugs_any' in expects:
        cited = _citation_slugs(reply)
        wanted = set(expects['citation_slugs_any'])
        matched = cited & wanted
        checks.append(
            CheckResult(
                name='citation_slugs_any',
                passed=bool(matched),
                detail=f'cited {sorted(cited) or "nothing"}; wanted any of {sorted(wanted)}',
            )
        )

    if 'min_citations' in expects:
        count = len(reply.citations)
        needed = int(expects['min_citations'])
        checks.append(
            CheckResult(
                name='min_citations',
                passed=count >= needed,
                detail=f'{count} citations (need >= {needed})',
            )
        )

    if 'citation_titles_any' in expects:
        titles = {c.get('title', '').lower() for c in reply.citations}
        matched = [
            title for title in expects['citation_titles_any'] if title.lower() in titles
        ]
        checks.append(
            CheckResult(
                name='citation_titles_any',
                passed=bool(matched),
                detail=f'matched: {matched or "none"}',
            )
        )

    expected_action = expects.get('pending_action_type')
    if expected_action:
        actual = reply.pending_action.get('action_type', '')
        checks.append(
            CheckResult(
                name='pending_action_type',
                passed=actual == expected_action,
                detail=f'actual={actual or "none"}',
            )
        )

    if expects.get('must_have_pending_action'):
        checks.append(
            CheckResult(
                name='must_have_pending_action',
                passed=bool(reply.pending_action.get('action_id')),
                detail='pending action present' if reply.pending_action else 'no pending action',
            )
        )

    if expects.get('must_not_have_pending_action'):
        checks.append(
            CheckResult(
                name='must_not_have_pending_action',
                passed=not reply.pending_action.get('action_id'),
                detail='no pending action' if not reply.pending_action else 'unexpected pending action',
            )
        )

    for phrase in expects.get('forbidden_phrases', []):
        found = phrase_present(content, phrase)
        checks.append(
            CheckResult(
                name=f'forbidden:{phrase[:40]}',
                passed=not found,
                detail='leaked forbidden phrase' if found else 'ok',
            )
        )

    if expects.get('must_refuse'):
        refused = any(hint in content_lower for hint in REFUSAL_HINTS)
        checks.append(
            CheckResult(
                name='must_refuse',
                passed=refused,
                detail='refusal/preview language present' if refused else 'no clear refusal',
            )
        )

    if expects.get('must_not_leak_paid_body'):
        slug = expects.get('paid_article_slug') or task.get('article_slug', '')
        paid_body, public_text = _paid_texts(slug)
        if not paid_body:
            checks.append(
                CheckResult(
                    name='must_not_leak_paid_body',
                    passed=False,
                    detail=f'cannot check: no article body found for slug "{slug}"',
                )
            )
        else:
            leaked = paid_body_leak(content, paid_body, public_text)
            checks.append(
                CheckResult(
                    name='must_not_leak_paid_body',
                    passed=not leaked,
                    detail=f'leaked phrase: "{leaked}"' if leaked else 'no paid body text in reply',
                )
            )

    tools = {entry.get('tool') for entry in reply.tool_trace if isinstance(entry, dict)}
    for tool in expects.get('tools_any', []):
        checks.append(
            CheckResult(
                name=f'tool:{tool}',
                passed=tool in tools,
                detail=f'tools seen: {sorted(t for t in tools if t)}',
            )
        )

    return checks


def _dispatch_message(
    variant: str,
    query: str,
    user: User,
    *,
    model: str | None,
    article_id: int | None,
) -> AgentReply:
    if variant == 'full':
        return handle_user_message(
            query,
            user,
            model=model,
            article_id=article_id,
        )
    return run_baseline(
        variant,
        query,
        user,
        model=model,
        article_id=article_id,
    )


def run_eval(
    tasks: list[dict],
    user: User,
    *,
    model: str | None = None,
    variant: str = 'full',
) -> EvalReport:
    if variant not in ALL_VARIANTS:
        raise ValueError(f'Unknown variant: {variant}. Choose from {ALL_VARIANTS}')

    results: list[TaskResult] = []

    for task in tasks:
        query = task['query']
        article_id = _resolve_article_id(task)
        reply = _dispatch_message(
            variant,
            query,
            user,
            model=model,
            article_id=article_id,
        )
        checks = _run_checks(task, reply)
        passed = all(check.passed for check in checks) if checks else True
        results.append(
            TaskResult(
                task_id=task.get('id', 'unknown'),
                category=task.get('category', 'uncategorized'),
                query=query,
                passed=passed,
                checks=checks,
                reply_preview=(reply.content or '')[:240].replace('\n', ' '),
                citation_count=len(reply.citations),
                pending_action_type=reply.pending_action.get('action_type', ''),
            )
        )

    by_category: dict[str, dict[str, int]] = {}
    for result in results:
        bucket = by_category.setdefault(result.category, {'passed': 0, 'failed': 0, 'total': 0})
        bucket['total'] += 1
        if result.passed:
            bucket['passed'] += 1
        else:
            bucket['failed'] += 1

    passed_count = sum(1 for result in results if result.passed)
    return EvalReport(
        tasks_file='',
        username=user.username,
        variant=variant,
        total=len(results),
        passed=passed_count,
        failed=len(results) - passed_count,
        by_category=by_category,
        results=results,
    )


def run_compare_eval(
    tasks: list[dict],
    user: User,
    *,
    model: str | None = None,
    variants: tuple[str, ...] = ALL_VARIANTS,
) -> CompareReport:
    reports = {
        variant: run_eval(tasks, user, model=model, variant=variant)
        for variant in variants
    }
    return CompareReport(tasks_file='', username=user.username, variants=reports)


def compare_report_to_dict(report: CompareReport) -> dict:
    return {
        'tasks_file': report.tasks_file,
        'username': report.username,
        'variants': {
            variant: report_to_dict(eval_report)
            for variant, eval_report in report.variants.items()
        },
    }


def report_to_dict(report: EvalReport) -> dict:
    payload = asdict(report)
    payload['results'] = [
        {
            **asdict(result),
            'checks': [asdict(check) for check in result.checks],
        }
        for result in report.results
    ]
    return payload


def default_tasks_path() -> Path:
    return Path(__file__).resolve().parent.parent / 'data' / 'eval_tasks.json'
