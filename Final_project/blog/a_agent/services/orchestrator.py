from __future__ import annotations

import re
from dataclasses import dataclass, field

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
from a_agent.tools.browsing_history import get_browsing_history, history_to_dicts
from a_agent.tools.chunk_search import _extract_terms_and_phrases, chunk_hits_to_dicts, search_article_chunks
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
    'comment on',
    'comment for',
    '帮我写评论',
    '写一条评论',
    '评论草稿',
    '发表评论',
    '幫我寫評論',
    '寫一條評論',
    '評論草稿',
    '發表評論',
    '幫我留言',
    '寫一則留言',
)


def _classify_intents(query: str) -> set[str]:
    q = query.lower()
    intents: set[str] = set()

    if any(h in q for h in CONTINUE_READING_HINTS):
        intents.add('history')
    if any(h in q for h in RECOMMEND_HINTS):
        intents.add('recommend')
    if any(h in q for h in PATH_HINTS) or ('path' in q and not any(h in q for h in CONTINUE_READING_HINTS)):
        intents.add('path')
    if any(h in q for h in REMOVE_LIST_HINTS) or (('remove' in q or 'delete' in q) and ('reading list' in q or 'from list' in q)):
        intents.add('action_remove')
    elif any(h in q for h in ADD_LIST_HINTS) or (('add' in q or 'save' in q) and ('reading list' in q or 'to list' in q)):
        intents.add('action_add')
    elif any(h in q for h in LIST_QUERY_HINTS):
        intents.add('reading_list')
    if any(h in q for h in COMMENT_HINTS):
        intents.add('action_comment')

    search_triggers = (
        'what', 'which', 'summarize', 'explain', 'cover', 'mention',
        'recommend', 'suggest', 'about', 'related', 'find', 'how', 'why',
        'give', 'progression', 'path', 'docker', 'git', 'rag', 'agent',
        'quiz', 'test', 'question', 'exam', 'pitfall', 'pitfalls', 'excerpt',
    )
    if not intents or any(word in q for word in search_triggers):
        intents.update({'keyword', 'chunk', 'vector'})
    return intents


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


def _extract_ordinal_index(query: str) -> int | None:
    q = query.lower()
    if any(tok in q for tok in ('first', '1st', '第一篇', '第一個', '第一个', '第1篇', '第 1 篇')):
        return 0
    if any(tok in q for tok in ('second', '2nd', '第二篇', '第二個', '第二个', '第2篇', '第 2 篇')):
        return 1
    if any(tok in q for tok in ('third', '3rd', '第三篇', '第三個', '第三个', '第3篇', '第 3 篇')):
        return 2
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

    # 1. Check ordinal references (e.g. "the second one you recommended" / "你剛才推薦的第二篇")
    ordinal_idx = _extract_ordinal_index(query)
    if ordinal_idx is not None:
        if chat_history:
            for msg in reversed(chat_history):
                if getattr(msg, 'role', '') == 'assistant':
                    cites = getattr(msg, 'citations', None) or []
                    if ordinal_idx < len(cites):
                        cid = cites[ordinal_idx].get('article_id')
                        if cid:
                            return [int(cid)]
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

    is_chinese = bool(re.search(r'[\u4e00-\u9fff]', query))
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


