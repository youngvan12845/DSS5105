from __future__ import annotations

from dataclasses import dataclass, field

from django.contrib.auth.models import AnonymousUser, User

from a_agent.tools.article_scope import (
    article_scope_to_dict,
    get_article_scope,
    scoped_keyword_hit,
    search_scoped_article_chunks,
    search_scoped_article_vectors,
)
from a_agent.tools.comment_draft import build_comment_draft, propose_post_comment
from a_agent.tools.browsing_history import get_browsing_history, history_to_dicts
from a_agent.tools.chunk_search import chunk_hits_to_dicts, search_article_chunks
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
from a_agent.services.llm import generate_answer, get_llm_info, llm_configured


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
    'read first',
    'what order',
    'getting started',
    '入门',
    '路径',
    'learn machine learning',
    'learn python',
)
ADD_LIST_HINTS = (
    'add to',
    'save to list',
    '加入清单',
)
REMOVE_LIST_HINTS = (
    'remove from',
    'delete from',
    'remove from my list',
    'remove from reading list',
    'delete from reading list',
    '从清单移除',
    '移出清单',
)
LIST_QUERY_HINTS = (
    'show my reading list',
    'my reading list',
    'what is in my list',
    'reading list items',
)
COMMENT_HINTS = (
    'draft a comment',
    'write a comment',
    'post a comment',
    'leave a comment',
    'comment on',
    'comment for',
    '帮我写评论',
    '写一条评论',
    '评论草稿',
    '发表评论',
)


def _classify_intents(query: str) -> set[str]:
    q = query.lower()
    intents: set[str] = set()

    if any(h in q for h in CONTINUE_READING_HINTS):
        intents.add('history')
    if any(h in q for h in RECOMMEND_HINTS):
        intents.add('recommend')
    if any(h in q for h in PATH_HINTS):
        intents.add('path')
    if any(h in q for h in LIST_QUERY_HINTS):
        intents.add('reading_list')
    elif any(h in q for h in REMOVE_LIST_HINTS):
        intents.add('action_remove')
    elif any(h in q for h in ADD_LIST_HINTS):
        intents.add('action_add')
    if any(h in q for h in COMMENT_HINTS):
        intents.add('action_comment')

    if not intents or any(word in q for word in ('what', 'which', 'summarize', 'explain', 'cover', 'mention')):
        intents.update({'keyword', 'chunk', 'vector'})
    return intents


def _format_citations(keyword_hits, chunk_hits, vector_hits) -> list[dict]:
    citations: list[dict] = []
    seen: set[int] = set()

    for hits, source in (
        (vector_hits, 'vector_search'),
        (chunk_hits, 'chunk_search'),
        (keyword_hits, 'keyword_search'),
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


def _article_ids_for_action(keyword_hits, chunk_hits, vector_hits, limit: int = 3) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    for hit in [*vector_hits, *keyword_hits, *chunk_hits]:
        article_id = getattr(hit, 'article_id', None)
        if article_id is None or article_id in seen:
            continue
        seen.add(article_id)
        ids.append(article_id)
        if len(ids) >= limit:
            break
    return ids


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
            content='I could not draft a comment for that article.',
            citations=citations,
            tool_trace=tool_trace,
        )

    action = propose_post_comment(user, article_id, draft, request=request)
    if not action:
        return AgentReply(
            content='That article is unavailable for commenting.',
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
) -> str:
    q = query.lower()

    if article_scope:
        combined = vector_hits or chunk_hits or keyword_hits
        if not combined:
            if not article_scope.can_read_full and not article_scope.is_free:
                return (
                    f'**{article_scope.title}** is a paid article and I only have preview access.\n\n'
                    'Subscribe or unlock the article to ask detailed questions about its full content.'
                )
            return (
                f'I could not find indexed content for **{article_scope.title}** yet.\n\n'
                'Ask an admin to run `python manage.py build_article_index --embed` after publishing.'
            )

        lines = [f'About **{article_scope.title}**:', '']
        source_hits = vector_hits[:3] if vector_hits else chunk_hits[:3]
        for hit in source_hits:
            score_note = f' (score {hit.score})' if hasattr(hit, 'score') and hit.score else ''
            lines.append(f'- {hit.content[:220]}...{score_note}')
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
            'No matching articles found in the blog corpus. Try different keywords, '
            'or check whether the content has been published yet.'
        )

    lines = ['Here is what I found in the article library:', '']
    for i, hit in enumerate(keyword_hits[:3], start=1):
        access_note = '' if hit.can_read_full else ' (paid — preview only)'
        lines.append(f'{i}. [{hit.title}]({hit.url}){access_note}')
        if hit.snippet:
            lines.append(f'   {hit.snippet[:180]}')
        lines.append('')

    source_hits = vector_hits[:2] if vector_hits else chunk_hits[:2]
    if source_hits:
        label = 'Vector matches' if vector_hits else 'Relevant passages'
        lines.append(f'{label}:')
        for hit in source_hits:
            score_note = f' (score {hit.score})' if hasattr(hit, 'score') and hit.score else ''
            lines.append(f'- **{hit.article_title}**{score_note}: {hit.content[:200]}...')

    lines.append('\nThis answer is grounded in on-site search tools, not model fabrication.')
    return '\n'.join(lines)


