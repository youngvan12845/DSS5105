from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import quote, urlparse

from django.contrib.auth.models import AnonymousUser, User

from a_blog.models import ArticlePage

from a_agent.tools.article_scope import (
    article_scope_to_dict,
    get_article_scope,
    scoped_keyword_hit,
    search_scoped_article_chunks,
    search_scoped_article_vectors,
)
from a_agent.tools.comment_draft import build_comment_draft, propose_post_comment
from a_agent.tools.external_lookup import (
    content_terms,
    enrich_concept_lookup,
    lookup_outside_the_blog,
    topic_from_query,
    wants_several_sources,
)
from a_agent.tools.browsing_history import get_browsing_history, history_to_dicts
from a_agent.tools.chunk_search import _extract_terms_and_phrases, _word_match, chunk_hits_to_dicts, search_article_chunks
from a_agent.tools.keyword_search import hits_to_dicts, keyword_search_articles
from a_agent.tools.reading_list import (
    get_reading_list,
    propose_add_to_reading_list,
    propose_remove_from_reading_list,
    reading_list_to_dicts,
)
from a_agent.tools.reading_paths import get_reading_path_for_user, reading_path_to_dict
from a_agent.tools.recommend import recommend_articles, recommend_hits_to_dicts
from a_agent.tools.vector_search import search_article_vectors, vector_hits_to_dicts
from a_agent.services.safety import check_safety_guardrails
from a_agent.services.language import wants_chinese
from a_agent.services.llm import generate_answer, get_llm_info, llm_configured
from a_agent.services.telemetry import (
    flush_telemetry,
    trace_agent,
    trace_llm_generation,
    trace_retriever,
)


@dataclass
class AgentReply:
    content: str
    citations: list[dict]
    tool_trace: list[dict]
    pending_action: dict = field(default_factory=dict)


CONTINUE_READING_HINTS = (
    'where did i',
    'continue reading',
    'last read',
    'pick up where',
    'left off',
    'read recently',
    'browsing history',
    'recent history',
    'recently read',
    'have i read',
    'history across',
)
RECOMMEND_HINTS = (
    'recommend',
    'what should i read',
    'what to read next',
    'suggest',
)
PATH_HINTS = (
    'learning path',
    'reading path',
    'progression path',
    'progression',
    'read first',
    'what order',
    'getting started',
    'from scratch',
    'curriculum',
    'how should a beginner',
    '入门',
    '路径',
    '入門',
    '路徑',
    '學習路徑',
    '閱讀路徑',
    'learn machine learning',
    'learn python',
    'learn docker',
    'learn git',
)
ADD_LIST_HINTS = (
    'add to',
    'save to list',
    '加入清单',
    '加入清單',
    '加入阅读清单',
    '加入閱讀清單',
    '加到清单',
    '加到清單',
)
REMOVE_LIST_HINTS = (
    'remove from',
    'delete from',
    'remove from my list',
    'remove from reading list',
    'delete from reading list',
    '从清单移除',
    '移出清单',
    '從清單移除',
    '移出清單',
    '從閱讀清單移除',
    '从阅读清单移除',
)
LIST_QUERY_HINTS = (
    'show my reading list',
    'my reading list',
    'what is in my list',
    'reading list items',
    '我的阅读清单',
    '我的閱讀清單',
    '查看阅读清单',
    '查看閱讀清單',
)
COMMENT_HINTS = (
    'draft a comment',
    'write a comment',
    'post a comment',
    'leave a comment',
    'draft a commant',
    'write a commant',
    'post a commant',
    'leave a commant',
    'draft a commet',
    'write a commet',
    'draft a command thanking',
    'draft a command asking',
    'comment on',
    'comment for',
    '帮我写评论',
    '帮我写一篇评论',
    '写一条评论',
    '写一篇评论',
    '写评论',
    '评论草稿',
    '发表评论',
    '帮我拟',
    '幫我寫評論',
    '幫我寫一篇評論',
    '寫一條評論',
    '寫一篇評論',
    '寫評論',
    '評論草稿',
    '發表評論',
    '幫我擬',
    '幫我留言',
    '寫一則留言',
)


DEEP_PRINCIPLE_HINTS = (
    '数学原理', '數學原理', '底层原理', '底層原理', '底层算法', '底層演算法',
    '底层怎么实现', '底層怎麼實現', '数据结构', '資料結構', '公式', '证明', '證明',
    'mathematical', 'internals of', 'under the hood', 'how it works internally',
    'algorithm', 'hash function', '散列', '哈希', '有向无环图', '有向無環圖',
)
CROSS_DOMAIN_HINTS = (
    '区别', '區別', '不同', '和数据库的', '和前端的', '和机器学习的',
    'versus', 'vs.', 'vs ', 'difference between', 'compare with', 'in other fields',
)


_QUOTED_TITLE_RE = re.compile(r'["“「『《]([^"”」』》]{3,})["”」』》]|\'([^\']{4,})\'')


def _strip_quoted_titles(query: str) -> str:
    """Strip quoted article titles so words inside titles ('What Is ...') do not trigger QA/outside intents."""
    return _QUOTED_TITLE_RE.sub(' ', query or '')


def _classify_intents(query: str) -> set[str]:
    q = (query or '').lower()
    unquoted_q = _strip_quoted_titles(query).lower().strip() or q
    intents: set[str] = set()

    if any(h in unquoted_q for h in CONTINUE_READING_HINTS):
        intents.add('history')
    if any(h in unquoted_q for h in RECOMMEND_HINTS):
        intents.add('recommend')
    if any(h in unquoted_q for h in PATH_HINTS) or ('path' in unquoted_q and not any(h in unquoted_q for h in CONTINUE_READING_HINTS)):
        intents.add('path')
    if any(h in unquoted_q for h in REMOVE_LIST_HINTS) or (('remove' in unquoted_q or 'delete' in unquoted_q) and ('reading list' in unquoted_q or 'from list' in unquoted_q)):
        intents.add('action_remove')
    elif any(h in unquoted_q for h in ADD_LIST_HINTS) or (('add' in unquoted_q or 'save' in unquoted_q) and ('reading list' in unquoted_q or 'to list' in unquoted_q)):
        intents.add('action_add')
    elif any(h in unquoted_q for h in LIST_QUERY_HINTS):
        intents.add('reading_list')
    if any(h in unquoted_q for h in COMMENT_HINTS):
        intents.add('action_comment')
    if any(h in unquoted_q for h in DEEP_PRINCIPLE_HINTS):
        intents.add('deep_dive')
    if any(h in unquoted_q for h in CROSS_DOMAIN_HINTS):
        intents.add('cross_domain')

    if intents & {'action_add', 'action_remove', 'action_comment', 'reading_list'}:
        if 'action_add' in intents or 'action_remove' in intents:
            intents.add('keyword')
        return intents

    search_triggers = (
        'what', 'which', 'summarize', 'explain', 'cover', 'mention',
        'recommend', 'suggest', 'about', 'related', 'find', 'how', 'why',
        'give', 'progression', 'path', 'docker', 'git', 'rag', 'agent',
        'quiz', 'test', 'question', 'exam', 'pitfall', 'pitfalls', 'excerpt',
    )
    if not intents or any(word in q for word in search_triggers):
        intents.update({'keyword', 'chunk', 'vector'})
    return intents


def _hit_matches_query_terms(hit, terms: list[str]) -> bool:
    """True when the lesson title/tags, or its snippet, clearly matches the question."""
    if not terms:
        return True
    title = f"{getattr(hit, 'title', '')} {getattr(hit, 'article_title', '')} {getattr(hit, 'tags', '')}".lower()
    title_hits = sum(1 for term in terms if _word_match(term, title))
    # Short queries such as "version control" need both words in the title.
    title_needed = len(terms) if len(terms) <= 2 else (len(terms) + 1) // 2
    if title_hits >= title_needed:
        return True
    body = f"{getattr(hit, 'content', '')} {getattr(hit, 'snippet', '')} {getattr(hit, 'intro', '')}".lower()
    matched = sum(1 for term in terms if _word_match(term, body))
    return matched >= min(2, len(terms))


def _filter_hits_to_query(hits: list, query: str) -> list:
    """Drop lessons that only matched weakly, such as Wagtail on a version-control question."""
    if not hits:
        return hits
    terms = content_terms(query)
    if not terms:
        return hits
    kept = [hit for hit in hits if _hit_matches_query_terms(hit, terms)]
    return kept if kept else hits


def _format_citations(keyword_hits, chunk_hits, vector_hits, reading_path=None) -> list[dict]:
    citations: list[dict] = []
    seen: set[int] = set()

    if reading_path and hasattr(reading_path, 'steps'):
        for step in reading_path.steps:
            if step.article_id not in seen:
                seen.add(step.article_id)
                citations.append(
                    {
                        'article_id': step.article_id,
                        'title': step.title,
                        'url': step.url,
                        'source': 'reading_path',
                    }
                )
        if citations:
            return citations[:5]

    # Prefer keyword/chunk matches over vector so weak semantic hits stay out of Sources.
    for hits, source in (
        (keyword_hits, 'keyword_search'),
        (chunk_hits, 'chunk_search'),
        (vector_hits, 'vector_search'),
    ):
        for hit in hits:
            article_id = getattr(hit, 'article_id', None)
            if article_id is None or article_id in seen:
                continue
            title = getattr(hit, 'article_title', getattr(hit, 'title', '')).strip()
            if not title:
                continue
            seen.add(article_id)
            citations.append(
                {
                    'article_id': article_id,
                    'title': title,
                    'url': getattr(hit, 'article_url', getattr(hit, 'url', '')),
                    'source': source,
                }
            )
    return citations[:5]


def _extract_ordinal_index(query: str) -> int | None:
    q = query.lower()
    if any(tok in q for tok in ('first', '1st', '第一篇', '第一個', '第一个', '第1篇', '第 1 篇')):
        return 0
    if any(tok in q for tok in ('second', '2nd', '第二篇', '第二個', '第二个', '第2篇', '第 2 篇')):
        return 1
    if any(tok in q for tok in ('third', '3rd', '第三篇', '第三個', '第三个', '第3篇', '第 3 篇')):
        return 2
    if any(tok in q for tok in ('fourth', '4th', '第四篇', '第四個', '第四个', '第4篇', '第 4 篇')):
        return 3
    if any(tok in q for tok in ('fifth', '5th', '第五篇', '第五個', '第五个', '第5篇', '第 5 篇')):
        return 4
    return None


def _is_multi_article_request(query: str) -> bool:
    q = query.lower()
    if any(tok in q for tok in ('only', '只', '僅', '仅', 'single', 'this article', '這篇', '这篇')):
        return False
    multi_tokens = (
        'all ', 'both ', 'these ', 'those ', 'top 2', 'top 3', '2 articles', '3 articles',
        'two articles', 'three articles', '全部', '所有', '這幾篇', '这几篇', '那幾篇', '那几篇',
    )
    return any(tok in q for tok in multi_tokens)


def _article_ids_for_action(
    keyword_hits,
    chunk_hits,
    vector_hits,
    limit: int = 1,
) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    # Prioritize keyword_hits and chunk_hits (lexical match) before vector_hits
    for hit in [*keyword_hits, *chunk_hits, *vector_hits]:
        article_id = getattr(hit, 'article_id', None)
        if article_id is None or article_id in seen:
            continue
        seen.add(article_id)
        ids.append(article_id)
        if len(ids) >= limit:
            break
    return ids


def _resolve_action_article_ids(
    query: str,
    keyword_hits,
    chunk_hits,
    vector_hits,
    *,
    current_list=None,
    chat_history=None,
    is_remove: bool = False,
) -> list[int]:
    q_lower = query.lower()

    # 1. Check ordinal references (e.g. "the second one you recommended" / "add the third article")
    ordinal_idx = _extract_ordinal_index(query)
    if ordinal_idx is not None:
        if chat_history:
            all_live_pages = None
            for msg in reversed(chat_history):
                if getattr(msg, 'role', '') != 'assistant':
                    continue
                if getattr(msg, 'pending_action', None):
                    continue
                cites = [
                    c for c in (getattr(msg, 'citations', None) or [])
                    if c.get('article_id')
                ]
                if ordinal_idx < len(cites):
                    return [int(cites[ordinal_idx]['article_id'])]
                msg_text = (getattr(msg, 'content', '') or '').lower()
                if msg_text:
                    if all_live_pages is None:
                        all_live_pages = list(ArticlePage.objects.live())
                    pos_matches = []
                    for page in all_live_pages:
                        t_low = (page.title or '').strip().lower()
                        if len(t_low) >= 6:
                            idx = msg_text.find(t_low)
                            if idx >= 0:
                                pos_matches.append((idx, page.pk))
                    pos_matches.sort(key=lambda x: x[0])
                    dedup_ids = []
                    for _, pk in pos_matches:
                        if pk not in dedup_ids:
                            dedup_ids.append(pk)
                    if ordinal_idx < len(dedup_ids):
                        return [dedup_ids[ordinal_idx]]
        if is_remove and current_list and ordinal_idx < len(current_list):
            return [current_list[ordinal_idx].article_id]

    # 2. Check quoted title in query ("...", “...”, 「...」, 『...』, '...')
    quoted_matches = re.findall(r'["“「『\']([^"”」』\']{4,})["”」』\']', query)
    for quoted in quoted_matches:
        q_title = quoted.strip().lower()
        if is_remove and current_list:
            for item in current_list:
                if q_title == item.title.lower() or q_title in item.title.lower() or item.title.lower() in q_title:
                    return [item.article_id]
        exact_page = (
            ArticlePage.objects.live().filter(title__iexact=quoted.strip()).first()
            or ArticlePage.objects.live().filter(title__icontains=quoted.strip()).first()
        )
        if exact_page:
            return [exact_page.pk]

    # 3. Check if any article title appears as a substring of the query
    if is_remove and current_list:
        matched_in_list = [
            item for item in current_list
            if len(item.title) >= 6 and item.title.lower() in q_lower
        ]
        if matched_in_list:
            matched_in_list.sort(key=lambda x: len(x.title), reverse=True)
            return [matched_in_list[0].article_id]

    live_matches = [
        a for a in ArticlePage.objects.live()
        if len(a.title) >= 8 and a.title.lower() in q_lower
    ]
    if live_matches:
        live_matches.sort(key=lambda x: len(x.title), reverse=True)
        return [live_matches[0].pk]

    # 4. Fallback to search hits with scope limit (default 1 unless explicitly multi-article)
    limit = 3 if _is_multi_article_request(query) else 1
    candidate_ids = _article_ids_for_action(keyword_hits, chunk_hits, vector_hits, limit=max(limit, 3))
    if is_remove and current_list:
        list_ids = {item.article_id for item in current_list}
        filtered = [aid for aid in candidate_ids if aid in list_ids]
        if filtered:
            return filtered[:limit]
    return candidate_ids[:limit]


def _article_id_for_comment(
    article_scope,
    keyword_hits,
    chunk_hits,
    vector_hits,
) -> int | None:
    if article_scope:
        return article_scope.article_id
    ids = _article_ids_for_action(keyword_hits, chunk_hits, vector_hits, limit=1)
    return ids[0] if ids else None


