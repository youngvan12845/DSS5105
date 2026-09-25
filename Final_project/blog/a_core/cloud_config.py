"""
Optional cloud settings, driven by environment variables.

- DATABASE_URL: use a hosted PostgreSQL such as Supabase instead of the
  POSTGRES_* variables.
- SUPABASE_S3_*: store uploaded media (Wagtail images, avatars, chat
  uploads) in Supabase Storage instead of the local media/ folder.

When neither is set, settings.py keeps the local-only defaults.
"""

from django.core.exceptions import ImproperlyConfigured
import dj_database_url

LOCAL_HOSTS = {'', 'localhost', '127.0.0.1', '::1'}
# Supabase's transaction pooler listens on 6543; the session pooler and
# direct connections use 5432.
SUPABASE_TRANSACTION_POOLER_PORT = 6543
SUPABASE_S3_PATH = '/storage/v1/s3'


def database_from_url(url):
    """Build a Django DATABASES entry from a postgres:// connection URL."""
    config = dj_database_url.parse(url, conn_max_age=60, conn_health_checks=True)

    if (config.get('HOST') or '').lower() not in LOCAL_HOSTS:
        # An explicit ?sslmode=... in the URL still wins.
        config.setdefault('OPTIONS', {}).setdefault('sslmode', 'require')

    if str(config.get('PORT')) == str(SUPABASE_TRANSACTION_POOLER_PORT):
        # Transaction pooling hands each transaction to a different server
        # connection, which breaks persistent connections and server-side
        # cursors.
        config['CONN_MAX_AGE'] = 0
        config['DISABLE_SERVER_SIDE_CURSORS'] = True

    return config


def supabase_media_storage(env):
    """Return a STORAGES['default'] entry for Supabase Storage, or None if not configured."""
    endpoint = env.get('SUPABASE_S3_ENDPOINT', '').strip().rstrip('/')
    if not endpoint:
        return None
    if not endpoint.endswith(SUPABASE_S3_PATH):
        raise ImproperlyConfigured(
            'SUPABASE_S3_ENDPOINT should look like '
            f'https://<project-ref>.supabase.co{SUPABASE_S3_PATH}'
        )

    bucket = env.get('SUPABASE_STORAGE_BUCKET', '').strip() or 'media'
    project_url = endpoint[: -len(SUPABASE_S3_PATH)]
    # Files are served from the bucket's public URL, so the bucket must be public.
    public_base = f'{project_url}/storage/v1/object/public/{bucket}'

    return {
        'BACKEND': 'storages.backends.s3.S3Storage',
        'OPTIONS': {
            'bucket_name': bucket,
            'endpoint_url': endpoint,
            'region_name': env.get('SUPABASE_S3_REGION', '').strip(),
            'access_key': env.get('SUPABASE_S3_ACCESS_KEY_ID', '').strip(),
            'secret_key': env.get('SUPABASE_S3_SECRET_ACCESS_KEY', '').strip(),
            'addressing_style': 'path',
            'signature_version': 's3v4',
            'default_acl': None,
            'file_overwrite': False,
            'querystring_auth': False,
            'url_protocol': public_base.split('://', 1)[0] + ':',
            'custom_domain': public_base.split('://', 1)[1],
        },
    }
