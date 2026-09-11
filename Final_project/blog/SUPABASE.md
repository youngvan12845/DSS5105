# Using Supabase (optional)

By default every teammate runs their own local PostgreSQL and keeps uploaded
images in `media/`, so nobody sees anyone else's articles or accounts.
Pointing the site at one Supabase project gives the whole team the same
articles, test accounts and images, and gives the future demo deployment a
database that is already online.

Supabase is used **only as PostgreSQL plus file storage**. Login still goes
through Django / allauth, and Ollama still runs locally.

Nothing changes until you set the variables below. Without them the site
keeps using `POSTGRES_*` and `media/`.

---

## One-time setup (one person)

Dashboard labels may differ slightly from these names.

1. **Create a project** at supabase.com. Region: **Southeast Asia (Singapore)**.
   Save the database password somewhere private.
2. **Turn off the Data API** (Project Settings → Data API). Supabase would
   otherwise expose every table in the `public` schema over REST, including
   `auth_user`. Django connects directly and does not need it. The migration
   script also revokes the API roles' access as a second layer.
3. **Get the connection string**: Connect → **Session pooler** (port 5432).
   The direct connection is IPv6-only on the free plan and fails on many
   networks. URL-encode special characters in the password (`@` → `%40`).
4. **Create a storage bucket** named `media` and mark it **public**
   (article images and avatars are public on the site anyway).
5. **Create S3 access keys**: Storage → Settings → S3 Connection. Note the
   endpoint, region, access key ID and secret.
6. Fill `.env` (see the commented block in `.env.example`):

   ```bash
   DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres
   SUPABASE_S3_ENDPOINT=https://<project-ref>.supabase.co/storage/v1/s3
   SUPABASE_S3_REGION=ap-southeast-1
   SUPABASE_S3_ACCESS_KEY_ID=...
   SUPABASE_S3_SECRET_ACCESS_KEY=...
   SUPABASE_STORAGE_BUCKET=media
   ```

7. **Copy the local data and images across** (target must be empty):

   ```bash
   pip install -r requirements.txt
   .venv/bin/python scripts/migrate_to_supabase.py
   ```

   It dumps the local database, restores it into Supabase in one transaction
   (a failure leaves Supabase untouched), prints row counts for a few tables,
   and uploads everything in `media/`. It needs `pg_dump` and `psql`; set
   `PG_BIN` if they are not on your PATH.

## Teammates

1. Get the `.env` values from the person above **by direct message**, never in
   the group chat or a commit.
2. `pip install -r requirements.txt`, then `./scripts/run_local.sh`.
   A local PostgreSQL is no longer required for day-to-day use.

## Rules for a shared database

- **Migrations**: only migrations that are merged into `main` are applied to
  Supabase, and by one person. If your branch changes models, run it against
  your local database (remove `DATABASE_URL` from `.env`) until it is merged.
  Two branches migrating the same database will break each other's tables.
- **Evaluation**: shared data changes as people use the site. Run evaluations
  against a fixed snapshot so numbers are reproducible.
- **Credentials**: use the pooler user from Supabase, share it privately, and
  rotate the password if it ever lands in a chat or commit.
- **Free plan**: inactive projects get paused. Open the dashboard before any
  demo or presentation to make sure the project is running.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `could not translate host name` or connection timeout | You are using the direct connection. Switch to the Session pooler string. |
| `SSL connection is required` | Remote URLs get `sslmode=require` automatically. Check the URL has no `sslmode=disable`. |
| Errors about prepared statements or cursors | You are on the transaction pooler (port 6543). The settings handle it, but the session pooler (5432) is simpler. |
| Images 403 / not found | The bucket must be public and named as in `SUPABASE_STORAGE_BUCKET`. |
| `SUPABASE_S3_ENDPOINT should look like ...` on startup | Use the S3 endpoint ending in `/storage/v1/s3`, not the project URL. |
