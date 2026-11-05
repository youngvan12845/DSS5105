"""Look up a topic outside the blog when on-site search finds nothing.

Results are notes for the reply. They are not blog lessons and must not be
added to the SOURCES list.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

_STRIP_PATTERNS = (
    r'\bsummarize the article (about|titled|called)\b',
    r'\bsummarize the article\b',
    r'\bfind articles about\b',
    r'\barticle about\b',
    r'\bon this blog\b',
    r'\bon this site\b',
    r'\bin the blog corpus\b',
    r'\bin this blog\b',
    r'\bthis blog\b',
    r'\bblog corpus\b',
)
_LEADING = re.compile(
    r'^(please |can you |could you |what is |what\'s |explain |tell me about )+',
    re.I,
)


def topic_from_query(query: str) -> str:
    text = re.sub(r'\s+', ' ', (query or '')).strip(' ?.')
    for pattern in _STRIP_PATTERNS:
        text = re.sub(pattern, ' ', text, flags=re.I)
    text = _LEADING.sub('', text)
    text = re.sub(r'\s+', ' ', text).strip(' ?.\"\'')
    if len(text) < 3 or len(text.split()) > 12:
        return ''
    return text[:120]


def _fetch(url: str, timeout: float = 4.0) -> str:
    request = urllib.request.Request(
        url,
        headers={'User-Agent': 'CheeseO-Reading-Assistant/1.0 (educational project)'},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode('utf-8', errors='replace')


def _duckduckgo_note(topic: str, fetch) -> dict | None:
    url = 'https://api.duckduckgo.com/?' + urllib.parse.urlencode({
        'q': topic,
        'format': 'json',
        'no_html': '1',
        'skip_disambig': '1',
    })
    try:
        payload = json.loads(fetch(url))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return None
    excerpt = (payload.get('AbstractText') or '').strip()
    if len(excerpt) < 40:
        return None
    return {
        'title': (payload.get('Heading') or topic).strip(),
        'url': (payload.get('AbstractURL') or '').strip(),
        'excerpt': excerpt[:700],
        'source_name': 'DuckDuckGo',
    }


def _wikipedia_title(topic: str, fetch) -> str:
    search_url = 'https://en.wikipedia.org/w/api.php?' + urllib.parse.urlencode({
        'action': 'query',
        'list': 'search',
        'srsearch': topic,
        'srlimit': '3',
        'format': 'json',
    })
    try:
        found = json.loads(fetch(search_url))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return ''
    hits = (found.get('query') or {}).get('search') or []
    topic_words = {word.lower() for word in re.findall(r'[A-Za-z0-9]+', topic) if len(word) > 3}
    for hit in hits:
        title = (hit.get('title') or '').strip()
        title_words = {word.lower() for word in re.findall(r'[A-Za-z0-9]+', title)}
        if title and topic_words & title_words:
            return title
    if hits:
        return (hits[0].get('title') or '').strip()
    return ''


def _wikipedia_note(topic: str, fetch) -> dict | None:
    title = _wikipedia_title(topic, fetch)
    if not title:
        return None
    summary_url = 'https://en.wikipedia.org/api/rest_v1/page/summary/' + urllib.parse.quote(title, safe='')
    try:
        payload = json.loads(fetch(summary_url))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return None
    excerpt = (payload.get('extract') or '').strip()
    if len(excerpt) < 40:
        return None
    content_urls = payload.get('content_urls') or {}
    desktop = content_urls.get('desktop') or {}
    return {
        'title': (payload.get('title') or title).strip(),
        'url': (desktop.get('page') or '').strip(),
        'excerpt': excerpt[:700],
        'source_name': 'Wikipedia',
    }


def lookup_outside_the_blog(query: str, *, fetch=None) -> list[dict]:
    topic = topic_from_query(query)
    if not topic:
        return []
    fetch = fetch or _fetch
    note = _duckduckgo_note(topic, fetch) or _wikipedia_note(topic, fetch)
    return [note] if note else []
