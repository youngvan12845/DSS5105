"""
Connect this checkout to a Supabase project, interactively.

Asks for the Session pooler connection string, the database password and the
Storage S3 keys, checks that each one works, and writes them to .env.
Secrets are typed at hidden prompts and only ever written to .env. Database settings
are saved as soon as the connection works, so a later storage problem does not
mean starting over.

    .venv/bin/python scripts/setup_supabase.py
"""

from __future__ import annotations

import getpass
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import quote

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / '.env'
PASSWORD_PLACEHOLDER = '[YOUR-PASSWORD]'
ENV_HEADER = '# Supabase (written by scripts/setup_supabase.py)'
ENV_KEYS = (
    'DATABASE_URL',
    'SUPABASE_S3_ENDPOINT',
    'SUPABASE_S3_REGION',
    'SUPABASE_S3_ACCESS_KEY_ID',
    'SUPABASE_S3_SECRET_ACCESS_KEY',
    'SUPABASE_STORAGE_BUCKET',
)
CONNECTION_RE = re.compile(
    r'^(?P<scheme>postgres(?:ql)?)://(?P<userinfo>.+)@(?P<host>[^@/:]+):(?P<port>\d+)/(?P<db>[\w-]+)'
)
POOLER_REGION_RE = re.compile(r'aws-\d+-(?P<region>[a-z0-9-]+)\.pooler\.supabase\.com$')


class SetupError(Exception):
    pass


def parse_connection_string(raw: str) -> dict:
    """Split a Supabase connection string into user, host, port, database, ref and region.

    The password part is ignored (it is asked for separately), so a string that
    still contains [YOUR-PASSWORD] or an unencoded password both work.
    """
    # Split on the last "@" so an unencoded "@" in a pasted password is harmless.
    match = CONNECTION_RE.match(raw.strip())
    if not match:
        raise SetupError(
            'That does not look like a connection string. It should start with '
            'postgresql:// and end with /postgres.'
        )

    user = match['userinfo'].split(':', 1)[0]
    host = match['host']
    port = int(match['port'])

    if host.startswith('db.') and host.endswith('.supabase.co'):
        raise SetupError(
            'This is the direct connection, which is IPv6-only on the free plan. '
            'In Supabase → Connect, pick "Session pooler" and copy that string instead.'
        )
    region_match = POOLER_REGION_RE.search(host)
    if not region_match or not user.startswith('postgres.'):
        raise SetupError('Expected a Session pooler string (host ends in pooler.supabase.com).')

    return {
        'scheme': match['scheme'],
        'user': user,
        'host': host,
        'port': port,
        'database': match['db'],
        'ref': user.split('.', 1)[1],
        'region': region_match['region'],
    }


def build_database_url(parts: dict, password: str) -> str:
    return (
        f"postgresql://{quote(parts['user'], safe='')}:{quote(password, safe='')}"
        f"@{parts['host']}:{parts['port']}/{parts['database']}"
    )


def update_env_text(text: str, values: dict[str, str]) -> str:
    """Set each key in an .env file's text, replacing (commented or not) existing lines."""
    lines = text.splitlines()
    remaining = dict(values)
    output = []
    for line in lines:
        match = re.match(r'^\s*#?\s*([A-Z0-9_]+)\s*=', line)
        key = match.group(1) if match else None
        if key in values:
            if key in remaining:
                output.append(f'{key}={remaining.pop(key)}')
            # Drop duplicate lines for a key that was already written.
            continue
        output.append(line)

    if remaining:
        if ENV_HEADER not in output:
            output += ['', ENV_HEADER]
        output += [f'{key}={value}' for key, value in remaining.items()]
    # Earlier runs could write the header more than once; keep only the first.
    cleaned = []
    for line in output:
        if line == ENV_HEADER and ENV_HEADER in cleaned:
            continue
        cleaned.append(line)
    return '\n'.join(cleaned).rstrip('\n') + '\n'


