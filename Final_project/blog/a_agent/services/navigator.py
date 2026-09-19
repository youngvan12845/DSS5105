import json
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set
from django.conf import settings
from a_users.models import BrowsingHistory

GRAPH_FILE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'data',
    'prerequisites_graph.json'
)


@lru_cache(maxsize=1)
def get_prerequisites_graph() -> Dict[str, Any]:
    """Loads and caches the 22-article prerequisite graph."""
    if not os.path.exists(GRAPH_FILE_PATH):
        return {}
    with open(GRAPH_FILE_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_concept_bridge(prereq_slug: str) -> Optional[Dict[str, Any]]:
    """
    Returns the bridge concept summary for a given prerequisite article.
    Searches either direct article entry or inside other articles' prerequisites.
    """
    graph = get_prerequisites_graph()
    # 1. Search in prerequisites definitions of other articles
    for _, meta in graph.items():
        for p in meta.get('prerequisites', []):
            if p.get('slug') == prereq_slug:
                return {
                    'slug': prereq_slug,
                    'title': p.get('title'),
                    'key_concept': p.get('key_concept'),
                    'bridge_summary': p.get('bridge_summary'),
                }
    # 2. If article exists directly, synthesize default
    if prereq_slug in graph:
        meta = graph[prereq_slug]
        return {
            'slug': prereq_slug,
            'title': meta.get('title'),
            'key_concept': meta.get('title'),
            'bridge_summary': f"This is a foundational prerequisite for '{meta.get('title')}'. Understanding these core concepts is recommended before advancing.",
        }
    return None


def calculate_article_readiness(
    user,
    article_slug: str,
    session_mastered: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Computes reading readiness score and gap analysis for a given article and user.
    Statuses:
      - green: 100% ready (all prereqs read or marked mastered)
      - yellow: 1~99% ready (some gaps detected)
      - orange: 0% ready (foundational missing)
    """
    graph = get_prerequisites_graph()
    article_meta = graph.get(article_slug)

    if not article_meta:
        return {
            'status': 'green',
            'score': 100,
            'difficulty': 'beginner',
            'gaps': [],
            'ready_prereqs': [],
            'intermediate_insights': {},
            'next_milestones': [],
        }

    prereqs = article_meta.get('prerequisites', [])
    difficulty = article_meta.get('difficulty', 'beginner')
    intermediate_insights = article_meta.get('intermediate_insights', {})
    next_milestones = article_meta.get('next_milestones', [])

    if not prereqs:
        return {
            'status': 'green',
            'score': 100,
            'difficulty': difficulty,
            'gaps': [],
            'ready_prereqs': [],
            'intermediate_insights': intermediate_insights,
            'next_milestones': next_milestones,
        }

    # Query user browsing history
    read_slugs: Set[str] = set()
    if user and getattr(user, 'is_authenticated', False):
        article_ids = list(
            BrowsingHistory.objects.filter(user=user).values_list('article_id', flat=True)
        )
        if article_ids:
            from a_blog.models import ArticlePage
            read_slugs = set(
                ArticlePage.objects.filter(id__in=article_ids).values_list('slug', flat=True)
            )

    # Union with session-based senior mastered tags
    mastered: Set[str] = set(session_mastered or [])

    gaps: List[Dict[str, Any]] = []
    ready_prereqs: List[Dict[str, Any]] = []

    for p in prereqs:
        p_slug = p.get('slug')
        if p_slug in read_slugs or p_slug in mastered:
            ready_prereqs.append(p)
        else:
            gaps.append(p)

    total_count = len(prereqs)
    gap_count = len(gaps)

    if gap_count == 0:
        status = 'green'
        score = 100
    elif gap_count < total_count:
        status = 'yellow'
        score = round(((total_count - gap_count) / total_count) * 100)
    else:
        status = 'orange'
        score = 0

    return {
        'status': status,
        'score': score,
        'difficulty': difficulty,
        'gaps': gaps,
        'ready_prereqs': ready_prereqs,
        'intermediate_insights': intermediate_insights,
        'next_milestones': next_milestones,
        'article_title': article_meta.get('title'),
        'series': article_meta.get('series'),
    }


def mark_prerequisite_mastered(session, topic_or_slug: str) -> List[str]:
    """
    Appends topic_or_slug to session['mastered_prereqs'] and marks modified.
    """
    if 'mastered_prereqs' not in session:
        session['mastered_prereqs'] = []
    if topic_or_slug not in session['mastered_prereqs']:
        session['mastered_prereqs'].append(topic_or_slug)
        if hasattr(session, 'modified'):
            session.modified = True
    return session['mastered_prereqs']
