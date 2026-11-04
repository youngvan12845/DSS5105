import json
from typing import Any, Dict
from a_agent.services.navigator import get_prerequisites_graph


def build_article_graph_data(article) -> Dict[str, Any]:
    """
    Builds the complete knowledge graph topology for an article:
    - Central node: Current article
    - Incoming nodes: Prerequisites with key concepts & bridge summaries
    - Orbiting insight nodes: Production pitfalls & architecture tradeoffs
    - Outgoing nodes: Next milestones / next chapters
    """
    if not article:
        return {'nodes': [], 'links': [], 'has_data': False}

    from a_blog.models import ArticlePage

    graph = get_prerequisites_graph()
    meta = graph.get(article.slug, {})

    nodes = []
    links = []

    # 1. Central Current Node
    current_node = {
        'id': 'current',
        'slug': article.slug,
        'label': article.title,
        'type': 'current',
        'difficulty': meta.get('difficulty', 'beginner'),
        'series': meta.get('series', getattr(article, 'series_slug', '')),
        'url': getattr(article, 'url', None),
        'concept': 'Current Topic',
        'summary': getattr(article, 'intro', '') or 'Current article being explored.',
    }
    nodes.append(current_node)

    # 2. Prerequisites (Incoming)
    prereqs = meta.get('prerequisites', [])
    for idx, p in enumerate(prereqs):
        p_slug = p.get('slug')
        target_article = None
        try:
            target_article = ArticlePage.objects.filter(slug=p_slug, live=True).first() if p_slug else None
        except Exception:
            pass
        node_id = f'prereq_{idx}'
        nodes.append({
            'id': node_id,
            'slug': p_slug,
            'label': p.get('title', p_slug),
            'type': 'prerequisite',
            'concept': p.get('key_concept', 'Foundational Principle'),
            'summary': p.get('bridge_summary', 'Prerequisite knowledge recommended before this chapter.'),
            'url': getattr(target_article, 'url', None),
        })
        links.append({
            'source': node_id,
            'target': 'current',
            'type': 'requires',
            'label': 'prerequisite',
        })

    # If no prerequisites in graph, check prev_lesson
    if not prereqs and getattr(article, 'series_slug', None) and hasattr(article, 'get_prev_lesson'):
        prev = article.get_prev_lesson()
        if prev:
            node_id = 'prereq_prev'
            nodes.append({
                'id': node_id,
                'slug': prev.slug,
                'label': prev.title,
                'type': 'prerequisite',
                'concept': f"Chapter #{getattr(prev, 'chapter_number', 1)} Lesson #{getattr(prev, 'lesson_number', 1)}",
                'summary': getattr(prev, 'intro', '') or 'Previous lesson in this curriculum.',
                'url': prev.url,
            })
            links.append({
                'source': node_id,
                'target': 'current',
                'type': 'requires',
                'label': 'previous lesson',
            })

    # 3. Intermediate Insights / Concept Nodes
    insights = meta.get('intermediate_insights', {})
    pitfall = insights.get('production_pitfall')
    tradeoff = insights.get('tradeoff_challenge')
    if pitfall:
        nodes.append({
            'id': 'pitfall',
            'label': 'Production Pitfall',
            'type': 'pitfall',
            'concept': 'Common Production Trap',
            'summary': pitfall,
        })
        links.append({
            'source': 'current',
            'target': 'pitfall',
            'type': 'insight',
            'label': 'pitfall',
        })
    if tradeoff:
        nodes.append({
            'id': 'tradeoff',
            'label': 'Architecture Tradeoff',
            'type': 'tradeoff',
            'concept': 'System Design Choice',
            'summary': tradeoff,
        })
        links.append({
            'source': 'current',
            'target': 'tradeoff',
            'type': 'insight',
            'label': 'tradeoff',
        })

    # 4. Next Milestones (Outgoing)
    milestones = meta.get('next_milestones', [])
    for idx, m in enumerate(milestones):
        m_slug = m.get('slug')
        target_article = None
        try:
            target_article = ArticlePage.objects.filter(slug=m_slug, live=True).first() if m_slug else None
        except Exception:
            pass
        node_id = f'milestone_{idx}'
        nodes.append({
            'id': node_id,
            'slug': m_slug,
            'label': m.get('title', m_slug),
            'type': 'milestone',
            'concept': 'Next Milestone',
            'summary': m.get('reason', 'Advanced topic following this chapter.'),
            'url': getattr(target_article, 'url', None),
        })
        links.append({
            'source': 'current',
            'target': node_id,
            'type': 'leads_to',
            'label': 'next step',
        })

    # If no milestones in graph, check next_lesson
    if not milestones and getattr(article, 'series_slug', None) and hasattr(article, 'get_next_lesson'):
        nxt = article.get_next_lesson()
        if nxt:
            node_id = 'milestone_next'
            nodes.append({
                'id': node_id,
                'slug': nxt.slug,
                'label': nxt.title,
                'type': 'milestone',
                'concept': f"Chapter #{getattr(nxt, 'chapter_number', 1)} Lesson #{getattr(nxt, 'lesson_number', 1)}",
                'summary': getattr(nxt, 'intro', '') or 'Next lesson in this curriculum.',
                'url': nxt.url,
            })
            links.append({
                'source': 'current',
                'target': node_id,
                'type': 'leads_to',
                'label': 'next lesson',
            })

    return {
        'nodes': nodes,
        'links': links,
        'has_data': len(nodes) > 1,
        'difficulty': meta.get('difficulty', 'beginner'),
        'series': meta.get('series', ''),
        'prereq_count': len([n for n in nodes if n['type'] == 'prerequisite']),
        'milestone_count': len([n for n in nodes if n['type'] == 'milestone']),
    }
