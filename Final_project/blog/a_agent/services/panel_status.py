"""Presentation only: access decisions remain in tools.access."""
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone


def build_panel_status(user, scope, llm_info=None, *, tool_trace=None):
    membership = 'No membership'
    expires = None
    if not getattr(user, 'is_authenticated', False):
        membership = 'Signed out'
    else:
        try:
            profile = user.profile
        except ObjectDoesNotExist:
            membership = 'Membership status unavailable'
        else:
            expires = profile.subscription_end_date
            if profile.has_valid_subscription():
                membership = 'Active membership'
            elif expires and expires <= timezone.now().date():
                membership = 'Expired membership'
            elif profile.is_subscribed:
                membership = 'Membership status unavailable'

    reason = getattr(scope, 'access_reason', '') if scope else ''
    can_read = bool(scope and scope.can_read_full)
    labels = {
        'free': 'Free · Full access',
        'subscription': 'Member · Full access',
        'staff': 'Staff · Full access',
        'purchased': 'Article unlocked',
    }
    access_label = labels.get(reason, 'Full access') if can_read else 'Preview only'
    if scope is None:
        access_label = 'Article access unavailable'
    trace = tool_trace or []
    response_mode = next((item.get('mode') for item in reversed(trace)
                          if item.get('tool') == 'response_mode'), None)
    configured = bool(llm_info and llm_info.configured)
    if response_mode == 'fallback':
        service_label = 'Search fallback'
        service_detail = 'AI did not generate this reply. Search results are shown instead.'
    elif response_mode == 'ai':
        service_label = 'AI response'
        service_detail = 'This reply was generated using the configured AI service.'
    elif configured:
        service_label = 'AI configured'
        service_detail = 'AI is configured. A request may still fail and use search fallback.'
    else:
        service_label = 'Search fallback'
        service_detail = 'AI is unavailable or not configured. Search-based replies remain available.'
    return {
        'access_label': access_label,
        'can_read_full': can_read,
        'access_known': scope is not None,
        'membership_label': membership,
        'expires': expires,
        'show_subscription': bool(scope and not can_read),
        'subscription_cta': 'Renew membership' if membership == 'Expired membership' else 'View membership',
        'service_label': service_label,
        'service_detail': service_detail,
    }


def describe_readiness(readiness, article_slug, *, analysis=None):
    """Normalize display data. AI payload is opt-in until its backend is integrated.

    Proposed contract: status, article_concepts, prerequisite_concepts.
    Only status=ready with both concept lists explicitly present is successful.
    Article matching and permission enforcement are not performed here.
    """
    from a_agent.services.navigator import get_prerequisites_graph
    result = dict(readiness)
    result.update(article_concepts=[], prerequisite_concepts=[], no_prerequisites=False)
    if analysis is not None:
        result.update(configured=False, learning_state='unavailable', source_label='AI analysis',
                      gaps=[], ready_prereqs=[], total_prereqs=0, covered_prereqs=0,
                      difficulty=None, intermediate_insights={})
        if not isinstance(analysis, dict):
            return result
        status = analysis.get('status')
        if status in ('pending', 'analyzing'):
            result['learning_state'] = 'analyzing'
            return result
        if status != 'ready':
            return result
        # Missing, null and malformed lists are not equivalent to an empty list.
        for key in ('article_concepts', 'prerequisite_concepts'):
            values = analysis.get(key)
            if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
                return result
        difficulty = analysis.get('difficulty')
        if difficulty not in ('beginner', 'intermediate', 'advanced'):
            return result
        result.update(configured=True, learning_state='ready', difficulty=difficulty,
                      article_concepts=list(dict.fromkeys(v.strip() for v in analysis['article_concepts'])),
                      prerequisite_concepts=list(dict.fromkeys(v.strip() for v in analysis['prerequisite_concepts'])),
                      no_prerequisites=not analysis['prerequisite_concepts'])
        return result

    meta = get_prerequisites_graph().get(article_slug)
    result.update(configured=meta is not None, learning_state='legacy' if meta is not None else 'unavailable',
                  source_label='Curated article data',
                  total_prereqs=len(meta.get('prerequisites', [])) if meta is not None else 0,
                  covered_prereqs=len(readiness.get('ready_prereqs', [])))
    # An existing missing JSON key must not silently mean no prerequisites.
    if meta is not None and not isinstance(meta.get('prerequisites'), list):
        result.update(configured=False, learning_state='unavailable')
    result['gaps'] = [dict(gap, prerequisite_concepts=[gap['key_concept']] if gap.get('key_concept') else [])
                      for gap in readiness.get('gaps', [])]
    return result