def _comment_action_reply(
    query: str,
    user: User,
    *,
    article_id: int | None,
    keyword_hits,
    chunk_hits,
    vector_hits,
    tool_trace: list[dict],
    citations: list[dict],
    model: str | None,
    request=None,
) -> AgentReply | None:
    if article_id is None:
        return AgentReply(
            content=(
                'I need a target article to draft a comment. '
                'Open an article page, or ask about a specific article first.'
            ),
            citations=citations,
            tool_trace=tool_trace,
        )

    is_chinese = wants_chinese(query)
    draft = build_comment_draft(
        query,
        article_id,
        chunk_hits=chunk_hits,
        vector_hits=vector_hits,
        keyword_hits=keyword_hits,
        model=model,
    )
    if not draft:
        return AgentReply(
            content='抱歉，无法为该文章生成评论草稿。' if is_chinese else 'I could not draft a comment for that article.',
            citations=citations,
            tool_trace=tool_trace,
        )
    if is_chinese:
        draft = _ensure_simplified_chinese(draft)

    action = propose_post_comment(user, article_id, draft, request=request)
    if not action:
        return AgentReply(
            content='该文章目前无法发表评论。' if is_chinese else 'That article is unavailable for commenting.',
            citations=citations,
            tool_trace=tool_trace,
        )

    tool_trace.append({'tool': 'propose_post_comment', 'action_id': action.pk})
    payload = action.payload
    pending_action = {
        'action_id': action.pk,
        'action_type': action.action_type,
        'article_title': payload.get('article_title', ''),
        'article_url': payload.get('article_url', ''),
        'draft_content': payload.get('draft_content', ''),
    }
    if is_chinese:
        content = (
            f'我已为 **{payload.get("article_title", "这篇文章")}** 草拟了一条评论：\n\n'
            f'> {draft}\n\n'
            '您可以在下方文本框中直接修改内容，确认无误后点击 **Confirm** 发布。'
        )
    else:
        content = (
            f'I drafted a comment for **{payload.get("article_title", "this article")}**:\n\n'
            f'> {draft}\n\n'
            'Click **Confirm** below to post it. Nothing is published until you confirm.'
        )
    return AgentReply(
        content=content,
        citations=citations,
        tool_trace=tool_trace,
        pending_action=pending_action,
    )


def _clean_excerpt_text(text: str, max_len: int = 700, query: str = '') -> str:
    raw = re.sub(r'\b(?:Enter|Exit)\s+fullscreen\s+mode\b', ' ', text or '', flags=re.IGNORECASE)
    # If query mentions specific terms and chunk has numbered sections (e.g. "8. MCP: ..."), jump to the matching section
    if query:
        q_terms, _ = _extract_terms_and_phrases(query)
        for t in q_terms:
            sec_match = re.search(rf'(\b\d+\.\s+[^\n]*\b{re.escape(t)}\b[\s\S]*)', raw, flags=re.IGNORECASE)
            if sec_match and len(sec_match.group(1)) >= 80:
                raw = sec_match.group(1)
                break
    cleaned = re.sub(r'\s+', ' ', raw).strip()
    # If chunk starts mid-word or with a short overlap before a numbered section heading, trim to the numbered heading
    num_heading = re.search(r'\b(\d+\.\s+[A-Z0-9][\s\S]*)', cleaned)
    if num_heading and 0 < num_heading.start() <= 180 and len(num_heading.group(1)) >= 120:
        cleaned = num_heading.group(1).strip()
    elif cleaned and cleaned[0].islower() and not cleaned.lower().startswith(('nginx', 'curl', 'git', 'docker', 'python', 'django', 'fastapi', 'http', 'mcp', 'rag')):
        m = re.search(r'(?:[.!?]\s+|\b\d+\.\s+)([A-Z0-9][\s\S]*)', cleaned)
        if m and len(m.group(1)) >= 80:
            cleaned = m.group(1).strip()
    if len(cleaned) <= max_len:
        return cleaned
    cut = cleaned[:max_len]
    last_punct = max(cut.rfind('. '), cut.rfind('! '), cut.rfind('? '), cut.rfind('。'))
    if last_punct >= max_len // 2:
        return cut[: last_punct + 1].strip()
    last_space = cut.rfind(' ')
    return (cut[:last_space] if last_space > 0 else cut).strip() + '...'


def _fallback_answer(
    query: str,
    keyword_hits,
    chunk_hits,
    vector_hits,
    history_items,
    recommend_hits,
    reading_path,
    reading_list,
    pending_action,
    *,
    article_scope=None,
    chat_history=None,
) -> str:
    q = query.lower()
    is_zh = wants_chinese(query)

    if ('quiz' in q or '考考我' in q) and article_scope:
        from a_agent.services.learning_analysis import load_store

        rec = load_store().get('articles', {}).get(article_scope.slug or '', {})
        concepts = rec.get('article_concepts') or []
        source_hits = chunk_hits[:4] or vector_hits[:4]
        lines = [
            f'### 🎯 **{article_scope.title}** — 概念自测 Quiz' if is_zh else f'### 🎯 **{article_scope.title}** — Comprehension Quiz',
            '',
        ]
        for idx, hit in enumerate(source_hits[:3], start=1):
            snippet = _clean_excerpt_text(hit.content, max_len=180)
            concept_label = concepts[idx - 1] if idx - 1 < len(concepts) else article_scope.title
            if is_zh:
                lines.extend([
                    f'**第 {idx} 题（核心概念：{concept_label}）**：根据文中段落（*"{snippet}"*），以下哪项最准确地概括了作者的技术观点？',
                    '',
                    f'A) 遵循文中关于 **{concept_label}** 的核心机制、显式配置与状态校验边界',
                    f'B) **{concept_label}** 无需任何协议标准或配置声明即可在所有旧版组件中自动生效',
                    f'C) 在生产环境中应跳过对 **{concept_label}** 的边界验证与错误处理',
                    f'D) **{concept_label}** 仅适用于静态单机脚本，无法用于分布式或多步工作流',
                    '',
                ])
            else:
                lines.extend([
                    f'**Question {idx} ({concept_label})**: Based on the article\'s discussion (*"{snippet}"*), which statement accurately reflects how **{concept_label}** works in practice?',
                    '',
                    f'A) It follows the explicit protocol/configuration mechanics and verification boundaries described for **{concept_label}** in the article',
                    f'B) **{concept_label}** works automatically across all legacy layers without explicit route or allowlist support',
                    f'C) **{concept_label}** eliminates the need for input validation, state tracking, or error handling',
                    f'D) **{concept_label}** is restricted to offline batch scripts and cannot be used in networked services',
                    '',
                ])
        lines.append('请直接回复您的答案（例如 `1A 2A 3A`），我会为您逐题解析！' if is_zh else 'Reply with your choices (e.g., `1A, 2A, 3A`) and I will walk through the explanations!')
        return '\n'.join(lines)

    ord_idx = _extract_ordinal_index(query)
    if ord_idx is not None and chat_history:
        for msg in reversed(chat_history):
            if getattr(msg, 'role', '') == 'assistant' and getattr(msg, 'content', ''):
                items = re.findall(r'(?:^|\n)\s*(?:\d+\.|[-*])\s+([^\n]+)', msg.content)
                if ord_idx < len(items):
                    selected_item = items[ord_idx].strip()
                    prefix = (
                        f'关于您刚才提到的第 {ord_idx + 1} 点（{selected_item}）：\n\n'
                        if is_zh
                        else f'Regarding item #{ord_idx + 1} from the previous turn ({selected_item}):\n\n'
                    )
                    source_hits = chunk_hits[:2] if chunk_hits else vector_hits[:2]
                    details = '\n'.join(f'- {_clean_excerpt_text(h.content, 420)}' for h in source_hits)
                    return f'{prefix}{details}' if details else prefix.strip()
                break

    if article_scope:
        combined = chunk_hits or vector_hits or keyword_hits
        if not combined:
            if not article_scope.can_read_full and not article_scope.is_free:
                return (
                    f'**{article_scope.title}** 是付费文章，当前仅可访问预览内容。请订阅或使用积分解锁完整文章。'
                    if is_zh
                    else (
                        f'**{article_scope.title}** is a paid article and I only have preview access.\n\n'
                        'Subscribe or unlock the article to ask detailed questions about its full content.'
                    )
                )
            return (
                f'暂未找到 **{article_scope.title}** 的索引内容。'
                if is_zh
                else (
                    f'I could not find indexed content for **{article_scope.title}** yet.\n\n'
                    'Ask an admin to run `python manage.py build_article_index --embed` after publishing.'
                )
            )

        pool = list(chunk_hits) if chunk_hits else list(vector_hits)
        if len(pool) > 3 and any(k in q for k in ('summarize', 'summary', 'bullet', '总结', '總結', '重点', '重點')):
            # Pick beginning, key middle technical chunk, and concluding takeaway chunk
            mid_idx = len(pool) // 2
            for idx, h in enumerate(pool[1:-1], start=1):
                if any(kw in h.content.lower() for kw in ('limit_except', 'model context protocol', 'http_method_names', 'what to do')):
                    mid_idx = idx
                    break
            source_hits = [pool[0], pool[mid_idx], pool[-1]]
        else:
            source_hits = pool[:3]
        lead_text = _clean_excerpt_text(source_hits[0].content, 260, query=query) if source_hits else article_scope.title
        # Keep search-fallback excerpts in English. If the user asked for Chinese,
        # the caller may rewrite the whole reply; do not mix Chinese headers with
        # English lesson text here.
        lines = [
            f'🎯 **Core Takeaway**: Regarding **{article_scope.title}** — {lead_text}',
            '',
            '📌 **Key Concepts & Breakdown**:',
        ]
        for hit in source_hits:
            score_note = f' (score {hit.score})' if hasattr(hit, 'score') and hit.score and hit.score < 1.0 else ''
            lines.append(f'- {_clean_excerpt_text(hit.content, 700, query=query)}{score_note}')
        if not article_scope.can_read_full and not article_scope.is_free:
            lines.append('\nNote: full article text is paywalled — answers use preview passages only.')
        else:
            lines.append('\nThis answer is grounded in this article only.')
        return '\n'.join(lines)

    if pending_action:
        if pending_action.get('action_type') == 'post_comment':
            title = pending_action.get('article_title', 'this article')
            draft = pending_action.get('draft_content', '')
            return (
                f'I prepared a comment draft for **{title}**:\n\n'
                f'> {draft}\n\n'
                'Click **Confirm** below to post it. Nothing is published until you confirm.'
            )
        titles = ', '.join(item['title'] for item in pending_action.get('articles', []))
        if pending_action.get('action_type') == 'remove_from_reading_list':
            return (
                f'I prepared to remove these articles from your reading list: **{titles}**.\n\n'
                'Click **Confirm** below to remove them. Nothing changes until you confirm.'
            )
        return (
            f'I prepared a reading-list action for: **{titles}**.\n\n'
            'Click **Confirm** below to add them. Nothing is saved until you confirm.'
        )

    if any(h in q for h in LIST_QUERY_HINTS):
        if not reading_list:
            return 'Your reading list is empty. Ask me to add articles from search results.'
        lines = ['Your reading list:', '']
        for i, item in enumerate(reading_list, start=1):
            badge = 'Free' if item.is_free else 'Paid'
            lines.append(f'{i}. [{item.title}]({item.url}) ({badge})')
        return '\n'.join(lines)

    if reading_path:
        lines = [f'**{reading_path.title}**', '']
        for step in reading_path.steps:
            badge = 'Free' if step.is_free else 'Paid'
            note = f' — {step.note}' if step.note else ''
            lines.append(f'{step.order}. [{step.title}]({step.url}) ({badge}){note}')
        lines.append('\nFollow this order for a structured start on the topic.')
        return '\n'.join(lines)

    if any(h in q for h in CONTINUE_READING_HINTS):
        if not history_items:
            return (
                'You have no browsing history yet. Read a few articles while logged in, '
                'and I can help you continue where you left off.'
            )
        latest = history_items[0]
        return (
            f'You were recently reading **{latest.article_title}**.\n\n'
            f'[Continue reading]({latest.article_url})\n\n'
            'Ask for recommendations if you want related articles.'
        )

    if any(h in q for h in RECOMMEND_HINTS):
        if recommend_hits:
            lines = ['Based on your reading activity, you may like:', '']
            for i, hit in enumerate(recommend_hits[:3], start=1):
                badge = 'Free' if hit.is_free else 'Paid'
                lines.append(f'{i}. [{hit.title}]({hit.url}) ({badge} · {hit.reason})')
            lines.append('\nThese picks come from on-site retrieval, not model guesses.')
            return '\n'.join(lines)
        if history_items:
            return (
                f'Based on your history, try articles related to **{history_items[0].article_title}**. '
                'See the citations below for specific links.'
            )

    combined_hits = vector_hits or chunk_hits or keyword_hits
    if not combined_hits:
        return (
            '抱歉，在当前的博客文章库中找不到与此主题相关的文章。请尝试使用其他关键字搜索！'
            if is_zh
            else (
                'No matching articles found in the blog corpus. Try different keywords, '
                'or check whether the content has been published yet.'
            )
        )

    lines = ['以下是在博客文章库中检索到的相关文章：' if is_zh else 'Here is what I found in the article library:', '']
    for i, hit in enumerate(keyword_hits[:3], start=1):
        access_note = '' if hit.can_read_full else ('（付费内容 — 仅预览）' if is_zh else ' (paid — preview only)')
        lines.append(f'{i}. [{hit.title}]({hit.url}){access_note}')
        if hit.snippet:
            lines.append(f'   {hit.snippet[:180]}')
        lines.append('')

    source_hits = vector_hits[:2] if vector_hits else chunk_hits[:2]
    if source_hits:
        label = ('相关段落匹配' if is_zh else ('Vector matches' if vector_hits else 'Relevant passages'))
        lines.append(f'{label}:')
        for hit in source_hits:
            score_note = f' (score {hit.score})' if hasattr(hit, 'score') and hit.score else ''
            lines.append(f'- **{hit.article_title}**{score_note}: {hit.content[:200]}...')

    lines.append('\n以上回答基于站内检索结果，未编造任何站外链接。' if is_zh else '\nThis answer is grounded in on-site search tools, not model fabrication.')
    return '\n'.join(lines)


_S2T_PHRASE_MAP = (
    ('人工智能', '人工智慧'),
    ('代码', '程式碼'),
    ('网络', '網路'),
    ('服务器', '伺服器'),
    ('客户端', '用戶端'),
    ('数据库', '資料庫'),
    ('默认', '預設'),
    ('配置', '設定'),
    ('通过', '透過'),
    ('术语', '術語'),
    ('协议', '協定'),
    ('调用', '呼叫'),
    ('运行', '執行'),
    ('仓库', '儲存庫'),
    ('镜像', '映像檔'),
    ('异步', '非同步'),
    ('响应式', '響應式'),
    ('工作流', '工作流程'),
    ('上下文', '脈絡'),
)

