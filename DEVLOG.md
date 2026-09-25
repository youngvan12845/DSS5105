# Development log — branch `renqian/dev`

Work done on Renqian's branch, newest first. Each entry records what changed,
why, how it was verified, and what is still open. Branched from `main` at
`9787088` (2026-09-10).

---

## 2026-09-18 — Connected to Supabase

**Result.** The site now runs on a real Supabase project (region
`ap-northeast-2`, Seoul). `scripts/migrate_to_supabase.py` copied everything
across with matching row counts — users 1→1, pages 15→15, articles 12→12,
index chunks 12→12 — uploaded the 4 files in `media/`, and revoked the Data
API roles on the `public` schema. Pages load, and article images are served
from the public bucket URL (HTTP 200).

**Latency.** Each query round-trips to Seoul in about 125 ms from here, and an
article page issues 53 queries, so it takes about 4.1 s (home 0.55 s, article
list 1.6 s). Two separate fixes: put the database in Singapore, in the same
region as wherever the demo is deployed, where the round trip is a few
milliseconds; and cut the query count, since 53 queries for one article is an
N+1 pattern that will hurt any deployment.

**Incident, fixed.** With `DATABASE_URL` in `.env`, `manage.py test` created a
`test_postgres` database on the shared Supabase project and ran every
migration against it. It was stopped, confirmed to hold only empty test
tables, and dropped; the real database was untouched (12 articles). Settings
now ignore `DATABASE_URL` and Supabase Storage whenever the command is
`test`, so tests always use the local database and never upload to the real
bucket. 34 tests pass locally in about 7 s.

**Setup script, from using it.** The first real run surfaced three rough
edges, now fixed: hidden prompts give no feedback, so the script now prints
how many characters it received; a bucket check using HEAD reported "wrong
key" for any 403, so it now uploads a test file and shows Supabase's actual
error code; and a storage mistake used to mean re-entering the database
password, so database settings are saved as soon as the connection works.

**Open.** Decide on the region before more data goes in. Teammates need the
`.env` values by direct message.

---

## 2026-09-18 — One-command Supabase setup

**Why.** Connecting to Supabase meant copying six values into `.env` by hand,
URL-encoding the database password, and finding out only at startup whether
any of them were wrong.

**Changed.** `scripts/setup_supabase.py` asks for the Session pooler string,
the database password and the S3 access key; derives the project ref, region
and Storage endpoint from the pooler string; connects to the database; uploads
and deletes a test file to confirm the bucket exists and is public; then
writes `.env` (mode 600) and offers to run the migration. Secrets are typed at
hidden prompts and never leave `.env`. Typos get up to three retries, and
`.env` is untouched unless every check passes.

**Verified.** 6 new tests: pooler parsing, an unencoded `@` in a pasted
password, rejection of the IPv6-only direct connection, and `.env` updates
that replace commented lines without touching anything else. Passwords with
`@ # $ ${VAR}`, quotes, spaces and Chinese characters round-trip through
`.env` and Django's settings unchanged. 33 tests pass.

**Open.** Not yet run against the real project.

---

## 2026-09-13 — First baseline comparison run

Full set of 33 tasks against all four systems, local `qwen2.5vl:7b`,
temperature 0.2. Raw results in `a_agent/eval/results/`.

| System | Passed | Rate |
|---|---|---|
| Full agent | 25/33 | 75.8% |
| Baseline C (basic RAG) | 17/33 | 51.5% |
| Baseline B (keyword search + LLM) | 7/33 | 21.2% |
| Baseline A (plain LLM) | 5/33 | 15.2% |

Dev 76.2%, holdout 75.0% — no sign that the set favours the tuned half.

