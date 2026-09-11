from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from .utils import RESET_MAX_ATTEMPTS


class PasswordResetCodeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('alice', 'alice@example.com', 'old-pass-123')

    def _request_reset(self, email='alice@example.com'):
        return self.client.post(reverse('password-reset-request'), {'email': email})

    def _submit_code(self, code, email='alice@example.com'):
        return self.client.post(
            reverse('password-reset-verify'),
            {'email': email, 'verification_code': code},
        )

    def _real_code(self, email='alice@example.com'):
        return cache.get(f'password_reset_code_{email}')

    def _wrong_code(self):
        real = self._real_code()
        return '000000' if real != '000000' else '111111'

    def test_correct_code_within_attempt_limit_is_accepted(self):
        self._request_reset()
        for _ in range(RESET_MAX_ATTEMPTS - 1):
            self._submit_code(self._wrong_code())

        response = self._submit_code(self._real_code())

        self.assertRedirects(response, reverse('password-reset-confirm'), fetch_redirect_response=False)

    def test_code_is_invalidated_after_too_many_wrong_attempts(self):
        self._request_reset()
        real = self._real_code()
        for _ in range(RESET_MAX_ATTEMPTS):
            self._submit_code(self._wrong_code())

        response = self._submit_code(real)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self._real_code())

    def test_unregistered_email_looks_the_same_as_registered(self):
        registered = self._request_reset()
        cache.clear()
        unregistered = self._request_reset('nobody@example.com')

        self.assertRedirects(unregistered, reverse('password-reset-verify'), fetch_redirect_response=False)
        self.assertEqual(registered['Location'], unregistered['Location'])
        self.assertEqual(len(mail.outbox), 1)

    def test_repeat_request_within_cooldown_does_not_send_another_code(self):
        self._request_reset()
        first_code = self._real_code()

        self._request_reset()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(self._real_code(), first_code)

    def test_new_password_can_be_set_after_valid_code(self):
        self._request_reset()
        self._submit_code(self._real_code())

        self.client.post(
            reverse('password-reset-confirm'),
            {'new_password': 'N3w-strong-pass!', 'confirm_password': 'N3w-strong-pass!'},
        )

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('N3w-strong-pass!'))
