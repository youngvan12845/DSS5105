"""Checks for the outside-lookup suite.

This suite is separate from the 13 September 33-question round.
Public pages are fixed notes, so the pass count does not depend on
whatever a search engine returns that day.
"""

from __future__ import annotations

import re
from contextlib import contextmanager

from a_agent.eval.grading import phrase_present
from a_agent.services.orchestrator import AgentReply

HELM_NOTE = {
    'title': 'Helm (package manager)',
    'url': 'https://en.wikipedia.org/wiki/Helm_(package_manager)',
    'excerpt': (
        'Helm is a package manager for Kubernetes. '
        'A Helm chart is a set of files that describe Kubernetes resources.'
    ),
    'source_name': 'Wikipedia',
}

GAN_NOTE = {
    'title': 'Generative adversarial network',
    'url': 'https://en.wikipedia.org/wiki/Generative_adversarial_network',
    'excerpt': (
        'A generative adversarial network is a machine learning model. '
        'Two networks contest with each other in a game.'
    ),
    'source_name': 'Wikipedia',
}

CILIUM_NOTE = {
    'title': 'Cilium',
    'url': 'https://cilium.io/',
    'excerpt': 'Cilium uses eBPF to connect and secure network traffic in Kubernetes.',
    'source_name': 'Cilium',
}

KUSTOMIZE_NOTE = {
    'title': 'Kustomize',
    'url': 'https://kustomize.io/',
    'excerpt': 'Kustomize customizes Kubernetes resource files without a template engine.',
    'source_name': 'Kustomize',
}

_OUTSIDE_SPLIT = re.compile(
    r'(\*\*Outside the blog\*\*|\*\*About .+?\*\*|\*\*博客之外\*\*|\*\*关于 .+?\*\*)',
    re.I,
)
_FIXED_SENTENCES = (
    'I cannot find any article about that topic in the blog corpus.',
    'I looked outside the blog and did not find a usable public note.',
    'I did not find a usable public note.',
    '抱歉，在当前的博客文章库中找不到与此主题相关的文章。',
    '博客外面没有找到可用的公开说明。',
    '没有找到可用的公开说明。',
)
_REFUSAL_BITS = (
    'cannot find any article',
    'not find any article',
    '找不到',
    'does not exist',
)


def fixture_notes(name: str, query: str) -> list[dict]:
    text = (query or '').lower()
    if name == 'helm':
        return [dict(HELM_NOTE)]
    if name == 'gan':
        return [dict(GAN_NOTE)]
    if name == 'cilium':
        return [dict(CILIUM_NOTE)]
    if name == 'helm_and_kustomize':
        return [dict(HELM_NOTE), dict(KUSTOMIZE_NOTE)]
    if name == 'helm_when_mentioned' and 'helm' in text:
        return [dict(HELM_NOTE)]
    return []


@contextmanager
def outside_task_context(task: dict, user):
    """Serve fixed public notes, and restore any history rows this task adds."""
    fixture = task.get('outside_fixture')
    opened = list(task.get('opened_slugs') or [])
    decoys = list(task.get('decoy_slugs') or [])
    history = _pin_history(user, opened + decoys) if (opened or decoys) else _noop()
    lookup = _patch_lookup(fixture) if fixture else _noop()
    with history, lookup:
        yield


def outside_checks(task: dict, reply: AgentReply) -> list:
    spec = (task.get('expects') or {}).get('outside')
    if not spec:
        return []
    mode = spec.get('mode') or ''
    content = reply.content or ''
    lesson, outside = _split(content)
    sources = _sources(reply)
    checks: list[CheckResult] = []

    if mode == 'full_miss':
        checks.extend(_labeled_public_note(lesson, outside, reply, sources, spec))
    elif mode == 'empty':
        checks.extend(_empty_lookup(content, reply, sources))
    elif mode == 'mixed':
        checks.extend(_mixed(lesson, outside, reply, sources, spec))
    elif mode == 'mixed_empty':
        checks.extend(_mixed_empty(lesson, outside, reply, sources, spec))
    elif mode == 'on_site':
        checks.extend(_on_site(content, outside, reply, spec))
    elif mode == 'article_page':
        checks.extend(_article_page(content, outside, reply))
    elif mode == 'paid':
        checks.extend(_no_outside(content, outside, reply, 'paid lesson stays on site'))
    elif mode == 'history':
        checks.extend(_history(content, reply, task))
    return checks


def _labeled_public_note(lesson, outside, reply, sources, spec) -> list[CheckResult]:
    return [
        _check('lesson_refuses', _has_refusal(lesson), 'first part names the missing lesson' if _has_refusal(lesson) else 'missing the blog-has-no-article sentence'),
        _check('outside_labeled', _is_labeled(outside), 'outside note is labeled' if _is_labeled(outside) else 'outside note has no site label'),
        _check('not_in_sources', not reply.citations, f'{len(reply.citations)} citations'),
        _check('source_on_topic', _source_matches(sources, spec), _source_detail(sources, spec)),
        _check('lesson_does_not_pretend', not _forbidden_in(lesson, spec), 'lesson part stays a refusal' if not _forbidden_in(lesson, spec) else 'lesson part uses a lesson phrase'),
        *_covers(sources, spec),
    ]


