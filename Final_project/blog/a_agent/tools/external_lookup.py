"""Look up a topic on the public web when the blog has no lesson.

Notes are not blog lessons and must not be added to the SOURCES list.
Each note keeps the page it came from so the reply can link to it.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

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
_MAX_NOTES = 4
# Words about the reader or the request. They are not something to look up.
_NOT_A_TOPIC = {
    'able', 'about', 'add', 'added', 'adding', 'after', 'again', 'also',
    'another', 'answer', 'around', 'article', 'articles', 'assignment',
    'because', 'basic', 'basics', 'been', 'before', 'begin', 'beginner',
    'being', 'blog', 'blogs', 'bookmark', 'bookmarks', 'browsing', 'chinese',
    'concept', 'concepts', 'continue', 'could', 'course', 'courses', 'delete',
    'does', 'doing', 'done', 'dont', 'each', 'english', 'example', 'examples',
    'explain', 'from', 'give', 'group', 'have', 'help', 'here', 'history',
    'into', 'join', 'joined', 'just', 'know', 'language', 'last', 'leave',
    'left', 'learning', 'lesson', 'lessons', 'like', 'list', 'lists', 'make',
    'mandarin', 'many', 'more', 'most', 'much', 'need', 'next', 'off', 'only',
    'order', 'other', 'over', 'path', 'paths', 'pick', 'plan', 'planning',
    'plans', 'please', 'project', 'projects', 'read', 'reading', 'really',
    'recent', 'recently', 'remove', 'removed', 'reply', 'response', 'save',
    'saved', 'series', 'should', 'show', 'site', 'some', 'someone',
    'something', 'start', 'started', 'still', 'stopped', 'such', 'summarize',
    'summary', 'team', 'tell', 'than', 'that', 'their', 'them', 'then',
    'there', 'these', 'they', 'this', 'those', 'through', 'time', 'track',
    'tracks', 'under', 'using', 'very', 'visited', 'want', 'were', 'what',
    'when', 'where', 'which', 'while', 'with', 'work', 'working', 'would',
    'your',
}


def _request_word(word: str) -> bool:
    """A request word, including a short typo such as "plana" for "plan a"."""
    if word in _NOT_A_TOPIC:
        return True
    for blocked in _NOT_A_TOPIC:
        extra = len(word) - len(blocked)
        if len(blocked) >= 4 and word.startswith(blocked) and 0 < extra <= 2:
            return True
    return False


def content_terms(text: str) -> list[str]:
    """Words that could be a subject, not the wording of the request."""
    seen: list[str] = []
    for word in re.findall(r'[a-z0-9]+', (text or '').lower()):
        if len(word) < 4 or _request_word(word) or word in seen:
            continue
        seen.append(word)
    return seen


def notes_about_the_question(notes: list[dict], query: str) -> list[dict]:
    """Keep a public note only when it is actually about the question."""
    topic = topic_from_query(query) or (query or '')
    terms = content_terms(topic)
    if not terms:
        terms = []
        for word in re.findall(r'[a-z0-9]+', topic.lower()):
            if len(word) >= 3 and not _request_word(word) and word not in terms:
                terms.append(word)
    if not terms:
        return []
    kept = []
    for note in notes or []:
        blob = f"{note.get('title') or ''} {note.get('excerpt') or ''}".lower()
        if any(
            re.search(rf'(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])', blob)
            for term in terms
        ):
            kept.append(note)
    return kept


def wants_several_sources(query: str) -> bool:
    """A long or multi-part question should cite more than one public page."""
    text = query or ''
    words = re.findall(r'[A-Za-z0-9\u4e00-\u9fff]+', text)
    if len(words) >= 18:
        return True
    lower = text.lower()
    return any(mark in lower for mark in (
        'compare', 'difference', 'versus', ' vs ', 'whether',
        '判断', '比较', '区别', '以及', '还是', '要不要',
    ))


def _cleaned_query(query: str) -> str:
    text = re.sub(r'\s+', ' ', (query or '')).strip(' ?.')
    for pattern in _STRIP_PATTERNS:
        text = re.sub(pattern, ' ', text, flags=re.I)
    return re.sub(r'\s+', ' ', text).strip(' ?.\"\'')


def topic_from_query(query: str) -> str:
    text = _LEADING.sub('', _cleaned_query(query))
    text = re.sub(r'\s+', ' ', text).strip(' ?.\"\'')
    if len(text) < 3 or len(text.split()) > 12:
        return ''
    return text[:120]


def _fetch(url: str, timeout: float = 4.0) -> str:
    # A short bot name gets an empty DuckDuckGo page, so this uses a browser header.
    request = urllib.request.Request(
        url,
        headers={
            'User-Agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            ),
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode('utf-8', errors='replace')


def _source_name(url: str, fallback: str = '') -> str:
    host = (urllib.parse.urlparse(url).hostname or '').removeprefix('www.')
    return host or fallback


def _public_url(href: str) -> str:
    href = (href or '').strip()
    if href.startswith('//'):
        href = 'https:' + href
    parsed = urllib.parse.urlparse(href)
    target = urllib.parse.parse_qs(parsed.query).get('uddg', [''])[0]
    url = target or href
    if not url.startswith(('http://', 'https://')):
        return ''
    host = (urllib.parse.urlparse(url).hostname or '').lower()
    if host.endswith('duckduckgo.com'):
        return ''
    return url


class _WebResultParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.notes: list[dict] = []
        self._capture = ''
        self._href = ''
        self._buf: list[str] = []
        self._pending: dict | None = None

    def handle_starttag(self, tag, attrs):
        if tag != 'a':
            return
        attr = dict(attrs)
        classes = attr.get('class', '')
        if 'result__a' in classes:
            self._capture = 'title'
            self._href = attr.get('href', '')
            self._buf = []
        elif 'result__snippet' in classes:
            self._capture = 'snippet'
            self._buf = []

    def handle_data(self, data):
        if self._capture:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag != 'a' or not self._capture:
            return
        text = re.sub(r'\s+', ' ', ''.join(self._buf)).strip()
        if self._capture == 'title':
            url = _public_url(self._href)
            if url and text:
                self._pending = {
                    'title': text[:180],
                    'url': url,
                    'excerpt': '',
                    'source_name': _source_name(url, 'Web'),
                }
        elif self._capture == 'snippet' and self._pending is not None:
            self._pending['excerpt'] = text[:700]
            self.notes.append(self._pending)
            self._pending = None
        self._capture = ''
        self._buf = []


def _web_notes(topic: str, fetch, limit: int) -> list[dict]:
    url = 'https://html.duckduckgo.com/html/?' + urllib.parse.urlencode({'q': topic})
    try:
        html = fetch(url)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return []
    parser = _WebResultParser()
    try:
        parser.feed(html or '')
    except Exception:
        return []
    notes = []
    seen = set()
    for note in parser.notes:
        if note['url'] in seen:
            continue
        seen.add(note['url'])
        notes.append(note)
        if len(notes) >= limit:
            break
    return notes


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
    page = (payload.get('AbstractURL') or '').strip()
    if len(excerpt) < 40 or not page.startswith(('http://', 'https://')):
        return None
    return {
        'title': (payload.get('Heading') or topic).strip(),
        'url': page,
        'excerpt': excerpt[:700],
        'source_name': _source_name(page, 'DuckDuckGo'),
    }


def _wikipedia_titles(topic: str, fetch, limit: int) -> list[str]:
    search_url = 'https://en.wikipedia.org/w/api.php?' + urllib.parse.urlencode({
        'action': 'query',
        'list': 'search',
        'srsearch': topic,
        'srlimit': str(max(3, limit)),
        'format': 'json',
    })
    try:
        found = json.loads(fetch(search_url))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return []
    hits = (found.get('query') or {}).get('search') or []
    topic_words = {word.lower() for word in re.findall(r'[A-Za-z0-9]+', topic) if len(word) > 3}
    single_word = len(topic.split()) == 1
    titles = []
    for hit in hits:
        title = (hit.get('title') or '').strip()
        title_words = {word.lower() for word in re.findall(r'[A-Za-z0-9]+', title)}
        if single_word:
            relevant = title.lower().startswith(topic.lower())
        else:
            relevant = bool(topic_words & title_words)
        if title and relevant and title not in titles:
            titles.append(title)
        if len(titles) >= limit:
            return titles
    return titles


def _wikipedia_summary(title: str, fetch) -> dict | None:
    summary_url = 'https://en.wikipedia.org/api/rest_v1/page/summary/' + urllib.parse.quote(title, safe='')
    try:
        payload = json.loads(fetch(summary_url))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return None
    excerpt = (payload.get('extract') or '').strip()
    if payload.get('type') == 'disambiguation' or 'may refer to' in excerpt[:80].lower():
        return None
    if len(excerpt) < 40:
        return None
    content_urls = payload.get('content_urls') or {}
    desktop = content_urls.get('desktop') or {}
    page = (desktop.get('page') or '').strip()
    if not page.startswith(('http://', 'https://')):
        return None
    return {
        'title': (payload.get('title') or title).strip(),
        'url': page,
        'excerpt': excerpt[:700],
        'source_name': 'Wikipedia',
    }


def _wikipedia_notes(topic: str, fetch, limit: int) -> list[dict]:
    notes = []
    seen = set()
    for title in _wikipedia_titles(topic, fetch, limit):
        note = _wikipedia_summary(title, fetch)
        if note and note['url'] not in seen:
            notes.append(note)
            seen.add(note['url'])
        if len(notes) >= limit:
            break
    return notes


def lookup_outside_the_blog(query: str, *, fetch=None) -> list[dict]:
    topic = topic_from_query(query)
    if not topic:
        return []
    fetch = fetch or _fetch
    limit = 6 if wants_several_sources(query) else _MAX_NOTES
    wiki_limit = 3 if wants_several_sources(query) else 1
    web_query = _cleaned_query(query) or topic
    notes = _web_notes(web_query, fetch, limit)
    seen = {note['url'] for note in notes}
    extra_notes = [_duckduckgo_note(topic, fetch), *_wikipedia_notes(topic, fetch, wiki_limit)]
    for extra in extra_notes:
        if extra and extra['url'] not in seen and len(notes) < limit:
            notes.append(extra)
            seen.add(extra['url'])
    return notes_about_the_question(notes, topic)


def extract_enrichment_topics(query: str) -> list[str]:
    """Concepts worth a short public note when the question asks for a deeper comparison."""
    q = (query or '').lower()
    topics = []
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
    if not topics and any(w in q for w in ('数学原理', '數學原理', '底层原理', '底層原理', 'algorithm', 'internals')):
        for acronym in re.findall(r'\b[A-Z]{2,10}\b', query or ''):
            if acronym not in ('HTTP', 'HTML', 'URL', 'GET', 'POST', 'GIT') and acronym not in topics:
                topics.append(acronym)
    return topics[:2]


def enrich_concept_lookup(query: str, *, fetch=None) -> list[dict]:
    """Public notes for a deep-dive or cross-domain question. Not blog lessons."""
    notes = []
    for topic in extract_enrichment_topics(query):
        found = lookup_outside_the_blog(topic, fetch=fetch)
        if not found:
            continue
        note = dict(found[0])
        note['source_abbr'] = note.get('source_name') or 'Web'
        note['is_external'] = True
        notes.append(note)
    return notes