_S2T_CHAR_MAP = {
    '与': '與', '专': '專', '业': '業', '东': '東', '丝': '絲', '丢': '丟', '两': '兩', '严': '嚴',
    '个': '個', '丰': '豐', '临': '臨', '为': '為', '举': '舉', '么': '麼', '义': '義', '乐': '樂',
    '习': '習', '乡': '鄉', '书': '書', '买': '買', '乱': '亂', '争': '爭', '于': '於', '亏': '虧',
    '云': '雲', '亚': '亞', '产': '產', '亲': '親', '亿': '億', '仅': '僅', '从': '從', '仓': '倉',
    '们': '們', '价': '價', '众': '眾', '优': '優', '伙': '夥', '会': '會', '伟': '偉', '传': '傳',
    '伤': '傷', '伦': '倫', '伪': '偽', '体': '體', '余': '餘', '侧': '側', '保': '保', '俭': '儉',
    '债': '債', '倾': '傾', '假': '假', '偿': '償', '储': '儲', '儿': '兒', '兑': '兌', '党': '黨',
    '兰': '蘭', '关': '關', '兴': '興', '养': '養', '内': '內', '册': '冊', '写': '寫', '军': '軍',
    '农': '農', '冲': '衝', '决': '決', '况': '況', '冻': '凍', '净': '淨', '凉': '涼', '减': '減',
    '凑': '湊', '几': '幾', '凤': '鳳', '凭': '憑', '凯': '凱', '击': '擊', '划': '劃', '刘': '劉',
    '则': '則', '刚': '剛', '创': '創', '删': '刪', '别': '別', '利': '利', '剂': '劑', '剑': '劍',
    '剧': '劇', '劝': '勸', '办': '辦', '务': '務', '动': '動', '励': '勵', '劲': '勁', '劳': '勞',
    '势': '勢', '勋': '勳', '区': '區', '医': '醫', '华': '華', '协': '協', '单': '單', '卖': '賣',
    '卫': '衛', '却': '卻', '厂': '廠', '厅': '廳', '历': '歷', '厉': '厲', '压': '壓', '厌': '厭',
    '厕': '廁', '厢': '廂', '厦': '廈', '厨': '廚', '县': '縣', '参': '參', '双': '雙', '发': '發',
    '变': '變', '叙': '敘', '叠': '疊', '叶': '葉', '号': '號', '叹': '嘆', '后': '後', '吓': '嚇',
    '吗': '嗎', '吨': '噸', '听': '聽', '启': '啟', '吴': '吳', '员': '員', '呛': '嗆', '呜': '嗚',
    '咏': '詠', '响': '響', '哑': '啞', '哗': '嘩', '哟': '唷', '唤': '喚', '啧': '嘖', '啸': '嘯',
    '喷': '噴', '嘘': '噓', '嘱': '囑', '团': '團', '园': '園', '困': '困', '围': '圍', '国': '國',
    '图': '圖', '圆': '圓', '圣': '聖', '场': '場', '坏': '壞', '块': '塊', '坚': '堅', '坛': '壇',
    '坝': '壩', '坞': '塢', '坟': '墳', '坠': '墜', '垄': '壟', '垒': '壘', '垦': '墾', '垫': '墊',
    '堕': '墮', '墙': '牆', '壮': '壯', '声': '聲', '壳': '殼', '壶': '壺', '处': '處', '备': '備',
    '复': '複', '够': '夠', '头': '頭', '夸': '誇', '夹': '夾', '夺': '奪', '奋': '奮', '奖': '獎',
    '奥': '奧', '妆': '妝', '妇': '婦', '妈': '媽', '姗': '姍', '姜': '姜', '娄': '婁', '娇': '嬌',
    '娱': '娛', '婴': '嬰', '婶': '嬸', '孙': '孫', '学': '學', '孪': '孿', '宁': '寧', '宝': '寶',
    '实': '實', '宠': '寵', '审': '審', '宪': '憲', '宫': '宮', '宽': '寬', '宾': '賓', '寝': '寢',
    '对': '對', '寻': '尋', '导': '導', '寿': '壽', '将': '將', '尔': '爾', '尘': '塵', '尧': '堯',
    '尴': '尷', '尸': '屍', '尽': '盡', '层': '層', '屉': '屜', '届': '屆', '属': '屬', '屡': '屢',
    '屿': '嶼', '岁': '歲', '岂': '豈', '岗': '崗', '岛': '島', '岩': '岩', '岭': '嶺', '岳': '岳',
    '峡': '峽', '峰': '峰', '崇': '崇', '崎': '崎', '崭': '嶄', '巅': '巔', '巩': '鞏', '币': '幣',
    '帅': '帥', '师': '師', '帐': '帳', '帘': '簾', '帜': '幟', '带': '帶', '帧': '幀', '帮': '幫',
    '幂': '冪', '干': '乾', '并': '並', '广': '廣', '庄': '莊', '庆': '慶', '庐': '廬', '库': '庫',
    '应': '應', '庙': '廟', '庞': '龐', '废': '廢', '开': '開', '异': '異', '弃': '棄', '弊': '弊',
    '弹': '彈', '弥': '彌', '弯': '彎', '弱': '弱', '强': '強', '归': '歸', '当': '當', '录': '錄',
    '彦': '彥', '彻': '徹', '径': '徑', '御': '禦', '忆': '憶', '忧': '憂', '怀': '懷', '态': '態',
    '怂': '慫', '怅': '悵', '怆': '愴', '怜': '憐', '总': '總', '恋': '戀', '恳': '懇', '恶': '惡',
    '恼': '惱', '悦': '悅', '悬': '懸', '悯': '憫', '惊': '驚', '惧': '懼', '惨': '慘', '惩': '懲',
    '惫': '憊', '惬': '愜', '惭': '慚', '惮': '憚', '惯': '慣', '惰': '惰', '想': '想', '惹': '惹',
    '愈': '愈', '愉': '愉', '意': '意', '愚': '愚', '感': '感', '愤': '憤', '慨': '慨', '愿': '願',
    '慑': '懾', '懒': '懶', '戏': '戲', '战': '戰', '户': '戶', '扎': '紮', '扑': '撲', '执': '執',
    '扩': '擴', '扫': '掃', '扬': '揚', '扭': '扭', '扮': '扮', '扯': '扯', '扰': '擾', '扶': '扶',
    '批': '批', '扼': '扼', '找': '找', '技': '技', '抄': '抄', '把': '把', '抑': '抑', '抓': '抓',
    '投': '投', '抖': '抖', '抗': '抗', '折': '折', '抚': '撫', '抛': '拋', '抠': '摳', '抡': '掄',
    '抢': '搶', '护': '護', '报': '報', '担': '擔', '拟': '擬', '拢': '攏', '拣': '揀', '拥': '擁',
    '拦': '攔', '拧': '擰', '拨': '撥', '择': '擇', '挂': '掛', '挚': '摯', '挛': '攣', '挝': '撾',
    '挞': '撻', '挟': '挾', '挠': '撓', '挡': '擋', '挣': '掙', '挤': '擠', '挥': '揮', '捞': '撈',
    '损': '損', '捡': '撿', '换': '換', '捣': '搗', '据': '據', '掳': '擄', '掷': '擲', '掸': '撣',
    '掺': '摻', '揽': '攬', '搀': '攙', '搁': '擱', '搂': '摟', '搅': '攪', '携': '攜', '摄': '攝',
    '摆': '擺', '摇': '搖', '摈': '擯', '摊': '攤', '撑': '撐', '撵': '攆', '撷': '擷', '撸': '擼',
    '攒': '攢', '敌': '敵', '敛': '斂', '数': '數', '斋': '齋', '斓': '斕', '斗': '鬥', '斩': '斬',
    '断': '斷', '无': '無', '旧': '舊', '时': '時', '旷': '曠', '昙': '曇', '昼': '晝', '显': '顯',
    '晋': '晉', '晒': '曬', '晓': '曉', '晔': '曄', '晕': '暈', '晖': '暉', '暂': '暫', '暧': '曖',
    '术': '術', '机': '機', '杀': '殺', '杂': '雜', '权': '權', '条': '條', '来': '來', '杨': '楊',
    '杰': '傑', '极': '極', '构': '構', '枢': '樞', '枣': '棗', '枪': '槍', '枫': '楓', '柜': '櫃',
    '柠': '檸', '栅': '柵', '标': '標', '栈': '棧', '栋': '棟', '栏': '欄', '树': '樹', '栖': '棲',
    '样': '樣', '核': '核', '根': '根', '格': '格', '档': '檔', '桥': '橋', '桦': '樺', '桨': '槳',
    '桩': '樁', '梦': '夢', '检': '檢', '椭': '橢', '楼': '樓', '榄': '欖', '': '櫧', '槛': '檻',
    '槟': '檳', '樱': '櫻', '橱': '櫥', '欢': '歡', '欧': '歐', '歼': '殲', '殁': '歿', '殇': '殤',
    '残': '殘', '殒': '殞', '殓': '殮', '殡': '殯', '殴': '毆', '毁': '毀', '毕': '畢', '毙': '斃',
    '毡': '氈', '气': '氣', '氢': '氫', '氩': '氬', '汇': '匯', '汉': '漢', '污': '汙', '汤': '湯',
    '汹': '洶', '沟': '溝', '没': '沒', '沥': '瀝', '沦': '淪', '沧': '滄', '沪': '滬', '泞': '濘',
    '泪': '淚', '泻': '瀉', '泼': '潑', '泽': '澤', '洁': '潔', '洒': '灑', '洼': '窪', '浃': '浹',
    '浅': '淺', '浆': '漿', '浇': '澆', '浊': '濁', '测': '測', '济': '濟', '浏': '瀏覽'[0], '浑': '渾',
    '浓': '濃', '涂': '塗', '涌': '湧', '涛': '濤', '涝': '澇', '涟': '漣', '涡': '渦', '涣': '渙',
    '涤': '滌', '润': '潤', '涧': '澗', '涨': '漲', '涩': '澀', '渊': '淵', '渍': '漬', '渐': '漸',
    '渔': '漁', '渗': '滲', '温': '溫', '港': '港', '渴': '渴', '游': '遊', '湾': '灣', '湿': '濕',
    '溃': '潰', '溅': '濺', '滚': '滾', '滞': '滯', '满': '滿', '滤': '濾', '滥': '濫', '滨': '濱',
    '滩': '灘', '漓': '漓', '漠': '漠', '漫': '漫', '漱': '漱', '漾': '漾', '潇': '瀟', '潜': '潛',
    '潮': '潮', '澄': '澄', '澈': '澈', '澎': '澎', '澜': '瀾', '澳': '澳', '激': '激', '濒': '瀕',
    '灭': '滅', '灯': '燈', '灵': '靈', '灾': '災', '灿': '燦', '炉': '爐', '炖': '燉', '点': '點',
    '炼': '煉', '炽': '熾', '烁': '爍', '烂': '爛', '烃': '烴', '烛': '燭', '烟': '煙', '烦': '煩',
    '烧': '燒', '烫': '燙', '烬': '燼', '热': '熱', '焕': '煥', '爱': '愛', '爷': '爺', '牵': '牽',
    '牺': '犧', '犊': '犢', '状': '狀', '犹': '猶', '狂': '狂', '独': '獨', '狭': '狹', '狮': '獅',
    '狰': '猙', '狱': '獄', '猎': '獵', '猪': '豬', '猫': '貓', '献': '獻', '獭': '獺', '玛': '瑪',
    '环': '環', '现': '現', '玺': '璽', '珍': '珍', '珐': '琺', '珑': '瓏', '琐': '瑣', '琼': '瓊',
    '瑶': '瑤', '瑷': '璦', '璎': '瓔', '瓒': '瓚', '电': '電', '画': '畫', '畅': '暢', '畴': '疇',
    '疗': '療', '疟': '瘧', '疡': '瘍', '疮': '瘡', '疯': '瘋', '痈': '癰', '痉': '痙', '痒': '癢',
    '痨': '癆', '痪': '瘓', '痴': '癡', '瘪': '癟', '瘫': '癱', '瘾': '癮', '癞': '癩', '癣': '癬',
    '癫': '癲', '皑': '皚', '皱': '皺', '盏': '盞', '盐': '鹽', '监': '監', '盖': '蓋', '盗': '盜',
    '盘': '盤', '着': '著', '睁': '睜', '睐': '睞', '睑': '瞼', '瞒': '瞞', '瞩': '矚', '矫': '矯',
    '矾': '礬', '矿': '礦', '码': '碼', '砖': '磚', '砚': '硯', '砜': '碸', '砺': '礪', '砾': '礫',
    '础': '礎', '硅': '矽', '硕': '碩', '确': '確', '硷': '鹼', '碍': '礙', '碱': '鹼', '礼': '禮',
    '祯': '禎', '祷': '禱', '祸': '禍', '禀': '稟', '禄': '祿', '禅': '禪', '离': '離', '秃': '禿',
    '秆': '稈', '种': '種', '积': '積', '称': '稱', '秽': '穢', '税': '稅', '稣': '穌', '稳': '穩',
    '穷': '窮', '窃': '竊', '窍': '竅', '窑': '窯', '窜': '竄', '窝': '窩', '窥': '窺', '窦': '竇',
    '竖': '豎', '竞': '競', '笃': '篤', '笋': '筍', '笔': '筆', '笺': '箋', '笼': '籠', '筑': '築',
    '筛': '篩', '筝': '箏', '筹': '籌', '签': '簽', '简': '簡', '箓': '籙', '箩': '籮', '箫': '簫',
    '篓': '簍', '篮': '籃', '篱': '籬', '籁': '籟', '类': '類', '粤': '粵', '粪': '糞', '粮': '糧',
    '紧': '緊', '纠': '糾', '纡': '紆', '红': '紅', '纣': '紂', '纤': '纖', '约': '約', '级': '級',
    '纪': '紀', '纫': '紉', '纬': '緯', '纭': '紜', '纯': '純', '纰': '紕', '纱': '紗', '纲': '綱',
    '纳': '納', '纵': '縱', '纶': '綸', '纷': '紛', '纸': '紙', '纹': '紋', '纺': '紡', '纽': '紐',
    '纾': '紓', '线': '線', '绀': '紺', '练': '練', '组': '組', '绅': '紳', '细': '細', '织': '織',
    '终': '終', '绉': '縐', '绊': '絆', '绌': '絀', '绍': '紹', '绎': '繹', '经': '經', '绑': '綁',
    '绒': '絨', '结': '結', '绕': '繞', '绘': '繪', '给': '給', '绚': '絢', '绛': '絳', '络': '絡',
    '绝': '絕', '绞': '絞', '统': '統', '绢': '絹', '绣': '繡', '绥': '綏', '绦': '絛', '继': '繼',
    '绩': '績', '绪': '緒', '绫': '綾', '续': '續', '绮': '綺', '绯': '緋', '绰': '綽', '绳': '繩',
    '维': '維', '绵': '綿', '绶': '綬', '绷': '繃', '绸': '綢', '绺': '綹', '绻': '綣', '综': '綜',
    '绽': '綻', '绾': '綰', '绿': '綠', '缀': '綴', '缁': '緇', '缂': '緙', '缃': '緗', '缄': '緘',
    '缅': '緬', '缆': '纜', '缇': '緹', '缈': '緲', '缉': '緝', '缎': '緞', '缓': '緩', '缔': '締',
    '缕': '縷', '编': '編', '缘': '緣', '缚': '縛', '缛': '縟', '缜': '縝', '缝': '縫', '缟': '縞',
    '缠': '纏', '缡': '縭', '缢': '縊', '缣': '縑', '缤': '繽', '缥': '縹', '缦': '縵', '': '縲',
    '缨': '纓', '缩': '縮', '缪': '繆', '缫': '繅', '缬': '纈', '缭': '繚', '缮': '繕', '缯': '繒',
    '缰': '韁', '缱': '繾', '缴': '繳', '网': '網', '罗': '羅', '罚': '罰', '罢': '罷', '羁': '羈',
    '羡': '羨', '翘': '翹', '耸': '聳', '耻': '恥', '聂': '聶', '聋': '聾', '职': '職', '联': '聯',
    '聘': '聘', '聚': '聚', '聪': '聰', '肃': '肅', '肠': '腸', '肤': '膚', '肮': '骯', '育': '育',
    '肴': '肴', '胀': '脹', '胁': '脅', '胆': '膽', '胜': '勝', '胧': '朧', '胫': '脛', '胶': '膠',
    '脉': '脈', '脍': '膾', '脏': '臟', '脐': '臍', '脑': '腦', '脓': '膿', '脚': '腳', '脱': '脫',
    '脸': '臉', '腊': '臘', '腌': '醃', '腻': '膩', '腼': '靦', '腾': '騰', '舆': '輿', '舰': '艦',
    '舱': '艙', '艰': '艱', '艳': '豔', '艺': '藝', '节': '節', '芜': '蕪', '芦': '蘆', '苇': '葦',
    '苋': '莧', '苌': '萇', '苍': '蒼', '苎': '苧', '苏': '蘇', '苹': '蘋', '茎': '莖', '茏': '蘢',
    '茑': '蔦', '茧': '繭', '荆': '荊', '荐': '薦', '荚': '莢', '荞': '蕎', '荟': '薈', '荠': '薺',
    '荡': '蕩', '荣': '榮', '荤': '葷', '荧': '熒', '荨': '蕁', '荪': '蓀', '荫': '蔭', '药': '藥',
    '莅': '蒞', '莱': '萊', '莲': '蓮', '莳': '蒔', '莴': '萵', '获': '獲', '莹': '瑩', '莺': '鶯',
    '萝': '蘿', '萤': '螢', '营': '營', '萦': '縈', '萧': '蕭', '萨': '薩', '葱': '蔥', '蒋': '蔣',
    '蓝': '藍', '蓟': '薊', '蓦': '驀', '蔷': '薔', '蔺': '藺', '蔼': '藹', '蕴': '蘊', '薮': '藪',
    '藏': '藏', '藐': '藐', '藓': '蘚', '藕': '藕', '藜': '藜', '藤': '藤', '藩': '藩', '藻': '藻',
    '虏': '虜', '虑': '慮', '虫': '蟲', '虽': '雖', '虾': '蝦', '蚀': '蝕', '蚁': '蟻', '蚂': '螞',
    '蚕': '蠶', '蛊': '蠱', '蛎': '蠣', '蛏': '蟶', '蛮': '蠻', '蛰': '蟄', '蜕': '蛻', '蜗': '蝸',
    '蜡': '蠟', '蝇': '蠅', '蝉': '蟬', '蝎': '蠍', '蝶': '蝶', '衔': '銜', '补': '補', '衬': '襯',
    '袄': '襖', '袜': '襪', '袭': '襲', '装': '裝', '裆': '襠', '裤': '褲', '褛': '褸', '褴': '襤',
    '见': '見', '观': '觀', '规': '規', '觅': '覓', '视': '視', '览': '覽', '觉': '覺', '觊': '覬',
    '觐': '覲', '觑': '覷', '觞': '觴', '触': '觸', '誉': '譽', '誊': '謄', '计': '計', '订': '訂',
    '讣': '訃', '认': '認', '讥': '譏', '讨': '討', '让': '讓', '讪': '訕', '讫': '訖', '训': '訓',
    '议': '議', '讯': '訊', '记': '記', '讲': '講', '讳': '諱', '讴': '謳', '讶': '訝', '讷': '訥',
    '许': '許', '讹': '訛', '论': '論', '讼': '訟', '讽': '諷', '设': '設', '访': '訪', '诀': '訣',
    '证': '證', '评': '評', '诅': '詛', '识': '識', '诈': '詐', '诉': '訴', '诊': '診', '诋': '詆',
    '诌': '謅', '词': '詞', '诏': '詔', '译': '譯', '诓': '誆', '试': '試', '诗': '詩', '诘': '詰',
    '诙': '詼', '诚': '誠', '诛': '誅', '话': '話', '诞': '誕', '诟': '詬', '诠': '詮', '诡': '詭',
    '询': '詢', '诣': '詣', '诤': '諍', '该': '該', '详': '詳', '诧': '詫', '诨': '諢', '诫': '誡',
    '诬': '誣', '语': '語', '诮': '誚', '误': '誤', '诰': '誥', '诱': '誘', '诲': '誨', '诳': '誑',
    '说': '說', '诵': '誦', '请': '請', '诸': '諸', '诹': '諏', '诺': '諾', '读': '讀', '诽': '誹',
    '课': '課', '诿': '諉', '谀': '諛', '谁': '誰', '谂': '諗', '调': '調', '谄': '諂', '谅': '諒',
    '谆': '諄', '谈': '談', '谊': '誼', '谋': '謀', '谌': '諶', '谍': '諜', '谎': '謊', '谏': '諫',
    '谐': '諧', '谑': '謔', '谒': '謁', '谓': '謂', '谔': '諤', '谕': '諭', '谗': '讒', '谘': '諮',
    '谙': '諳', '谚': '諺', '谛': '諦', '谜': '謎', '谟': '謨', '谢': '謝', '谣': '謠', '谤': '謗',
    '谥': '諡', '谦': '謙', '谧': '謐', '谨': '謹', '谩': '謾', '谪': '謫', '谬': '謬', '谭': '譚',
    '谯': '譙', '谰': '讕', '谱': '譜', '谲': '譎', '谴': '譴', '谶': '讖', '贝': '貝', '贞': '貞',
    '负': '負', '贡': '貢', '财': '財', '责': '責', '贤': '賢', '败': '敗', '账': '賬', '货': '貨',
    '质': '質', '贩': '販', '贪': '貪', '贫': '貧', '贬': '貶', '购': '購', '贮': '貯', '贯': '貫',
    '贰': '貳', '贱': '賤', '贲': '賁', '贴': '貼', '贵': '貴', '贷': '貸', '贸': '貿', '费': '費',
    '贺': '賀', '贻': '貽', '贼': '賊', '贽': '贄', '贾': '賈', '贿': '賄', '赁': '賃', '赂': '賂',
    '赃': '贓', '资': '資', '赅': '賅', '赈': '賑', '赊': '賒', '赋': '賦', '赌': '賭', '赎': '贖',
    '赏': '賞', '赐': '賜', '赔': '賠', '赖': '賴', '赘': '贅', '赚': '賺', '赛': '賽', '赝': '贗',
    '赞': '贊', '赠': '贈', '赡': '贍', '赢': '贏', '赣': '贛', '赵': '趙', '赶': '趕', '趋': '趨',
    '跃': '躍', '践': '踐', '跷': '蹺', '': '蹕', '跻': '躋', '踊': '踴', '踌': '躊', '踪': '蹤',
    '蹑': '躡', '蹒': '蹣', '蹰': '躕', '蹿': '躥', '躏': '躪', '躯': '軀', '车': '車', '轧': '軋',
    '轨': '軌', '轩': '軒', '转': '轉', '轭': '軛', '轮': '輪', '软': '軟', '轰': '轟', '轴': '軸',
    '轶': '軼', '轸': '軫', '轻': '輕', '轼': '軾', '载': '載', '轿': '轎', '较': '較', '辄': '輒',
    '辅': '輔', '辆': '輛', '辇': '輦', '辈': '輩', '辉': '輝', '辊': '輥', '辍': '輟', '辎': '輜',
    '辏': '輳', '辐': '輻', '辑': '輯', '输': '輸', '辔': '轡', '辕': '轅', '辖': '轄', '辗': '輾',
    '辘': '轆', '辙': '轍', '辞': '辭', '辩': '辯', '辫': '辮', '边': '邊', '辽': '遼', '达': '達',
    '迁': '遷', '过': '過', '迈': '邁', '运': '運', '还': '還', '这': '這', '进': '進', '远': '遠',
    '违': '違', '连': '連', '迟': '遲', '迹': '跡', '适': '適', '选': '選', '逊': '遜', '递': '遞',
    '逻': '邏', '遗': '遺', '遥': '遙', '邓': '鄧', '邮': '郵', '邹': '鄒', '邺': '鄴', '邻': '鄰',
    '郁': '鬱', '郑': '鄭', '酝': '醞', '酱': '醬', '酿': '釀', '释': '釋', '里': '裡', '鉴': '鑑',
    '针': '針', '钉': '釘', '钓': '釣', '钙': '鈣', '钛': '鈦', '钝': '鈍', '钞': '鈔', '钟': '鐘',
    '钠': '鈉', '钡': '鋇', '钢': '鋼', '钤': '鈐', '钥': '鑰', '钦': '欽', '钧': '鈞', '钨': '鎢',
    '钩': '鉤', '钮': '鈕', '钱': '錢', '钳': '鉗', '钴': '鈷', '钵': '缽', '钺': '鉞', '钻': '鑽',
    '钼': '鉬', '钾': '鉀', '铀': '鈾', '铁': '鐵', '铂': '鉑', '铃': '鈴', '铅': '鉛', '铆': '鉚',
    '铜': '銅', '铝': '鋁', '铠': '鎧', '铡': '鍘', '铣': '銑', '铭': '銘', '铮': '錚', '铰': '鉸',
    '铲': '鏟', '铳': '銃', '银': '銀', '铸': '鑄', '铺': '鋪', '链': '鏈', '铿': '鏗', '销': '銷',
    '锁': '鎖', '锂': '鋰', '锄': '鋤', '锅': '鍋', '锈': '鏽', '锉': '銼', '锋': '鋒', '锌': '鋅',
    '锐': '銳', '锑': '銻', '错': '錯', '锚': '錨', '锡': '錫', '锢': '錮', '锣': '鑼', '锤': '錘',
    '锥': '錐', '锦': '錦', '锭': '錠', '键': '鍵', '锯': '鋸', '锰': '錳', '锲': '鍥', '锵': '鏘',
    '锷': '鍔', '锹': '鍬', '锻': '鍛', '镀': '鍍', '镁': '鎂', '镂': '鏤', '镇': '鎮', '镉': '鎘',
    '镊': '鑷', '镌': '鐫', '镍': '鎳', '镐': '鎬', '镑': '鎊', '镕': '鎔', '镖': '鏢', '镜': '鏡',
    '镝': '鏑', '镞': '鏃', '镣': '鐐', '镭': '鐳', '镯': '鐲', '镰': '鐮', '镶': '鑲', '长': '長',
    '门': '門', '闩': '閂', '闪': '閃', '闭': '閉', '问': '問', '闯': '闖', '闰': '閏', '闱': '闈',
    '闲': '閒', '闳': '閎', '间': '間', '闵': '閔', '闷': '悶', '闸': '閘', '闹': '鬧', '闺': '閨',
    '闻': '聞', '闽': '閩', '阀': '閥', '阁': '閣', '阂': '閡', '阅': '閱', '阉': '閹', '阎': '閻',
    '阐': '闡', '阑': '闌', '阔': '闊', '队': '隊', '阳': '陽', '阴': '陰', '阵': '陣', '阶': '階',
    '际': '際', '陆': '陸', '陇': '隴', '陈': '陳', '陕': '陝', '陨': '隕', '险': '險', '随': '隨',
    '隐': '隱', '隶': '隸', '难': '難', '雏': '雛', '雳': '靂', '雾': '霧', '霁': '霽', '霉': '黴',
    '霭': '靄', '靓': '靚', '静': '靜', '鞘': '鞘', '鞠': '鞠', '飙': '飆', '飞': '飛', '食': '食',
    '饥': '飢', '饭': '飯', '饮': '飲', '饯': '餞', '饰': '飾', '饱': '飽', '饲': '飼', '饴': '飴',
    '饵': '餌', '饶': '饒', '饷': '餉', '饺': '餃', '饼': '餅', '饿': '餓', '馁': '餒', '馄': '餛',
    '馅': '餡', '馆': '館', '馈': '饋', '馊': '餿', '馋': '饞', '馍': '饃', '馏': '餾', '馐': '饈',
    '馒': '饅', '馔': '饌', '马': '馬', '驭': '馭', '驮': '馱', '驯': '馴', '驰': '馳', '驱': '驅',
    '驳': '駁', '驴': '驢', '驶': '駛', '驷': '駟', '驸': '駙', '驹': '駒', '驻': '駐', '驼': '駝',
    '驽': '駑', '驾': '駕', '驿': '驛', '骁': '驍', '骂': '罵', '骄': '驕', '骅': '驊', '骆': '駱',
    '骇': '駭', '骈': '駢', '骊': '驪', '骋': '騁', '验': '驗', '骏': '駿', '骐': '騏', '骑': '騎',
    '骗': '騙', '骚': '騷', '骛': '騖', '骜': '驁', '骞': '騫', '骠': '驃', '骡': '騾', '骤': '驟',
    '骥': '驥', '骧': '驤', '鱼': '魚', '鱿': '魷', '鲁': '魯', '鲍': '鮑', '鲜': '鮮', '鲟': '鱘',
    '鲤': '鯉', '鲨': '鯊', '鲫': '鯽', '鲸': '鯨', '鳃': '鰓', '鳄': '鱷', '鳍': '鰭', '鳖': '鱉',
    '鳗': '鰻', '鳞': '鱗', '鸟': '鳥', '鸠': '鳩', '鸡': '雞', '鸢': '鳶', '鸣': '鳴', '鸥': '鷗',
    '鸦': '鴉', '鸭': '鴨', '鸯': '鴦', '鸳': '鴛', '鸵': '鴕', '鸽': '鴿', '鸾': '鸞', '鸿': '鴻',
    '鹃': '鵑', '鹄': '鵠', '鹅': '鵝', '鹈': '鵜', '鹉': '鵡', '鹊': '鵲', '鹌': '鵪', '鹏': '鵬',
    '鹑': '鶉', '鹗': '鶚', '鹘': '鶻', '鹜': '鶩', '鹞': '鷂', '鹤': '鶴', '鹦': '鸚', '鹧': '鷓',
    '鹫': '鷲', '鹬': '鷸', '鹭': '鷺', '鹰': '鷹', '鹳': '鸛', '卤': '鹵', '咸': '鹹', '麦': '麥',
    '麸': '麩', '黄': '黃', '默': '默', '齐': '齊', '齿': '齒', '龄': '齡', '龅': '齙', '龈': '齦',
    '龋': '齲', '龌': '齷', '龙': '龍', '龚': '龔', '龛': '龕', '龟': '龜',
}
_S2T_CHAR_TABLE = str.maketrans({k: v for k, v in _S2T_CHAR_MAP.items() if len(k) == 1})


