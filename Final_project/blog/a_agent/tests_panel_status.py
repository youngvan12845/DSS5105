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

    def test_suggested_prompts_structure(self):
        from a_agent.views import _get_suggested_prompts
        mock_article = SimpleNamespace(id=1, title='Test Article', slug='test-article')
        prompts = _get_suggested_prompts(mock_article)
        self.assertIsInstance(prompts, list)
        self.assertGreaterEqual(len(prompts), 4)
        labels = [p['label'] for p in prompts]
        self.assertIn('🎯 Quiz Me', labels)
        self.assertIn('💡 Key Takeaways', labels)
        self.assertIn('⚠️ Pitfalls', labels)

    def test_quiz_and_excerpt_intent_triggers(self):
        from a_agent.services.orchestrator import _classify_intents
        quiz_intents = _classify_intents('Can you quiz me on this article?')
        self.assertTrue({'keyword', 'chunk', 'vector'}.issubset(quiz_intents))
        pitfall_intents = _classify_intents('What are the pitfalls?')
        self.assertTrue({'keyword', 'chunk', 'vector'}.issubset(pitfall_intents))

    def test_build_article_graph_data(self):
        from unittest.mock import patch
        from a_agent.services.concept_graph import build_article_graph_data

        fake_graph = {
            'demo-article': {
                'title': 'Demo Article',
                'difficulty': 'intermediate',
                'prerequisites': [
                    {'slug': 'prereq-1', 'title': 'Prerequisite 1', 'key_concept': 'Foundations', 'bridge_summary': 'Summary'}
                ],
                'intermediate_insights': {
                    'production_pitfall': 'Watch for race conditions',
                    'tradeoff_challenge': 'Speed vs memory'
                },
                'next_milestones': [
                    {'slug': 'milestone-1', 'title': 'Milestone 1', 'reason': 'Advanced step'}
                ]
            }
        }
        with patch('a_agent.services.concept_graph.get_prerequisites_graph', return_value=fake_graph):
            article = SimpleNamespace(
                slug='demo-article',
                title='Demo Article',
                intro='Intro text',
                url='/articles/demo-article/',
                series_slug='',
            )
            data = build_article_graph_data(article)
            self.assertTrue(data['has_data'])
            self.assertEqual(data['difficulty'], 'intermediate')
            node_ids = [n['id'] for n in data['nodes']]
            self.assertIn('current', node_ids)
            self.assertIn('prereq_0', node_ids)
            self.assertIn('pitfall', node_ids)
            self.assertIn('tradeoff', node_ids)
            self.assertIn('milestone_0', node_ids)

            # Verify link connectivity
            link_pairs = [(l['source'], l['target']) for l in data['links']]
            self.assertIn(('prereq_0', 'current'), link_pairs)
            self.assertIn(('current', 'pitfall'), link_pairs)
            self.assertIn(('current', 'tradeoff'), link_pairs)
            self.assertIn(('current', 'milestone_0'), link_pairs)

    def test_quiz_url_reverses(self):
        from django.urls import reverse
        url = reverse('a_agent:article_quiz', kwargs={'article_id': 42})
        self.assertEqual(url, '/agent/article/42/quiz/')

    def test_quiz_options_markdown_rendering(self):
        from a_agent.templatetags.agent_extras import agent_markdown
        text = (
            "1. What is Python?\n"
            "A) A programming language\n"
            "B) A snake species only\n"
            "C) A database engine\n"
            "D) A cloud provider\n"
        )
        rendered = agent_markdown(text)
        self.assertIn('quiz-option-btn', rendered)
        self.assertIn('data-question="1"', rendered)
        self.assertIn('data-letter="A"', rendered)
        self.assertIn('A programming language', rendered)
        self.assertIn('data-letter="B"', rendered)

    def test_message_template_renders_mascot_avatar(self):
        from django.template.loader import render_to_string
        context = {
            'message': {
                'role': 'assistant',
                'content': 'Hello from CheeseO!',
                'tool_trace': [],
                'citations': [],
            }
        }
        rendered = render_to_string('a_agent/partials/message.html', context)
        self.assertIn('cheese.png', rendered)
        self.assertIn('CheeseO Mascot', rendered)
        self.assertNotIn('>AI<', rendered)

    def test_outside_blog_lookup_is_labeled_and_not_a_source(self):
        import json

        from a_agent.services.orchestrator import _outside_blog_reply
        from a_agent.tools.external_lookup import lookup_outside_the_blog, topic_from_query

        topic = topic_from_query(
            'Summarize the article about Kubernetes Helm chart deployments on this blog.'
        )
        self.assertEqual(topic, 'Kubernetes Helm chart deployments')

        web_html = (
            '<a class="result__a" href="https://duckduckgo.com/l/?uddg='
            'https%3A%2F%2Fkubernetes.io%2Fdocs%2Fconcepts%2Fworkloads%2Fcontrollers%2Fdeployment%2F">'
            'Kubernetes Deployments</a>'
            '<a class="result__snippet" href="https://kubernetes.io/docs/concepts/workloads/controllers/deployment/">'
            'A Deployment provides declarative updates for Pods and ReplicaSets.</a>'
        )
        pages = {
            'web': web_html,
            'duckduckgo': '{"AbstractText": "", "Heading": "", "AbstractURL": ""}',
            'search': json.dumps({'query': {'search': [{'title': 'Helm (package manager)'}]}}),
            'summary': json.dumps({
                'title': 'Helm (package manager)',
                'extract': 'Helm is a package manager for Kubernetes. It installs applications as charts.',
                'content_urls': {'desktop': {'page': 'https://en.wikipedia.org/wiki/Helm_(package_manager)'}},
            }),
        }

        def fetch(url):
            if 'html.duckduckgo.com' in url:
                return pages['web']
            if 'api.duckduckgo.com' in url:
                return pages['duckduckgo']
            if 'list=search' in url:
                return pages['search']
            return pages['summary']

        notes = lookup_outside_the_blog(
            'Summarize the article about Kubernetes Helm chart deployments on this blog.',
            fetch=fetch,
        )
        urls = [note['url'] for note in notes]
        self.assertIn('https://kubernetes.io/docs/concepts/workloads/controllers/deployment/', urls)
        self.assertIn('https://en.wikipedia.org/wiki/Helm_(package_manager)', urls)
        self.assertTrue(any(note['source_name'] == 'Wikipedia' for note in notes))
        reply = _outside_blog_reply(
            'Summarize the article about Kubernetes Helm chart deployments on this blog.',
            notes,
            is_chinese=False,
            model=None,
            use_model=False,
        )
        self.assertIn('I cannot find any article about that topic in the blog corpus.', reply)
        self.assertIn('not a lesson on this site', reply)
        self.assertIn('Helm is a package manager for Kubernetes', reply)
        self.assertIn('{{cite:2:https://en.wikipedia.org/wiki/Helm_(package_manager)|', reply)

        from a_agent.templatetags.agent_extras import agent_markdown
        from a_agent.tools.external_lookup import wants_several_sources
        rendered = str(agent_markdown(
            'Charts use YAML.{{cite:1:https://kubernetes.io/docs/concepts/workloads/controllers/deployment/'
            '|Helm%20is%20a%20package%20manager|helm.sh|It%20installs%20charts.}}'
        ))
        self.assertIn('class="ext-cite"', rendered)
        self.assertIn('target="_blank"', rendered)
        self.assertIn('>1</a>', rendered)
        self.assertIn('data-ext-title="Helm is a package manager"', rendered)
        self.assertIn('data-ext-excerpt="It installs charts."', rendered)
        self.assertFalse(wants_several_sources(
            'Summarize the article about Kubernetes Helm chart deployments on this blog.'
        ))
        self.assertTrue(wants_several_sources('请给我解释一下优必选这个公司，并判断，他们大数据开发工程师要不要去'))

        from a_agent.services.orchestrator import (
            _append_opened_lesson_note,
            _break_outside_paragraphs,
            _drop_outside_from_lesson,
            _external_source_trace,
            _mixed_outside_lead,
            _soften_outside_heading,
            _uncovered_outside_topic,
        )
        stiff = (
            'Git tracks changes.\n\n'
            '**Outside the blog** (not a lesson on this site):\n'
            'Helm is a package manager for Kubernetes.[1][2][3][4]'
        )
        self.assertEqual(
            _soften_outside_heading(stiff, 'what is Helm', False),
            'Git tracks changes.\n\nHelm is not a lesson on this site. It is a package manager for Kubernetes.[1][2][3][4]',
        )
        self.assertEqual(
            _drop_outside_from_lesson(
                'Git tracks changes. Helm, on the other hand, is a package manager. [1]',
                'what is Helm',
            ),
            'Git tracks changes.',
        )
        self.assertEqual(
            _mixed_outside_lead('Helm', False),
            '**About Helm** (not on this site, so here is a note from outside):',
        )
        self.assertIn('站内没有，站外给你解答', _mixed_outside_lead('Helm', True))
        self.assertEqual(
            _break_outside_paragraphs('Helm is a package manager. It installs charts.[1]'),
            'Helm is a package manager.\n\nIt installs charts.[1]',
        )
        opened = SimpleNamespace(article_id=7, article_title='What Is Git?')
        git_lesson = SimpleNamespace(article_id=7, title='What Is Git?')
        other_lesson = SimpleNamespace(article_id=8, title='Docker Volumes')
        self.assertEqual(
            _append_opened_lesson_note('Git tracks files.', [opened], [git_lesson], False),
            'Git tracks files.\n\nYou already opened **What Is Git?**.',
        )
        self.assertEqual(
            _append_opened_lesson_note('Git tracks files.', [opened], [other_lesson], False),
            'Git tracks files.',
        )
        git_hit = SimpleNamespace(
            title='What Is Git?',
            article_title='',
            snippet='A helm is mentioned only in the body, not the title.',
            content='helm',
            intro='',
        )
        self.assertEqual(
            _uncovered_outside_topic('What is Git, and what is Helm?', [git_hit]),
            'what is Helm',
        )
        self.assertEqual(_uncovered_outside_topic('What is Git?', [git_hit]), '')
        self.assertEqual(
            _uncovered_outside_topic(
                'I have just joined a team project, but I do not know how to use Git. '
                'Could you help me plan a learning path using lessons on this site,',
                [git_hit],
            ),
            '',
        )
        self.assertEqual(
            _uncovered_outside_topic(
                'I have just joined a team project, but I don\'t know how to use Git. '
                'Could you help me plana learning path using lessons on this site,',
                [git_hit],
            ),
            '',
        )
        self.assertEqual(
            _uncovered_outside_topic(
                'Please summarize this article in Chinese, and explain what a repository '
                'and a commit are using an example of a group assignment.',
                [git_hit],
            ),
            '',
        )
        from a_agent.services.orchestrator import (
            _is_direct_answer_query,
            _refers_to_opened_article,
        )
        self.assertTrue(_refers_to_opened_article('请用中文总结这篇文章'))
        self.assertTrue(_refers_to_opened_article(
            'Please summarize this article in Chinese, and explain what a repository is.'
        ))
        self.assertTrue(_is_direct_answer_query('What is version control?'))
        self.assertTrue(_is_direct_answer_query(
            '请用中文总结这篇文章，并用一个小组作业的例子解释什么是 repository 和 commit。'
        ))
        self.assertFalse(_is_direct_answer_query(
            'Could you help me plan a learning path using lessons on this site'
        ))
        self.assertEqual(
            _uncovered_outside_topic(
                'What is Git, and I just joined a team project?',
                [git_hit],
            ),
            '',
        )
        self.assertEqual(_uncovered_outside_topic('What does Helm do?', [git_hit]), 'helm')
        self.assertEqual(
            _uncovered_outside_topic('Could you plan a learning path for Helm?', [git_hit]),
            'helm',
        )
        from a_agent.tools.external_lookup import notes_about_the_question
        kept = notes_about_the_question(
            [
                {
                    'title': 'Helm',
                    'url': 'https://helm.sh/',
                    'excerpt': 'Helm is a package manager for Kubernetes.',
                },
                {
                    'title': 'Marshall Plan',
                    'url': 'https://example.com/marshall-plan',
                    'excerpt': 'The Marshall Plan was an American initiative enacted in 1948.',
                },
            ],
            'what is Helm',
        )
        self.assertEqual([item['title'] for item in kept], ['Helm'])
        kept_git = notes_about_the_question(
            [
                {'title': 'Git', 'url': 'https://git-scm.com/', 'excerpt': 'Git is a version control system.'},
                {
                    'title': 'Marshall Plan',
                    'url': 'https://example.com/marshall-plan',
                    'excerpt': 'The Marshall Plan was an American initiative enacted in 1948.',
                },
            ],
            'Git',
        )
        self.assertEqual([item['title'] for item in kept_git], ['Git'])
        plana_pages = notes_about_the_question(
            [
                {
                    'title': 'PLANA',
                    'url': 'https://example.com/plana',
                    'excerpt': 'PLANA is here to make your day trips easier.',
                },
            ],
            'plana',
        )
        self.assertEqual(plana_pages, [])
        from a_agent.services.orchestrator import _hits_for_path
        path = SimpleNamespace(topic='git', steps=[SimpleNamespace(article_id=7)])
        kept_hits = _hits_for_path(
            [
                SimpleNamespace(article_id=3, title='Supervised Learning in Depth', article_title=''),
                SimpleNamespace(article_id=9, title='Rebase Branch – Git Rebase', article_title=''),
                SimpleNamespace(article_id=7, title='What Is Git?', article_title=''),
            ],
            path,
        )
        self.assertEqual([hit.article_id for hit in kept_hits], [9, 7])
        from a_agent.services.orchestrator import _ensure_path_lessons
        lesson_path = SimpleNamespace(
            title='Git & Version Control Starter Path',
            steps=[
                SimpleNamespace(
                    order=1,
                    title='Chapter 1. Git & GitHub Overview',
                    url='https://example.com/git-overview',
                    note='Start here',
                ),
            ],
        )
        fixed = _ensure_path_lessons(
            'Click the link below:\n\n[Git & Version Control Starter Path](#path)',
            lesson_path,
            False,
        )
        self.assertNotIn('Starter Path](', fixed)
        self.assertIn('https://example.com/git-overview', fixed)
        self.assertIn('Chapter 1. Git & GitHub Overview', fixed)
        sources = _external_source_trace(notes)['sources']
        self.assertTrue(all(item['url'].startswith('https://') for item in sources))
        self.assertTrue(all(item.get('host') for item in sources))
        self.assertGreaterEqual(len(sources), 2)

        from a_agent.services.orchestrator import _question_leaves_this_article
        cicd = SimpleNamespace(title='The CI/CD Pipeline That Was Lying to Us: A Deploy Debugging Story')
        self.assertEqual(
            _question_leaves_this_article(
                'Summarize the article about Kubernetes Helm chart deployments on this blog.',
                cicd,
            ),
            'Kubernetes Helm chart deployments',
        )
        self.assertEqual(_question_leaves_this_article('Summarize this article.', cicd), '')
        self.assertEqual(_question_leaves_this_article('What are the main points?', cicd), '')

    def test_scoped_retrieval_helpers_and_term_extraction(self):
        from a_agent.tools.article_scope import _extract_article_headings, is_summary_query
        from a_agent.tools.chunk_search import _extract_terms_and_phrases

        self.assertTrue(is_summary_query('Summarize this article in five bullet points.'))
        self.assertFalse(is_summary_query('According to this article, what does MCP stand for?'))

        terms, _ = _extract_terms_and_phrases(
            'According to this article, what does MCP stand for? Quote the expansion exactly.'
        )
        self.assertEqual(terms, ['mcp'])

        headings = _extract_article_headings('<h2>1. AI Agent</h2><h2>8. MCP: Model Context Protocol</h2>')
        self.assertEqual(headings, ['1. AI Agent', '8. MCP: Model Context Protocol'])

    def test_reading_list_action_scope_and_ordinal_resolution(self):
        from a_agent.services.orchestrator import (
            _article_ids_for_action,
            _extract_ordinal_index,
            _is_multi_article_request,
        )

        self.assertEqual(_extract_ordinal_index('Add the second article you recommended'), 1)
        self.assertIsNone(_extract_ordinal_index(
            'Summarize the article about Kubernetes Helm chart deployments on this blog.'
        ))
        self.assertEqual(_extract_ordinal_index('把你剛才推薦的第一篇加入清單'), 0)
        self.assertEqual(_extract_ordinal_index('Remove the 3rd article'), 2)
        self.assertIsNone(_extract_ordinal_index('Add this article to my reading list'))

        self.assertFalse(_is_multi_article_request('Add "20 Agentic AI Terms" to my reading list'))
        self.assertFalse(_is_multi_article_request('Remove only "20 Agentic AI Terms" from my reading list'))
        self.assertTrue(_is_multi_article_request('Add all 3 articles to my reading list'))

        hits = [
            SimpleNamespace(article_id=21),
            SimpleNamespace(article_id=18),
            SimpleNamespace(article_id=19),
        ]
        self.assertEqual(_article_ids_for_action(hits, [], []), [21])
        self.assertEqual(_article_ids_for_action(hits, [], [], limit=3), [21, 18, 19])

    def test_markdown_sanitization_and_simplified_chinese_conversion(self):
        from a_agent.services.language import wants_chinese
        from a_agent.services.orchestrator import (
            _ensure_simplified_chinese,
            _ensure_traditional_chinese,
            _is_no_match_response,
            _sanitize_markdown_output,
        )

        self.assertTrue(wants_chinese(
            '请用中文总结这篇文章，并用一个小组作业的例子解释什么是 repository 和 commit。'
        ))
        self.assertTrue(wants_chinese(
            'Please summarize this article in Chinese, and explain what a repository and a commit are.'
        ))
        self.assertTrue(wants_chinese('Summarize this article in Chinese'))
        self.assertFalse(wants_chinese('What is version control?'))
        from a_agent.services.orchestrator import (
            _chinese_unavailable_notice,
            _mostly_english,
        )
        self.assertTrue(_mostly_english(
            'What Is Version Control? Grasp the concepts of repository and commit in Git. '
            'When coding, you need to manage several files which are dependent on one another.'
        ))
        self.assertFalse(_mostly_english('这是一段完整的中文总结，没有大段英文原文。'))
        notice = _chinese_unavailable_notice('What Is Version Control?')
        self.assertIn('暂时无法生成中文回答', notice)
        self.assertNotIn('Core Takeaway', notice)
        from a_agent.services.orchestrator import _filter_hits_to_query, _format_citations
        mixed = [
            SimpleNamespace(
                article_id=29,
                article_title='What Is Version Control?',
                title='',
                tags='git',
                content='Version control tracks changes.',
                article_url='/vc/',
            ),
            SimpleNamespace(
                article_id=88,
                article_title='I Built a Version Bump Tool in Rust',
                title='',
                tags='rust',
                content='A faster version bump CLI.',
                article_url='/rust/',
            ),
            SimpleNamespace(
                article_id=99,
                article_title='Wagtail CMS Quick Start',
                title='',
                tags='cms',
                content='Publish pages with Wagtail.',
                article_url='/wagtail/',
            ),
        ]
        kept = _filter_hits_to_query(mixed, 'What is version control?')
        self.assertEqual([hit.article_id for hit in kept], [29])
        cites = _format_citations([], [], kept)
        self.assertEqual([c['title'] for c in cites], ['What Is Version Control?'])

        dirty = 'Here is [Key Concepts](#concepts) and a truncated link [Read More](https://example.com/unfin'
        cleaned = _sanitize_markdown_output(dirty)
        self.assertIn('**Key Concepts**', cleaned)
        self.assertIn('**Read More**', cleaned)
        self.assertNotIn('](#', cleaned)
        self.assertNotIn('https://example.com/unfin', cleaned)

        unclosed_fence = '```bash\ndocker compose up -d'
        self.assertTrue(_sanitize_markdown_output(unclosed_fence).endswith('```'))

        trad_input = '透過設定預設伺服器和網路程式碼，理解人工智慧術語與協定。`程式碼`'
        simp_output = _ensure_simplified_chinese(trad_input)
        for expected in ('通过', '配置', '默认', '服务器', '网络', '代码', '人工智能', '术语', '协议'):
            self.assertIn(expected, simp_output)
        self.assertIn('`程式碼`', simp_output)

        simp = '通过配置默认服务器和网络代码，理解人工智能术语与协议。'
        trad = _ensure_traditional_chinese(simp)
        for expected in ('透過', '設定', '預設', '伺服器', '網路', '程式碼', '人工智慧', '術語', '協定'):
            self.assertIn(expected, trad)

        self.assertTrue(_is_no_match_response('I cannot find any article about that topic in the blog corpus.'))
        self.assertTrue(_is_no_match_response('抱歉，找不到相关文章。'))
        self.assertTrue(_is_no_match_response('抱歉，找不到相關文章。'))
        self.assertFalse(_is_no_match_response('MCP stands for Model Context Protocol.'))

    def test_editable_comment_draft_and_target_articles_in_message_template(self):
        comment_ctx = {
            'message': {
                'role': 'assistant',
                'content': 'I drafted a comment for you:',
                'tool_trace': [],
                'citations': [],
                'pending_action': {
                    'action_id': 99,
                    'action_type': 'post_comment',
                    'article_title': 'What Is Git?',
                    'draft_content': 'Thanks for this Git guide! Could you explain what an API is?',
                },
            }
        }
        rendered_comment = render_to_string('a_agent/partials/message.html', comment_ctx)
        self.assertIn('<textarea', rendered_comment)
        self.assertIn('name="draft_content"', rendered_comment)
        self.assertIn('Could you explain what an API is?', rendered_comment)

        list_ctx = {
            'message': {
                'role': 'assistant',
                'content': 'Ready to save:',
                'tool_trace': [],
                'citations': [],
                'pending_action': {
                    'action_id': 100,
                    'action_type': 'add_to_reading_list',
                    'articles': [
                        {'article_id': 21, 'title': '20 Agentic AI Terms Every Developer Should Know', 'url': '/blog/20-terms/'},
                    ],
                },
            }
        }
        rendered_list = render_to_string('a_agent/partials/message.html', list_ctx)
        self.assertIn('Target article(s) to save (1)', rendered_list)
        self.assertIn('20 Agentic AI Terms Every Developer Should Know', rendered_list)

    def test_comment_intent_extraction_and_session_urls(self):
        from django.urls import reverse
        from a_agent.tools.comment_draft import _extract_comment_intent

        intent = _extract_comment_intent('help me to write a comment to ask what is API')
        self.assertEqual(intent, 'what is API')
        self.assertEqual(
            reverse('a_agent:article_reset_session', kwargs={'article_id': 21}),
            '/agent/article/21/reset/',
        )
        self.assertEqual(
            reverse('a_agent:clear_all_sessions'),
            '/agent/session/clear-all/',
        )

    def test_series_first_article_has_no_prerequisites(self):
        from a_agent.services.concept_graph import build_article_graph_data
        from a_agent.services.learning_analysis import is_series_first_article, load_store
        from a_agent.services.navigator import calculate_article_readiness

        store = load_store()
        for slug, series, title in (
            ('git-chapter-1-git-github-overview', 'git', 'Chapter 1. Git & GitHub Overview'),
            ('docker-chapter-1-docker-introduction', 'docker', 'Chapter 1. Docker Introduction'),
        ):
            rec = store['articles'].get(slug, {})
            self.assertEqual(rec.get('prerequisite_concepts'), [])
            self.assertEqual(rec.get('matches'), [])

            mock_article = SimpleNamespace(
                slug=slug,
                title=title,
                intro='Series Lesson 1',
                url=f'/blog/series/{slug}/',
                series_slug=series,
                chapter_number=1,
                lesson_number=1,
                get_prev_lesson=lambda: None,
                get_next_lesson=lambda: None,
            )
            self.assertTrue(is_series_first_article(mock_article))
            readiness = calculate_article_readiness(None, slug)
            self.assertEqual(readiness['gaps'], [])
            self.assertEqual(readiness['ready_prereqs'], [])

            graph_data = build_article_graph_data(mock_article)
            self.assertEqual(graph_data['prereq_count'], 0)
            prereq_nodes = [n for n in graph_data['nodes'] if n['type'] == 'prerequisite']
            self.assertEqual(prereq_nodes, [])

    def test_cloudflare_model_switcher_and_acyclic_learning_analysis(self):
        from a_agent.config import get_model_options, normalize_model
        from a_agent.services.learning_analysis import load_store

        with self.settings(AGENT_LLM_PROVIDER='cloudflare'):
            options = get_model_options()
            self.assertTrue(any(o['id'] == '@cf/qwen/qwen2.5-coder-32b-instruct' for o in options))
            self.assertEqual(normalize_model('qwen2.5vl:7b'), '@cf/qwen/qwen2.5-coder-32b-instruct')
            self.assertEqual(
                normalize_model('@cf/meta/llama-3.3-70b-instruct-fp8-fast'),
                '@cf/meta/llama-3.3-70b-instruct-fp8-fast',
            )

        store = load_store()
        adj = {s: [m['slug'] for m in r.get('matches', [])] for s, r in store['articles'].items()}
        visited = {}
        cycles = []

        def dfs(u, path):
            visited[u] = 1
            for v in adj.get(u, []):
                if visited.get(v) == 1:
                    cycles.append(path + [v])
                elif visited.get(v, 0) == 0:
                    dfs(v, path + [v])
            visited[u] = 2

        for s in adj:
            if visited.get(s, 0) == 0:
                dfs(s, [s])
        self.assertEqual(cycles, [])
        self.assertGreater(len(store.get('bridges', {})), 100)
