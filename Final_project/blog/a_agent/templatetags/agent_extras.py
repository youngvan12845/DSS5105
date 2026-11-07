import re
from urllib.parse import unquote, urlparse

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

from a_agent.tools.browsing_history import article_link

register = template.Library()


@register.filter(name='same_site_url')
def same_site_url(url: str) -> str:
    return article_link(url or '')


@register.filter(name='agent_markdown')
def agent_markdown(value: str) -> str:
    """Render structured markdown used by the agent (code blocks, inline code, bold, links, lists)."""
    if not value:
        return ''

    text = article_link_in_text(value)

    ext_cites = []

    def save_ext_cite(match):
        number, url = match.group(1), match.group(2)
        if not url.startswith(('http://', 'https://')):
            return match.group(0)
        host = (urlparse(url).hostname or '').removeprefix('www.')
        title = unquote(match.group(3) or '').strip() or host
        site = unquote(match.group(4) or '').strip() or host
        excerpt = unquote(match.group(5) or '').strip()
        token = f'___EXT_CITE_{len(ext_cites)}___'
        ext_cites.append(
            f'<a href="{escape(url)}" target="_blank" rel="noopener noreferrer" class="ext-cite"'
            f' data-ext-title="{escape(title)}" data-ext-site="{escape(site)}" data-ext-excerpt="{escape(excerpt)}">'
            f'{escape(number)}</a>'
        )
        return token

    text = re.sub(
        r'\{\{cite:(\d+):(https?://[^}|]+)(?:\|([^|]*)\|([^|]*)\|([^}]*))?\}\}',
        save_ext_cite,
        text,
    )

    # 1. Protect fenced code blocks ```lang\ncode\n```
    code_blocks = []
    def save_code_block(match):
        lang = match.group(1) or ''
        code = match.group(2)
        escaped_code = escape(code.strip())
        placeholder = f'___CODE_BLOCK_{len(code_blocks)}___'
        lang_badge = f'<div class="px-3 py-1 bg-slate-800 text-slate-400 text-xs font-mono border-b border-slate-700">{escape(lang)}</div>' if lang else ''
        code_blocks.append(
            f'<div class="my-3 rounded-lg overflow-hidden border border-slate-700 bg-slate-900 text-slate-100 shadow-sm">'
            f'{lang_badge}'
            f'<pre class="p-3 overflow-x-auto text-xs font-mono leading-relaxed"><code>{escaped_code}</code></pre>'
            f'</div>'
        )
        return placeholder

    text = re.sub(r'```([a-zA-Z0-9_-]*)\n?(.*?)```', save_code_block, text, flags=re.DOTALL)

    # 2. Protect inline code `code`
    inline_codes = []
    def save_inline_code(match):
        code = match.group(1)
        escaped_code = escape(code)
        placeholder = f'___INLINE_CODE_{len(inline_codes)}___'
        inline_codes.append(
            f'<code class="px-1.5 py-0.5 mx-0.5 text-xs font-mono font-semibold text-purple-700 bg-purple-50 border border-purple-200 rounded">{escaped_code}</code>'
        )
        return placeholder

    text = re.sub(r'`([^`\n]+)`', save_inline_code, text)

    # 3. Escape normal HTML
    text = escape(text)

    # 4. Bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)

    # 5. Markdown Links [text](url) -> open in same tab
    text = re.sub(
        r'\[([^\]]+)\]\(([^)]+)\)',
        r'<a href="\2" class="text-purple-600 font-medium hover:underline">\1</a>',
        text,
    )

    # 6. Bullet lists and Interactive Quiz Options
    has_quiz_options = bool(re.search(r'(?:^|\n)\s*[A-D][\)\.\:]\s+', text))
    lines = text.split('\n')
    processed_lines = []
    current_q_num = '1'

    for line in lines:
        stripped = line.strip()
        q_match = re.match(r'^(?:###\s*)?(?:Question\s*)?(\d+)[\.\:]\s*(.+)$', stripped, re.IGNORECASE)
        opt_match = re.match(r'^\s*([A-D])[\)\.\:]\s+(.+)$', stripped, re.IGNORECASE)

        if (
            has_quiz_options
            and q_match
            and not opt_match
            and not q_match.group(2).strip().startswith('<a ')
            and ('?' in stripped or '？' in stripped or any(kw in stripped.lower() for kw in ('question', 'which', 'what', 'how', 'why', 'who', 'where', 'when', '第', '题', '題')))
        ):
            current_q_num = q_match.group(1)
            q_text = q_match.group(2).strip()
            processed_lines.append(
                f'<div class="quiz-question-header mt-4 mb-2 font-bold text-slate-900 flex items-start gap-2">'
                f'<span class="px-2 py-0.5 rounded-md bg-purple-100 text-purple-700 text-xs font-mono shrink-0">Q{current_q_num}</span>'
                f'<span>{q_text}</span>'
                f'</div>'
            )
        elif opt_match:
            letter = opt_match.group(1).upper()
            opt_content = opt_match.group(2).strip()
            btn_html = (
                f'<button type="button" class="quiz-option-btn group w-full text-left my-1.5 p-3 rounded-xl border border-slate-200 bg-white hover:border-purple-400 hover:bg-purple-50/50 shadow-sm transition-all duration-150 flex items-center justify-between gap-3 cursor-pointer" data-question="{current_q_num}" data-letter="{letter}">'
                f'<div class="flex items-center gap-3 min-w-0">'
                f'<span class="quiz-option-badge w-6 h-6 rounded-md bg-slate-100 text-slate-700 font-bold text-xs flex items-center justify-center shrink-0 group-hover:bg-purple-600 group-hover:text-white transition-colors">{letter}</span>'
                f'<span class="quiz-option-text text-sm text-slate-800 font-medium leading-snug">{opt_content}</span>'
                f'</div>'
                f'<span class="quiz-option-check w-4 h-4 rounded-full border border-slate-300 flex items-center justify-center text-[10px] text-transparent shrink-0 transition-colors">✓</span>'
                f'</button>'
            )
            processed_lines.append(btn_html)
        elif stripped.startswith(('• ', '- ', '* ')):
            bullet_content = stripped[2:].strip()
            processed_lines.append(f'<div class="agent-bullet-item flex items-start gap-2 my-1"><span class="text-purple-500 font-bold shrink-0">•</span><span>{bullet_content}</span></div>')
        else:
            processed_lines.append(line)

    text = '<br>'.join(processed_lines)
    # Clean up excess br tags around quiz elements and bullet items
    text = re.sub(r'<br>(<div class="quiz-question-header|<button type="button" class="quiz-option-btn|<div class="agent-bullet-item)', r'\1', text)
    text = re.sub(r'(</button>|</div>)<br>(<button type="button" class="quiz-option-btn|<div class="agent-bullet-item)', r'\1\2', text)
    text = re.sub(r'(<div class="agent-bullet-item.*?</div>)<br>', r'\1', text)
    # Collapse multiple consecutive <br>
    text = re.sub(r'(<br>\s*){3,}', '<br><br>', text)

    # 7. Restore inline code and code blocks
    for i, code_html in enumerate(inline_codes):
        text = text.replace(f'___INLINE_CODE_{i}___', code_html)
    for i, block_html in enumerate(code_blocks):
        text = text.replace(f'<br>___CODE_BLOCK_{i}___', f'___CODE_BLOCK_{i}___')
        text = text.replace(f'___CODE_BLOCK_{i}___<br>', f'___CODE_BLOCK_{i}___')
        text = text.replace(f'___CODE_BLOCK_{i}___', block_html)
    for index, cite_html in enumerate(ext_cites):
        text = text.replace(f'___EXT_CITE_{index}___', cite_html)

    return mark_safe(text)


def article_link_in_text(value: str) -> str:
    """Turn stored testserver links into paths before markdown is rendered."""
    parsed_hosts = ('http://testserver', 'https://testserver')
    for host in parsed_hosts:
        value = value.replace(host, '')
    return value


@register.filter(name='looks_chinese')
def looks_chinese(value: str) -> bool:
    return bool(re.search(r'[\u4e00-\u9fff]', value or ''))


@register.filter(name='session_title')
def session_title(value: str) -> str:
    """Hide the decorative document prefix and legacy id in displayed titles only."""
    if not value:
        return ''
    return re.sub(r'^\s*📄\s*(?:\[\d+\]\s*)?', '', value)