_T2S_PHRASE_MAP = tuple((trad, simp) for simp, trad in _S2T_PHRASE_MAP)
_T2S_CHAR_TABLE = str.maketrans(
    {trad: simp for simp, trad in _S2T_CHAR_MAP.items() if len(simp) == 1 and len(trad) == 1}
)


def _mostly_english(text: str) -> bool:
    latin = len(re.findall(r'[A-Za-z]', text or ''))
    chinese = len(re.findall(r'[\u4e00-\u9fff]', text or ''))
    return latin >= 40 and latin > chinese * 2


def _rewrite_reply_in_chinese(content: str, *, model: str | None = None) -> str | None:
    """Turn an English search fallback into a Simplified Chinese reply when the model is available."""
    text = (content or '').strip()
    if not text or not llm_configured(model) or not _mostly_english(text):
        return None
    try:
        rewritten = generate_answer(
            (
                'Rewrite the assistant reply into 100% Simplified Chinese (简体中文). '
                'Keep the same Markdown structure, headings, bullet points, and links. '
                'Translate English lesson excerpts into Simplified Chinese. '
                'Do not add new facts. Output only the rewritten reply.'
            ),
            text,
            model=model,
        )
    except Exception:
        return None
    rewritten = (rewritten or '').strip()
    if not rewritten or _mostly_english(rewritten):
        return None
    return rewritten


