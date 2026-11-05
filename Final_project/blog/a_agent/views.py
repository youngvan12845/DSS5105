from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from a_blog.models import ArticlePage

from .config import OLLAMA_MODEL_OPTIONS, get_model_options, normalize_model
from .models import AgentActionLog, ChatMessage, ChatSession, ReadingListItem
from .tools.comment_draft import execute_post_comment
from .tools.reading_list import (
    execute_add_to_reading_list,
    execute_remove_from_reading_list,
    get_reading_list,
)
from .services.proactive import ensure_session_continue_nudge
from .services.learning_analysis import (
    BRIDGE_UNAVAILABLE,
    allowed_source,
    article_version,
    bridge_cache_key,
    cached_bridge_summary,
    display_analysis,
    explain_concept,
    save_bridge_summary,
)
from .services.article_text import html_to_text
from .services.llm import generate_answer, get_llm_info
from .services.panel_status import build_panel_status, describe_readiness
from .services.orchestrator import handle_user_message
from .tools.access import can_user_read_full
from .tools.article_scope import get_article_scope
from .tools.browsing_history import get_browsing_history
from .services.navigator import (
    calculate_article_readiness,
    get_concept_bridge,
    get_prerequisites_graph,
    mark_prerequisite_mastered,
)


def _article_urls(request) -> dict[str, str]:
    urls = {}
    for page in ArticlePage.objects.live():
        url = page.get_url(request=request) or ''
        if url:
            urls[page.slug] = url
    return urls


def _with_article_urls(items, urls: dict[str, str]) -> list[dict]:
    attached = []
    for item in items or []:
        row = dict(item)
        row['url'] = urls.get(row.get('slug') or '', '')
        attached.append(row)
    return attached


def _described_readiness(request, article):
    session_mastered = request.session.get('mastered_prereqs', [])
    readiness = calculate_article_readiness(
        request.user,
        article.slug,
        session_mastered=session_mastered,
    )
    live_titles = dict(ArticlePage.objects.live().values_list('slug', 'title'))
    analysis, matches = display_analysis(article, live_titles=live_titles)
    described = describe_readiness(readiness, article.slug, analysis=analysis)
    urls = _article_urls(request)
    described['concept_matches'] = _with_article_urls(matches, urls)
    described['gaps'] = _with_article_urls(described.get('gaps'), urls)
    return described, analysis, matches


def _ai_concept_bridge(request, prereq_slug: str, concept: str) -> dict:
    article = ArticlePage.objects.live().filter(slug=prereq_slug).first()
    if article is None:
        return {'slug': '', 'bridge_summary': BRIDGE_UNAVAILABLE, 'show_link': False}
    can_read, _reason = can_user_read_full(request.user, article, request=request)
    source, tier = allowed_source(
        article.title or '',
        article.intro or '',
        html_to_text(str(article.body or '')),
        can_read_full=can_read,
    )
    key = bridge_cache_key(article.slug, article_version(article), concept, tier)
    summary = cached_bridge_summary(key)
    if not summary:
        summary = explain_concept(concept, source, generate=generate_answer)
        if summary:
            save_bridge_summary(key, summary, tier)
    return {
        'slug': article.slug,
        'title': article.title,
        'url': article.get_url(request=request) or '',
        'bridge_summary': summary or BRIDGE_UNAVAILABLE,
        'show_link': True,
    }


def _parse_article_id(value) -> int | None:
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _get_or_create_article_session(user, article: ArticlePage) -> ChatSession:
    title = f'📄 {article.title[:70]}'
    legacy_title = f'📄 [{article.pk}] {article.title[:70]}'
    session = (
        ChatSession.objects.filter(user=user, title=title).first()
        or ChatSession.objects.filter(user=user, title=legacy_title).first()
    )
    if session is None:
        session = ChatSession.objects.create(user=user, title=title)
    elif session.title != title:
        session.title = title
        session.save(update_fields=['title', 'updated_at'])
    return session


def _session_model(session: ChatSession) -> str:
    return normalize_model(session.llm_model or None)


