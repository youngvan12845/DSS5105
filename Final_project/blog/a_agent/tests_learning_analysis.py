import os
import tempfile
from types import SimpleNamespace

from django.test import SimpleTestCase

from a_agent.services.learning_analysis import (
    BRIDGE_UNAVAILABLE,
    allowed_source,
    analysis_for_display,
    analyze_article_text,
    bridge_cache_key,
    content_version,
    explain_concept,
    invalidate_if_changed,
    load_store,
    match_concepts,
    matched_coverage,
    ready_payload_from_model,
    store_article_analysis,
)


class LearningAnalysisTests(SimpleTestCase):
    def article(self, slug='compose', title='Docker Compose', body=''):
        return SimpleNamespace(slug=slug, title=title, intro='A short intro', body=body or 'Compose runs many containers together.')

    def test_valid_model_json_keeps_an_explicit_empty_prerequisite_list(self):
        payload = ready_payload_from_model({
            'difficulty': 'Beginner',
            'article_concepts': ['Variables'],
            'prerequisite_concepts': [],
        })
        self.assertEqual(payload['status'], 'ready')
        self.assertEqual(payload['difficulty'], 'beginner')
        self.assertEqual(payload['prerequisite_concepts'], [])

    def test_invalid_model_json_does_not_become_beginner(self):
        for raw in (
            {},
            {'difficulty': 'medium', 'article_concepts': ['Git'], 'prerequisite_concepts': []},
            {'difficulty': 'beginner', 'article_concepts': [], 'prerequisite_concepts': None},
            {'difficulty': 'beginner', 'article_concepts': ['Git'], 'prerequisite_concepts': ['']},
        ):
            with self.subTest(raw=raw):
                self.assertIsNone(ready_payload_from_model(raw))

    def test_failed_generation_is_unavailable(self):
        def explode(system, user):
            raise RuntimeError('secret traceback')

        result = analyze_article_text(title='Git', intro='', body='text', generate=explode)
        self.assertEqual(result, {'status': 'unavailable'})
        self.assertNotIn('secret', str(result))

    def test_short_or_ungrounded_text_is_unavailable(self):
        called = []
        short = analyze_article_text(title='rag', intro='1', body='', generate=lambda system, user: called.append(1))
        self.assertEqual(short, {'status': 'unavailable'})
        self.assertEqual(called, [])

        def generic(system, user):
            return '{"difficulty":"beginner","article_concepts":["system"],"prerequisite_concepts":[]}'

        ungrounded = analyze_article_text(
            title='RAG',
            intro='',
            body='RAG retrieves documents before the model answers the question.',
            generate=generic,
        )
        self.assertEqual(ungrounded, {'status': 'unavailable'})

    def test_grounded_concepts_are_kept(self):
        def generate(system, user):
            self.assertIn('梯度下降直觉理解', user)
            return '{"difficulty":"beginner","article_concepts":["RAG","documents"],"prerequisite_concepts":["梯度下降"]}'

        result = analyze_article_text(
            title='What is RAG',
            intro='',
            body='RAG retrieves documents before the model answers the question.',
            generate=generate,
            other_titles=['梯度下降直觉理解'],
        )
        self.assertEqual(result['article_concepts'], ['RAG', 'documents'])
        self.assertEqual(result['prerequisite_concepts'], ['梯度下降'])

    def test_match_uses_real_titles_and_skips_the_current_article(self):
        catalog = [
            {'slug': 'compose', 'title': 'Docker Compose'},
            {'slug': 'containers', 'title': 'Introduction to Containers'},
            {'slug': 'ports', 'title': 'Exposing Container Ports'},
        ]
        matches = match_concepts(
            ['Containers', 'Missing concept', 'Container Ports'],
            catalog,
            exclude_slug='compose',
        )
        self.assertEqual([item['slug'] for item in matches], ['containers', 'ports'])
        self.assertNotIn('missing-concept', [item['slug'] for item in matches])
        chinese = match_concepts(['梯度下降'], [{'slug': 'grad', 'title': '梯度下降直觉理解'}])
        self.assertEqual(chinese, [{'concept': '梯度下降', 'slug': 'grad', 'title': '梯度下降直觉理解'}])
        titled = match_concepts(['What Is Git?'], [{'slug': 'git-what-is-git', 'title': 'What Is Git?'}])
        self.assertEqual(titled[0]['slug'], 'git-what-is-git')

    def test_coverage_uses_visits_and_session_marks_only(self):
        matches = [{'concept': 'Containers', 'slug': 'containers'}, {'concept': 'Ports', 'slug': 'ports'}]
        self.assertEqual(matched_coverage(matches, {'containers'}, {'ports'}), (2, 2))
        self.assertEqual(matched_coverage(matches, set(), set()), (0, 2))

    def test_preview_source_omits_paid_body(self):
        full, full_tier = allowed_source('Title', 'Intro', 'PAID BODY', can_read_full=True)
        preview, preview_tier = allowed_source('Title', 'Intro', 'PAID BODY', can_read_full=False)
        self.assertIn('PAID BODY', full)
        self.assertEqual(full_tier, 'full')
        self.assertNotIn('PAID BODY', preview)
        self.assertEqual(preview_tier, 'preview')
        self.assertNotEqual(
            bridge_cache_key('ports', 'v1', 'Ports', full_tier),
            bridge_cache_key('ports', 'v1', 'Ports', preview_tier),
        )

    def test_missing_record_stays_unset_and_stale_record_is_not_ready(self):
        self.assertEqual(analysis_for_display(None, current_version='v2', live_titles={}), (None, []))
        payload, matches = analysis_for_display(
            {
                'status': 'ready',
                'version': 'v1',
                'difficulty': 'advanced',
                'article_concepts': ['Compose'],
                'prerequisite_concepts': ['Containers'],
                'matches': [{'concept': 'Containers', 'slug': 'containers', 'title': 'Old title'}],
            },
            current_version='v2',
            live_titles={'containers': 'Introduction to Containers'},
        )
        self.assertEqual(payload, {'status': 'stale'})
        self.assertEqual(matches, [])

    def test_ready_record_refreshes_titles_and_drops_deleted_articles(self):
        payload, matches = analysis_for_display(
            {
                'status': 'ready',
                'version': 'v1',
                'difficulty': 'intermediate',
                'article_concepts': ['Compose'],
                'prerequisite_concepts': ['Containers', 'Ports'],
                'matches': [
                    {'concept': 'Containers', 'slug': 'containers', 'title': 'Old title'},
                    {'concept': 'Ports', 'slug': 'gone', 'title': 'Gone'},
                ],
            },
            current_version='v1',
            live_titles={'containers': 'Introduction to Containers'},
        )
        self.assertEqual(payload['difficulty'], 'intermediate')
        self.assertEqual(matches, [{
            'concept': 'Containers',
            'slug': 'containers',
            'title': 'Introduction to Containers',
        }])

    def test_publish_marks_a_changed_article_stale_without_calling_the_model(self):
        article = self.article()
        version = content_version(article.title, article.intro, article.body)
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'learning_analysis.json')
            store_article_analysis(
                article,
                [{'slug': 'containers', 'title': 'Introduction to Containers'}],
                lambda system, user: '{"difficulty":"intermediate","article_concepts":["Compose"],"prerequisite_concepts":["Containers"]}',
                path=path,
            )
            article.body = 'Compose runs many containers together. Updated.'
            self.assertTrue(invalidate_if_changed(article, path=path))
            payload, matches = analysis_for_display(
                load_store(path)['articles']['compose'],
                current_version=content_version(article.title, article.intro, article.body),
                live_titles={'containers': 'Introduction to Containers'},
            )
        self.assertEqual(payload['status'], 'stale')
        self.assertEqual(matches, [])
        self.assertNotEqual(version, content_version(article.title, article.intro, article.body))

    def test_bridge_failure_does_not_invent_an_explanation(self):
        self.assertIsNone(explain_concept('Ports', 'Intro', generate=lambda system, user: ''))
        self.assertEqual(BRIDGE_UNAVAILABLE, 'Concept explanation is unavailable.')