def check_database(url: str) -> int:
    """Connect and return the number of tables already in the public schema."""
    import psycopg2

    try:
        with psycopg2.connect(url, sslmode='require', connect_timeout=15) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
                return cur.fetchone()[0]
    except psycopg2.OperationalError as exc:
        message = str(exc).strip().splitlines()[0]
        if 'password authentication failed' in message:
            hint = (
                'The database password is wrong. If you just reset it: make sure you clicked the '
                'button that saves it (generating one is not enough), then wait a minute or two — '
                'the pooler takes a moment to pick up a new password.'
            )
        elif 'Tenant or user not found' in message:
            hint = 'The project reference in the user name does not match this pooler host.'
        else:
            hint = 'Check the connection string and that the project is not paused.'
        raise SetupError(f'Could not connect: {message}\n{hint}') from exc


def check_storage(endpoint: str, region: str, key_id: str, secret: str, bucket: str, ref: str) -> None:
    """Upload a small file, confirm it is publicly readable, then delete it."""
    import boto3
    from botocore.config import Config
    from botocore.exceptions import ClientError

    client = boto3.client(
        's3',
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
        config=Config(signature_version='s3v4', s3={'addressing_style': 'path'}),
    )
    # Upload rather than HEAD the bucket: HEAD responses carry no error body, so a
    # 403 there cannot tell a wrong secret from a region mismatch.
    key = f'_setup_check/{uuid.uuid4().hex}.txt'
    try:
        client.put_object(Bucket=bucket, Key=key, Body=b'ok', ContentType='text/plain')
    except ClientError as exc:
        error = exc.response.get('Error', {})
        code = error.get('Code', '')
        message = error.get('Message', '')
        hints = {
            'NoSuchBucket': f'Create a bucket named "{bucket}" in Storage with "Public bucket" on.',
            'InvalidAccessKeyId': 'The access key ID is wrong.',
            'SignatureDoesNotMatch': (
                'The secret does not match the access key ID, or the region is wrong. '
                'Check the region shown on the S3 Connection page.'
            ),
            'AccessDenied': 'The key is valid but not allowed to write to this bucket.',
        }
        hint = hints.get(code, '')
        raise SetupError(
            f'Storage said: {code or "error"} — {message or exc}'
            + (f'\n     {hint}' if hint else '')
        ) from exc
    public_url = f'https://{ref}.supabase.co/storage/v1/object/public/{bucket}/{key}'
    try:
        with urllib.request.urlopen(public_url, timeout=15) as response:
            is_public = response.status == 200
    except urllib.error.HTTPError:
        is_public = False
    finally:
        client.delete_object(Bucket=bucket, Key=key)

    if not is_public:
        raise SetupError(
            f'Bucket "{bucket}" works but is private, so images would not load on the site. '
            'In Storage, edit the bucket and turn on "Public bucket".'
        )


def read_secret(prompt: str) -> str:
    """Hidden prompt that confirms the length, so a failed paste is visible without showing the value."""
    value = getpass.getpass(prompt)
    if not value:
        raise SetupError('Nothing was entered. Paste the value and press Enter.')
    note = ''
    if value != value.strip():
        note = ' — includes leading or trailing spaces, which were removed'
        value = value.strip()
    print(f'     (received {len(value)} characters{note})')
    return value


def ask(prompt: str, default: str = '') -> str:
    suffix = f' [{default}]' if default else ''
    value = input(f'{prompt}{suffix}: ').strip()
    return value or default


def with_retries(step, attempts: int = 3):
    """Run a setup step, letting the user fix a typo instead of starting over."""
    for attempt in range(1, attempts + 1):
        try:
            return step()
        except SetupError as exc:
            print(f'\n     {exc}\n')
            if attempt == attempts:
                raise SetupError('Stopped after repeated failures. Run the script again to retry.') from exc
            print('     Try again.\n')


