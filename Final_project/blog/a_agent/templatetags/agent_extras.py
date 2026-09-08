import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name='agent_markdown')
def agent_markdown(value: str) -> str:
    """Render lightweight markdown used by the agent (links, bold, line breaks)."""
    if not value:
        return ''

    text = escape(value)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(
        r'\[([^\]]+)\]\(([^)]+)\)',
        r'<a href="\2" class="text-pink-600 hover:underline" target="_blank" rel="noopener">\1</a>',
        text,
    )
    return mark_safe(text.replace('\n', '<br>'))


@register.filter(name='session_title')
def session_title(value: str) -> str:
    """Strip legacy article-id prefix from article-scoped session titles."""
    if not value:
        return ''
    return re.sub(r'^📄\s*\[\d+\]\s*', '📄 ', value)
