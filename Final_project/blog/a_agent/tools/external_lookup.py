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
    r'这篇博客',
    r'本站文章',
    r'博客里',
    r'文章关于',
)
_LEADING = re.compile(
    r'^(please |can you |could you |what is |what\'s |explain |tell me about |请问|请教|请解释|帮我查一下|查一下|什么是|解释一下|说明一下|如何理解|告诉我关于|介绍一下)+',
    re.I,
)


def topic_from_query(query: str) -> str:
    text = re.sub(r'\s+', ' ', (query or '')).strip(' ?.')
    for pattern in _STRIP_PATTERNS:
        text = re.sub(pattern, ' ', text, flags=re.I)
    text = _LEADING.sub('', text)
    text = re.sub(r'[？\?！!。，,\'\"“”‘’（）\(\)]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip(' ?.\"\'')
    if not text:
        return ''
    # In Chinese, words are not space-separated, so 2+ chars is a valid concept
    if re.search(r'[\u4e00-\u9fff]', text):
        if len(text) < 2:
            return ''
        return text[:120]
    if len(text) < 3 or len(text.split()) > 14:
        return ''
    return text[:120]


def _fetch(url: str, timeout: float = 4.0) -> str:
    request = urllib.request.Request(
        url,
        headers={'User-Agent': 'CheeseO-Reading-Assistant/1.0 (educational project)'},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode('utf-8', errors='replace')


def _tavily_search_notes(query: str, limit: int = 3) -> list[dict]:
    """Full-web search via Tavily API if configured."""
    import os
    try:
        from django.conf import settings
        api_key = getattr(settings, 'TAVILY_API_KEY', None) or os.getenv('TAVILY_API_KEY')
    except Exception:
        api_key = os.getenv('TAVILY_API_KEY')
    if not api_key:
        return []
    url = 'https://api.tavily.com/search'
    payload = json.dumps({'api_key': api_key, 'query': query, 'max_results': limit}).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json', 'User-Agent': 'CheeseO/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            results = data.get('results', [])
            return [
                {
                    'title': r.get('title') or query,
                    'url': r.get('url') or '',
                    'excerpt': (r.get('content') or '')[:700],
                    'source_name': 'Web Search',
                    'source_abbr': 'Web',
                    'is_external': True,
                }
                for r in results
                if r.get('url')
            ]
    except Exception:
        return []


def _serper_search_notes(query: str, limit: int = 3) -> list[dict]:
    """Google web search via Serper API if configured."""
    import os
    try:
        from django.conf import settings
        api_key = getattr(settings, 'SERPER_API_KEY', None) or os.getenv('SERPER_API_KEY')
    except Exception:
        api_key = os.getenv('SERPER_API_KEY')
    if not api_key:
        return []
    url = 'https://google.serper.dev/search'
    payload = json.dumps({'q': query, 'num': limit}).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={'X-API-KEY': api_key, 'Content-Type': 'application/json', 'User-Agent': 'CheeseO/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            results = data.get('organic', [])
            return [
                {
                    'title': r.get('title') or query,
                    'url': r.get('link') or '',
                    'excerpt': (r.get('snippet') or '')[:700],
                    'source_name': 'Web Search',
                    'source_abbr': 'Web',
                    'is_external': True,
                }
                for r in results
                if r.get('link')
            ]
    except Exception:
        return []


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
    if excerpt and len(excerpt) >= 40:
        return {
            'title': (payload.get('Heading') or topic).strip(),
            'url': (payload.get('AbstractURL') or '').strip(),
            'excerpt': excerpt[:700],
            'source_name': 'DuckDuckGo',
            'source_abbr': 'DDG',
            'is_external': True,
        }
    # Fallback to RelatedTopics
    for rel in payload.get('RelatedTopics', [])[:3]:
        if isinstance(rel, dict) and rel.get('Text') and rel.get('FirstURL'):
            txt = (rel.get('Text') or '').strip()
            if len(txt) >= 30:
                first_url = rel.get('FirstURL') or ''
                heading = first_url.rstrip('/').split('/')[-1].replace('_', ' ')
                return {
                    'title': heading or topic,
                    'url': first_url,
                    'excerpt': txt[:700],
                    'source_name': 'DuckDuckGo',
                    'source_abbr': 'DDG',
                    'is_external': True,
                }
    return None


def _wikipedia_title(topic: str, fetch) -> str:
    is_chinese = bool(re.search(r'[\u4e00-\u9fff]', topic))
    lang = 'zh' if is_chinese else 'en'

    search_terms = [topic]
    if is_chinese:
        cleaned = re.sub(r'[的之在与和对于关于什么是有哪些怎么实现]', ' ', topic).strip()
        words = [w for w in cleaned.split() if len(w) >= 2]
        if len(words) > 1:
            search_terms.append(' OR '.join(words))
            search_terms.extend(words)
    else:
        words = [w for w in re.findall(r'[A-Za-z0-9]+', topic) if len(w) >= 3]
        if len(words) > 1:
            search_terms.append(' OR '.join(words))
            search_terms.extend(words)

    for term in search_terms:
        search_url = f'https://{lang}.wikipedia.org/w/api.php?' + urllib.parse.urlencode({
            'action': 'query',
            'list': 'search',
            'srsearch': term,
            'srlimit': '3',
            'format': 'json',
            'utf8': '1',
        })
        try:
            found = json.loads(fetch(search_url))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
            continue
        hits = (found.get('query') or {}).get('search') or []
        topic_words = {word.lower() for word in re.findall(r'[A-Za-z0-9\u4e00-\u9fff]+', topic) if len(word) >= 2}
        for hit in hits:
            title = (hit.get('title') or '').strip()
            title_words = {word.lower() for word in re.findall(r'[A-Za-z0-9\u4e00-\u9fff]+', title)}
            if title and topic_words & title_words:
                return title
        if hits:
            return (hits[0].get('title') or '').strip()
    return ''


def _wikipedia_note(topic: str, fetch) -> dict | None:
    is_chinese = bool(re.search(r'[\u4e00-\u9fff]', topic))
    lang = 'zh' if is_chinese else 'en'
    title = _wikipedia_title(topic, fetch)
    if not title:
        return None
    summary_url = f'https://{lang}.wikipedia.org/api/rest_v1/page/summary/' + urllib.parse.quote(title, safe='')
    excerpt = ''
    desktop_page = ''
    try:
        payload = json.loads(fetch(summary_url))
        excerpt = (payload.get('extract') or '').strip()
        content_urls = payload.get('content_urls') or {}
        desktop = content_urls.get('desktop') or {}
        desktop_page = (desktop.get('page') or '').strip()
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        pass

    if not desktop_page:
        desktop_page = f'https://{lang}.wikipedia.org/wiki/' + urllib.parse.quote(title.replace(' ', '_'))

    if not excerpt:
        # Fallback to OpenSearch snippet
        search_url = f'https://{lang}.wikipedia.org/w/api.php?' + urllib.parse.urlencode({
            'action': 'query',
            'list': 'search',
            'srsearch': title,
            'srlimit': '1',
            'format': 'json',
            'utf8': '1',
        })
        try:
            s_data = json.loads(fetch(search_url))
            s_hits = (s_data.get('query') or {}).get('search') or []
            if s_hits:
                excerpt = re.sub(r'<[^>]+>', '', s_hits[0].get('snippet') or '').strip()
        except Exception:
            pass

    if len(excerpt) < 20:
        return None

    return {
        'title': title,
        'url': desktop_page,
        'excerpt': excerpt[:700],
        'source_name': 'Wikipedia',
        'source_abbr': 'Wiki',
        'is_external': True,
    }


def lookup_outside_the_blog(query: str, *, fetch=None) -> list[dict]:
    topic = topic_from_query(query) or query.strip()
    if not topic or len(topic) < 2:
        return []
    fetch = fetch or _fetch

    # 1. Full-web search if API key configured (Tavily / Serper)
    web_notes = _tavily_search_notes(topic) or _serper_search_notes(topic)
    if web_notes:
        return web_notes[:3]

    # 2. Wikipedia multi-language search
    wiki_note = _wikipedia_note(topic, fetch)

    # 3. DuckDuckGo knowledge graph
    ddg_note = _duckduckgo_note(topic, fetch)

    notes = []
    if wiki_note:
        notes.append(wiki_note)
    if ddg_note and not any(n.get('url') == ddg_note.get('url') for n in notes):
        notes.append(ddg_note)

    return notes[:3]


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