def _empty_lookup(content, reply, sources) -> list[CheckResult]:
    says_missing = any(sentence.lower() in content.lower() for sentence in _FIXED_SENTENCES[1:])
    leftover = content
    for sentence in _FIXED_SENTENCES:
        leftover = re.sub(re.escape(sentence), '', leftover, flags=re.I)
    leftover = re.sub(r'[\s*#：:（）()。.,]+', '', leftover)
    return [
        _check('lesson_refuses', _has_refusal(content), 'refusal present' if _has_refusal(content) else 'no refusal'),
        _check('says_nothing_found', says_missing, 'says no public note' if says_missing else 'does not say the lookup was empty'),
        _check('not_in_sources', not reply.citations, f'{len(reply.citations)} citations'),
        _check('no_sources', not sources, f'{len(sources)} outside sources'),
        _check('does_not_invent', not leftover, 'no extra definition' if not leftover else 'wrote a note without a source'),
    ]


def _mixed(lesson, outside, reply, sources, spec) -> list[CheckResult]:
    site_citations = [item for item in reply.citations if not item.get('is_external')]
    titles = ' '.join((item.get('title') or '') for item in site_citations).lower()
    on_site = spec.get('on_site_token', 'git')
    outside_name = spec.get('outside_name', 'helm')
    helm_in_sources = any(outside_name in (item.get('title') or '').lower() for item in reply.citations)
    return [
        _check('on_site_citation', on_site in titles, f'citation titles: {titles or "none"}'),
        _check('outside_not_in_sources', not helm_in_sources, 'outside topic stayed out of SOURCES' if not helm_in_sources else 'outside topic is listed as a source'),
        _check('outside_labeled', _is_labeled(outside) and outside_name.lower() in outside.lower(), 'mixed note is labeled' if outside else 'no outside section'),
        _check('lesson_omits_outside_topic', not re.search(rf'(?<![A-Za-z0-9]){re.escape(outside_name)}(?![A-Za-z0-9])', lesson, re.I), 'lesson part leaves the outside topic out' if lesson else 'no lesson part'),
        _check('source_on_topic', _source_matches(sources, spec), _source_detail(sources, spec)),
    ]


def _mixed_empty(lesson, outside, reply, sources, spec) -> list:
    site_citations = [item for item in reply.citations if not item.get('is_external')]
    titles = ' '.join((item.get('title') or '') for item in site_citations).lower()
    on_site = spec.get('on_site_token', 'git')
    outside_name = spec.get('outside_name', 'helm')
    says_missing = any(sentence.lower() in (outside or '').lower() for sentence in _FIXED_SENTENCES[1:])
    helm_in_sources = any(outside_name in (item.get('title') or '').lower() for item in reply.citations)
    return [
        _check('on_site_citation', on_site in titles, f'citation titles: {titles or "none"}'),
        _check('outside_not_in_sources', not helm_in_sources, 'outside topic stayed out of SOURCES' if not helm_in_sources else 'outside topic is listed as a source'),
        _check('outside_labeled', _is_labeled(outside) and outside_name.lower() in outside.lower(), 'empty outside note is labeled' if outside else 'no outside section'),
        _check('says_nothing_found', says_missing, 'says no public note' if says_missing else 'does not say the lookup was empty'),
        _check('no_sources', not sources, f'{len(sources)} outside sources'),
        _check('lesson_omits_outside_topic', not re.search(rf'(?<![A-Za-z0-9]){re.escape(outside_name)}(?![A-Za-z0-9])', lesson, re.I), 'lesson part leaves the outside topic out'),
    ]


def _on_site(content, outside, reply, spec) -> list:
    token = (spec.get('on_site_token') or '').lower()
    titles = ' '.join((item.get('title') or '') for item in reply.citations if not item.get('is_external')).lower()
    named = bool(token) and (token in titles or token in content.lower())
    return [
        *_no_outside(content, outside, reply, 'on-site lesson does not look outside'),
        _check('names_lesson', named, f'citation titles: {titles or "none"}'),
    ]


def _covers(sources, spec) -> list:
    needed = [item.lower() for item in spec.get('sources_cover') or []]
    if not needed:
        return []
    blob = ' '.join(f"{source.get('title') or ''} {source.get('excerpt') or ''}" for source in sources).lower()
    return [
        _check(f'source_covers:{token}', token in blob, 'present' if token in blob else 'missing from the public notes')
        for token in needed
    ]


def _article_page(content, outside, reply) -> list:
    stayed = any(bit in content.lower() for bit in ('only covers', 'article scope', '只回答当前文章', '文章范围'))
    return [
        _check('stays_on_article', stayed, 'panel kept the open article' if stayed else 'panel did not keep the open article'),
        *_no_outside(content, outside, reply, 'article page does not look outside'),
    ]