def handle_user_message(
    query: str,
    user: User | AnonymousUser,
    *,
    request=None,
    model: str | None = None,
    image_path: str | None = None,
    article_id: int | None = None,
) -> AgentReply:
    tool_trace: list[dict] = []
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
            'has_image': bool(image_path),
        }
    )

    history_items = []
    if 'history' in intents or 'recommend' in intents:
        history_items = get_browsing_history(user, limit=5)
        tool_trace.append({'tool': 'get_browsing_history', 'result_count': len(history_items)})

    keyword_hits = []
    chunk_hits = []
    vector_hits = []
    if article_scope:
        keyword_hits = scoped_keyword_hit(article_scope.article_id, query, user, request=request)
        chunk_hits = search_scoped_article_chunks(
            article_scope.article_id, query, user, limit=6, request=request
        )
        vector_hits = search_scoped_article_vectors(
            article_scope.article_id, query, user, limit=6, request=request
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
            tool_trace.append({'tool': 'search_article_vectors', 'result_count': len(vector_hits)})

    recommend_hits = []
    if 'recommend' in intents and not article_scope:
        recommend_hits = recommend_articles(user, limit=3, request=request)
        tool_trace.append({'tool': 'recommend_articles', 'result_count': len(recommend_hits)})

    reading_path = None
    if 'path' in intents and not article_scope:
        reading_path = get_reading_path_for_user(query, user, request=request)
        tool_trace.append({'tool': 'get_reading_path', 'found': reading_path is not None})

    reading_list = []
    if 'reading_list' in intents and user.is_authenticated:
        reading_list = get_reading_list(user)
        tool_trace.append({'tool': 'get_reading_list', 'result_count': len(reading_list)})

    pending_action: dict = {}
    if 'action_add' in intents and user.is_authenticated and not article_scope:
        article_ids = _article_ids_for_action(keyword_hits, chunk_hits, vector_hits)
        if not article_ids and ('keyword' not in intents and 'chunk' not in intents and 'vector' not in intents):
            keyword_hits = keyword_search_articles(query, user, limit=3, request=request)
            article_ids = _article_ids_for_action(keyword_hits, chunk_hits, vector_hits)
        action = propose_add_to_reading_list(user, article_ids, request=request)
        if action:
            pending_action = {
                'action_id': action.pk,
                'action_type': action.action_type,
                'articles': action.payload.get('articles', []),
            }
            tool_trace.append({'tool': 'propose_add_to_reading_list', 'action_id': action.pk})

    if 'action_remove' in intents and user.is_authenticated and not article_scope:
        current_list = get_reading_list(user)
        article_ids = _article_ids_for_action(keyword_hits, chunk_hits, vector_hits)
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
        elif not current_list:
            return AgentReply(
                content='Your reading list is empty — there is nothing to remove.',
                citations=[],
                tool_trace=tool_trace,
            )

    if 'action_comment' in intents and user.is_authenticated:
        if not article_scope and not (keyword_hits or chunk_hits or vector_hits):
            keyword_hits = keyword_search_articles(query, user, limit=3, request=request)
            chunk_hits = search_article_chunks(query, user, limit=3, request=request)
            vector_hits = search_article_vectors(query, user, limit=3, request=request)
        article_id = _article_id_for_comment(
            article_scope, keyword_hits, chunk_hits, vector_hits
        )
        comment_reply = _comment_action_reply(
            query,
            user,
            article_id=article_id,
            keyword_hits=keyword_hits,
            chunk_hits=chunk_hits,
            vector_hits=vector_hits,
            tool_trace=tool_trace,
            citations=_format_citations(keyword_hits, chunk_hits, vector_hits),
            model=model,
            request=request,
        )
        if comment_reply:
            return comment_reply

    citations = _format_citations(keyword_hits, chunk_hits, vector_hits)

    if llm_configured():
        if article_scope:
            system_prompt = (
                'You are a blog reading co-pilot focused on ONE article. '
                'Answer ONLY using passages from the scoped article below. '
                'Do not mention or cite other articles. '
                'Respond in English unless the user writes in another language. '
                'If the user asks for a summary, synthesize the provided passages. '
                'If content is paywalled and passages are preview-only, say so clearly. '
                'If passages are empty, say the article is not indexed yet.'
            )
        else:
            system_prompt = (
                'You are a blog reading co-pilot. Answer ONLY using the provided tool results. '
                'Respond in English unless the user writes in another language. '
                'Cite article titles and include markdown links when URLs are available. '
                'If content is paywalled and the user cannot read the full text, do not leak paid body text. '
                'If tool results are empty, say you cannot find it in the blog corpus. '
                'If a pending reading-list or comment action is present, tell the user to confirm before anything is saved.'
            )
        user_prompt = (
            f'User question: {query}\n\n'
            f'Intents: {sorted(intents)}\n\n'
        )
        if article_scope:
            user_prompt += f'Focused article:\n{article_scope_to_dict(article_scope)}\n\n'
        user_prompt += (
            f'Browsing history:\n{history_to_dicts(history_items)}\n\n'
            f'Keyword hits:\n{hits_to_dicts(keyword_hits)}\n\n'
            f'Chunk hits:\n{chunk_hits_to_dicts(chunk_hits)}\n\n'
            f'Vector hits:\n{vector_hits_to_dicts(vector_hits)}\n\n'
            f'Recommendations:\n{recommend_hits_to_dicts(recommend_hits)}\n\n'
            f'Reading path:\n{reading_path_to_dict(reading_path)}\n\n'
            f'Reading list:\n{reading_list_to_dicts(reading_list)}\n\n'
            f'Pending action:\n{pending_action or None}'
        )
        try:
            content = generate_answer(
                system_prompt,
                user_prompt,
                model=model,
                image_path=image_path,
            )
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
    )
    return AgentReply(
        content=content,
        citations=citations,
        tool_trace=tool_trace,
        pending_action=pending_action,
    )
