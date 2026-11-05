from __future__ import annotations

import re

from django.contrib.auth.models import User

from a_agent.models import AgentActionLog
from a_agent.services.llm import generate_answer, llm_configured
from a_blog.models import ArticlePage, Comment

from .access import get_article_access


def propose_post_comment(
    user: User,
    article_id: int,
    draft_content: str,
    *,
    request=None,
) -> AgentActionLog | None:
    draft_content = draft_content.strip()
    if not draft_content:
        return None

    article = ArticlePage.objects.filter(pk=article_id).live().first()
    if article is None:
        return None

    access = get_article_access(user, article, request=request)
    return AgentActionLog.objects.create(
        user=user,
        action_type='post_comment',
        payload={
            'article_id': article.pk,
            'article_title': article.title,
            'article_url': access.url,
            'draft_content': draft_content[:2000],
        },
        confirmed=False,
        executed=False,
    )


def execute_post_comment(action: AgentActionLog) -> Comment:
    if action.action_type != 'post_comment':
        raise ValueError('Unsupported action type')

    payload = action.payload
    article = ArticlePage.objects.get(pk=payload['article_id'])
    content = payload.get('draft_content', '').strip()
    if not content:
        raise ValueError('Comment draft is empty')

    return Comment.objects.create(
        article=article,
        author=action.user,
        content=content,
    )


def _excerpt_from_hits(chunk_hits, vector_hits, keyword_hits, limit: int = 400) -> str:
    for hits in (vector_hits, chunk_hits):
        for hit in hits[:2]:
            text = getattr(hit, 'content', '') or getattr(hit, 'snippet', '')
            if text:
                return text[:limit]
    for hit in keyword_hits[:1]:
        text = getattr(hit, 'snippet', '') or getattr(hit, 'intro', '')
        if text:
            return text[:limit]
    return ''


_META_REFUSAL_PATTERNS = (
    'mix-up',
    'could you clarify',
    'you meant to ask',
    'as an ai',
    'i am an ai',
    'this article focuses on',
    'does not mention',
    'not covered in this article',
)


def _extract_comment_intent(query: str) -> str:
    """Extract the specific question or topic the user wants to express in their comment."""
    cleaned = re.sub(
        r'^(?:please\s+|can you\s+|could you\s+|help me(?:\s+to)?\s+)*'
        r'(?:draft|write|post|leave)\s+a\s+comment\s*'
        r'(?:on\s+this\s+article\s*)?(?:to\s+ask|asking|about|saying|that)?\s*',
        '',
        query.strip(),
        flags=re.IGNORECASE,
    ).strip()
    return cleaned or query.strip()


def build_comment_draft(
    query: str,
    article_id: int,
    *,
    chunk_hits,
    vector_hits,
    keyword_hits,
    model: str | None = None,
) -> str | None:
    article = ArticlePage.objects.filter(pk=article_id).live().first()
    if article is None:
        return None

    excerpt = _excerpt_from_hits(chunk_hits, vector_hits, keyword_hits)
    context_block = excerpt or (article.intro or article.title)
    user_intent = _extract_comment_intent(query)

    if llm_configured():
        is_chinese = bool(re.search(r'[\u4e00-\u9fff]', query))
        lang_rule = (
            '4. Write the comment in Simplified Chinese (简体中文). Regardless of whether the user wrote in Traditional or Simplified Chinese, always output Simplified Chinese.'
            if is_chinese
            else '4. Write the comment in English (unless the user explicitly requested another language).'
        )
        system_prompt = (
            'You are ghostwriting a public reader comment (2-3 sentences) to be posted in the comment section of a blog article. '
            'Write strictly from the reader\'s first-person perspective ("I"). '
            'CRITICAL RULES:\n'
            '1. Output ONLY the ready-to-post comment text itself. No quotes around it, no markdown, no hashtags, no "Dear author".\n'
            '2. NEVER talk back to the user, NEVER ask the user for clarification, and NEVER say "It seems there might be a mix-up" or "This article focuses on X instead of Y".\n'
            '3. If the user wants to ask a question in the comment (even about a tangential or beginner concept like "what is API" on a Git article), '
            'briefly thank the author for the article and naturally ask that exact question to the author/community in first person.\n'
            f'{lang_rule}'
        )
        user_prompt = (
            f'Article being commented on: "{article.title}"\n'
            f'Article summary: {article.intro or ""}\n'
            f'Relevant excerpt:\n{context_block}\n\n'
            f'What the reader wants to say or ask in their comment: {user_intent}\n'
            f'Original command: {query}\n\n'
            'Write the reader\'s comment text now (first-person reader voice, ready to post):'
        )
        try:
            draft = generate_answer(system_prompt, user_prompt, model=model).strip().strip('"').strip("'")
            if draft and not any(pat in draft.lower() for pat in _META_REFUSAL_PATTERNS):
                return draft[:2000]
        except Exception:
            pass

    if user_intent and user_intent.lower() != query.lower():
        return (
            f'Thanks for sharing "{article.title}"! '
            f'I found this really helpful, and I was also wondering: {user_intent.rstrip("?")}? '
            'Would love to hear your thoughts!'
        )

    if excerpt:
        return (
            f'I really enjoyed "{article.title}". '
            f'The part about {excerpt[:120].strip()}… was especially helpful. Thanks for sharing!'
        )
    return (
        f'Thanks for publishing "{article.title}" — clear and useful. '
        'Looking forward to more posts on this topic.'
    )
