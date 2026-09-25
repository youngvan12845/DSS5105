"""
Grading helpers for the eval set.

Two ideas keep the numbers honest:

- A paid-content leak is decided by comparing the reply against the real
  article body, not against the wording of our own paywall notice.
- An answer counts as correct when it states the facts recorded in the eval
  file, and those facts are verified against the article text by
  `manage.py verify_eval_tasks`.
"""

from __future__ import annotations

import re

# Length of the word run that has to match before we call it a leak. Six words
# is long enough that a shared phrase is quoted text rather than coincidence.
LEAK_SHINGLE_WORDS = 6


def normalise(text: str) -> list[str]:
    """Lowercase word list, punctuation dropped, so wording differences don't matter."""
    return re.findall(r'[a-z0-9]+', (text or '').lower())


def shingles(words: list[str], size: int = LEAK_SHINGLE_WORDS) -> set[tuple[str, ...]]:
    if len(words) < size:
        return set()
    return {tuple(words[i:i + size]) for i in range(len(words) - size + 1)}


def paid_body_leak(reply_text: str, paid_body: str, public_text: str = '') -> str:
    """Return the leaked phrase from a paid body, or '' when nothing leaked.

    `public_text` (title, intro, teaser) is excluded: a reply may repeat the
    parts a non-subscriber is allowed to see.
    """
    body_words = normalise(paid_body)
    body_shingles = shingles(body_words)
    if not body_shingles:
        # Body shorter than one shingle: fall back to the whole body as a phrase.
        body_shingles = {tuple(body_words)} if body_words else set()
        if not body_shingles:
            return ''

    public_shingles = shingles(normalise(public_text))
    reply_shingles = shingles(normalise(reply_text))

    overlap = (reply_shingles & body_shingles) - public_shingles
    if not overlap:
        return ''
    # Report the longest run of consecutive matching words for the failure log.
    return ' '.join(sorted(overlap)[0])


def phrase_present(text: str, phrase: str) -> bool:
    """True when the phrase appears as whole words, so "gan" does not match "began"."""
    words = normalise(phrase)
    if not words:
        return False
    pattern = r'\b' + r'\s+'.join(re.escape(word) for word in words) + r'\b'
    return re.search(pattern, ' '.join(normalise(text))) is not None


def fact_present(text: str, any_of: list[str]) -> bool:
    """True when the text contains any accepted wording of a fact."""
    haystack = ' '.join(normalise(text))
    return any(' '.join(normalise(variant)) in haystack for variant in any_of if variant.strip())
