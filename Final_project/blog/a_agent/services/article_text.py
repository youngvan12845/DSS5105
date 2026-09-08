from __future__ import annotations

import re

from bs4 import BeautifulSoup


def html_to_text(html: str) -> str:
    if not html:
        return ''
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text('\n')
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def chunk_text(text: str, *, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r'\n+', text) if p.strip()]
    chunks: list[str] = []
    current = ''

    for para in paragraphs:
        if len(current) + len(para) + 1 <= chunk_size:
            current = f'{current}\n{para}'.strip()
        else:
            if current:
                chunks.append(current)
            current = para

    if current:
        chunks.append(current)

    if len(chunks) <= 1:
        return chunks

    merged: list[str] = []
    for i, chunk in enumerate(chunks):
        if i == 0:
            merged.append(chunk)
            continue
        prev = merged[-1]
        tail = prev[-overlap:] if overlap else ''
        merged.append(f'{tail}\n{chunk}'.strip())
    return merged