@login_required
def chat_view(
    request: HttpRequest,
    session_id: int | None = None,
    article_id: int | None = None,
) -> HttpResponse:
    sessions = ChatSession.objects.filter(user=request.user)[:20]
    scoped_article_id = article_id or _parse_article_id(request.GET.get('article'))

    if session_id:
        session = get_object_or_404(ChatSession, pk=session_id, user=request.user)
    elif scoped_article_id:
        article = get_object_or_404(ArticlePage.objects.live(), pk=scoped_article_id)
        session = _get_or_create_article_session(request.user, article)
    else:
        existing_empty = (
            ChatSession.objects.filter(user=request.user, title='New chat')
            .exclude(messages__role=ChatMessage.ROLE_USER)
            .first()
        )
        if existing_empty:
            session = existing_empty
        else:
            session = ChatSession.objects.create(user=request.user, title='New chat')
        sessions = ChatSession.objects.filter(user=request.user)[:20]

    if not scoped_article_id:
        ensure_session_continue_nudge(session, request.user, request=request)

    selected_model = _session_model(session)
    chat_messages = session.messages.all()
    history_items = get_browsing_history(request.user, limit=3)
    article_scope = (
        get_article_scope(scoped_article_id, request.user, request=request)
        if scoped_article_id
        else None
    )
    return render(
        request,
        'a_agent/chat.html',
        {
            'session': session,
            'sessions': sessions,
            'chat_messages': chat_messages,
            'llm_info': get_llm_info(selected_model),
            'model_options': get_model_options(),
            'selected_model': selected_model,
            'continue_reading': history_items[0] if history_items else None,
            'recent_history': history_items,
            'article_scope': article_scope,
            'scoped_article_id': scoped_article_id,
        },
    )


@login_required
def new_session_view(request: HttpRequest) -> HttpResponse:
    existing_empty = (
        ChatSession.objects.filter(user=request.user, title='New chat')
        .exclude(messages__role=ChatMessage.ROLE_USER)
        .first()
    )
    if existing_empty:
        existing_empty.messages.all().delete()
        return redirect('a_agent:chat_session', session_id=existing_empty.pk)
    session = ChatSession.objects.create(user=request.user, title='New chat')
    return redirect('a_agent:chat_session', session_id=session.pk)


@login_required
@require_POST
def clear_all_sessions_view(request: HttpRequest) -> HttpResponse:
    ChatSession.objects.filter(user=request.user).delete()
    return redirect('a_agent:chat')


@login_required
@require_POST
def reset_article_session_view(request: HttpRequest, article_id: int) -> HttpResponse:
    article = get_object_or_404(ArticlePage.objects.live(), pk=article_id)
    session = _get_or_create_article_session(request.user, article)
    session.messages.all().delete()
    if request.htmx:
        return article_panel_view(request, article_id)
    return redirect(article.get_url(request=request) or 'a_agent:chat_article', article_id=article_id)


@login_required
def article_quiz_view(request: HttpRequest, article_id: int) -> HttpResponse:
    article = get_object_or_404(ArticlePage.objects.live(), pk=article_id)
    title = f'🎯 Quiz: {article.title[:65]}'

    if request.GET.get('reset') == '1':
        ChatSession.objects.filter(user=request.user, title=title).delete()
        return redirect('a_agent:article_quiz', article_id=article_id)

    session = ChatSession.objects.filter(user=request.user, title=title).first()
    if not session:
        session = ChatSession.objects.create(user=request.user, title=title)
        quiz_prompt = (
            "🎯 Quiz Me: Please generate 2 to 3 conceptual check questions with options (A, B, C, D) "
            "based on the core technical concepts and trade-offs in this article to test my understanding."
        )
        ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_USER,
            content=quiz_prompt,
        )
        selected_model = _session_model(session)
        reply = handle_user_message(
            quiz_prompt,
            request.user,
            request=request,
            model=selected_model,
            article_id=article.id,
        )
        ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            content=reply.content,
            citations=reply.citations,
            tool_trace=reply.tool_trace,
            pending_action=reply.pending_action or {},
        )

    selected_model = _session_model(session)
    chat_messages = session.messages.all()
    article_scope = get_article_scope(article_id, request.user, request=request)
    llm_info = get_llm_info(selected_model)

    return render(
        request,
        'a_agent/quiz.html',
        {
            'article': article,
            'session': session,
            'chat_messages': chat_messages,
            'selected_model': selected_model,
            'model_options': get_model_options(),
            'llm_info': llm_info,
            'article_scope': article_scope,
        },
    )


@login_required
@require_POST
def delete_session_view(request: HttpRequest, session_id: int) -> HttpResponse:
    session = get_object_or_404(ChatSession, pk=session_id, user=request.user)
    session.delete()
    return redirect('a_agent:chat')


