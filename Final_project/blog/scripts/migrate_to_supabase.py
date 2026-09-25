"""
Copy the local PostgreSQL data and uploaded media into Supabase.

Run once, by one person, after filling DATABASE_URL (and the SUPABASE_S3_*
variables for media) in .env — see SUPABASE.md:

    .venv/bin/python scripts/migrate_to_supabase.py

The source is the local database described by the POSTGRES_* variables
(or SOURCE_DATABASE_URL). The target must be empty; the copy runs in a single
transaction, so a failure leaves the target untouched.
"""

import glob
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'a_core.settings')

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BASE_DIR / '.env')

PG_BIN_CANDIDATES = [
    '/opt/homebrew/opt/postgresql@*/bin',
    '/usr/local/opt/postgresql@*/bin',
    '/Library/PostgreSQL/*/bin',
]
# Dump lines that fail on the target: every database already has the public
# schema (and on Supabase our role does not own it), and transaction_timeout
# only exists on PostgreSQL 17+.
SKIPPED_DUMP_STATEMENTS = (
    'CREATE SCHEMA public;',
    'COMMENT ON SCHEMA public ',
    'SET transaction_timeout',
)
# Tables compared after the copy as a sanity check.
CHECK_TABLES = ['auth_user', 'wagtailcore_page', 'a_blog_articlepage', 'a_agent_articlechunk']
# Supabase exposes the public schema through its Data API to these roles.
# Django connects directly, so they should not see Django's tables.
REVOKE_SUPABASE_API_ROLES = """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
    REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;
    RAISE NOTICE 'Revoked Data API access (anon, authenticated) on the public schema.';
  END IF;
END $$;
"""


def fail(message):
    print(f'Error: {message}', file=sys.stderr)
    sys.exit(1)


def find_pg_tool(name):
    explicit = os.environ.get('PG_BIN')
    if explicit and (Path(explicit) / name).exists():
        return str(Path(explicit) / name)
    if found := shutil.which(name):
        return found
    for pattern in PG_BIN_CANDIDATES:
        for directory in sorted(glob.glob(pattern), reverse=True):
            if (Path(directory) / name).exists():
                return str(Path(directory) / name)
    fail(f'{name} not found. Install PostgreSQL client tools or set PG_BIN to their folder.')


def source_database_url():
    if url := os.environ.get('SOURCE_DATABASE_URL', '').strip():
        return url
    user = quote(os.environ.get('POSTGRES_USER', 'postgres'), safe='')
    password = quote(os.environ.get('POSTGRES_PASSWORD', ''), safe='')
    host = os.environ.get('POSTGRES_HOST', 'localhost')
    port = os.environ.get('POSTGRES_PORT', '5432')
    name = os.environ.get('POSTGRES_DB', 'cheeseoo')
    auth = f'{user}:{password}' if password else user
    return f'postgresql://{auth}@{host}:{port}/{name}'


def describe(url):
    parts = urlparse(url)
    return f'{parts.hostname}:{parts.port or 5432}{parts.path}'


def psql_value(psql, url, sql):
    result = subprocess.run(
        [psql, url, '-X', '-tAc', sql], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def copy_database(source, target):
    pg_dump = find_pg_tool('pg_dump')
    psql = find_pg_tool('psql')

    if describe(source) == describe(target):
        fail('source and target are the same database.')

    tables_in_target = int(psql_value(
        psql, target, "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'"
    ))
    if tables_in_target:
        fail(f'target already has {tables_in_target} tables in the public schema. '
             'This script only copies into an empty database.')

    with tempfile.TemporaryDirectory() as tmp:
        dump_file = Path(tmp) / 'dump.sql'
        print(f'Dumping {describe(source)} ...')
        subprocess.run(
            [pg_dump, source, '--schema=public', '--no-owner', '--no-privileges',
             '--file', str(dump_file)],
            check=True,
        )
        lines = dump_file.read_text().splitlines(keepends=True)
        dump_file.write_text(''.join(
            line for line in lines if not line.startswith(SKIPPED_DUMP_STATEMENTS)
        ))

        print(f'Restoring into {describe(target)} ...')
        subprocess.run(
            [psql, target, '-X', '-q', '-v', 'ON_ERROR_STOP=1', '--single-transaction',
             '-f', str(dump_file)],
            check=True,
        )

    subprocess.run([psql, target, '-X', '-q', '-c', REVOKE_SUPABASE_API_ROLES], check=True)

    print('Row counts (source -> target):')
    for table in CHECK_TABLES:
        sql = f'SELECT count(*) FROM {table}'
        print(f'  {table}: {psql_value(psql, source, sql)} -> {psql_value(psql, target, sql)}')


def upload_media():
    # settings.py only switches to Supabase Storage when this is set.
    if not os.environ.get('SUPABASE_S3_ENDPOINT', '').strip():
        print('Media: SUPABASE_S3_* not set, skipping upload (files stay in media/).')
        return

    import django

    django.setup()
    from django.conf import settings
    from django.core.files import File
    from django.core.files.storage import default_storage

    media_root = Path(settings.MEDIA_ROOT)
    uploaded = skipped = 0
    for path in sorted(p for p in media_root.rglob('*') if p.is_file()):
        name = path.relative_to(media_root).as_posix()
        if default_storage.exists(name):
            skipped += 1
            continue
        with path.open('rb') as fh:
            default_storage.save(name, File(fh, name=name))
        uploaded += 1
    print(f'Media: uploaded {uploaded} files, {skipped} already present.')


def main():
    target = os.environ.get('DATABASE_URL', '').strip()
    if not target:
        fail('DATABASE_URL is not set. Add the Supabase connection string to .env first.')

    copy_database(source_database_url(), target)
    upload_media()
    print('Done. Restart the site with ./scripts/run_local.sh to use the new database.')


if __name__ == '__main__':
    main()