def setup_database():
    print('1/3  Database — Supabase → Connect → Session pooler. Paste the string:')
    parts = parse_connection_string(input('> '))
    password = read_secret('     Database password (hidden): ')
    database_url = build_database_url(parts, password)
    print(f"     Project {parts['ref']}, region {parts['region']}. Connecting ...")
    tables = check_database(database_url)
    print(f'     Connected. The database has {tables} tables in the public schema.\n')
    return parts, database_url, tables


def setup_storage(parts: dict):
    print('2/3  Storage — Storage → Settings → S3 Connection → New access key.')
    endpoint = ask('     Endpoint', f"https://{parts['ref']}.supabase.co/storage/v1/s3")
    region = ask('     Region', parts['region'])
    bucket = ask('     Bucket', 'media')
    key_id = ask('     Access key ID')
    secret = read_secret('     Secret access key (hidden): ')
    print('     Uploading a test file ...')
    check_storage(endpoint, region, key_id, secret, bucket, parts['ref'])
    print('     Storage works and the bucket is public.\n')
    return endpoint, region, bucket, key_id, secret


def write_env(values: dict[str, str]) -> None:
    existing = ENV_PATH.read_text() if ENV_PATH.exists() else ''
    ENV_PATH.write_text(update_env_text(existing, values))
    os.chmod(ENV_PATH, 0o600)


def saved_database():
    """Reuse a DATABASE_URL already in .env if the user wants to, re-checking it first."""
    from dotenv import dotenv_values

    url = (dotenv_values(ENV_PATH).get('DATABASE_URL') or '') if ENV_PATH.exists() else ''
    if 'supabase.com' not in url:
        return None
    if not ask('The Supabase database is already set in .env. Keep it? (Y/n)', 'y').lower().startswith('y'):
        return None
    parts = parse_connection_string(url)
    print(f"     Project {parts['ref']}, region {parts['region']}. Connecting ...")
    tables = check_database(url)
    print(f'     Connected. The database has {tables} tables in the public schema.\n')
    return parts, url, tables


def main() -> None:
    print('Connect this checkout to Supabase. Secrets are typed at hidden prompts.\n')

    reused = saved_database()
    if reused:
        parts, database_url, tables = reused
    else:
        parts, database_url, tables = with_retries(setup_database)
        # Save as soon as it works, so a storage problem does not mean starting over.
        write_env({'DATABASE_URL': database_url})
        print('     Database settings saved to .env.\n')

    endpoint, region, bucket, key_id, secret = with_retries(lambda: setup_storage(parts))

    print('3/3  Writing .env ...')
    values = {
        'DATABASE_URL': database_url,
        'SUPABASE_S3_ENDPOINT': endpoint,
        'SUPABASE_S3_REGION': region,
        'SUPABASE_S3_ACCESS_KEY_ID': key_id,
        'SUPABASE_S3_SECRET_ACCESS_KEY': secret,
        'SUPABASE_STORAGE_BUCKET': bucket,
    }
    write_env(values)
    print(f'     Saved to {ENV_PATH} (readable only by you).\n')

    print('Reminder: in Project Settings → Data API, turn the Data API off.')
    print('Django connects directly and does not need it.\n')

    if tables == 0:
        answer = ask('Copy the local database and media into Supabase now? (y/N)', 'n')
        if answer.lower().startswith('y'):
            subprocess.run([sys.executable, str(BASE_DIR / 'scripts' / 'migrate_to_supabase.py')], check=True)
            return
        print('Later: .venv/bin/python scripts/migrate_to_supabase.py')
    else:
        print('Supabase already has tables, so the local data was not copied.')
    print('Start the site with ./scripts/run_local.sh')


if __name__ == '__main__':
    try:
        main()
    except SetupError as exc:
        print(f'\n{exc}', file=sys.stderr)
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled. Anything already confirmed (such as the database) stays in .env.', file=sys.stderr)
        sys.exit(1)