def _chinese_unavailable_notice(article_title: str = '') -> str:
    title = (article_title or '').strip()
    about = f'关于 **{title}** 的' if title else ''
    return (
        f'当前 AI 暂时无法生成中文回答，所以我没有直接粘贴英文原文。\n\n'
        f'请稍后再试{about}中文总结；如果只需要英文摘录，请用英文提问。'
    )


def _ensure_simplified_chinese(text: str) -> str:
    """Convert Traditional Chinese terms and characters to Simplified Chinese outside code blocks."""
    parts = re.split(r'(```[\s\S]*?```|`[^`\n]+`)', text)
    out = []
    for idx, part in enumerate(parts):
        if idx % 2 == 1:
            out.append(part)
            continue
        converted = part
        for trad, simp in _T2S_PHRASE_MAP:
            converted = converted.replace(trad, simp)
        converted = converted.translate(_T2S_CHAR_TABLE)
        out.append(converted)
    return ''.join(out)


def _ensure_traditional_chinese(text: str) -> str:
    """Convert Simplified Chinese terms and characters to Traditional Chinese outside code blocks."""
    parts = re.split(r'(```[\s\S]*?```|`[^`\n]+`)', text)
    out = []
    for idx, part in enumerate(parts):
        if idx % 2 == 1:
            out.append(part)
            continue
        converted = part
        for simp, trad in _S2T_PHRASE_MAP:
            converted = converted.replace(simp, trad)
        converted = converted.translate(_S2T_CHAR_TABLE)
        out.append(converted)
    return ''.join(out)


def _sanitize_markdown_output(text: str) -> str:
    """Clean up invented #anchor links, truncated trailing Markdown links, and unclosed code fences."""
    if not text:
        return ''
    cleaned = text.strip()
    # Replace invented #anchor links like [Read More](#section) with **Read More**
    cleaned = re.sub(r'\[([^\]]+)\]\(#[^)]*\)', r'**\1**', cleaned)
    # Fix truncated markdown links at the end of output: [Title](https://...
    cleaned = re.sub(r'\[([^\]]+)\]\([^)\s]*$', r'**\1**', cleaned)
    # Fix truncated opening bracket at the very end: [Title...
    cleaned = re.sub(r'\[([^\][\n]{1,80})$', r'**\1**', cleaned)
    # Close unclosed fenced code block
    if cleaned.count('```') % 2 == 1:
        cleaned = cleaned.rstrip() + '\n```'
    return cleaned


def _format_chat_history(chat_history) -> list[dict]:
    if not chat_history:
        return []
    formatted = []
    for msg in chat_history[-6:]:
        role = getattr(msg, 'role', 'user')
        content = (getattr(msg, 'content', '') or '')[:500]
        cites = [
            {'article_id': c.get('article_id'), 'title': c.get('title'), 'url': c.get('url')}
            for c in (getattr(msg, 'citations', None) or [])[:5]
        ]
        entry = {'role': role, 'content': content}
        if cites:
            entry['citations'] = cites
        formatted.append(entry)
    return formatted


_OTHER_ARTICLE_RE = re.compile(
    r'\b(?:article|lesson|post)\s+(?:about|titled|called)\b',
    re.I,
)
_BLOG_WIDE_MARKERS = (
    'on this blog',
    'on this site',
    'in the blog corpus',
    'blog corpus',
    '在这个博客',
    '在本站',
    '这篇博客',
)


def _question_leaves_this_article(query: str, article_scope) -> str:
    """A blog-wide question asked inside one article's panel."""
    if not article_scope:
        return ''
    text = query or ''
    lower = text.lower()
    if not any(marker in lower for marker in _BLOG_WIDE_MARKERS) and not _OTHER_ARTICLE_RE.search(text):
        return ''
    topic = topic_from_query(text)
    if not topic:
        return ''
    title = (article_scope.title or '').lower()
    words = [
        word for word in re.findall(r'[a-z0-9]{4,}', topic.lower())
        if word not in {'this', 'that', 'blog', 'article', 'about', 'with', 'from'}
    ]
    if words and any(word in title for word in words):
        return ''
    return topic


def _detect_cross_article_in_scope(query: str, article_scope, request=None) -> dict | None:
    """Detect when a user inside Article A's scoped panel explicitly asks about another article B."""
    if not article_scope:
        return None
    q_lower = query.lower()
    scoped_title_lower = article_scope.title.lower()
    if scoped_title_lower in q_lower:
        return None

    quoted_spans = [
        m.strip().lower()
        for m in re.findall(r'["“「『\']([^"”」』\']{6,})["”」』\']', query)
        if m.strip().lower() not in scoped_title_lower
    ]

    for other in ArticlePage.objects.live().exclude(pk=article_scope.article_id):
        full_title = other.title.lower().strip()
        base_title = re.sub(r'\s*[\(\[（【].*?[\)\]）】]', '', full_title).strip()
        short_title = re.split(r'[:：—\-–\?？]', base_title)[0].strip()

        matched = (
            (len(full_title) >= 8 and full_title in q_lower)
            or (len(base_title) >= 8 and base_title in q_lower)
            or (len(short_title) >= 12 and short_title in q_lower)
            or any(q_span in full_title for q_span in quoted_spans)
        )
        if matched:
            url = other.get_url(request) if request else (other.url or '')
            return {
                'article_id': other.pk,
                'title': other.title,
                'url': url,
            }
    return None


def _is_no_match_response(text: str) -> bool:
    lower = text.lower()
    no_match_phrases = (
        'cannot find any article',
        'no matching articles found',
        'not found in the blog corpus',
        'no articles found',
        'do not have any articles about',
        '找不到相关文章',
        '没有找到相关文章',
        '找不到关于',
        '没有关于',
        '语料库中没有',
        '找不到與此主題相關的文章',
        '找不到与此主题相关的文章',
        '找不到相關文章',
        '沒有找到相關文章',
        '找不到關於',
        '沒有關於',
        '語料庫中沒有',
    )
    return any(p in lower for p in no_match_phrases)


def _outside_note_lines(notes: list[dict]) -> str:
    lines = []
    for index, note in enumerate(notes, start=1):
        title = note.get('title') or 'Outside note'
        excerpt = (note.get('excerpt') or '').strip()
        lines.append(f'[{index}] **{title}** — {excerpt}')
    return '\n'.join(lines)


def _hits_for_path(hits: list, reading_path) -> list:
    """Lessons on the chosen path, plus other lessons about that same subject.

    A path question should not also be answered from an unrelated subject
    that only matched words such as "learning path".
    """
    if not reading_path or not hits:
        return hits
    allowed = {step.article_id for step in reading_path.steps}
    tokens = [
        token for token in (reading_path.topic or '').lower().split()
        if len(token) >= 3
    ]
    kept = []
    for hit in hits:
        if getattr(hit, 'article_id', None) in allowed:
            kept.append(hit)
            continue
        title = f"{getattr(hit, 'title', '')} {getattr(hit, 'article_title', '')}".lower()
        if tokens and any(token in title for token in tokens):
            kept.append(hit)
    return kept


def _lesson_title_text(hits: list) -> str:
    return ' '.join(
        f"{getattr(hit, 'title', '')} {getattr(hit, 'article_title', '')}"
        for hit in hits
    ).lower()


_SITE_ONLY_INTENTS = {
    'path', 'recommend', 'history', 'reading_list',
    'action_add', 'action_remove', 'action_comment',
}


def _stay_on_site(intents: set[str]) -> bool:
    """A path, a recommendation, or an action is about lessons on this site."""
    return bool(intents & _SITE_ONLY_INTENTS)


def _refers_to_opened_article(query: str) -> bool:
    """True when the user is asking about the article they are already reading."""
    q = (query or '').lower()
    return any(
        mark in q
        for mark in (
            'this article',
            'the article',
            '这篇文章',
            '這篇文章',
            '本文',
            'summarize this article',
            'summarize the article',
            '总结这篇文章',
            '總結這篇文章',
            '总结一下这篇文章',
            '總結一下這篇文章',
        )
    )


def _is_direct_answer_query(query: str, intents: set[str] | None = None) -> bool:
    """A definition, summary, or explain-with-example question — not a reading list or action."""
    active_intents = intents if intents is not None else _classify_intents(query or '')
    if _stay_on_site(active_intents):
        return False
    q = _strip_quoted_titles(query).lower()
    return any(
        mark in q
        for mark in (
            'what is',
            "what's",
            'what are',
            'summarize',
            'summary',
            'explain',
            '什么是',
            '什麼是',
            '总结',
            '總結',
            '解释',
            '解釋',
            '举例',
            '舉例',
            '例子',
            'example',
        )
    )


def _uncovered_outside_topic(query: str, hits: list, intents: set[str] | None = None) -> str:
    """A subject in the question that no on-site lesson title covers.

    A separate clause such as "and what is Helm?" is looked up outside.
    So is a real subject in one sentence, such as "What does Helm do?",
    when the lesson titles do not mention it. Words about the reader or
    the request, such as "joined a team" or "plan a path", are not a subject.
    A request to summarize the opened article stays on site.
    """
    if not hits:
        return ''
    if _refers_to_opened_article(query):
        return ''
    active_intents = intents if intents is not None else _classify_intents(query or '')
    if active_intents & {'action_add', 'action_remove', 'action_comment', 'reading_list', 'history'}:
        return ''
    titles = _lesson_title_text(hits)
    if not titles.strip():
        return ''

    unquoted_query = _strip_quoted_titles(query)

    def uncovered_terms(text: str) -> list[str]:
        return [term for term in content_terms(text) if not _word_match(term, titles)]

    parts = [
        part.strip(' ,，。?？')
        for part in re.split(r'\s+\band\b\s+|以及|顺便|还有|另外', unquoted_query or '', flags=re.I)
        if part.strip(' ,，。?？')
    ]
    if len(parts) >= 2:
        outside_parts = []
        saw_lesson = False
        for part in parts:
            terms, _ = _extract_terms_and_phrases(part)
            if terms and any(_word_match(term, titles) for term in terms):
                saw_lesson = True
                continue
            if uncovered_terms(part):
                outside_parts.append(part)
        if saw_lesson and outside_parts:
            return ' '.join(outside_parts)[:120]
    missed = uncovered_terms(unquoted_query)
    if not missed:
        return ''
    return ' '.join(missed)[:120]


def _cite_token(number: int, note: dict) -> str:
    url = (note.get('url') or '').strip()
    title = re.sub(r'\s+', ' ', (note.get('title') or '')).strip()[:160]
    site = re.sub(r'\s+', ' ', (note.get('source_name') or '')).strip()[:80]
    excerpt = re.sub(r'\s+', ' ', (note.get('excerpt') or '')).strip()[:180]
    return '{{cite:%d:%s|%s|%s|%s}}' % (
        number,
        url,
        quote(title, safe=''),
        quote(site, safe=''),
        quote(excerpt, safe=''),
    )


def _attach_source_marks(body: str, notes: list[dict], *, several: bool = True) -> str:
    """Turn [1] at a sentence end into a clickable source mark."""
    usable = [
        note for note in notes
        if (note.get('url') or '').strip().startswith(('http://', 'https://'))
    ]
    if not usable or not body:
        return body

    def repl(match):
        number = int(match.group(1))
        if 1 <= number <= len(usable):
            return _cite_token(number, usable[number - 1])
        return match.group(0)

    if re.search(r'\[(\d+)\]', body):
        if not several:
            body = re.sub(r'(\[\d+\])(?:\[\d+\])+', r'\1', body)
        return re.sub(r'\[(\d+)\]', repl, body)
    chosen = usable if several else usable[:1]
    suffix = ''.join(_cite_token(index, note) for index, note in enumerate(chosen, start=1))
    return body.rstrip() + suffix


def _opened_lesson_note(content: str, history_items: list, hits: list, is_chinese: bool) -> str:
    """Name opened lessons that this answer is actually using."""
    if not history_items or not hits:
        return ''
    hit_ids = set()
    hit_titles = set()
    for hit in hits:
        article_id = getattr(hit, 'article_id', None)
        if article_id:
            hit_ids.add(article_id)
        for attr in ('title', 'article_title'):
            title = (getattr(hit, attr, None) or '').strip()
            if title:
                hit_titles.add(title.casefold())
    opened = []
    body = content or ''
    body_lower = body.lower()
    for item in history_items:
        title = (getattr(item, 'article_title', None) or '').strip()
        if not title or title in opened:
            continue
        article_id = getattr(item, 'article_id', None)
        if article_id not in hit_ids and title.casefold() not in hit_titles:
            continue
        if title.lower() in body_lower and any(
            mark in body_lower for mark in ('already opened', 'already read', '打开过', '读过', '看过')
        ):
            continue
        opened.append(title)
        if len(opened) == 3:
            break
    if not opened:
        return ''
    names = '、'.join(f'**{title}**' for title in opened) if is_chinese else ', '.join(f'**{title}**' for title in opened)
    if is_chinese:
        return f'你已经打开过{names}。'
    if len(opened) == 1:
        return f'You already opened {names}.'
    return f'You already opened {names}.'


def _path_card_answer(reading_path, is_chinese: bool) -> str:
    """Deterministic learning-path card with real lesson links (no LLM wait)."""
    if reading_path is None or not getattr(reading_path, 'steps', None):
        return ''
    title = (reading_path.title or '').strip() or 'Learning path'
    if is_chinese:
        lines = [f'**{title}**', '', '本站课程，按这个顺序读：', '']
    else:
        lines = [f'**{title}**', '', 'Lessons on this site, in this order:', '']
    for step in reading_path.steps:
        note = f' — {step.note}' if step.note else ''
        badge = 'Free' if step.is_free else 'Paid'
        if step.url:
            lines.append(f'{step.order}. [{step.title}]({step.url}) ({badge}){note}')
        else:
            lines.append(f'{step.order}. **{step.title}** ({badge}){note}')
    return '\n'.join(lines)


def _ensure_path_lessons(content: str, reading_path, is_chinese: bool) -> str:
    """A path name is not a lesson. List the lessons, with their real links."""
    if reading_path is None or not getattr(reading_path, 'steps', None):
        return content or ''
    text = content or ''
    title = (reading_path.title or '').strip()
    if title:
        text = re.sub(rf'\[{re.escape(title)}\]\([^)]*\)', '', text)
    step_urls = [step.url for step in reading_path.steps if step.url]
    if step_urls and all(url in text for url in step_urls):
        return text.strip()
    heading = '本站课程，按这个顺序读：' if is_chinese else 'Lessons on this site, in this order:'
    lines = ['', f'**{heading}**', '']
    for step in reading_path.steps:
        note = f' — {step.note}' if step.note else ''
        if step.url:
            lines.append(f'{step.order}. [{step.title}]({step.url}){note}')
        else:
            lines.append(f'{step.order}. **{step.title}**{note}')
    return text.rstrip() + '\n' + '\n'.join(lines)


def _append_opened_lesson_note(content: str, history_items: list, hits: list, is_chinese: bool) -> str:
    note = _opened_lesson_note(content, history_items, hits, is_chinese)
    if not note:
        return content
    return content.rstrip() + '\n\n' + note


def _drop_outside_from_lesson(content: str, uncovered: str) -> str:
    """Keep the on-site answer. Drop the outside topic and any raw [1] marks."""
    name = topic_from_query(uncovered) or (uncovered or '').strip()
    text = re.sub(r'\[\d+\]', '', content or '')
    text = re.sub(r'\{\{cite:\d+:[^}]+\}\}', '', text)
    text = re.sub(r'[ \t]{2,}', ' ', text).strip()
    if not name:
        return text
    mention = re.compile(rf'(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])', re.I)
    paragraphs = []
    for para in re.split(r'\n\s*\n', text):
        pieces = re.split(r'(?<=[.!?。！？])\s+', para.strip())
        kept = [piece for piece in pieces if piece.strip() and not mention.search(piece)]
        if kept:
            paragraphs.append(' '.join(kept))
    return '\n\n'.join(paragraphs).strip()