@login_required
@require_POST
def send_message_view(request: HttpRequest, session_id: int) -> HttpResponse:
    session = get_object_or_404(ChatSession, pk=session_id, user=request.user)
    content = request.POST.get('content', '').strip()
    image_file = request.FILES.get('image')
    selected_model = normalize_model(request.POST.get('llm_model') or session.llm_model or None)

    if session.llm_model != selected_model:
        session.llm_model = selected_model
        session.save(update_fields=['llm_model', 'updated_at'])

    if not content and not image_file:
        return render(
            request,
            'a_agent/partials/error.html',
            {'error': 'Please enter a question or attach an image'},
            status=400,
        )

    if not content and image_file:
        content = '[Image attached]'

    prior_messages = list(session.messages.order_by('-created_at')[:6])[::-1]

    user_message = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.ROLE_USER,
        content=content,
        image=image_file,
    )

    article_id = _parse_article_id(request.POST.get('article_id'))
    reply = handle_user_message(
        content,
        request.user,
        request=request,
        model=selected_model,
        image_file=user_message.image or None,
        article_id=article_id,
        chat_history=prior_messages,
    )
    assistant_message = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.ROLE_ASSISTANT,
        content=reply.content,
        citations=reply.citations,
        tool_trace=reply.tool_trace,
        pending_action=reply.pending_action or {},
    )

    if session.title in ('New chat', 'Reading Assistant') and len(content) <= 40:
        session.title = content[:40]
        session.save(update_fields=['title', 'updated_at'])
    else:
        session.save(update_fields=['updated_at'])

    if request.htmx:
        return render(
            request,
            'a_agent/partials/assistant_message.html',
            {'assistant_message': assistant_message},
        )

    return redirect('a_agent:chat_session', session_id=session.pk)


@login_required
@require_POST
def confirm_action_view(request: HttpRequest, action_id: int) -> HttpResponse:
    action = get_object_or_404(
        AgentActionLog,
        pk=action_id,
        user=request.user,
        executed=False,
    )
    if action.confirmed:
        return render(
            request,
            'a_agent/partials/error.html',
            {'error': 'This action was already confirmed.'},
            status=400,
        )

    context = {'action': action}

    if action.action_type == 'add_to_reading_list':
        created = execute_add_to_reading_list(action)
        context['created_count'] = len(created)
    elif action.action_type == 'remove_from_reading_list':
        context['removed_count'] = execute_remove_from_reading_list(action)
    elif action.action_type == 'post_comment':
        edited_draft = request.POST.get('draft_content', '').strip()
        if edited_draft:
            payload = dict(action.payload or {})
            payload['draft_content'] = edited_draft[:2000]
            action.payload = payload
            action.save(update_fields=['payload'])
        comment = execute_post_comment(action)
        context['comment'] = comment
    else:
        return render(
            request,
            'a_agent/partials/error.html',
            {'error': f'Unsupported action type: {action.action_type}'},
            status=400,
        )

    action.confirmed = True
    action.executed = True
    action.save(update_fields=['confirmed', 'executed'])

    ChatMessage.objects.filter(
        pending_action__action_id=action.pk,
    ).update(pending_action={})

    return render(
        request,
        'a_agent/partials/action_confirmed.html',
        context,
    )


@login_required
@require_POST
def cancel_action_view(request: HttpRequest, action_id: int) -> HttpResponse:
    action = get_object_or_404(
        AgentActionLog,
        pk=action_id,
        user=request.user,
        executed=False,
    )
    if action.confirmed:
        return render(
            request,
            'a_agent/partials/error.html',
            {'error': 'This action was already confirmed.'},
            status=400,
        )

    action.delete()
    ChatMessage.objects.filter(
        pending_action__action_id=action_id,
    ).update(pending_action={})

    return render(
        request,
        'a_agent/partials/action_cancelled.html',
        {},
    )


def _get_suggested_prompts(article) -> list[dict]:
    return [
        {
            'label': '🎯 Quiz Me',
            'prompt': '🎯 Quiz Me: Generate 2-3 conceptual check questions with options (A, B, C, D) based on this article to test my understanding.',
        },
        {
            'label': '💡 Key Takeaways',
            'prompt': 'What are the core technical principles and key takeaways from this article?',
        },
        {
            'label': '⚠️ Pitfalls',
            'prompt': 'What are common mistakes, pitfalls, or production edge cases related to the concepts in this article?',
        },
        {
            'label': '🔍 Deep Dive',
            'prompt': 'Could you break down the code implementation or architecture explained in this article step by step?',
        },
        {
            'label': '📝 Summary',
            'prompt': 'Please summarize this article in 3 clear, actionable bullet points.',
        },
    ]


@login_required
def article_panel_view(request: HttpRequest, article_id: int) -> HttpResponse:
    article = get_object_or_404(ArticlePage.objects.live(), pk=article_id)
    session = _get_or_create_article_session(request.user, article)
    selected_model = _session_model(session)
    chat_messages = session.messages.all()[:20]
    article_scope = get_article_scope(article_id, request.user, request=request)
    readiness, _analysis, _matches = _described_readiness(request, article)
    llm_info = get_llm_info(selected_model)
    panel_status = build_panel_status(request.user, article_scope, llm_info)
    return render(
        request,
        'a_agent/partials/article_panel.html',
        {
            'session': session,
            'article': article,
            'article_scope': article_scope,
            'chat_messages': chat_messages,
            'llm_info': llm_info,
            'panel_status': panel_status,
            'model_options': get_model_options(),
            'selected_model': selected_model,
            'readiness': readiness,
            'suggested_prompts': _get_suggested_prompts(article),
        },
    )


