"""Detect when a reply should be written in Simplified Chinese."""

from __future__ import annotations

import re

_CHINESE_CHAR = re.compile(r'[\u4e00-\u9fff]')
_ASK_CHINESE = re.compile(
    r'(?:'
    r'\bin\s+chinese\b|'
    r'\bin\s+simplified\s+chinese\b|'
    r'\bin\s+mandarin\b|'
    r'\breply\s+in\s+chinese\b|'
    r'\banswer\s+in\s+chinese\b|'
    r'\brespond\s+in\s+chinese\b|'
    r'\bwrite\s+in\s+chinese\b|'
    r'\bsummarize\s+in\s+chinese\b|'
    r'\bchinese\s+summary\b|'
    r'用中文|'
    r'中文总结|'
    r'中文總結|'
    r'中文回答|'
    r'中文回复|'
    r'中文回覆|'
    r'翻译成中文|'
    r'翻譯成中文|'
    r'改成中文'
    r')',
    re.I,
)


def wants_chinese(query: str) -> bool:
    """True when the question is in Chinese, or asks for a Chinese reply."""
    text = query or ''
    if _CHINESE_CHAR.search(text):
        return True
    return bool(_ASK_CHINESE.search(text))