**Headline result: paywall.** Baseline C, which retrieves without access
checks, reproduced paid body text verbatim on two of the three paywall
tasks ("a linear relationship between features and…", "a single
responsibility clear inputs outputs…"). The full agent leaked nothing on
any of them. This is the differentiator the proposal claims, now measured,
and it is what the paid-leak detector was rebuilt to catch.

**Where the agent's advantage is thin.** On factual Q&A and cross-article
lookup, baseline C scores close to the full agent (5/6 and 4/5). The gap
comes almost entirely from continue-reading, recommendation and actions,
where A and B score near zero because they have no tools. The report should
say this plainly rather than claiming a uniform win.

**Remaining failures of the full agent (8).**

| Task | Type | Cause |
|---|---|---|
| action-001, action-004 | defect | `_classify_intents` matches the literal string "add to"; "Add the RAG article to my reading list" does not contain it, so no action is proposed |
| state-002, state-004 | defect | Phrasing misses `CONTINUE_READING_HINTS`, so `get_browsing_history` is never called — yet the reply still says "based on the browsing history" |
| rec-002 | defect | Recommendations name articles in the text but return no citations: `recommend_articles` results never reach `_format_citations` |
| adv-002 | defect | Paid article answered with "not indexed yet" instead of naming the paywall |
| cross-004, path-003 | incomplete answer | Correct as far as it goes, missing one required fact |

Four distinct defects, all with an identified cause — the start of the ≥10
failure cases `Evaluation.pdf` needs.

**Instrument fixes made after the first run** (first run: full 69.7%,
C 42.4%, B 18.2%, A 12.1%, kept in `2026-09-12_all_variants.json`):
`REFUSAL_HINTS` missed "not found", and forbidden phrases matched
substrings, so "gan" fired on the assistant correctly echoing the fake
title it was asked about. Forbidden phrases now match whole words.

**Caveat.** Two tasks flipped between the two runs (`qa-004`, `adv-005`),
so single-run numbers carry sampling noise. Repeat runs before quoting a
figure in the report.

---

## 2026-09-12 — Eval set rewritten so the numbers mean something (`860494c`)

**Why.** The 33-task set had no gold answers. Scoring checked whether the reply
contained certain keywords, so `qa-001` ("What is RAG?") passed on any reply
containing "RAG" — the word is in the question. The paid-leak check was
inverted: it failed replies containing our own paywall notice ("subscribe or
purchase") and passed a verbatim body dump unless it happened to mention
sklearn, MSE or R². The course spec asks for answers verified against the data
and for an explanation of why the set is not rigged in our favour.

**Changed.**

- Every answer task now carries a `gold_answer` and the `facts` the reply must
  state, taken from the article bodies, with the source slug recorded.
- Paid leaks are decided by comparing the reply against the real article body
  (matching six-word runs), excluding title and intro, which are public.
- New checks: `citation_slugs_any` (cited the right article, not merely
  something) and `ordered_mentions` (reading-path steps in the right order).
- Tasks split into `dev` (21) and `holdout` (12); 8 history-dependent tasks
  flagged `human_review`.
- New `manage.py verify_eval_tasks`: checks every fact against its source
  article and flags facts that only echo the question.

**Verified.** 24 tests pass, including leak-detector cases for a correct
refusal, a verbatim leak, a reformatted leak and a paraphrase.
`verify_eval_tasks` passes on all 33 tasks — and caught three bad facts in the
first draft of the file (one copied from the question, one unsupported by its
article, one with no source at all).

**Found a defect.** Asked for the full body of a paid article, the agent leaks
nothing but replies "The article is not indexed yet." The article *is* indexed;
it is paywalled. The system prompt in `orchestrator.py` tells the model to say
this whenever passages look empty, and redacted paid passages take that branch.
Recorded in `adv-002` as `observed_failure`; the task now fails until the
prompt is fixed. Candidate failure case #1 for `Evaluation.pdf`.

**Open.** Fix the prompt (and then update the recorded failure). Decide whether
answer accuracy also needs an LLM judge or human marking beyond fact checks.

---

## 2026-09-12 — Optional Supabase database and media storage (`66d5e62`)

**Why.** Everyone runs a separate local database and `media/` folder, so no one
sees the same articles or accounts, and there is nothing for a demo link to
point at. Sprint 2 and 3 both require a working demo link on the first slide.

**Changed.**

- `DATABASE_URL`, when set, replaces the `POSTGRES_*` settings. Remote hosts get
  `sslmode=require`; the transaction pooler port (6543) turns off persistent
  connections and server-side cursors.
- `SUPABASE_S3_*`, when set, stores uploads in Supabase Storage via
  django-storages and serves them from the bucket's public URL.
- Chat image uploads read through the storage backend instead of
  `FieldFile.path`, which remote storage does not provide.
- `scripts/migrate_to_supabase.py` copies the local database into an empty
  Supabase database in one transaction, revokes the Data API roles on the
  `public` schema, compares row counts and uploads `media/`.
- `SUPABASE.md` documents setup and the rules for sharing one database.

Nothing changes for teammates who do not set the variables.

**Verified.** New tests for URL parsing, storage config and chat images without
a local path. The site ran against `DATABASE_URL` on local Postgres. The
migration script was rehearsed into an empty local database: row counts and
sequences matched, and a second run correctly refused a non-empty target.

**Open.** Not yet run against a real Supabase project. Migrations against a
shared database must come from `main` only, applied by one person. pgvector
instead of the current Python-side cosine loop is a later option.

---

## 2026-09-11 — Password reset hardened (`d595c3d`)

**Why.** A security review of the whole codebase found that the six-digit
password reset code had no limit on wrong guesses. Within its ten-minute
lifetime it could be brute-forced and used to set a new password on any
account. Reproduced locally: 200 wrong codes, no lockout, the code still valid,
and the correct code still accepted afterwards.

**Changed.** The code is invalidated after 5 wrong attempts; reset emails are
throttled per address (1/minute, 5/hour); registered and unregistered addresses
get identical responses, so the form no longer reveals who has an account;
codes are generated with `secrets` and compared in constant time.

**Verified.** 5 tests covering lockout, throttling, the enumeration case and a
successful reset.

**Open.** The limits live in Django's cache, which is per-process LocMemCache
today; a multi-worker deployment needs a shared cache. The other findings from
the review (payment callback idempotency, points race condition, `DEBUG` and
`SECRET_KEY` defaults, `javascript:` links in agent markdown) are not fixed.

---

## Notes for the team

- All of the above is on `renqian/dev` and not merged. `main` is untouched.
- The security finding was reported privately to the team lead rather than as a
  public issue.