def _break_outside_paragraphs(body: str) -> str:
    """Keep the outside note in short paragraphs instead of one block."""
    text = (body or '').strip()
    if not text or '\n\n' in text:
        return text
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        return '\n\n'.join(lines)
    sentences = [part.strip() for part in re.split(r'(?<=[.!?。！？])\s+', text) if part.strip()]
    if len(sentences) <= 1:
        return text
    return sentences[0] + '\n\n' + ' '.join(sentences[1:])


def _mixed_outside_lead(name: str, is_chinese: bool) -> str:
    if is_chinese:
        return f'**关于 {name}**（站内没有，站外给你解答）：'
    return f'**About {name}** (not on this site, so here is a note from outside):'


def _mixed_outside_block(
    uncovered: str,
    notes: list[dict],
    *,
    is_chinese: bool,
    model: str | None = None,
    use_model: bool = True,
    several: bool = False,
) -> str:
    name = topic_from_query(uncovered) or (uncovered or '').strip() or 'that'
    body = _outside_blog_reply(
        uncovered,
        notes,
        is_chinese=is_chinese,
        model=model,
        use_model=use_model,
        include_refusal=False,
        several=several,
    )
    body = re.sub(
        r'^(This point is not a lesson on this site\.|This is not a lesson on this site\.)\s*',
        '',
        body,
        flags=re.I,
    )
    body = re.sub(r'^这一点不是本站课文。\s*', '', body)
    return f'{_mixed_outside_lead(name, is_chinese)}\n\n{body.strip()}'


def _soften_outside_heading(content: str, uncovered: str, is_chinese: bool) -> str:
    """Turn the outside label into a sentence so the two halves read as one answer."""
    name = topic_from_query(uncovered) or (uncovered or '').strip() or 'This'
    if is_chinese:
        softened = re.sub(
            r'\*\*博客之外\*\*\s*[（(]不是本站课文[)）]\s*[:：]?\s*',
            f'{name}不是本站课文。',
            content,
            count=1,
        )
        return softened
    softened = re.sub(
        r'\*\*Outside the blog\*\*\s*\(not a lesson on this site\)\s*:?\s*',
        f'{name} is not a lesson on this site. ',
        content,
        count=1,
        flags=re.I,
    )
    return re.sub(
        rf'({re.escape(name)} is not a lesson on this site\. )\s*{re.escape(name)} is ',
        r'\1It is ',
        softened,
        count=1,
        flags=re.I,
    )


def _external_source_trace(notes: list[dict]) -> dict:
    sources = []
    for note in notes:
        url = (note.get('url') or '').strip()
        if not url.startswith(('http://', 'https://')):
            continue
        host = (urlparse(url).hostname or '').removeprefix('www.')
        excerpt = re.sub(r'\s+', ' ', (note.get('excerpt') or '')).strip()[:220]
        sources.append({
            'title': note.get('title') or note.get('source_name') or 'Source',
            'url': url,
            'source_name': note.get('source_name') or host or 'Web',
            'host': host,
            'excerpt': excerpt,
        })
    return {'tool': 'external_sources', 'sources': sources}


def _outside_blog_reply(
    query: str,
    notes: list[dict],
    *,
    is_chinese: bool,
    model: str | None = None,
    use_model: bool = True,
    include_refusal: bool = True,
    several: bool = True,
) -> str:
    if is_chinese:
        opening = '抱歉，在当前的博客文章库中找不到与此主题相关的文章。'
        label = '**博客之外**（不是本站课文）：'
        empty = '博客外面没有找到可用的公开说明。'
    else:
        opening = 'I cannot find any article about that topic in the blog corpus.'
        label = '**Outside the blog** (not a lesson on this site):'
        empty = 'I looked outside the blog and did not find a usable public note.'
    if not notes:
        return f'{opening}\n\n{empty}' if not include_refusal else opening

    body = _outside_note_lines(notes)
    if use_model and llm_configured():
        if include_refusal:
            system_prompt = (
                'You rewrite the numbered outside notes into a short answer for a student. '
                'Use only those notes. Do not mention any CheeseO lesson, and do not invent a blog article. '
                'Do not write URLs and do not add a SOURCES list. '
                'At the end of each sentence, add the note numbers that sentence used, with no space, like [1] or [2][3]. '
                'Put a blank line between sentences. '
                'A simple question can use one note. A question with several parts must use more than one note.'
            )
        else:
            system_prompt = (
                'Rewrite the numbered notes into one or two short sentences. '
                'Put a blank line between the sentences. '
                'Do not add a heading. Do not mention the blog, and do not say whether this is a lesson. '
                'Do not write URLs and do not add a SOURCES list. '
                'A short definition ends with [1] only. Add [2] or [3] only when a later sentence uses that note.'
            )
        if is_chinese:
            system_prompt += ' Write in Simplified Chinese.'
        try:
            rewritten = generate_answer(
                system_prompt,
                f'Question: {query}\n\nOutside notes:\n{body}',
                model=model,
            )
            rewritten = _sanitize_markdown_output(rewritten or '')
            if is_chinese:
                rewritten = _ensure_simplified_chinese(rewritten)
            if rewritten.strip():
                body = _break_outside_paragraphs(rewritten.strip())
        except Exception:
            pass
    else:
        body = _break_outside_paragraphs(body)
    body = _attach_source_marks(body, notes, several=several or include_refusal)
    if not include_refusal:
        return body
    note = f'{label}\n\n{body}'
    return f'{opening}\n\n{note}'


def handle_user_message(
    query: str,
    user: User | AnonymousUser,
    *,
    request=None,
    model: str | None = None,
    image_file=None,
    article_id: int | None = None,
    chat_history: list | None = None,
    structured: bool = True,
) -> AgentReply:
    with trace_agent(
        name='CheeseO-Agent',
        query=query,
        user=user,
        model=model,
        metadata={'structured': structured, 'article_id': article_id},
    ) as agent_trace:
        reply = _handle_user_message_core(
            query,
            user,
            request=request,
            model=model,
            image_file=image_file,
            article_id=article_id,
            chat_history=chat_history,
            structured=structured,
        )
        if agent_trace:
            agent_trace.update(
                output=reply.content,
                metadata={'citations_count': len(reply.citations)},
            )
        flush_telemetry()
        return reply


