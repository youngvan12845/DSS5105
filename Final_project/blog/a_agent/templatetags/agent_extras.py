import re

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

    # 6. Bullet lists: lines starting with •, -, *
    lines = text.split('\n')
    processed_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(('• ', '- ', '* ')):
            bullet_content = stripped[2:].strip()
            processed_lines.append(f'<div class="flex items-start gap-2 my-1"><span class="text-purple-500 font-bold shrink-0">•</span><span>{bullet_content}</span></div>')
        else:
            processed_lines.append(line)

    text = '<br>'.join(processed_lines)
    # Collapse multiple consecutive <br>
    text = re.sub(r'(<br>\s*){3,}', '<br><br>', text)

    # 7. Restore inline code and code blocks
    for i, code_html in enumerate(inline_codes):
        text = text.replace(f'___INLINE_CODE_{i}___', code_html)
    for i, block_html in enumerate(code_blocks):
        text = text.replace(f'<br>___CODE_BLOCK_{i}___', f'___CODE_BLOCK_{i}___')
        text = text.replace(f'___CODE_BLOCK_{i}___<br>', f'___CODE_BLOCK_{i}___')
        text = text.replace(f'___CODE_BLOCK_{i}___', block_html)

    return mark_safe(text)


def article_link_in_text(value: str) -> str:
    """Turn stored testserver links into paths before markdown is rendered."""
    parsed_hosts = ('http://testserver', 'https://testserver')
    for host in parsed_hosts:
        value = value.replace(host, '')
    return value


@register.filter(name='session_title')
def session_title(value: str) -> str:
    """Hide the decorative document prefix and legacy id in displayed titles only."""
    if not value:
        return ''
    return re.sub(r'^\s*📄\s*(?:\[\d+\]\s*)?', '', value)
