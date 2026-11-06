"""Look up a topic outside the blog when on-site search finds nothing or when
enriching deep mathematical/system principles and cross-domain analogies.

Results are notes for the reply.
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
        'source_abbr': 'DDG',
        'is_external': True,
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
        'source_abbr': 'Wiki',
        'is_external': True,
    }


def lookup_outside_the_blog(query: str, *, fetch=None) -> list[dict]:
    topic = topic_from_query(query)
    if not topic:
        return []
    fetch = fetch or _fetch
    note = _duckduckgo_note(topic, fetch) or _wikipedia_note(topic, fetch)
    return [note] if note else []


def extract_enrichment_topics(query: str) -> list[str]:
    """Extract targeted concepts for deep-dive principles or cross-domain analogy."""
    q = (query or '').lower()
    topics = []

    # 1. Cross-domain comparison targets
    if any(k in q for k in ('数据库', '資料庫', 'database', 'db')):
        if any(w in q for w in ('index', '索引')):
            topics.append('Database index')
        if any(w in q for w in ('transaction', '事务', '事務')):
            topics.append('Database transaction')
    if any(k in q for k in ('前端', 'frontend', 'css', 'ui')):
        if any(w in q for w in ('container', '容器')):
            topics.append('Container query')
    if any(k in q for k in ('机器学习', '機器學習', 'ml', 'ai', 'data science')):
        if any(w in q for w in ('pipeline', '流水线', '管线')):
            topics.append('Pipeline (computing)')

    # 2. Mathematical and CS algorithmic internals
    patterns = [
        (r'\b(sha-?1|sha-?256|hash function|散列|哈希|散列函数)\b', 'Cryptographic hash function'),
        (r'\b(dag|directed acyclic graph|有向无环图|有向無環圖)\b', 'Directed acyclic graph'),
        (r'\b(cgroups?|control groups?|控制组)\b', 'Cgroups'),
        (r'\b(namespaces?|命名空间|命名空間)\b', 'Linux namespaces'),
        (r'\b(epoll|io multiplexing|多路复用|多路復用)\b', 'Epoll'),
        (r'\b(b-?tree|b树|b\+树|b-樹)\b', 'B-tree'),
        (r'\b(raft|paxos|consensus|共识算法)\b', 'Raft (algorithm)'),
        (r'\b(crdt)\b', 'Conflict-free replicated data type'),
    ]
    for pattern, target in patterns:
        if re.search(pattern, q, re.I) and target not in topics:
            topics.append(target)

    # 3. Fallback: If query explicitly asks for mathematical or underlying principles
    if not topics and any(w in q for w in ('数学原理', '數學原理', '底层原理', '底層原理', 'algorithm', 'internals')):
        acronyms = re.findall(r'\b[A-Z]{2,10}\b', query)
        for acr in acronyms:
            if acr not in ('HTTP', 'HTML', 'URL', 'GET', 'POST', 'GIT'):
                topics.append(acr)

    return topics[:2]


def enrich_concept_lookup(query: str, *, fetch=None) -> list[dict]:
    """Look up authoritative external concepts to enrich deep principles or cross-domain analogy."""
    topics = extract_enrichment_topics(query)
    if not topics:
        return []
    fetch = fetch or _fetch
    results = []
    for t in topics:
        note = _wikipedia_note(t, fetch) or _duckduckgo_note(t, fetch)
        if note:
            results.append(note)
    return results