def concept_bridge_view(request: HttpRequest, prereq_slug: str) -> HttpResponse:
    concept = request.GET.get('concept', '').strip()
    if concept:
        bridge = _ai_concept_bridge(request, prereq_slug, concept)
    else:
        bridge = get_concept_bridge(prereq_slug)
        if bridge:
            bridge = dict(bridge)
            bridge['url'] = _article_urls(request).get(prereq_slug, '')
            bridge['show_link'] = bool(bridge['url'])
    if not bridge:
        return HttpResponse(
            f"<div class='mt-2 p-2 rounded bg-rose-50 border border-rose-200 text-rose-700 text-[11px]'>No concept bridge found for '{prereq_slug}'.</div>"
        )
    return render(request, 'a_agent/partials/concept_bridge_card.html', {'bridge': bridge})


@require_POST
def master_prerequisite_view(request: HttpRequest) -> HttpResponse:
    article_slug = request.POST.get('article_slug', '').strip()
    prereq_slug = request.POST.get('prereq_slug', '').strip()
    mark_all = request.POST.get('mark_all') == 'true'

    article = get_object_or_404(ArticlePage.objects.live(), slug=article_slug)
    _readiness, analysis, matches = _described_readiness(request, article)

    if mark_all:
        if analysis and analysis.get('status') == 'ready':
            for item in matches:
                mark_prerequisite_mastered(request.session, item['slug'])
        else:
            graph = get_prerequisites_graph()
            meta = graph.get(article_slug, {})
            for p in meta.get('prerequisites', []):
                mark_prerequisite_mastered(request.session, p['slug'])
    elif prereq_slug:
        mark_prerequisite_mastered(request.session, prereq_slug)

    readiness, _analysis, _matches = _described_readiness(request, article)
    return render(
        request,
        'a_agent/partials/readiness_panel.html',
        {
            'readiness': readiness,
            'article': article,
        }
    )


@login_required
@require_POST
def article_send_message_view(request: HttpRequest, article_id: int) -> HttpResponse:
    article = get_object_or_404(ArticlePage.objects.live(), pk=article_id)
    session = _get_or_create_article_session(request.user, article)
    content = request.POST.get('content', '').strip()
    image_file = request.FILES.get('image')
    selected_model = normalize_model(request.POST.get('llm_model') or session.llm_model or None)

    if session.llm_model != selected_model:
        session.llm_model = selected_model
        session.save(update_fields=['llm_model', 'updated_at'])

    if not content and not image_file:
        return render(
            request,
            'a_agent/partials/error.html',
            {'error': 'Please enter a question or attach an image'},
            status=400,
        )

    if not content and image_file:
        content = '[Image attached]'

    prior_messages = list(session.messages.order_by('-created_at')[:6])[::-1]

    user_message = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.ROLE_USER,
        content=content,
        image=image_file,
    )
    reply = handle_user_message(
        content,
        request.user,
        request=request,
        model=selected_model,
        image_file=user_message.image or None,
        article_id=article_id,
        chat_history=prior_messages,
    )
    assistant_message = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.ROLE_ASSISTANT,
        content=reply.content,
        citations=reply.citations,
        tool_trace=reply.tool_trace,
        pending_action=reply.pending_action or {},
    )
    session.save(update_fields=['updated_at'])

    if request.htmx:
        return render(
            request,
            'a_agent/partials/article_message_pair.html',
            {
                'user_message': user_message,
                'assistant_message': assistant_message,
                'panel_status': build_panel_status(
                    request.user,
                    get_article_scope(article_id, request.user, request=request),
                    get_llm_info(selected_model),
                    tool_trace=reply.tool_trace,
                ),
            },
        )

    return redirect('a_agent:chat_article', article_id=article_id)


@login_required
def reading_list_view(request: HttpRequest) -> HttpResponse:
    items = get_reading_list(request.user, limit=200)
    return render(
        request,
        'a_agent/reading_list.html',
        {
            'items': items,
            'total': len(items),
        },
    )


@login_required
@require_POST
def remove_reading_list_item_view(request: HttpRequest, article_id: int) -> HttpResponse:
    ReadingListItem.objects.filter(user=request.user, article_id=article_id).delete()
    return redirect('a_agent:reading_list')
