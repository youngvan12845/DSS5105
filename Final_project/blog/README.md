# CheeseO Blog + Reading Co-Pilot Agent

Django/Wagtail blog with an HTMX-based **Reading Assistant** (`/agent/`) for grounded Q&A, recommendations, reading paths, and confirm-before-action workflows.

**Full documentation**:
- 中文：[DOCUMENTATION.md](./DOCUMENTATION.md)
- English: [DOCUMENTATION_EN.md](./DOCUMENTATION_EN.md)

## Requirements

- Python 3.10+
- PostgreSQL (local)
- **[Ollama](https://ollama.com/download) (recommended)** — local LLM + embeddings for full AI Q&A

## Ollama setup — required for full AI Q&A

**Default config uses local models, not a cloud API.** Every teammate who wants natural-language answers (not rule-based fallback) should complete this checklist.

### Checklist

- [ ] Install [Ollama](https://ollama.com/download) and keep the app running in the background
- [ ] From `blog/`, run `./scripts/setup_ollama.sh` (downloads chat + embedding models)
- [ ] Run `python manage.py build_article_index --embed` (needs Ollama for vectors)
- [ ] Start the site with `./scripts/run_local.sh`
- [ ] Open `/agent/` — badge should show **`Ollama · … (local)`**, not `Ollama offline · rule-based fallback`

### Models pulled by default

| Model | Purpose | Size (approx.) |
|-------|---------|----------------|
| `qwen2.5vl:7b` | Chat / optional image Q&A | ~several GB |
| `nomic-embed-text` | Vector semantic search | smaller |

**Lighter chat model (optional):** set `OLLAMA_MODEL=qwen2.5:7b` in `.env`, then `ollama pull qwen2.5:7b`.

### Without Ollama

The site still runs, but the Assistant falls back to **retrieval snippets only** — no fluent LLM summaries. Not suitable for demo.

### Alternative: OpenAI (no local model download)

Set in `.env`:

```env
AGENT_LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

Requires a paid API key; paid article snippets may be sent to OpenAI. Vector search still works best if you also run Ollama for embeddings, or use `build_article_index` without `--embed` (keyword/chunk only).

---

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

./scripts/setup_ollama.sh   # pull local models — do this before --embed
python manage.py build_article_index --embed

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

1. Clone repo → follow Quick start + **Ollama checklist** above
2. Each member verifies `/agent/` shows **Ollama (local)**, not fallback
3. Expand `eval_tasks.json` together
4. Record demo video from local run if public hosting is unavailable
