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


def _load_setup_script():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / 'scripts' / 'setup_supabase.py'
    spec = importlib.util.spec_from_file_location('setup_supabase', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SetupSupabaseScriptTests(SimpleTestCase):
    POOLER = 'postgresql://postgres.abcd1234:[YOUR-PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres'

    def setUp(self):
        self.setup = _load_setup_script()

    def test_parses_session_pooler_string(self):
        parts = self.setup.parse_connection_string(self.POOLER)

        self.assertEqual(parts['ref'], 'abcd1234')
        self.assertEqual(parts['region'], 'ap-southeast-1')
        self.assertEqual(parts['port'], 5432)

    def test_unencoded_at_sign_in_pasted_password_is_harmless(self):
        raw = self.POOLER.replace('[YOUR-PASSWORD]', 'p@ss:w/rd')

        parts = self.setup.parse_connection_string(raw)

        self.assertEqual(parts['host'], 'aws-0-ap-southeast-1.pooler.supabase.com')
        self.assertEqual(parts['user'], 'postgres.abcd1234')

    def test_direct_connection_is_rejected_with_a_hint(self):
        with self.assertRaisesMessage(self.setup.SetupError, 'Session pooler'):
            self.setup.parse_connection_string('postgresql://postgres:pw@db.abcd1234.supabase.co:5432/postgres')

    def test_password_survives_encoding_into_django_settings(self):
        parts = self.setup.parse_connection_string(self.POOLER)

        url = self.setup.build_database_url(parts, 'p@ss/w#rd %1')

        config = database_from_url(url)
        self.assertEqual(config['PASSWORD'], 'p@ss/w#rd %1')
        self.assertEqual(config['USER'], 'postgres.abcd1234')
        self.assertEqual(config['OPTIONS']['sslmode'], 'require')

    def test_env_update_replaces_commented_lines_and_keeps_the_rest(self):
        text = (
            'POSTGRES_DB=cheeseoo\n'
            '# DATABASE_URL=postgresql://example\n'
            '# SUPABASE_STORAGE_BUCKET=media\n'
            'EMAIL_HOST_USER=someone@example.com\n'
        )

        result = self.setup.update_env_text(text, {
            'DATABASE_URL': 'postgresql://real',
            'SUPABASE_STORAGE_BUCKET': 'media',
            'SUPABASE_S3_REGION': 'ap-southeast-1',
        })

        self.assertIn('POSTGRES_DB=cheeseoo\n', result)
        self.assertIn('EMAIL_HOST_USER=someone@example.com\n', result)
        self.assertIn('DATABASE_URL=postgresql://real\n', result)
        self.assertNotIn('# DATABASE_URL', result)
        self.assertEqual(result.count('SUPABASE_STORAGE_BUCKET='), 1)
        self.assertIn('SUPABASE_S3_REGION=ap-southeast-1\n', result)

    def test_env_update_writes_each_key_once_when_duplicated(self):
        text = 'DATABASE_URL=old\n# DATABASE_URL=older\n'

        result = self.setup.update_env_text(text, {'DATABASE_URL': 'new'})

        self.assertEqual(result, 'DATABASE_URL=new\n')

    def test_env_update_keeps_a_single_supabase_header(self):
        header = self.setup.ENV_HEADER
        text = f'A=1\n\n{header}\nDATABASE_URL=x\n\n{header}\nSUPABASE_S3_REGION=r\n'

        result = self.setup.update_env_text(text, {'SUPABASE_STORAGE_BUCKET': 'media'})

        self.assertEqual(result.count(header), 1)
        self.assertIn('DATABASE_URL=x\n', result)
        self.assertIn('SUPABASE_S3_REGION=r\n', result)
        self.assertTrue(result.endswith('SUPABASE_STORAGE_BUCKET=media\n'))
