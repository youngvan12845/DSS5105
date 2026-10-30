"""AI difficulty and concept analysis.

Generation runs from the analyze_learning_paths command, not during page load.
Publishing an article only marks an older result stale. A missing record keeps
the curated graph; an explicit failed or stale record must not fall back to it.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Any, Callable

from a_agent.services.article_text import html_to_text

logger = logging.getLogger(__name__)

DIFFICULTIES = ('beginner', 'intermediate', 'advanced')
READY = 'ready'
UNAVAILABLE = 'unavailable'
STALE = 'stale'
MAX_CONCEPTS = 8
MIN_BODY_CHARS = 30
BRIDGE_UNAVAILABLE = 'Concept explanation is unavailable.'
GENERIC_CONCEPTS = {
    'system', 'article', 'concept', 'introduction', 'overview', 'basic', 'content',
    'topic', 'learning', 'reader', '系统', '文章', '概念', '内容', '介绍', '基础',
}

_ANALYSIS_SYSTEM = (
    'You analyze one article for a reading assistant. Reply with one JSON object only. '
    'difficulty is beginner, intermediate, or advanced. '
    'article_concepts is two to four short phrases copied verbatim from the title, intro, or body. '
    'Do not use generic words such as system, article, or concept. '
    'prerequisite_concepts lists concepts a reader should know first. Prefer phrases from the other '
    'article titles provided. Use an empty list only when none of those titles is needed. '
    'Do not invent article titles, slugs, or links.'
)

_BRIDGE_SYSTEM = (
    'Explain one prerequisite concept in two to four sentences for a reader about '
    'to open another article. Use only the source text. If the source is a title and '
    'intro, say the explanation is based on the public preview. Do not invent another '
    'article, do not claim the reader has learned the concept, and do not quote long passages.'
)


def default_store_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'data',
        'learning_analysis.json',
    )


def content_version(title: str, intro: str, body: str) -> str:
    blob = f'{title}\n{intro}\n{body}'.encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def article_version(article) -> str:
    return content_version(article.title or '', article.intro or '', html_to_text(str(article.body or '')))


def extract_json_object(text: str | dict) -> dict | None:
    if not text:
        return None
    if isinstance(text, dict):
        return text
    if not isinstance(text, str):
        return None
    cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    start = cleaned.find('{')
    end = cleaned.rfind('}')
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _concept_list(values: Any) -> list[str] | None:
    if not isinstance(values, list):
        return None
    cleaned: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            return None
        cleaned.append(re.sub(r'\s+', ' ', value).strip())
    return list(dict.fromkeys(cleaned))[:MAX_CONCEPTS]


def ready_payload_from_model(data: dict) -> dict | None:
    if not isinstance(data, dict):
        return None
    difficulty = str(data.get('difficulty', '')).strip().lower()
    if difficulty not in DIFFICULTIES:
        return None
    article_concepts = _concept_list(data.get('article_concepts'))
    prerequisite_concepts = _concept_list(data.get('prerequisite_concepts'))
    if article_concepts is None or prerequisite_concepts is None:
        return None
    return {
        'status': READY,
        'difficulty': difficulty,
        'article_concepts': article_concepts,
        'prerequisite_concepts': prerequisite_concepts,
    }


def _source_text(title: str, intro: str, body: str) -> str:
    return f'{title}\n{intro}\n{body}'.strip()


def _is_generic(concept: str) -> bool:
    return concept.casefold().strip() in GENERIC_CONCEPTS


def _grounded_concepts(concepts: list[str], source: str) -> list[str]:
    folded = source.casefold()
    kept = []
    for concept in concepts:
        token = concept.casefold().strip()
        if len(token) < 2 or _is_generic(concept) or token not in folded:
            continue
        kept.append(concept)
    return kept


def analyze_article_text(
    *,
    title: str,
    intro: str,
    body: str,
    generate: Callable[[str, str], str],
    other_titles: list[str] | None = None,
) -> dict:
    if len(body.strip()) < MIN_BODY_CHARS:
        return {'status': UNAVAILABLE}
    titles = [item for item in (other_titles or []) if item and item != title]
    catalog_text = '\n'.join(f'- {item}' for item in titles[:80]) or '- none'
    user_prompt = (
        f'Title: {title}\nIntro: {intro}\n\nArticle text:\n{body[:8000]}\n\n'
        f'Other article titles:\n{catalog_text}'
    )
    try:
        raw = generate(_ANALYSIS_SYSTEM, user_prompt)
    except Exception:
        logger.exception('Learning analysis request failed for %s', title)
        return {'status': UNAVAILABLE}
    payload = ready_payload_from_model(extract_json_object(raw) or {})
    if payload is None:
        return {'status': UNAVAILABLE}
    source = _source_text(title, intro, body)
    article_concepts = _grounded_concepts(payload['article_concepts'], source)
    if not article_concepts:
        return {'status': UNAVAILABLE}
    payload['article_concepts'] = article_concepts
    payload['prerequisite_concepts'] = [item for item in payload['prerequisite_concepts'] if not _is_generic(item)]
    return payload


def _ascii_tokens(text: str) -> list[str]:
    return re.findall(r'[a-z0-9]+', text.lower())


def _cjk_parts(text: str) -> list[str]:
    return re.findall(r'[\u4e00-\u9fff]{2,}', text)


def _significant_tokens(text: str) -> list[str]:
    return [token for token in _ascii_tokens(text) if len(token) > 2]


def _title_matches_concept(title: str, concept: str) -> bool:
    ascii_needles = _significant_tokens(concept)
    cjk_parts = _cjk_parts(concept)
    if not ascii_needles and not cjk_parts:
        return False
    if cjk_parts and not all(part in title for part in cjk_parts):
        return False
    if not ascii_needles:
        return True
    haystack = _significant_tokens(title)
    width = len(ascii_needles)
    return any(haystack[index:index + width] == ascii_needles for index in range(len(haystack) - width + 1))


def match_concepts(concepts: list[str], catalog: list[dict], *, exclude_slug: str | None = None) -> list[dict]:
    """Link a concept only when that phrase appears in a real article title."""
    prepared = []
    for item in catalog:
        slug = (item.get('slug') or '').strip()
        title = (item.get('title') or '').strip()
        if not slug or not title or slug == exclude_slug:
            continue
        prepared.append((slug, title))

    matches = []
    used: set[str] = set()
    for concept in concepts:
        if _is_generic(concept):
            continue
        best = None
        for slug, title in prepared:
            if slug in used or not _title_matches_concept(title, concept):
                continue
            spare = len(title) - len(concept)
            if best is None or spare < best[0]:
                best = (spare, slug, title)
        if best:
            used.add(best[1])
            matches.append({'concept': concept, 'slug': best[1], 'title': best[2]})
    return matches


def matched_coverage(matches: list[dict], visited_slugs, mastered_slugs) -> tuple[int, int]:
    known = set(visited_slugs) | set(mastered_slugs)
    covered = sum(1 for item in matches if item.get('slug') in known)
    return covered, len(matches)


def allowed_source(title: str, intro: str, body: str, *, can_read_full: bool) -> tuple[str, str]:
    if can_read_full:
        return f'{title}\n{intro}\n{body}'.strip()[:8000], 'full'
    return f'{title}\n{intro}'.strip(), 'preview'


def bridge_cache_key(slug: str, version: str, concept: str, tier: str) -> str:
    raw = f'{slug}|{version}|{concept.strip().lower()}|{tier}'
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def load_store(path: str | None = None) -> dict:
    path = path or default_store_path()
    if not os.path.exists(path):
        return {'articles': {}, 'bridges': {}}
    try:
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        logger.exception('Could not read learning analysis store %s', path)
        return {'articles': {}, 'bridges': {}}
    if not isinstance(data, dict):
        return {'articles': {}, 'bridges': {}}
    articles = data.get('articles')
    bridges = data.get('bridges')
    return {
        'articles': articles if isinstance(articles, dict) else {},
        'bridges': bridges if isinstance(bridges, dict) else {},
    }


def save_store(data: dict, path: str | None = None) -> None:
    path = path or default_store_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = f'{path}.tmp'
    with open(temporary, 'w', encoding='utf-8') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


def analysis_for_display(record: dict | None, *, current_version: str, live_titles: dict[str, str]) -> tuple[dict | None, list[dict]]:
    """Return the payload passed to describe_readiness, plus verified article links.

    None means there is no AI record yet, so the curated graph can still be shown.
    """
    if not record:
        return None, []
    if record.get('status') == READY and record.get('version') == current_version:
        payload = ready_payload_from_model(record)
        if payload is None:
            return {'status': UNAVAILABLE}, []
        matches = []
        for item in record.get('matches') or []:
            if not isinstance(item, dict):
                continue
            slug = item.get('slug')
            concept = item.get('concept')
            if slug in live_titles and concept in payload['prerequisite_concepts']:
                matches.append({'concept': concept, 'slug': slug, 'title': live_titles[slug]})
        return payload, matches
    if record.get('version') and record.get('version') != current_version:
        return {'status': STALE}, []
    return {'status': UNAVAILABLE}, []


def store_article_analysis(article, catalog: list[dict], generate: Callable[[str, str], str], *, path: str | None = None) -> dict:
    version = article_version(article)
    body = html_to_text(str(article.body or ''))
    payload = analyze_article_text(
        title=article.title or '',
        intro=article.intro or '',
        body=body,
        generate=generate,
        other_titles=[item.get('title', '') for item in catalog if item.get('slug') != article.slug],
    )
    record = {'version': version, 'status': payload['status']}
    if payload['status'] == READY:
        record.update(payload)
        record['matches'] = match_concepts(
            payload['prerequisite_concepts'],
            catalog,
            exclude_slug=article.slug,
        )
    path = path or default_store_path()
    store = load_store(path)
    store['articles'][article.slug] = record
    save_store(store, path)
    return record


def invalidate_if_changed(article, *, path: str | None = None) -> bool:
    path = path or default_store_path()
    store = load_store(path)
    record = store['articles'].get(article.slug)
    if not isinstance(record, dict) or record.get('status') != READY:
        return False
    if record.get('version') == article_version(article):
        return False
    record['status'] = STALE
    save_store(store, path)
    return True


def display_analysis(article, *, path: str | None = None, live_titles: dict[str, str] | None = None):
    path = path or default_store_path()
    record = load_store(path)['articles'].get(article.slug)
    if live_titles is None:
        from a_blog.models import ArticlePage

        live_titles = dict(ArticlePage.objects.live().values_list('slug', 'title'))
    return analysis_for_display(record if isinstance(record, dict) else None,
                                current_version=article_version(article),
                                live_titles=live_titles)


def cached_bridge_summary(key: str, *, path: str | None = None) -> str | None:
    item = load_store(path)['bridges'].get(key)
    if isinstance(item, dict) and isinstance(item.get('summary'), str) and item['summary'].strip():
        return item['summary'].strip()
    return None


def save_bridge_summary(key: str, summary: str, tier: str, *, path: str | None = None) -> None:
    path = path or default_store_path()
    store = load_store(path)
    store['bridges'][key] = {'summary': summary.strip()[:800], 'tier': tier}
    save_store(store, path)


def explain_concept(concept: str, source: str, *, generate: Callable[[str, str], str]) -> str | None:
    if not concept.strip() or not source.strip():
        return None
    try:
        raw = generate(_BRIDGE_SYSTEM, f'Concept: {concept}\n\nSource:\n{source[:4000]}')
    except Exception:
        logger.exception('Concept bridge request failed for %s', concept)
        return None
    summary = re.sub(r'\s+', ' ', raw or '').strip()
    if not summary:
        return None
    return summary[:800]