def _history(content, reply, task) -> list[CheckResult]:
    opened = _titles_for_slugs(task.get('opened_slugs') or [])
    decoys = _titles_for_slugs(task.get('decoy_slugs') or [])
    marked = any(bit in content.lower() for bit in ('already opened', 'already read', '打开过', '读过', '看过'))
    opened_named = all(title and title.lower() in content.lower() for title in opened) if opened else False
    decoy_named = any(title and title.lower() in content.lower() for title in decoys)
    return [
        *_no_outside(content, _split(content)[1], reply, 'history question stays on site'),
        _check('names_opened_lesson', marked and opened_named, f'opened titles {opened or "missing"}'),
        _check('skips_unrelated_history', not decoy_named, f'decoy titles {decoys or "missing"}'),
    ]


def _no_outside(content, outside, reply, label: str) -> list[CheckResult]:
    looked = _lookup_called(reply)
    return [
        _check('no_lookup', not looked, label if not looked else 'looked outside'),
        _check('no_outside_section', not outside.strip(), 'no outside section' if not outside.strip() else 'outside section present'),
    ]


def _split(content: str) -> tuple[str, str]:
    match = _OUTSIDE_SPLIT.search(content or '')
    if not match:
        return content or '', ''
    return content[:match.start()], content[match.start():]


def _sources(reply: AgentReply) -> list[dict]:
    found = []
    for entry in reply.tool_trace or []:
        if isinstance(entry, dict) and entry.get('tool') == 'external_sources':
            found.extend(entry.get('sources') or [])
    return found


def _lookup_called(reply: AgentReply) -> bool:
    return any(
        isinstance(entry, dict) and entry.get('tool') == 'external_lookup'
        for entry in reply.tool_trace or []
    )


def _has_refusal(text: str) -> bool:
    lowered = (text or '').lower()
    return any(bit in lowered for bit in _REFUSAL_BITS)


def _is_labeled(outside: str) -> bool:
    lowered = (outside or '').lower()
    return any(bit in lowered for bit in (
        'not a lesson on this site',
        'not on this site',
        '不是本站课文',
        '站外给你解答',
    ))


def _source_matches(sources: list[dict], spec: dict) -> bool:
    required = [item.lower() for item in spec.get('topic_all') or []]
    any_of = [item.lower() for item in spec.get('topic_any') or []]
    rejected = [item.lower() for item in spec.get('reject_titles') or []]
    for source in sources:
        blob = f"{source.get('title') or ''} {source.get('excerpt') or ''}".lower()
        if any(word in blob for word in ('may refer to', 'disambiguation')):
            continue
        if any(word in blob for word in rejected):
            continue
        if required and not all(word in blob for word in required):
            continue
        if any_of and not any(word in blob for word in any_of):
            continue
        return True
    return False


def _source_detail(sources: list[dict], spec: dict) -> str:
    if _source_matches(sources, spec):
        titles = [source.get('title') or '' for source in sources]
        return f'on topic: {titles}'
    if not sources:
        return 'no outside source'
    titles = [source.get('title') or '' for source in sources]
    return f'off topic: {titles}'


def _forbidden_in(lesson: str, spec: dict) -> bool:
    return any(phrase_present(lesson, phrase) for phrase in spec.get('lesson_forbidden') or [])


def _titles_for_slugs(slugs: list[str]) -> list[str]:
    from a_blog.models import ArticlePage

    titles = []
    for slug in slugs:
        article = ArticlePage.objects.filter(slug=slug).first()
        titles.append(article.title if article else '')
    return titles


def _check(name: str, passed: bool, detail: str):
    from a_agent.eval.runner import CheckResult

    return CheckResult(name=name, passed=passed, detail=detail)


@contextmanager
def _noop():
    yield


@contextmanager
def _patch_lookup(fixture: str):
    import a_agent.services.orchestrator as orchestrator

    original = orchestrator.lookup_outside_the_blog

    def fake(query, *args, **kwargs):
        return fixture_notes(fixture, query)

    orchestrator.lookup_outside_the_blog = fake
    try:
        yield
    finally:
        orchestrator.lookup_outside_the_blog = original


@contextmanager
def _pin_history(user, slugs: list[str]):
    from a_blog.models import ArticlePage
    from a_users.models import BrowsingHistory

    created: list[int] = []
    restored: list[tuple] = []
    for slug in slugs:
        article = ArticlePage.objects.filter(slug=slug).first()
        if article is None:
            continue
        existing = BrowsingHistory.objects.filter(user=user, article_id=article.pk).first()
        if existing is not None:
            restored.append((existing.pk, existing.viewed_at, existing.article_title, existing.article_url))
        BrowsingHistory.add_or_update_history(
            user,
            article.pk,
            article.title,
            f'http://127.0.0.1/blog/{article.slug}/',
        )
        if existing is None:
            row = BrowsingHistory.objects.filter(user=user, article_id=article.pk).first()
            if row is not None:
                created.append(row.pk)
    try:
        yield
    finally:
        if created:
            BrowsingHistory.objects.filter(pk__in=created).delete()
        for pk, viewed_at, title, url in restored:
            BrowsingHistory.objects.filter(pk=pk).update(
                viewed_at=viewed_at,
                article_title=title,
                article_url=url,
            )
