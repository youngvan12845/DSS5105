from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from a_blog.models import ArticlePage
from a_users.models import BrowsingHistory
from a_agent.services.navigator import (
    get_prerequisites_graph,
    calculate_article_readiness,
    get_concept_bridge,
    mark_prerequisite_mastered,
)

User = get_user_model()


class NavigatorServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testreader', password='password123')
        self.factory = RequestFactory()

    def test_graph_loads_and_has_articles(self):
        graph = get_prerequisites_graph()
        self.assertIsInstance(graph, dict)
        self.assertGreaterEqual(len(graph), 20)
        # Check a key article
        self.assertIn('linear-regression-practice', graph)
        meta = graph['linear-regression-practice']
        self.assertEqual(meta['difficulty'], 'intermediate')
        self.assertTrue(len(meta['prerequisites']) >= 1)
        self.assertIn('intermediate_insights', meta)
        self.assertIn('production_pitfall', meta['intermediate_insights'])

    def test_graph_prerequisites_refer_to_valid_articles(self):
        graph = get_prerequisites_graph()
        for slug, meta in graph.items():
            for prereq in meta.get('prerequisites', []):
                prereq_slug = prereq['slug']
                self.assertIn(
                    prereq_slug,
                    graph,
                    f"Article {slug} has non-existent prerequisite: {prereq_slug}"
                )

    def test_readiness_calculation_for_new_user(self):
        # New user has not read anything
        readiness = calculate_article_readiness(self.user, 'linear-regression-practice')
        self.assertIn(readiness['status'], ('yellow', 'orange'))
        self.assertLess(readiness['score'], 100)
        self.assertGreater(len(readiness['gaps']), 0)
        # Verify gap contains gradient descent
        gap_slugs = [g['slug'] for g in readiness['gaps']]
        self.assertIn('gradient-descent-intuition', gap_slugs)

    def test_readiness_calculation_with_senior_override(self):
        # User marks topic or prerequisite as mastered
        session_mastered = ['gradient-descent-intuition', 'ml-supervised-unsupervised']
        readiness = calculate_article_readiness(
            self.user,
            'linear-regression-practice',
            session_mastered=session_mastered
        )
        self.assertEqual(readiness['status'], 'green')
        self.assertEqual(readiness['score'], 100)
        self.assertEqual(len(readiness['gaps']), 0)
        # Senior insights should be available
        self.assertIn('intermediate_insights', readiness)
        self.assertIn('production_pitfall', readiness['intermediate_insights'])

    def test_concept_bridge_retrieval(self):
        bridge = get_concept_bridge('gradient-descent-intuition')
        self.assertIsNotNone(bridge)
        self.assertIn('title', bridge)
        self.assertIn('bridge_summary', bridge)
        self.assertTrue(len(bridge['bridge_summary']) > 10)