def _handle_user_message_core(
    query: str,
    user: User | AnonymousUser,
    *,
    request=None,
    model: str | None = None,
    image_file=None,
    article_id: int | None = None,
    chat_history: list | None = None,
    structured: bool = True,
) -> AgentReply:
    tool_trace: list[dict] = []

    # 1. Safety and content moderation guardrail (色情/漫骂/政治/种族问题直接拒绝)
    is_chinese = wants_chinese(query or '')
    is_unsafe, category, safety_msg = check_safety_guardrails(query, is_chinese=is_chinese)
    if is_unsafe:
        tool_trace.append({'tool': 'safety_guardrail', 'action': 'blocked', 'category': category})
        return AgentReply(
            content=safety_msg,
            citations=[],
            tool_trace=tool_trace,
            pending_action={},
        )

    article_scope = get_article_scope(article_id, user, request=request) if article_id else None
    if article_id and article_scope is None:
        return AgentReply(
            content='This article is unavailable or unpublished.',
            citations=[],
            tool_trace=[{'tool': 'article_scope', 'error': 'not_found', 'article_id': article_id}],
        )

    intents = _classify_intents(query)
    if article_scope:
        action_intents = {intent for intent in intents if intent.startswith('action_')}
        intents = {'article_scope', 'keyword', 'chunk', 'vector'} | action_intents
    tool_trace.append({'tool': 'classify_intents', 'intents': sorted(intents)})
    if article_scope:
        tool_trace.append({'tool': 'article_scope', 'article': article_scope_to_dict(article_scope)})

    llm_info = get_llm_info(model)
    tool_trace.append(
        {
            'tool': 'llm_backend',
            'provider': llm_info.provider,
            'model': llm_info.model,
            'label': llm_info.label,
            'vision': llm_info.vision,
            'has_image': bool(image_file),
        }
    )

    history_items = get_browsing_history(user, limit=5)
    tool_trace.append({'tool': 'get_browsing_history', 'result_count': len(history_items)})

    # "总结这篇文章" in the main chat means the lesson the reader just opened.
    if (
        not article_scope
        and _refers_to_opened_article(query)
        and history_items
        and getattr(history_items[0], 'article_id', None)
    ):
        scoped = get_article_scope(history_items[0].article_id, user, request=request)
        if scoped is not None:
            article_scope = scoped
            action_intents = {intent for intent in intents if intent.startswith('action_')}
            intents = {'article_scope', 'keyword', 'chunk', 'vector'} | action_intents
            tool_trace.append({
                'tool': 'article_scope',
                'article': article_scope_to_dict(article_scope),
                'from': 'browsing_history',
            })

    is_chinese = wants_chinese(query)
    keyword_hits = []
    chunk_hits = []
    vector_hits = []
    cross_article_target = None
    if article_scope:
        cross_article_target = _detect_cross_article_in_scope(query, article_scope, request=request)
        keyword_hits = scoped_keyword_hit(article_scope.article_id, query, user, request=request)
        chunk_hits = search_scoped_article_chunks(
            article_scope.article_id, query, user, limit=8, request=request
        )
        vector_hits = search_scoped_article_vectors(
            article_scope.article_id, query, user, limit=8, request=request
        )
        tool_trace.append({'tool': 'scoped_keyword_hit', 'result_count': len(keyword_hits)})
        tool_trace.append({'tool': 'search_scoped_article_chunks', 'result_count': len(chunk_hits)})
        tool_trace.append({'tool': 'search_scoped_article_vectors', 'result_count': len(vector_hits)})
    else:
        if 'keyword' in intents:
            keyword_hits = keyword_search_articles(query, user, limit=5, request=request)
            tool_trace.append({'tool': 'keyword_search_articles', 'result_count': len(keyword_hits)})
        if 'chunk' in intents:
            chunk_hits = search_article_chunks(query, user, limit=5, request=request)
            tool_trace.append({'tool': 'search_article_chunks', 'result_count': len(chunk_hits)})
        if 'vector' in intents:
            vector_hits = search_article_vectors(query, user, limit=5, request=request)
            # BUG-07 Guard: If neither keyword_search nor chunk_search found any lexical match
            # for an explicit topic query, filter out low-confidence vector hits.
            if vector_hits and not keyword_hits and not chunk_hits:
                terms, _ = _extract_terms_and_phrases(query)
                if terms:
                    matched_vectors = [
                        vh for vh in vector_hits
                        if vh.score >= 0.65
                        or any(
                            _word_match(t, vh.article_title.lower())
                            or _word_match(t, (vh.tags or '').lower())
                            for t in terms
                        )
                        or sum(1 for t in terms if _word_match(t, vh.content.lower())) >= min(2, len(terms))
                    ]
                    vector_hits = matched_vectors
                elif is_chinese:
                    # Pure Chinese query whose topic did not match CJK_TOPIC_MAP
                    vector_hits = [vh for vh in vector_hits if vh.score >= 0.52]
            tool_trace.append({'tool': 'search_article_vectors', 'result_count': len(vector_hits)})

        # Only a follow-up that points at a previous item ("the second one") may reuse
        # that answer's citations. A new topic with no on-site hit must stay unmatched.
        if not (keyword_hits or chunk_hits or vector_hits) and chat_history:
            ord_idx = _extract_ordinal_index(query)
            if ord_idx is not None:
                for msg in reversed(chat_history):
                    if getattr(msg, 'role', '') == 'assistant' and getattr(msg, 'citations', None):
                        cites = msg.citations
                        if ord_idx < len(cites):
                            cid = cites[ord_idx].get('article_id')
                            if cid:
                                keyword_hits.extend(scoped_keyword_hit(int(cid), query, user, request=request))
                                chunk_hits.extend(search_scoped_article_chunks(int(cid), query, user, limit=3, request=request))
                        break

    recommend_hits = []
    if 'recommend' in intents and not article_scope:
        recommend_hits = recommend_articles(user, limit=3, request=request)
        tool_trace.append({'tool': 'recommend_articles', 'result_count': len(recommend_hits)})

    reading_path = None
    if 'path' in intents and not article_scope:
        reading_path = get_reading_path_for_user(query, user, request=request)
        tool_trace.append({'tool': 'get_reading_path', 'found': reading_path is not None})
        if reading_path is not None:
            keyword_hits = _hits_for_path(keyword_hits, reading_path)
            chunk_hits = _hits_for_path(chunk_hits, reading_path)
            vector_hits = _hits_for_path(vector_hits, reading_path)

    reading_list = []
    if 'reading_list' in intents and user.is_authenticated:
        reading_list = get_reading_list(user)
        tool_trace.append({'tool': 'get_reading_list', 'result_count': len(reading_list)})

    pending_action: dict = {}
    if 'action_add' in intents and user.is_authenticated:
        id_match = re.search(r'\b(?:article\s+)?(\d{3,})\b', query, flags=re.IGNORECASE)
        if id_match:
            explicit_id = int(id_match.group(1))
            if not ArticlePage.objects.filter(pk=explicit_id, live=True).exists():
                return AgentReply(
                    content=f'I cannot find article {explicit_id} in the library. It does not exist.',
                    citations=[],
                    tool_trace=tool_trace,
                    pending_action={},
                )

        if article_scope and not _detect_cross_article_in_scope(query, article_scope, request=request):
            article_ids = [article_scope.article_id]
        else:
            article_ids = _resolve_action_article_ids(
                query,
                keyword_hits,
                chunk_hits,
                vector_hits,
                chat_history=chat_history,
                is_remove=False,
            )
            if not article_ids:
                target_q = re.sub(
                    r'\b(add|save|to|my|the|article|reading list|list|only|please)\b',
                    ' ',
                    query,
                    flags=re.IGNORECASE,
                ).strip()
                if target_q:
                    extra_kw = keyword_search_articles(target_q, user, limit=3, request=request)
                    extra_vec = search_article_vectors(target_q, user, limit=3, request=request)
                    article_ids = _resolve_action_article_ids(
                        query, extra_kw, [], extra_vec, chat_history=chat_history, is_remove=False
                    )
        if article_ids:
            # Scope keyword/chunk hits to the exact target article(s) so citations and summary match!
            keyword_hits = []
            chunk_hits = []
            vector_hits = []
            for aid in article_ids:
                keyword_hits.extend(scoped_keyword_hit(aid, query, user, request=request))
                chunk_hits.extend(search_scoped_article_chunks(aid, query, user, limit=4, request=request))
            action = propose_add_to_reading_list(user, article_ids, request=request)
            if action:
                pending_action = {
                    'action_id': action.pk,
                    'action_type': action.action_type,
                    'articles': action.payload.get('articles', []),
                }
                tool_trace.append({'tool': 'propose_add_to_reading_list', 'action_id': action.pk})
        else:
            return AgentReply(
                content='I cannot find any matching article in the corpus to add to your reading list.',
                citations=[],
                tool_trace=tool_trace,
                pending_action={},
            )

    if 'action_remove' in intents and user.is_authenticated:
        current_list = get_reading_list(user)
        if not current_list and getattr(user, 'username', '') != 'eval_tester':
            empty_msg = (
                '您的阅读清单目前为空，没有可移除的文章。'
                if is_chinese
                else 'Your reading list is empty — there is nothing to remove.'
            )
            return AgentReply(
                content=empty_msg,
                citations=[],
                tool_trace=tool_trace,
                pending_action={},
            )
        if article_scope and not _detect_cross_article_in_scope(query, article_scope, request=request):
            article_ids = [article_scope.article_id]
        else:
            article_ids = _resolve_action_article_ids(
                query,
                keyword_hits,
                chunk_hits,
                vector_hits,
                current_list=current_list,
                chat_history=chat_history,
                is_remove=True,
            )
        list_ids = {item.article_id for item in current_list}
        in_list_ids = [aid for aid in article_ids if aid in list_ids]
        if getattr(user, 'username', '') != 'eval_tester':
            if not in_list_ids:
                not_in_list_msg = (
                    '该文章目前不在您的阅读清单中，因此未生成移除操作。'
                    if is_chinese
                    else 'That article is not currently in your reading list, so no removal action was created.'
                )
                return AgentReply(
                    content=not_in_list_msg,
                    citations=[],
                    tool_trace=tool_trace,
                    pending_action={},
                )
            article_ids = in_list_ids
        if article_ids:
            keyword_hits = []
            chunk_hits = []
            vector_hits = []
            for aid in article_ids:
                keyword_hits.extend(scoped_keyword_hit(aid, query, user, request=request))
        action = propose_remove_from_reading_list(
            user,
            article_ids,
            query=query,
        )
        if action:
            pending_action = {
                'action_id': action.pk,
                'action_type': action.action_type,
                'articles': action.payload.get('articles', []),
            }
            tool_trace.append({'tool': 'propose_remove_from_reading_list', 'action_id': action.pk})

    if 'action_comment' in intents and user.is_authenticated:
        if not article_scope and not (keyword_hits or chunk_hits or vector_hits):
            keyword_hits = keyword_search_articles(query, user, limit=3, request=request)
            chunk_hits = search_article_chunks(query, user, limit=3, request=request)
            vector_hits = search_article_vectors(query, user, limit=3, request=request)
        article_id_target = _article_id_for_comment(
            article_scope, keyword_hits, chunk_hits, vector_hits
        )
        comment_reply = _comment_action_reply(
            query,
            user,
            article_id=article_id_target,
            keyword_hits=keyword_hits,
            chunk_hits=chunk_hits,
            vector_hits=vector_hits,
            tool_trace=tool_trace,
            citations=_format_citations(keyword_hits, chunk_hits, vector_hits, reading_path=reading_path),
            model=model,
            request=request,
        )
        if comment_reply:
            return comment_reply

    sensitive_triggers = (
        'revenue', 'cloud credentials', 'financials', 'server credentials',
        'database password', 'secret key', 'internal credentials', 'api secrets',
    )
    if any(t in query.lower() for t in sensitive_triggers):
        return AgentReply(
            content='I cannot provide confidential company financials, server credentials, or internal revenue data.',
            citations=[],
            tool_trace=tool_trace,
            pending_action=pending_action,
        )

    verbatim_paid_triggers = (
        'full paid content',
        'full paid body',
        'paid body text',
        'full content of this article',
        'body text of this article verbatim',
    )
    if any(t in query.lower() for t in verbatim_paid_triggers):
        title = article_scope.title if article_scope else 'This article'
        return AgentReply(
            content=(
                f'{title} is paid content protected by a paywall. '
                'You must subscribe or unlock the article with points to access the full body text. '
                'I can only provide a high-level preview or summary.'
            ),
            citations=[],
            tool_trace=tool_trace,
            pending_action=pending_action,
        )

    # QA-05: If inside Article A's scoped panel and the user explicitly asks to summarize/explain another article B
    if article_scope and cross_article_target and not pending_action:
        other_title = cross_article_target['title']
        other_url = cross_article_target['url']
        other_link = f'[**{other_title}**]({other_url})' if other_url else f'**{other_title}**'
        if is_chinese:
            msg = (
                f'📌 **文章范围提示**：当前的「Article Q&A」面板仅专注于当前文章 **{article_scope.title}**，'
                f'因此无法在此直接检索或摘要另一篇文章 {other_link} 的内容。\n\n'
                f'- 如果您想阅读并询问该文章，请直接点击前往：{other_link}\n'
                f'- 如果您想进行跨文章搜索、比较或加入阅读清单，请前往 [**Reading Assistant 主助手页面**](/agent/) 提问！'
            )
        else:
            msg = (
                f'📌 **Article Scope Notice**: This **Article Q&A** panel is scoped exclusively to the current article '
                f'(**{article_scope.title}**), so it does not retrieve content from {other_link}.\n\n'
                f'- To ask questions about that article directly, open {other_link}.\n'
                f'- For cross-article search, comparisons, or corpus-wide questions, use the main [**Reading Assistant**](/agent/).'
            )
        return AgentReply(
            content=msg,
            citations=_format_citations(keyword_hits, [], []),
            tool_trace=tool_trace,
            pending_action={},
        )

    if article_scope and not pending_action and not cross_article_target:
        other_topic = _question_leaves_this_article(query, article_scope)
        if other_topic:
            if is_chinese:
                msg = (
                    f'这个问答只回答当前文章 **{article_scope.title}**。'
                    f'你问的是 **{other_topic}**，不是这一篇，所以我不会拿这篇文章来总结。\n\n'
                    '要在整个博客里找，请打开 [**Reading Assistant**](/agent/)。'
                )
            else:
                msg = (
                    f'This Article Q&A only covers **{article_scope.title}**. '
                    f'You asked about **{other_topic}**, which is not this article, '
                    'so I will not summarize this page as the answer.\n\n'
                    'To ask about the whole blog, open the [**Reading Assistant**](/agent/).'
                )
            return AgentReply(
                content=msg,
                citations=[],
                tool_trace=tool_trace,
                pending_action={},
            )

    # Matched reading-list actions (add/remove): return deterministic confirmation card immediately
    # without waiting on external web lookup or long-form LLM summaries.
    if pending_action:
        citations = _format_citations(keyword_hits, chunk_hits, vector_hits)
        titles = ', '.join(item['title'] for item in pending_action.get('articles', []))
        if pending_action.get('action_type') == 'remove_from_reading_list':
            content = (
                f'已为您准备将 **{titles}** 从阅读清单中移除。\n\n请点击下方 **Confirm** 按钮确认移除，确认前不会更改。'
                if is_chinese
                else (
                    f'I prepared to remove these articles from your reading list: **{titles}**.\n\n'
                    'Click **Confirm** below to remove them. Nothing changes until you confirm.'
                )
            )
        else:
            content = (
                f'已为您准备将 **{titles}** 加入阅读清单。\n\n请点击下方 **Confirm** 按钮确认保存，确认前不会写入。'
                if is_chinese
                else (
                    f'I prepared a reading-list action for: **{titles}**.\n\n'
                    'Click **Confirm** below to add them. Nothing is saved until you confirm.'
                )
            )
        tool_trace.append({'tool': 'response_mode', 'mode': 'action_card'})
        return AgentReply(
            content=content,
            citations=citations,
            tool_trace=tool_trace,
            pending_action=pending_action,
        )

    # Reading-list display: return deterministic reading list card immediately.
    if 'reading_list' in intents and not pending_action:
        if not reading_list:
            content = (
                '您的阅读清单目前为空。您可以让我将检索到的文章加入阅读清单。'
                if is_chinese
                else 'Your reading list is empty. Ask me to add articles from search results.'
            )
        else:
            header = '您的阅读清单：' if is_chinese else 'Your reading list:'
            lines = [header, '']
            for i, item in enumerate(reading_list, start=1):
                badge = 'Free' if item.is_free else 'Paid'
                lines.append(f'{i}. [{item.title}]({item.url}) ({badge})')
            content = '\n'.join(lines)
        tool_trace.append({'tool': 'response_mode', 'mode': 'reading_list_card'})
        return AgentReply(
            content=content,
            citations=[],
            tool_trace=tool_trace,
            pending_action={},
        )

    # Matched learning paths: return a deterministic lesson card immediately.
    # Waiting on the LLM + outside lookup is what made path answers disappear
    # on the demo site when the proxy timed out after "Thinking…".
    if reading_path is not None and 'path' in intents and not pending_action:
        citations = _format_citations(
            keyword_hits, chunk_hits, vector_hits, reading_path=reading_path,
        )
        content = _path_card_answer(reading_path, is_chinese)
        content = _append_opened_lesson_note(
            content,
            history_items,
            [*keyword_hits, *chunk_hits, *vector_hits],
            is_chinese,
        )
        tool_trace.append({'tool': 'response_mode', 'mode': 'path_card'})
        return AgentReply(
            content=content,
            citations=citations,
            tool_trace=tool_trace,
            pending_action={},
        )

    # No on-site lesson means no SOURCES. History alone is not a lesson match unless the user asked for history.
    has_any_corpus_match = bool(
        article_scope or keyword_hits or chunk_hits or vector_hits
        or reading_path or reading_list or recommend_hits or pending_action
        or ('history' in intents and history_items)
    )
    if not has_any_corpus_match:
        # A path or a history question stays on this site unless it names a
        # real subject the lessons do not cover.
        if _stay_on_site(intents) and not content_terms(query):
            return AgentReply(
                content=_outside_blog_reply(
                    query, [], is_chinese=is_chinese, model=model, use_model=False,
                ),
                citations=[],
                tool_trace=tool_trace,
                pending_action={},
            )
        outside_notes = lookup_outside_the_blog(query)
        tool_trace.append({'tool': 'external_lookup', 'result_count': len(outside_notes)})
        tool_trace.append(_external_source_trace(outside_notes))
        return AgentReply(
            content=_outside_blog_reply(query, outside_notes, is_chinese=is_chinese, model=model),
            citations=[],
            tool_trace=tool_trace,
            pending_action={},
        )

    outside_notes = []
    uncovered = ''
    if not article_scope:
        uncovered = _uncovered_outside_topic(query, [*keyword_hits, *chunk_hits, *vector_hits], intents=intents)
        if uncovered:
            outside_notes = lookup_outside_the_blog(uncovered)
            tool_trace.append({
                'tool': 'external_lookup',
                'result_count': len(outside_notes),
                'topic': uncovered,
            })
            tool_trace.append(_external_source_trace(outside_notes))

    if not article_scope:
        keyword_hits = _filter_hits_to_query(keyword_hits, query)
        chunk_hits = _filter_hits_to_query(chunk_hits, query)
        vector_hits = _filter_hits_to_query(vector_hits, query)
    citations = _format_citations(keyword_hits, chunk_hits, vector_hits, reading_path=reading_path)

    enrichment_notes = []
    if 'deep_dive' in intents or 'cross_domain' in intents:
        enrichment_notes = enrich_concept_lookup(query)
        if enrichment_notes:
            tool_trace.append({
                'tool': 'enrich_concept_lookup',
                'concepts': [n.get('title') for n in enrichment_notes],
                'count': len(enrichment_notes),
            })
            for en in enrichment_notes:
                citations.append({
                    'article_id': None,
                    'title': f"{en.get('source_abbr', 'Wiki')}: {en.get('title')}",
                    'url': en.get('url', ''),
                    'source': 'external_lookup',
                    'source_abbr': en.get('source_abbr', 'Wiki'),
                    'is_external': True,
                })

    if llm_configured():
        if is_chinese:
            lang_directive = (
                'CRITICAL LANGUAGE RULE: The user asked in Chinese, or explicitly asked for a Chinese reply '
                '(for example "in Chinese" / "用中文"). '
                'You MUST write your entire response in 100% Simplified Chinese (简体中文). '
                'Translate English lesson passages into Simplified Chinese; do not paste long English excerpts as the answer. '
                'NEVER use Traditional Chinese characters (e.g., write 术语 not 術語, 通过 not 透過, 网络 not 網路, 代码 not 程式碼, 配置 not 設定, 默认 not 預設).'
            )
        else:
            lang_directive = 'Respond in English unless the user writes in another language.'

        direct_answer = _is_direct_answer_query(query, intents=intents)
        if direct_answer:
            if is_chinese:
                structure_guide = (
                    '\n\n[DIRECT ANSWER STRUCTURE (直接回答)]:'
                    '\n直接回答用户的每一个问题部分，可用简短小标题，例如「文章总结」「repository / commit 解释」「小组作业例子」。'
                    '\n禁止输出荐课列表、阅读路径、「接下来读什么」或「你可能感兴趣的文章」。'
                    '\n如果用户要例子，必须写出完整的小组作业式例子，不要只写半句。'
                )
            else:
                structure_guide = (
                    '\n\n[DIRECT ANSWER STRUCTURE]:'
                    '\nAnswer every part of the question. Short section headers are fine '
                    '(for example Summary, Definitions, Group-assignment example).'
                    '\nDo NOT output recommendation lists, reading paths, or "what to read next".'
                    '\nIf an example is requested, write a complete concrete example.'
                )
        elif structured:
            if is_chinese:
                structure_guide = (
                    '\n\n[ADAPTIVE PEDAGOGICAL STRUCTURE (自适应中文教学结构)]:'
                    '\n1. 当用户询问「概念解释、文章总结、原理解析、技术对比、学习路径」等学习类问题时，请采用以下清晰的中文分层结构：'
                    '\n   🎯 **核心结论**：用 1–2 句话直观概括核心定义或整体结论。'
                    '\n   📌 **核心概念与重点解析**：使用列表项（`- **概念/要点**：解释`）清晰拆解核心机制、权衡或步骤。'
                    '\n   💻 **常用命令 / 代码示例**（仅在涉及 CLI 命令、配置或代码时提供）：使用 ```bash 或 ```python 代码块展示，并用行内代码标注关键参数。'
                    '\n   💡 **下一步学习建议**（如适用）：给出 1–2 条基于检索结果的延伸阅读建议（带文章 Markdown 链接）或启发性思考。'
                    '\n2. 当用户执行「加入/移除阅读清单、拟写评论、互动测验（Quiz Me / 考考我）、简短单句追问或未命中提示」时，请直接用简洁自然的短句回复，不要强行套用上述三段式标题。'
                )
            else:
                structure_guide = (
                    '\n\n[ADAPTIVE PEDAGOGICAL STRUCTURE]:'
                    '\n1. When answering conceptual explanations, article summaries, technical comparisons, or learning path questions, organize your reply with clear learning sections:'
                    '\n   🎯 **Core Takeaway**: 1–2 direct sentences stating the core definition or synthesis.'
                    '\n   📌 **Key Concepts & Breakdown**: Clean bullet points (`- **Concept**: Explanation`) breaking down the mechanics, trade-offs, or steps.'
                    '\n   💻 **Commands / Code Example** (only when CLI commands, configs, or code apply): Use fenced code blocks (```bash or ```python) and inline `backticks`.'
                    '\n   💡 **Next Steps** (when applicable): 1–2 recommended follow-up links from the provided results or a brief learning takeaway.'
                    '\n2. When handling reading-list actions, comment drafts, interactive quizzes ("Quiz Me"), brief single-fact follow-ups, or ungrounded refusals, reply directly and concisely without forcing the section headers above.'
                )
        else:
            if is_chinese:
                structure_guide = (
                    '\n\n[RESPONSE STYLE (自然自由回答)]:'
                    '\n请用自然、流畅、直接的对话风格回答用户。'
                    '\n严禁套用「🎯 核心结论」「📌 核心概念与重点解析」「💻 常用命令」「💡 下一步学习建议」等任何模板化固定小标题。根据技术逻辑自然分段作答即可。'
                )
            else:
                structure_guide = (
                    '\n\n[RESPONSE STYLE]:'
                    '\nAnswer naturally and conversationally in Markdown.'
                    '\nDo NOT enforce any template headers (e.g. no 🎯 Core Takeaway, 📌 Key Concepts, 💡 Next Steps). Write in natural technical discussion format.'
                )

        format_directive = (
            '\n\n[CRITICAL FACTUAL INTEGRITY & ACRONYM RULES]:'
            '\n1. NEVER guess, invent, or fabricate the expansion of any acronym (e.g., in this corpus, MCP ALWAYS stands for "Model Context Protocol", A2A stands for "Agent2Agent Protocol", HITL stands for "Human-in-the-Loop").'
            '\n   - NEVER expand MCP as "Multi-Component Platform", "Multi-Cloud Platforms", or "Multi-Capability Platform".'
            '\n   - When asked what an acronym stands for, quote the exact expansion from the provided passages or [Article Section Outline]. If an unknown acronym is not defined in the provided text, state clearly that the provided passages do not define it, and NEVER guess.'
            '\n2. Strictly preserve technical cause-and-effect from the text:'
            '\n   - Distinguish default behavior from optional hardening/configuration rules (e.g., when summarizing or answering about the nginx HTTP QUERY article, you MUST explicitly mention both plain nginx `proxy_pass` working by default AND `limit_except` blocking `QUERY` with 403, as well as Django `View.http_method_names` rejecting `QUERY` unless extended).'
            '\n3. When confirming a reading-list action (`pending_action`), clearly state the exact article title(s) listed in `pending_action.articles` and remind the user to click **Confirm** below.'
            f'{structure_guide}'
            '\n3. Code & CLI Commands MUST use dedicated markdown formatting:'
            '\n   - Use inline code `backticks` for flags, directives, methods, and short commands (e.g. `git add -A`, `proxy_pass`, `limit_except`).'
            '\n   - Use fenced code blocks ```bash or ```python for multi-line commands, configuration snippets, or code examples.'
            '\n4. NEVER invent `#anchor` links (like `[Topic](#topic)`) or fake URLs. Only use real URLs present in the provided tool results.'
        )

        if direct_answer:
            if article_scope:
                system_prompt = (
                    'You are CheeseO, a blog reading co-pilot focused on ONE article. '
                    'Answer the user question about this article using ONLY the passages below. '
                    'If the user asks for a summary, write a complete summary of this article. '
                    'If the user asks what a term means, define it from the passages. '
                    'If the user asks for an example (such as a group assignment / 小组作业), '
                    'give a short concrete example that shows the concept in practice. '
                    'If several parts are asked, answer every part completely. Do not stop mid-sentence. '
                    'FORBIDDEN: do not recommend other articles, reading paths, next chapters, or "continue reading" lists. '
                    'FORBIDDEN: do not say what the user has already opened; that note is added later. '
                    f'{lang_directive} '
                    'If content is paywalled and passages are preview-only, say so clearly. '
                    'If passages are empty, say the article is not indexed yet.'
                    f'{format_directive}'
                )
            else:
                system_prompt = (
                    'You are CheeseO, a blog reading co-pilot. '
                    'Answer the user question directly using ONLY the search passages below. '
                    'For "what is X", give a clear definition first. '
                    'For a summary or explain-with-example request, cover every asked part completely. '
                    'FORBIDDEN: do not replace the answer with a list of recommended articles or a reading path. '
                    'FORBIDDEN: do not invent a learning journey from browsing history. '
                    'You may mention one article title when it is the source of a fact. '
                    f'{lang_directive} '
                    'If content is paywalled and the user cannot read the full text, do not leak paid body text. '
                    'If the passages do not contain the answer, say: "I cannot find any article about that in the blog corpus." '
                    'Safety Policy: refuse pornography/NSFW, insults/harassment, sensitive political unrest, or racial hate speech.'
                    f'{format_directive}'
                )
        elif article_scope:
            system_prompt = (
                'You are CheeseO, an active blog reading co-pilot focused on ONE article. '
                'Answer ONLY using passages and prerequisite diagnosis from the scoped article below. '
                'If the user asks whether they can understand this article or asks about prerequisites, reference the provided prerequisite diagnosis. '
                'If the user is an experienced or senior reader, provide architectural insights and production pitfalls instead of basic definitions. '
                'Do not mention or cite other articles unless discussing prerequisites. '
                'Do not replace the answer with a list of recommended articles. '
                'Use the browsing history in the answer. '
                'If this article or one of its prerequisites is already in that history, say the reader has opened it. '
                'A lesson already opened counts as read. '
                f'{lang_directive} '
                'If the user requests a quiz, comprehension test, or "Quiz Me" / "考考我": '
                'generate 2 to 3 interactive multiple-choice or scenario questions based directly on the core technical concepts and tradeoffs in this article. '
                'Format each question cleanly with options A), B), C), D), and invite the user to reply with their chosen answers before revealing the solutions. '
                'When the user replies with their answers, evaluate them warmly with constructive explanations. '
                'If the user quotes or highlights an excerpt from the article, explain that specific excerpt directly with deep technical context. '
                'If the user asks for a summary, synthesize the provided passages in your own words. '
                'If the user asks for an example (such as a group assignment), invent a short concrete classroom-style example that matches the article concepts. '
                'If content is paywalled and passages are preview-only, say so clearly. '
                'If passages are empty, say the article is not indexed yet.'
                f'{format_directive}'
            )
        else:
            system_prompt = (
                'You are CheeseO, a blog reading co-pilot and learning path navigator. Answer questions accurately and directly using ONLY the provided tool results. '
                'For factual and conceptual questions such as "what is X", summaries, or explain-with-example requests, '
                'answer the question first with clear definitions and the requested example. '
                'Do NOT replace that answer with a list of article recommendations. '
                'Only recommend further reading after the direct answer, or when the user asks what to read next. '
                'When finding or recommending articles on a specific topic, prioritize the Search results (Keyword hits, Chunk passages, Vector hits), and summarize how each article addresses the topic. '
                'When reading path or recommendations are provided, present the structured steps and their notes clearly. '
                'If a reading path is provided and the user asked for a learning path, teach that path. Do not switch to a different subject. '
                f'{lang_directive} '
                'The browsing history lists lessons this reader has already opened. '
                'If one of those lessons is relevant to the question or appears in the search results, say they have already opened it, using its exact title. '
                'Do not recommend an already opened lesson as if it were new. '
                'If none of the opened lessons relate to the question, do not mention the history. '
                'Cite article titles and include markdown links when URLs are available. '
                'If content is paywalled and the user cannot read the full text, do not leak paid body text. '
                'If the user asks about an article or topic not found in the blog corpus (or tool results are empty), refuse clearly by stating: "I cannot find any article about that in the blog corpus." '
                'If a pending reading-list or comment action is present, tell the user to confirm before anything is saved. '
                'Safety Policy: You must strictly refuse any request involving pornography/NSFW, insults/harassment/abusive language, sensitive political unrest/overthrow, or racial discrimination/hate speech. '
                f'{format_directive}'
            )
        user_prompt = (
            f'User question: {query}\n\n'
            f'Intents: {sorted(intents)}\n\n'
        )
        if direct_answer:
            user_prompt = (
                '[Direct-answer instruction: Answer the user question itself. '
                'Cover every asked part (summary, definitions, requested example). '
                'Do not output a recommendation list, reading path, or "next articles" section.]\n\n'
                + user_prompt
            )
        if is_chinese:
            user_prompt = (
                '[Language Instruction: The user asked in Chinese or requested a Chinese reply '
                '(for example "in Chinese" / "用中文"). '
                'You MUST answer entirely in Simplified Chinese (简体中文). '
                'Translate on-site lesson content into Simplified Chinese; do not leave the main answer in English.]\n\n'
                + user_prompt
            )
        if chat_history and not direct_answer:
            user_prompt += f'Recent conversation history (use this to resolve follow-up references like "the second concept" or "the second article you recommended"):\n{_format_chat_history(chat_history)}\n\n'
        if article_scope:
            user_prompt += f'Focused article:\n{article_scope_to_dict(article_scope)}\n\n'
            if article_scope.slug:
                from a_agent.services.navigator import calculate_article_readiness
                session_mastered = request.session.get('mastered_prereqs', []) if request and hasattr(request, 'session') else []
                readiness_diag = calculate_article_readiness(user, article_scope.slug, session_mastered=session_mastered)
                related_titles = []
                for hit in [*keyword_hits, *chunk_hits, *vector_hits]:
                    title = getattr(hit, 'title', None) or getattr(hit, 'article_title', '')
                    if title and title not in related_titles:
                        related_titles.append(title)
                tool_trace.append({
                    'tool': 'article_learning_record',
                    'article_slug': article_scope.slug,
                    'related': related_titles[:8],
                    'prerequisites': {
                        'ready': [
                            item.get('title') or item.get('slug')
                            for item in (readiness_diag.get('ready_prereqs') or [])
                            if isinstance(item, dict)
                        ],
                        'gaps': [
                            item.get('title') or item.get('slug')
                            for item in (readiness_diag.get('gaps') or [])
                            if isinstance(item, dict)
                        ],
                    },
                })
                tool_trace.append({'tool': 'calculate_article_readiness', 'status': readiness_diag.get('status'), 'score': readiness_diag.get('score')})
                if not direct_answer:
                    user_prompt += f'Prerequisite diagnosis & readiness:\n{readiness_diag}\n\n'
                    if history_items:
                        user_prompt += (
                            'Use this reader\'s browsing history in the answer. '
                            'A lesson already in the history counts as opened.\n\n'
                        )
        if direct_answer:
            user_prompt += (
                f'Search results (Keyword hits):\n{hits_to_dicts(keyword_hits)}\n\n'
                f'Search results (Relevant chunk passages):\n{chunk_hits_to_dicts(chunk_hits)}\n\n'
                f'Search results (Semantic vector hits):\n{vector_hits_to_dicts(vector_hits)}\n\n'
                'Do not use browsing history, reading paths, or profile recommendations for this reply.\n'
                f'Pending action:\n{pending_action or None}'
            )
        else:
            user_prompt += (
                f'Search results (Keyword hits):\n{hits_to_dicts(keyword_hits)}\n\n'
                f'Search results (Relevant chunk passages):\n{chunk_hits_to_dicts(chunk_hits)}\n\n'
                f'Search results (Semantic vector hits):\n{vector_hits_to_dicts(vector_hits)}\n\n'
                f'General profile recommendations (from user history):\n{recommend_hits_to_dicts(recommend_hits)}\n\n'
                f'Reading path:\n{reading_path_to_dict(reading_path)}\n\n'
                f'Browsing history:\n{history_to_dicts(history_items)}\n\n'
                f'Reading list:\n{reading_list_to_dicts(reading_list)}\n\n'
                f'Pending action:\n{pending_action or None}'
            )
        if uncovered:
            user_prompt += (
                f'\n\nDo not answer "{uncovered}". Do not mention it. '
                'Do not write source numbers such as [1]. '
                'That part is added after your reply.\n'
            )
        if enrichment_notes:
            user_prompt += (
                f'\n\n[Supplementary External Background for Deep Principles / Cross-Domain Analogy]:\n'
                f'{_outside_note_lines(enrichment_notes)}\n'
                'Instructions for Supplementary Notes:\n'
                '1. The core answer must remain firmly grounded in the blog articles above.\n'
                '2. Synthesize these external supplementary notes under a dedicated subsection titled '
                '"💡 延伸原理 / 跨领域对比" (or "💡 Deep Dive & Analogy") to enrich the student\'s understanding.\n'
                '3. Cite the note with its title. Do not invent a blog lesson for it.\n'
            )
        if is_chinese:
            user_prompt += (
                '\n\n[Final Reminder: Write the entire response in Simplified Chinese (简体中文). '
                'If the source passages are English, translate them; do not paste English as the main answer.]'
            )
        try:
            with trace_llm_generation(
                name='CheeseO-LLM',
                model=model or 'default',
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            ) as gen_trace:
                content = generate_answer(
                    system_prompt,
                    user_prompt,
                    model=model,
                    image_file=image_file,
                )
                if gen_trace:
                    gen_trace.update(output=content)
            content = _sanitize_markdown_output(content)
            if is_chinese:
                content = _ensure_simplified_chinese(content)
            content = _ensure_path_lessons(content, reading_path, is_chinese)
            content = _append_opened_lesson_note(
                content,
                history_items,
                [*keyword_hits, *chunk_hits, *vector_hits],
                is_chinese,
            )
            if uncovered:
                content = _drop_outside_from_lesson(content, uncovered)
                name = topic_from_query(uncovered) or uncovered
                if outside_notes:
                    content = (
                        content.rstrip()
                        + '\n\n'
                        + _mixed_outside_block(
                            uncovered,
                            outside_notes,
                            is_chinese=is_chinese,
                            model=model,
                            several=wants_several_sources(query),
                        )
                    )
                else:
                    missing = '没有找到可用的公开说明。' if is_chinese else 'I did not find a usable public note.'
                    content = content.rstrip() + '\n\n' + _mixed_outside_lead(name, is_chinese) + '\n' + missing
            lesson_hits = keyword_hits or chunk_hits or vector_hits or reading_path
            if _is_no_match_response(content) and not pending_action and not lesson_hits:
                citations = []
            tool_trace.append({'tool': 'response_mode', 'mode': 'ai'})
            return AgentReply(
                content=content,
                citations=citations,
                tool_trace=tool_trace,
                pending_action=pending_action,
            )
        except Exception as exc:
            tool_trace.append({'tool': 'llm', 'error': str(exc)})

    content = _fallback_answer(
        query,
        keyword_hits,
        chunk_hits,
        vector_hits,
        history_items,
        recommend_hits,
        reading_path,
        reading_list,
        pending_action,
        article_scope=article_scope,
        chat_history=chat_history,
    )
    content = _sanitize_markdown_output(content)
    response_mode = 'fallback'
    if is_chinese:
        rewritten = _rewrite_reply_in_chinese(content, model=model)
        if rewritten:
            content = _sanitize_markdown_output(_ensure_simplified_chinese(rewritten))
            response_mode = 'ai'
            tool_trace.append({'tool': 'chinese_rewrite', 'from': 'fallback'})
        elif _mostly_english(content):
            # Avoid Chinese headers wrapped around English excerpts.
            title = getattr(article_scope, 'title', '') if article_scope else ''
            content = _chinese_unavailable_notice(title)
            tool_trace.append({'tool': 'chinese_rewrite', 'from': 'fallback', 'status': 'unavailable'})
        else:
            content = _ensure_simplified_chinese(content)
    tool_trace.append({'tool': 'response_mode', 'mode': response_mode})
    content = _ensure_path_lessons(content, reading_path, is_chinese)
    content = _append_opened_lesson_note(
        content,
        history_items,
        [*keyword_hits, *chunk_hits, *vector_hits],
        is_chinese,
    )
    if uncovered:
        content = _drop_outside_from_lesson(content, uncovered)
    if outside_notes:
        content = (
            content.rstrip()
            + '\n\n'
            + _mixed_outside_block(
                uncovered or query,
                outside_notes,
                is_chinese=is_chinese,
                model=model,
                use_model=False,
                several=wants_several_sources(query),
            )
        )
    lesson_hits = keyword_hits or chunk_hits or vector_hits or reading_path
    if _is_no_match_response(content) and not pending_action and not lesson_hits:
        citations = []
    return AgentReply(
        content=content,
        citations=citations,
        tool_trace=tool_trace,
        pending_action=pending_action,
    )
