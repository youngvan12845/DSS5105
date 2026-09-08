# CheeseO Blog + Reading Co-Pilot Agent

Django/Wagtail blog with an HTMX-based **Reading Assistant** (`/agent/`) for grounded Q&A, recommendations, reading paths, and confirm-before-action workflows.

**Full documentation**:
- 中文：[DOCUMENTATION.md](./DOCUMENTATION.md)
- English: [DOCUMENTATION_EN.md](./DOCUMENTATION_EN.md)

## Requirements

- Python 3.10+
- PostgreSQL (local)
- Optional: [Ollama](https://ollama.com/download) for local LLM + embeddings

## Quick start

```bash
cd blog
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env — at minimum set POSTGRES_PASSWORD

python manage.py migrate
python manage.py createsuperuser

# Optional demo articles (first-time setup)
python manage.py seed_demo_content
python manage.py build_article_index --embed

./scripts/setup_ollama.sh   # optional, for local LLM
./scripts/run_local.sh
```

Open:

- Home: http://127.0.0.1:8000/home/
- Articles: http://127.0.0.1:8000/blog/
- Reading Assistant: http://127.0.0.1:8000/agent/
- Wagtail CMS: http://127.0.0.1:8000/blog/cms/

## Environment variables

See [`.env.example`](.env.example). Important keys:

| Variable | Purpose |
|----------|---------|
| `POSTGRES_*` | Database connection |
| `AGENT_LLM_PROVIDER` | `ollama` (default) or `openai` |
| `OLLAMA_MODEL` | Chat/vision model, e.g. `qwen2.5vl:7b` |
| `OLLAMA_EMBED_MODEL` | Embeddings, e.g. `nomic-embed-text` |
| `OPENAI_API_KEY` | Only if using OpenAI instead of Ollama |

After publishing new articles, the search index rebuilds automatically. For a full corpus refresh:

```bash
python manage.py build_article_index --embed
```

## Agent features (high level)

- Keyword / chunk / vector retrieval with citations
- Article-scoped Q&A panel on article pages
- Browsing-history recommendations + session continue-reading nudge
- Reading paths from `a_agent/data/reading_paths.json`
- Confirm-before-action: reading list add/remove, comment draft
- Paywall-aware retrieval (respects subscription + point-unlocked articles)

## Evaluation

Task set (32 questions): [`a_agent/data/eval_tasks.json`](a_agent/data/eval_tasks.json)

| Variant | Description |
|---------|-------------|
| `full` | Complete Reading Assistant (tools + paywall + confirm actions) |
| `baseline_a` | Plain LLM, no retrieval |
| `baseline_b` | Wagtail keyword search + LLM |
| `baseline_c` | Vector/chunk RAG + LLM (no tools, personalization, or paywall masking) |

```bash
# Full agent only
python manage.py run_agent_eval

# One baseline
python manage.py run_agent_eval --variant baseline_b --no-fail-exit

# Compare all four systems (for Evaluation.pdf tables)
python manage.py run_agent_eval --variant all --output eval_compare.json --no-fail-exit
```

Use `--username`, `--model`, and `--tasks` as needed. Baseline sweeps usually pass `--no-fail-exit` so every variant finishes even when tasks fail.

## Useful commands

```bash
python manage.py seed_demo_content
python manage.py build_article_index
python manage.py build_article_index --embed
python manage.py run_agent_eval
```

## Project layout

```
blog/
├── a_agent/          # Reading Assistant app
├── a_blog/           # Wagtail articles + comments
├── a_users/          # Profiles, browsing history
├── a_order/          # Membership / recharge
├── scripts/          # run_local.sh, setup_ollama.sh
└── manage.py
```

## Group workflow tip

1. Clone repo → follow Quick start above
2. Each member verifies `/agent/` works locally
3. Expand `eval_tasks.json` together
4. Record demo video from local run if public hosting is unavailable
