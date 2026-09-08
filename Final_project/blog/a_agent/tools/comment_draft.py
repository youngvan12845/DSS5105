from __future__ import annotations

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

    if llm_configured():
        system_prompt = (
            'You write short, thoughtful blog comments (2-4 sentences). '
            'Sound natural and specific to the article. '
            'No markdown, no hashtags, no greeting like "Dear author". '
            'Match the language the user used in their request.'
        )
        user_prompt = (
            f'User request: {query}\n\n'
            f'Article title: {article.title}\n'
            f'Article intro: {article.intro or ""}\n'
            f'Relevant excerpt:\n{context_block}\n\n'
            'Write the comment text only.'
        )
        try:
            draft = generate_answer(system_prompt, user_prompt, model=model).strip()
            if draft:
                return draft[:2000]
        except Exception:
            pass

    if excerpt:
        return (
            f'I really enjoyed "{article.title}". '
            f'The part about {excerpt[:120].strip()}… was especially helpful. Thanks for sharing!'
        )
    return (
        f'Thanks for publishing "{article.title}" — clear and useful. '
        'Looking forward to more posts on this topic.'
    )
