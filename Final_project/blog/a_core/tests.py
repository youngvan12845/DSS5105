from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings

from a_agent.models import ChatMessage, ChatSession
from a_agent.services.llm import _build_user_message

from .cloud_config import database_from_url, supabase_media_storage

SUPABASE_ENV = {
    'SUPABASE_S3_ENDPOINT': 'https://abcd1234.supabase.co/storage/v1/s3',
    'SUPABASE_S3_REGION': 'ap-southeast-1',
    'SUPABASE_S3_ACCESS_KEY_ID': 'key-id',
    'SUPABASE_S3_SECRET_ACCESS_KEY': 'secret',
}


class DatabaseFromUrlTests(SimpleTestCase):
    def test_local_url_does_not_force_ssl(self):
        config = database_from_url('postgresql://postgres@localhost:5432/cheeseoo')

        self.assertEqual(config['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(config['NAME'], 'cheeseoo')
        self.assertNotIn('sslmode', config.get('OPTIONS', {}))

    def test_remote_url_requires_ssl(self):
        config = database_from_url(
            'postgresql://postgres.abcd1234:pw@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres'
        )

        self.assertEqual(config['OPTIONS']['sslmode'], 'require')
        self.assertEqual(config['USER'], 'postgres.abcd1234')
        self.assertFalse(config.get('DISABLE_SERVER_SIDE_CURSORS'))

    def test_explicit_sslmode_in_url_wins(self):
        config = database_from_url('postgresql://u:pw@db.example.com:5432/app?sslmode=verify-full')

        self.assertEqual(config['OPTIONS']['sslmode'], 'verify-full')

    def test_transaction_pooler_disables_persistent_connections_and_cursors(self):
        config = database_from_url(
            'postgresql://postgres.abcd1234:pw@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres'
        )

        self.assertEqual(config['CONN_MAX_AGE'], 0)
        self.assertTrue(config['DISABLE_SERVER_SIDE_CURSORS'])

    def test_url_encoded_password_is_decoded(self):
        config = database_from_url('postgresql://u:p%40ss%2Fword@db.example.com:5432/app')

        self.assertEqual(config['PASSWORD'], 'p@ss/word')


class SupabaseMediaStorageTests(SimpleTestCase):
    def test_not_configured_returns_none(self):
        self.assertIsNone(supabase_media_storage({}))

    def test_builds_s3_storage_with_public_bucket_url(self):
        storage = supabase_media_storage(SUPABASE_ENV)
        options = storage['OPTIONS']

        self.assertEqual(storage['BACKEND'], 'storages.backends.s3.S3Storage')
        self.assertEqual(options['bucket_name'], 'media')
        self.assertEqual(options['endpoint_url'], SUPABASE_ENV['SUPABASE_S3_ENDPOINT'])
        self.assertEqual(options['custom_domain'], 'abcd1234.supabase.co/storage/v1/object/public/media')
        self.assertEqual(options['url_protocol'], 'https:')
        self.assertFalse(options['file_overwrite'])

    def test_file_url_points_at_public_object(self):
        from storages.backends.s3 import S3Storage

        storage = S3Storage(**supabase_media_storage(SUPABASE_ENV)['OPTIONS'])

        self.assertEqual(
            storage.url('original_images/cat.png'),
            'https://abcd1234.supabase.co/storage/v1/object/public/media/original_images/cat.png',
        )

    def test_rejects_endpoint_without_s3_path(self):
        with self.assertRaises(ImproperlyConfigured):
            supabase_media_storage({**SUPABASE_ENV, 'SUPABASE_S3_ENDPOINT': 'https://abcd1234.supabase.co'})


class NoPathStorage(Storage):
    """Keeps files in memory and, like S3-style storage, has no local path."""

    def __init__(self):
        self.files = {}

    def _save(self, name, content):
        self.files[name] = content.read()
        return name

    def _open(self, name, mode='rb'):
        return ContentFile(self.files[name], name=name)

    def exists(self, name):
        return name in self.files

    def size(self, name):
        return len(self.files[name])

    def delete(self, name):
        self.files.pop(name, None)

    def url(self, name):
        return f'https://storage.example/{name}'


@override_settings(STORAGES={
    'default': {'BACKEND': 'a_core.tests.NoPathStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class ChatImageWithoutLocalPathTests(TestCase):
    """Remote storage has no filesystem path; the LLM must still get the image."""

    def test_uploaded_image_is_sent_as_data_url(self):
        user = User.objects.create_user('bob', 'bob@example.com', 'pw')
        session = ChatSession.objects.create(user=user, title='t')
        message = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_USER,
            content='what is this?',
            image=SimpleUploadedFile('shot.png', b'\x89PNG fake bytes', content_type='image/png'),
        )

        with self.assertRaises(NotImplementedError):
            message.image.path

        content = _build_user_message('what is this?', message.image)

        self.assertEqual(content[0], {'type': 'text', 'text': 'what is this?'})
        self.assertTrue(content[1]['image_url']['url'].startswith('data:image/png;base64,'))

    def test_missing_image_falls_back_to_text_only(self):
        self.assertEqual(_build_user_message('hi', None), 'hi')
