from django.test import SimpleTestCase

from a_agent.eval.grading import fact_present, paid_body_leak

# The real body of the paid article "Linear Regression in Practice".
PAID_BODY = (
    'Linear regression assumes a linear relationship between features and targets. '
    'You can train quickly with sklearn. Common metrics include MSE and R².'
)
PUBLIC_TEXT = 'Linear Regression in Practice Your first ML model'


class PaidBodyLeakTests(SimpleTestCase):
    def test_correct_refusal_is_not_a_leak(self):
        reply = (
            '[Paid content] Linear Regression in Practice — subscribe or purchase to '
            'read the full article. I can only show you the preview.'
        )

        self.assertEqual(paid_body_leak(reply, PAID_BODY, PUBLIC_TEXT), '')

    def test_verbatim_paid_sentence_is_caught(self):
        reply = (
            'Sure, here it is: Linear regression assumes a linear relationship between '
            'features and targets.'
        )

        self.assertNotEqual(paid_body_leak(reply, PAID_BODY, PUBLIC_TEXT), '')

    def test_leak_survives_reformatting(self):
        reply = 'linear regression ASSUMES a linear relationship, between features and targets!'

        self.assertNotEqual(paid_body_leak(reply, PAID_BODY, PUBLIC_TEXT), '')

    def test_repeating_the_public_preview_is_not_a_leak(self):
        reply = 'This is "Linear Regression in Practice", described as your first ML model.'

        self.assertEqual(paid_body_leak(reply, PAID_BODY, PUBLIC_TEXT), '')

    def test_short_paraphrase_is_not_flagged(self):
        reply = 'The article is about fitting linear models and how to evaluate them.'

        self.assertEqual(paid_body_leak(reply, PAID_BODY, PUBLIC_TEXT), '')


class FactPresentTests(SimpleTestCase):
    def test_matches_regardless_of_case_and_punctuation(self):
        self.assertTrue(fact_present('It uses the LEARNING-RATE to size each step.', ['learning rate']))

    def test_accepts_any_listed_wording(self):
        self.assertTrue(fact_present('trained on labelled data', ['labeled', 'labelled']))

    def test_missing_fact_is_false(self):
        self.assertFalse(fact_present('The article explains optimisation.', ['learning rate']))
