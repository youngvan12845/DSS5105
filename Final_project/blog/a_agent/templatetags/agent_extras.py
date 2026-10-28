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
    """Render lightweight markdown used by the agent (links, bold, line breaks)."""
    if not value:
        return ''

    text = escape(article_link_in_text(value))
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(
        r'\[([^\]]+)\]\(([^)]+)\)',
        r'<a href="\2" class="text-purple-600 hover:underline" target="_blank" rel="noopener">\1</a>',
        text,
    )
    return mark_safe(text.replace('\n', '<br>'))


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