def handle_user_message(
    query: str,
    user: User | AnonymousUser,
    *,
    request=None,
    model: str | None = None,
    image_file=None,
    article_id: int | None = None,
    chat_history: list | None = None,
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
            'has_image': bool(image_file),
        }
    )

    history_items = []
    if 'history' in intents or 'recommend' in intents:
        history_items = get_browsing_history(user, limit=5)
        tool_trace.append({'tool': 'get_browsing_history', 'result_count': len(history_items)})

    is_chinese = bool(re.search(r'[\u4e00-\u9fff]', query))
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
            # for an explicit ASCII/English topic term, filter out low-confidence vector hits.
            if vector_hits and not keyword_hits and not chunk_hits:
                terms, _ = _extract_terms_and_phrases(query)
                if terms and not is_chinese:
                    matched_vectors = [
                        vh for vh in vector_hits
                        if vh.score >= 0.65
                        or any(
                            t in vh.article_title.lower() or t in vh.content.lower() or t in (vh.tags or '').lower()
                            for t in terms
                        )
                    ]
                    vector_hits = matched_vectors
                elif terms and is_chinese:
                    # Mixed Chinese + ASCII identifier (e.g. "查找關於 zqxv987 的文章")
                    matched_vectors = [
                        vh for vh in vector_hits
                        if vh.score >= 0.65
                        or any(
                            t in vh.article_title.lower() or t in vh.content.lower() or t in (vh.tags or '').lower()
                            for t in terms
                        )
                    ]
                    vector_hits = matched_vectors
            tool_trace.append({'tool': 'search_article_vectors', 'result_count': len(vector_hits)})

        # Follow-up coreference fallback: if query is a follow-up (e.g. "What about the second one?")
        # and returned no search hits, pull context from the previous assistant message's citations.
        if not (keyword_hits or chunk_hits or vector_hits) and chat_history:
            ord_idx = _extract_ordinal_index(query)
            for msg in reversed(chat_history):
                if getattr(msg, 'role', '') == 'assistant' and getattr(msg, 'citations', None):
                    cites = msg.citations
                    target_cites = [cites[ord_idx]] if (ord_idx is not None and ord_idx < len(cites)) else cites[:2]
                    for c in target_cites:
                        cid = c.get('article_id')
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
        if not current_list:
            return AgentReply(
                content='Your reading list is empty — there is nothing to remove.',
                citations=[],
                tool_trace=tool_trace,
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

    # BUG-07: If not scoped and no tools returned any matches at all, return a clean no-match response with empty citations
    has_any_corpus_match = bool(
        article_scope or keyword_hits or chunk_hits or vector_hits
        or reading_path or history_items or reading_list or recommend_hits or pending_action
    )
    if not has_any_corpus_match:
        no_match_msg = (
            '抱歉，在当前的博客文章库中找不到与此主题相关的文章。请尝试使用其他关键字搜索！'
            if is_chinese
            else 'I cannot find any article about that topic in the blog corpus. Try searching with different keywords.'
        )
        return AgentReply(
            content=no_match_msg,
            citations=[],
            tool_trace=tool_trace,
            pending_action={},
        )

    citations = _format_citations(keyword_hits, chunk_hits, vector_hits, reading_path=reading_path)

    if llm_configured():
        if is_chinese:
            lang_directive = (
                'CRITICAL LANGUAGE RULE: The user asked in Chinese (Traditional or Simplified). '
                'You MUST write your entire response in 100% Simplified Chinese (简体中文). '
                'NEVER use Traditional Chinese characters (e.g., write 术语 not 術語, 通过 not 透過, 网络 not 網路, 代码 not 程式碼, 配置 not 設定, 默认 not 預設).'
            )
        else:
            lang_directive = 'Respond in English unless the user writes in another language.'

        format_directive = (
            '\n\n[CRITICAL FACTUAL INTEGRITY & ACRONYM RULES]:'
            '\n1. NEVER guess, invent, or fabricate the expansion of any acronym (e.g., in this corpus, MCP ALWAYS stands for "Model Context Protocol", A2A stands for "Agent2Agent Protocol", HITL stands for "Human-in-the-Loop").'
            '\n   - NEVER expand MCP as "Multi-Component Platform", "Multi-Cloud Platforms", or "Multi-Capability Platform".'
            '\n   - When asked what an acronym stands for, quote the exact expansion from the provided passages or [Article Section Outline]. If an unknown acronym is not defined in the provided text, state clearly that the provided passages do not define it, and NEVER guess.'
            '\n2. Strictly preserve technical cause-and-effect from the text:'
            '\n   - Distinguish default behavior from optional hardening/configuration rules (e.g., plain nginx `proxy_pass` forwards HTTP `QUERY` fine by default; it is only blocked when an explicit `limit_except` block is added).'
            '\n3. When confirming a reading-list action (`pending_action`), clearly state the exact article title(s) listed in `pending_action.articles` and remind the user to click **Confirm** below.'
            '\n\n[PEDAGOGICAL CO-PILOT STYLE & FORMATTING]:'
            '\n1. Write naturally like a warm, knowledgeable engineering mentor and learning co-pilot — avoid robotic boilerplate headers on every single turn.'
            '\n2. Structure your explanation for effortless reading:'
            '\n   - Start directly with a clear, intuitive answer or concise synthesis.'
            '\n   - Use clean bullet points (`- **Concept**: Explanation`) or numbered steps when breaking down multiple ideas, trade-offs, or architecture.'
            '\n   - End with a brief, relevant takeaway or a natural follow-up learning question when helpful.'
            '\n3. Code & CLI Commands MUST use dedicated markdown formatting:'
            '\n   - Use inline code `backticks` for flags, directives, methods, and short commands (e.g. `git add -A`, `proxy_pass`, `limit_except`).'
            '\n   - Use fenced code blocks ```bash or ```python for multi-line commands, configuration snippets, or code examples.'
            '\n4. NEVER invent `#anchor` links (like `[Topic](#topic)`) or fake URLs. Only use real URLs present in the provided tool results.'
        )

        if article_scope:
            system_prompt = (
                'You are CheeseO, an active blog reading co-pilot and learning path navigator focused on ONE article. '
                'Answer ONLY using passages and prerequisite diagnosis from the scoped article below. '
                'If the user asks whether they can understand this article or asks about prerequisites, reference the provided prerequisite diagnosis. '
                'If the user is an experienced or senior reader, provide architectural insights and production pitfalls instead of basic definitions. '
                'Do not mention or cite other articles unless discussing prerequisites. '
                f'{lang_directive} '
                'If the user requests a quiz, comprehension test, or "Quiz Me" / "考考我": '
                'generate 2 to 3 interactive multiple-choice or scenario questions based directly on the core technical concepts and tradeoffs in this article. '
                'Format each question cleanly with options A), B), C), D), and invite the user to reply with their chosen answers before revealing the solutions. '
                'When the user replies with their answers, evaluate them warmly with constructive explanations. '
                'If the user quotes or highlights an excerpt from the article, explain that specific excerpt directly with deep technical context. '
                'If the user asks for a summary, synthesize the provided passages. '
                'If content is paywalled and passages are preview-only, say so clearly. '
                'If passages are empty, say the article is not indexed yet.'
                f'{format_directive}'
            )
        else:
            system_prompt = (
                'You are CheeseO, a blog reading co-pilot and learning path navigator. Answer questions accurately and directly using ONLY the provided tool results. '
                'For factual and conceptual questions, state the technical definitions, core mechanisms, and key facts clearly before suggesting reading paths. '
                'When finding or recommending articles on a specific topic, prioritize the Search results (Keyword hits, Chunk passages, Vector hits), and summarize how each article addresses the topic. '
                'When reading path or recommendations are provided, present the structured steps and their notes clearly. '
                f'{lang_directive} '
                'Cite article titles and include markdown links when URLs are available. '
                'If content is paywalled and the user cannot read the full text, do not leak paid body text. '
                'If the user asks about an article or topic not found in the blog corpus (or tool results are empty), refuse clearly by stating: "I cannot find any article about that in the blog corpus." '
                'If a pending reading-list or comment action is present, tell the user to confirm before anything is saved.'
                f'{format_directive}'
            )
        user_prompt = (
            f'User question: {query}\n\n'
            f'Intents: {sorted(intents)}\n\n'
        )
        if is_chinese:
            user_prompt = f'[Language Instruction: The user query is in Chinese (Traditional or Simplified). You MUST answer entirely in Simplified Chinese (简体中文).]\n\n' + user_prompt
        if chat_history:
            user_prompt += f'Recent conversation history (use this to resolve follow-up references like "the second concept" or "the second article you recommended"):\n{_format_chat_history(chat_history)}\n\n'
        if article_scope:
            user_prompt += f'Focused article:\n{article_scope_to_dict(article_scope)}\n\n'
            if article_scope.slug:
                from a_agent.services.navigator import calculate_article_readiness
                session_mastered = request.session.get('mastered_prereqs', []) if request and hasattr(request, 'session') else []
                readiness_diag = calculate_article_readiness(user, article_scope.slug, session_mastered=session_mastered)
                tool_trace.append({'tool': 'calculate_article_readiness', 'status': readiness_diag.get('status'), 'score': readiness_diag.get('score')})
                user_prompt += f'Prerequisite diagnosis & readiness:\n{readiness_diag}\n\n'
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
        if is_chinese:
            user_prompt += '\n\n[Final Reminder: Regardless of whether the user wrote in Traditional or Simplified Chinese, you MUST write your entire response in Simplified Chinese (简体中文).]'
        try:
            content = generate_answer(
                system_prompt,
                user_prompt,
                model=model,
                image_file=image_file,
            )
            content = _sanitize_markdown_output(content)
            if is_chinese:
                content = _ensure_simplified_chinese(content)
            if _is_no_match_response(content) and not pending_action:
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

    tool_trace.append({'tool': 'response_mode', 'mode': 'fallback'})
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
    content = _sanitize_markdown_output(content)
    if is_chinese:
        content = _ensure_simplified_chinese(content)
    if _is_no_match_response(content) and not pending_action:
        citations = []
    return AgentReply(
        content=content,
        citations=citations,
        tool_trace=tool_trace,
        pending_action=pending_action,
    )
