from datetime import timedelta
from types import SimpleNamespace

from django.core.exceptions import ObjectDoesNotExist
from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.utils import timezone

from a_agent.services.panel_status import build_panel_status


class PanelStatusTests(SimpleTestCase):
    def user(self, active=False, days=None, subscribed=False):
        end = None if days is None else timezone.now().date() + timedelta(days=days)
        return SimpleNamespace(is_authenticated=True, profile=SimpleNamespace(
            is_subscribed=subscribed, subscription_end_date=end,
            has_valid_subscription=lambda: active))

    def scope(self, reason, allowed=True):
        return SimpleNamespace(access_reason=reason, can_read_full=allowed)

    def test_access_labels_are_independent_of_membership(self):
        for reason, label in [('free', 'Free · Full access'), ('staff', 'Staff · Full access'),
                              ('purchased', 'Article unlocked')]:
            with self.subTest(reason=reason):
                status = build_panel_status(self.user(), self.scope(reason))
                self.assertEqual(status['access_label'], label)
                self.assertEqual(status['membership_label'], 'No membership')
                self.assertFalse(status['show_subscription'])

    def test_active_and_expired_memberships(self):
        active = build_panel_status(self.user(True, 10, True), self.scope('subscription'))
        self.assertEqual(active['membership_label'], 'Active membership')
        for days in [-1, 0]:
            status = build_panel_status(self.user(False, days, True), self.scope('paywall', False))
            self.assertEqual(status['membership_label'], 'Expired membership')
            self.assertEqual(status['subscription_cta'], 'Renew membership')
            self.assertTrue(status['show_subscription'])

    def test_unconfirmed_and_signed_out_states(self):
        status = build_panel_status(self.user(False, None, True), None)
        self.assertEqual(status['membership_label'], 'Membership status unavailable')
        self.assertEqual(status['access_label'], 'Article access unavailable')
        guest = build_panel_status(SimpleNamespace(is_authenticated=False), self.scope('login_required', False))
        self.assertEqual(guest['membership_label'], 'Signed out')
        self.assertFalse(guest['can_read_full'])

    def test_missing_profile(self):
        class UserWithoutProfile:
            is_authenticated = True

            @property
            def profile(self):
                raise ObjectDoesNotExist()
        status = build_panel_status(UserWithoutProfile(), None)
        self.assertEqual(status['membership_label'], 'Membership status unavailable')

    def test_actual_response_overrides_configuration(self):
        configured = SimpleNamespace(configured=True)
        status = build_panel_status(self.user(), self.scope('free'), configured)
        self.assertEqual(status['service_label'], 'AI configured')
        for mode, label in [('fallback', 'Search fallback'), ('ai', 'AI response')]:
            status = build_panel_status(self.user(), self.scope('free'), configured,
                                        tool_trace=[{'tool': 'response_mode', 'mode': mode}])
            self.assertEqual(status['service_label'], label)

    def test_templates_show_preview_and_oob_update(self):
        status = build_panel_status(self.user(False, -1, True), self.scope('paywall', False))
        html = render_to_string('a_agent/partials/panel_status.html', {
            'panel_status': status, 'status_oob': True})
        self.assertIn('Preview only', html)
        self.assertIn('Renew membership', html)
        self.assertIn('hx-swap-oob="outerHTML"', html)
        self.assertIn('Paid article text is not included', html)

    def test_readiness_metadata_distinguishes_missing_configuration(self):
        from unittest.mock import patch
        from a_agent.services.panel_status import describe_readiness
        with patch('a_agent.services.navigator.get_prerequisites_graph', return_value={
            'known': {'prerequisites': [{'slug': 'a'}, {'slug': 'b'}]},
            'intro': {'prerequisites': []},
        }):
            result = describe_readiness({'ready_prereqs': [{'slug': 'a'}]}, 'known')
            self.assertTrue(result['configured'])
            self.assertEqual(result['total_prereqs'], 2)
            self.assertEqual(result['covered_prereqs'], 1)
            self.assertFalse(describe_readiness({}, 'missing')['configured'])
            self.assertTrue(describe_readiness({}, 'intro')['configured'])

    def test_ai_concepts_are_separate_and_not_skill_scores(self):
        from a_agent.services.panel_status import describe_readiness
        data = describe_readiness({}, 'unused', analysis={
            'status': 'ready', 'difficulty': 'intermediate',
            'article_concepts': ['Docker Compose'],
            'prerequisite_concepts': ['Containers', 'Ports'],
        })
        html = render_to_string('a_agent/partials/readiness_panel.html', {'readiness': data})
        self.assertIn('Article concepts', html)
        self.assertIn('Prerequisite concepts', html)
        self.assertIn('Docker Compose', html)
        self.assertNotIn('Prerequisite coverage', html)
        self.assertNotIn('No prerequisites identified', html)

    def test_empty_list_only_means_none_after_success(self):
        from a_agent.services.panel_status import describe_readiness
        for status in ['failed', 'unavailable', 'pending', 'analyzing', 'stale']:
            with self.subTest(status=status):
                data = describe_readiness({}, 'unused', analysis={
                    'status': status, 'article_concepts': [], 'prerequisite_concepts': [],
                })
                self.assertFalse(data['no_prerequisites'])
                html = render_to_string('a_agent/partials/readiness_panel.html', {'readiness': data})
                self.assertNotIn('No prerequisites identified', html)
        ready = describe_readiness({}, 'unused', analysis={
            'status': 'ready', 'difficulty': 'beginner',
            'article_concepts': ['Variables'], 'prerequisite_concepts': [],
        })
        self.assertTrue(ready['no_prerequisites'])

    def test_missing_or_invalid_ai_fields_are_unavailable(self):
        from a_agent.services.panel_status import describe_readiness
        for payload in [[], {}, {'status': 'ready'},
                        {'status': 'ready', 'difficulty': 'beginner', 'article_concepts': [], 'prerequisite_concepts': None},
                        {'status': 'ready', 'difficulty': 'beginner', 'article_concepts': [], 'prerequisite_concepts': ['']}]:
            with self.subTest(payload=payload):
                data = describe_readiness({}, 'unused', analysis=payload)
                self.assertEqual(data['learning_state'], 'unavailable')
                self.assertFalse(data['no_prerequisites'])

    def test_legacy_concept_is_not_relabelled_as_article_concept(self):
        from unittest.mock import patch
        from a_agent.services.panel_status import describe_readiness
        with patch('a_agent.services.navigator.get_prerequisites_graph', return_value={
            'legacy': {'prerequisites': [{'slug': 'a', 'key_concept': 'Containers'}]},
        }):
            data = describe_readiness({'gaps': [{'slug': 'a', 'title': 'Article', 'key_concept': 'Containers'}]}, 'legacy')
            self.assertEqual(data['article_concepts'], [])
            self.assertEqual(data['gaps'][0]['prerequisite_concepts'], ['Containers'])
            self.assertEqual(data['source_label'], 'Curated article data')
