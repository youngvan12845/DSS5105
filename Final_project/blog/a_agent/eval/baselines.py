from __future__ import annotations

from django.contrib.auth.models import AnonymousUser, User

from a_agent.models import ArticleChunk
from a_agent.services.embeddings import cosine_similarity, embed_text
from a_agent.services.llm import generate_answer, llm_configured
from a_agent.services.orchestrator import AgentReply, _format_citations
from a_agent.tools.article_scope import scoped_keyword_hit
from a_agent.tools.keyword_search import hits_to_dicts, keyword_search_articles
from a_agent.tools.vector_search import VectorHit, vector_hits_to_dicts

BASELINE_VARIANTS = ('baseline_a', 'baseline_b', 'baseline_c')


def _search_vectors_raw(
    query: str,
    *,
    article_id: int | None = None,
    limit: int = 5,
) -> list[VectorHit]:
    """Baseline C retrieval — no paywall masking or personalization."""

    if not query.strip():
        return []

    query_embedding = embed_text(query)
    chunks_qs = ArticleChunk.objects.exclude(embedding=[]).order_by('article_id', 'chunk_index')
    if article_id is not None:
        chunks_qs = chunks_qs.filter(article_id=article_id)

    scored: list[tuple[float, ArticleChunk]] = []
    if query_embedding:
        for chunk in chunks_qs.iterator():
            if not chunk.embedding:
                continue
            score = cosine_similarity(query_embedding, chunk.embedding)
            if score <= 0:
                continue
            scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)

    hits: list[VectorHit] = []
    seen_articles: set[int] = set()

    if scored:
        for score, chunk in scored:
            if chunk.article_id in seen_articles and len(hits) >= limit:
                continue
            hits.append(
                VectorHit(
                    article_id=chunk.article_id,
                    article_title=chunk.article_title,
                    article_url=chunk.article_url,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content[:500],
                    tags=chunk.tags,
                    is_free=chunk.is_free,
                    can_read_full=True,
                    score=round(score, 4),
                )
            )
            seen_articles.add(chunk.article_id)
            if len(hits) >= limit:
                break
        return hits

    chunks = ArticleChunk.objects.filter(content__icontains=query).order_by('article_id', 'chunk_index')
    if article_id is not None:
        chunks = chunks.filter(article_id=article_id)
    for chunk in chunks[: limit * 2]:
        if chunk.article_id in seen_articles:
            continue
        hits.append(
            VectorHit(
                article_id=chunk.article_id,
                article_title=chunk.article_title,
                article_url=chunk.article_url,
                chunk_index=chunk.chunk_index,
                content=chunk.content[:500],
                tags=chunk.tags,
                is_free=chunk.is_free,
                can_read_full=True,
                score=0.0,
            )
        )
        seen_articles.add(chunk.article_id)
        if len(hits) >= limit:
            break
    return hits


def _llm_from_context(
    *,
    variant: str,
    query: str,
    context_label: str,
    context_payload: str,
    model: str | None,
) -> str:
    if not llm_configured():
        if not context_payload.strip():
            return (
                f'[{variant}] No LLM configured and no retrieval results. '
                'Start Ollama or set OPENAI_API_KEY.'
            )
        return f'[{variant}] Retrieval-only preview (LLM offline):\n\n{context_payload[:1200]}'

    system_prompt = (
        f'You are running as {variant} for evaluation. '
        f'Answer ONLY using the {context_label} below. '
        'Respond in English. Cite article titles when available. '
        'If context is empty, say you cannot find it in the blog.'
    )
    user_prompt = f'User question: {query}\n\n{context_label}:\n{context_payload or "(empty)"}'
    return generate_answer(system_prompt, user_prompt, model=model)


def run_baseline(
    variant: str,
    query: str,
    user: User | AnonymousUser,
    *,
    model: str | None = None,
    article_id: int | None = None,
    request=None,
) -> AgentReply:
    if variant not in BASELINE_VARIANTS:
        raise ValueError(f'Unknown baseline variant: {variant}')

    tool_trace: list[dict] = [{'tool': variant, 'article_id': article_id}]

    if variant == 'baseline_a':
        tool_trace.append({'tool': 'plain_llm', 'retrieval': False})
        content = _llm_from_context(
            variant=variant,
            query=query,
            context_label='Blog corpus',
            context_payload='',
            model=model,
        )
        return AgentReply(content=content, citations=[], tool_trace=tool_trace)

    if variant == 'baseline_b':
        if article_id:
            keyword_hits = scoped_keyword_hit(article_id, query, user, request=request)
        else:
            keyword_hits = keyword_search_articles(query, user, limit=5, request=request)
        tool_trace.append({'tool': 'keyword_search_articles', 'result_count': len(keyword_hits)})
        context_payload = hits_to_dicts(keyword_hits)
        content = _llm_from_context(
            variant=variant,
            query=query,
            context_label='Keyword search hits',
            context_payload=str(context_payload),
            model=model,
        )
        citations = _format_citations(keyword_hits, [], [])
        return AgentReply(content=content, citations=citations, tool_trace=tool_trace)

    vector_hits = _search_vectors_raw(query, article_id=article_id, limit=5)
    tool_trace.append({'tool': 'search_article_vectors_raw', 'result_count': len(vector_hits)})
    context_payload = vector_hits_to_dicts(vector_hits)
    content = _llm_from_context(
        variant=variant,
        query=query,
        context_label='Vector/chunk retrieval hits',
        context_payload=str(context_payload),
        model=model,
    )
    citations = _format_citations([], [], vector_hits)
    return AgentReply(content=content, citations=citations, tool_trace=tool_trace)
