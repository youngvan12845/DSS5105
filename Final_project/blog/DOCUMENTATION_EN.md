# CheeseO Blog Reading Co-Pilot — Project Documentation

**Course**: DSS5105 Capstone · Group 4 · Track 5 (Custom)  
**Project**: Blog Reading Co-Pilot Agent  
**Code path**: `Final_project/blog/`  
**Last updated**: 2026-09-08  

**中文文档**: [DOCUMENTATION.md](./DOCUMENTATION.md)

---

## 1. Features

### 1.1 Overview

CheeseO is a Django + Wagtail blog platform with an integrated **Reading Assistant** — an Agent system built with dedicated **tools**, **source citations**, and **confirm-before-action** workflows.

Unlike a plain ChatGPT chatbox, answers are **grounded in on-site article retrieval**, not free-form model generation. Operations involving paid content, reading-list changes, and comment publishing follow explicit rules and are audit-logged.

**Target users**: Blog readers who want to find articles quickly, ask questions, plan reading order, and manage a personal reading list.

---

### 1.2 Base Blog Platform

Beyond the Agent, the site already provides full blog and membership features:

| Module | Features |
|--------|----------|
| `a_blog` | Articles, tags, comments, Wagtail CMS |
| `a_users` | Sign-up/login, profiles, **browsing history** |
| `a_order` | Subscriptions, point recharge |
| `a_points` | Daily check-in, point records |
| Paywall | Free/paid articles, point unlock, subscription full access |

The Agent reuses these modules for data and permissions — no duplicate user system.

---

### 1.3 Six Core Agent Capabilities

Aligned with the project proposal (`PROJECT_OVERVIEW.md` §4):

#### (1) Retrieval & Tracing

- Three retrieval modes: **keyword search** (Wagtail), **chunk full-text search**, **vector semantic search** (Ollama embeddings).
- Answers include **citation cards** linking back to source articles.
- **Article Focus** mode on article pages restricts Q&A to the current article only.

**Examples**: “What is RAG?”, “Summarize this article”

#### (2) Recommendations & Discovery

- Recommends next reads from **browsing history** and **tag overlap**.
- Empty Assistant sessions show a **Continue Reading** nudge (recent history + recommendation chips).

**Examples**: “What should I read next?”, “Recommend articles about Python”

#### (3) Reading Path Planning

- Paths are **manually curated** in `a_agent/data/reading_paths.json` (matched by topic/tags).
- The Agent returns an ordered article list with notes when it detects a learning intent.

**Example**: “I want to learn machine learning. What reading path should I follow?”

#### (4) Proactive Assistance (v1)

- **In-session** prompts: welcome message, recent reads, recommendations, and quick-action chips on new general sessions.
- **Does not include** email/push scheduled reminders (out of v1 scope).

#### (5) Confirmed Actions

All side-effect operations follow **propose → user Confirm → execute**, logged in `AgentActionLog`:

| Action | Flow |
|--------|------|
| Add to reading list | Agent detects intent → pending card → Confirm → writes `ReadingListItem` |
| Remove from reading list | Same pattern → Confirm → delete |
| Comment draft | Agent drafts comment → Confirm → posts to `a_blog` comments |

Nothing is saved or published **until the user confirms**.

#### (6) Paywall-aware Q&A

- Retrieval respects user access (anonymous / free / subscription / point-unlocked).
- Locked paid articles return **preview snippets** only; LLM system prompts forbid leaking full paid body text.
- Topics not in the corpus (e.g. “quantum computing article”) should be **refused**, not hallucinated.

---

### 1.4 UI Entry Points

| Entry | URL | Description |
|-------|-----|-------------|
| Home | `/home/` | CheeseO landing page |
| Articles | `/blog/` | Article listing |
| Reading Assistant | `/agent/` | Main chat UI (login required) |
| Reading list | `/agent/reading-list/` | Standalone saved-articles page |
| Article Agent panel | Right dock / mobile drawer on article pages | Single-article Q&A |
| Wagtail CMS | `/blog/cms/` | Content admin |
| Browsing history | `/profile/browsing-history/` | User read history |

Use **Reading Assistant** in the nav bar or **Reading List** in the user dropdown.

---

### 1.5 Additional Features

- **Multi-session chat**: create, switch, and delete sessions; per-article sessions supported.
- **Swappable LLM backend**: Ollama by default; OpenAI optional; rule-based fallback when offline.
- **Optional vision input**: image upload for questions (requires a vision model, e.g. `qwen2.5vl:7b`).
- **Auto index rebuild**: Wagtail publish/unpublish triggers per-article index updates.
- **English UI**: Agent and main site UI are in English (legacy Chinese CMS content may need re-seeding).

---

## 2. Code Architecture

### 2.1 Tech Stack

| Layer | Technology |
|-------|------------|
| Web framework | Django 5.1 |
| CMS | Wagtail 7.0 |
| Frontend | HTMX + Tailwind CSS |
| Database | PostgreSQL |
| LLM | Ollama (default) / OpenAI API |
| Embeddings | Ollama `nomic-embed-text` |
| Vector storage | PostgreSQL JSONField (`ArticleChunk.embedding`) |

---

### 2.2 Project Layout

```
blog/
├── a_core/              # Django project settings, root URLs
├── a_home/              # Home, About, Help
├── a_blog/              # Wagtail articles, comments, templates
├── a_users/             # Users, profiles, browsing history
├── a_order/             # Subscriptions and recharge
├── a_points/            # Points and daily check-in
├── a_agent/             # ★ Reading Assistant core app
│   ├── models.py        # Sessions, messages, chunks, reading list, audit log
│   ├── views.py         # Chat, confirm actions, reading list page
│   ├── urls.py
│   ├── signals.py       # Publish/unpublish → auto index
│   ├── services/
│   │   ├── orchestrator.py    # Agent orchestration (intent → tools → LLM)
│   │   ├── llm.py             # Ollama / OpenAI client
│   │   ├── embeddings.py      # Vector embeddings
│   │   ├── article_index.py   # Index build logic
│   │   ├── article_text.py    # HTML → text, chunking
│   │   └── proactive.py       # Session continue-reading nudge
│   ├── tools/             # Agent tool layer (single responsibility each)
│   │   ├── keyword_search.py
│   │   ├── chunk_search.py
│   │   ├── vector_search.py
│   │   ├── article_scope.py
│   │   ├── browsing_history.py
│   │   ├── recommend.py
│   │   ├── reading_paths.py
│   │   ├── reading_list.py
│   │   ├── comment_draft.py
│   │   └── access.py          # Paywall access checks
│   ├── data/
│   │   ├── reading_paths.json
│   │   └── eval_tasks.json    # Eval task set (for grading)
│   ├── eval/              # Eval runner + baselines A/B/C
│   ├── templates/a_agent/ # Chat UI and partials
│   └── management/commands/
│       ├── build_article_index.py
│       ├── seed_demo_content.py
│       └── run_agent_eval.py
├── templates/           # Site-wide templates (header, etc.)
├── scripts/
│   ├── run_local.sh
│   └── setup_ollama.sh
├── manage.py
├── requirements.txt
└── .env.example
```

---

### 2.3 System Architecture & Data Flow

```
┌─────────────┐     HTMX      ┌──────────────────┐
│   Browser   │ ◄──────────► │  a_agent/views   │
└─────────────┘               └────────┬─────────┘
                                       │
                                       ▼
                            ┌──────────────────────┐
                            │ services/orchestrator │
                            │  1. Intent classify    │
                            │  2. Call tools         │
                            │  3. Build prompt       │
                            │  4. LLM / fallback     │
                            └──────────┬───────────┘
                                       │
         ┌─────────────┬───────────────┼───────────────┬─────────────┐
         ▼             ▼               ▼               ▼             ▼
   keyword_search  chunk_search   vector_search   recommend    reading_list
         │             │               │               │             │
         └─────────────┴───────────────┴───────────────┴─────────────┘
                                       │
                                       ▼
                            ┌──────────────────────┐
                            │ access.py (Paywall)   │
                            │ ArticleChunk (index)    │
                            │ Wagtail ArticlePage     │
                            │ BrowsingHistory         │
                            └──────────────────────┘
```

**Typical Q&A flow**:

1. User sends a message via HTMX POST → `send_message_view`
2. Message saved to `ChatMessage`; `handle_user_message()` is called
3. Orchestrator classifies **intents** (retrieval, recommend, path, history, actions, …)
4. Corresponding **tools** run; structured hits, history, paths, etc. are collected
5. Write intents create `AgentActionLog` as **pending_action** (not executed yet)
6. LLM generates an answer from tool results; if no LLM, `_fallback_answer()` applies rules
7. Assistant message rendered with citations and pending actions; Confirm triggers `confirm_action_view`

---

### 2.4 Orchestrator

File: `a_agent/services/orchestrator.py`

| Step | Description |
|------|-------------|
| `_classify_intents()` | Keyword heuristics; multiple intents can apply |
| Tool calls | Per intent; results logged in `tool_trace` for debug/eval |
| Article scope | When `article_id` is set, retrieval is limited to that article |
| LLM prompt | Answer from tool results only; English by default; no paid-body leaks |
| Fallback | When Ollama is offline, stitch retrieval snippets into a readable reply |

**Intent → tool mapping**:

| Intent | Tool |
|--------|------|
| `keyword` | `keyword_search_articles` |
| `chunk` | `search_article_chunks` |
| `vector` | `search_article_vectors` |
| `history` | `get_browsing_history` |
| `recommend` | `recommend_articles` |
| `path` | `get_reading_path_for_user` |
| `reading_list` | `get_reading_list` |
| `action_add` | `propose_add_to_reading_list` |
| `action_remove` | `propose_remove_from_reading_list` |
| `action_comment` | `build_comment_draft` + `propose_post_comment` |

---

### 2.5 Core Data Models

File: `a_agent/models.py`

| Model | Purpose |
|-------|---------|
| `ChatSession` | User chat session (title, selected LLM model) |
| `ChatMessage` | Single message; stores citations, tool_trace, pending_action (JSON) |
| `ArticleChunk` | Article text chunks + optional embedding vectors |
| `ReadingListItem` | Saved article in user's reading list |
| `AgentActionLog` | Pending/executed action audit trail |

---

### 2.6 Tool Layer Design

Each tool file maps to one capability with clear inputs/outputs (suitable for Capstone tool specification tables):

- **Retrieval**: `keyword_search` / `chunk_search` / `vector_search` / `article_scope`
- **Personalization**: `browsing_history` / `recommend`
- **Planning**: `reading_paths`
- **Action**: `reading_list` / `comment_draft`
- **Access control**: `access` (used by retrieval tools)

Paywall logic is centralized in `access.py` → `can_user_read_full()`.

---

### 2.7 Indexing & Wagtail Integration

- **Manual full rebuild**: `python manage.py build_article_index [--embed]`
- **Auto incremental index**: `a_agent/signals.py` listens to `page_published` / `page_unpublished`
- Index logic lives in `services/article_index.py` → `index_article()`

---

## 3. Running the Project

### 3.1 Requirements

| Dependency | Notes |
|------------|-------|
| Python | 3.10+ |
| PostgreSQL | Local install; create database first |
| Git | Clone the repo |
| Ollama (recommended) | Local LLM + embeddings — [download](https://ollama.com/download) |
| OpenAI (optional) | Set `AGENT_LLM_PROVIDER=openai` and API key |

---

### 3.2 First-Time Setup

```bash
# 1. Enter project directory
cd Final_project/blog

# 2. Virtual environment and dependencies
python3.10 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Environment variables
cp .env.example .env
# Edit .env — at minimum POSTGRES_PASSWORD and DJANGO_SECRET_KEY

# 4. Create PostgreSQL database (psql or pgAdmin)
# CREATE DATABASE cheeseoo;

# 5. Migrations
python manage.py migrate

# 6. Admin user
python manage.py createsuperuser

# 7. (Optional) Demo articles
python manage.py seed_demo_content

# 8. Build retrieval index (embeddings recommended)
python manage.py build_article_index --embed

# 9. (Optional) Pull Ollama models
./scripts/setup_ollama.sh
```

---

### 3.3 Daily Development

```bash
cd Final_project/blog
source .venv/bin/activate

# Ensure PostgreSQL and Ollama are running
./scripts/run_local.sh
```

Open in browser:

- Site: http://127.0.0.1:8000/home/
- Reading Assistant: http://127.0.0.1:8000/agent/
- CMS: http://127.0.0.1:8000/blog/cms/

---

### 3.4 Management Commands

| Command | Description |
|---------|-------------|
| `python manage.py runserver` | Start dev server |
| `python manage.py seed_demo_content` | Seed demo articles |
| `python manage.py build_article_index` | Rebuild text index (no vectors) |
| `python manage.py build_article_index --embed` | Rebuild index + Ollama vectors |
| `python manage.py run_agent_eval` | Run agent evaluation |
| `python manage.py run_agent_eval --variant all --no-fail-exit` | Compare full agent vs baselines A/B/C |

> After publishing in Wagtail CMS, the index for that article **updates automatically**. Run `build_article_index --embed` only on first deploy or bulk imports.

---

### 3.5 Environment Variables

See `.env.example`:

| Variable | Description |
|----------|-------------|
| `POSTGRES_*` | PostgreSQL connection |
| `DJANGO_DEBUG` | Dev mode (`False` in production) |
| `DJANGO_SECRET_KEY` | Django secret key |
| `AGENT_LLM_PROVIDER` | `ollama` (default) or `openai` |
| `OLLAMA_MODEL` | Chat model, e.g. `qwen2.5vl:7b` |
| `OLLAMA_EMBED_MODEL` | Embedding model, e.g. `nomic-embed-text` |
| `OPENAI_API_KEY` | Required when using OpenAI |
| `OPENAI_MODEL` | e.g. `gpt-4o-mini` |

---

### 3.6 Suggested Demo Flow

After login, use this order for a Sprint video (~5 min):

1. Open `/agent/` — show Continue Reading nudge
2. Ask “What is RAG?” — show citations
3. Open an article — use the side panel “Summarize this article”
4. “Add the RAG article to my reading list” — Confirm → check `/agent/reading-list/`
5. Open a locked paid article — ask for full text — show paywall (no leak)
6. Ask about a non-existent topic (e.g. quantum computing) — show refusal

---

### 3.7 FAQ

**Q: Assistant shows “Ollama offline · rule-based fallback”**  
A: Start the Ollama app or run `./scripts/setup_ollama.sh`; or switch to OpenAI.

**Q: Agent says “article is not indexed yet”**  
A: Run `python manage.py build_article_index --embed`, or republish the article in CMS to trigger auto-index.

**Q: Vector search returns nothing**  
A: Ensure Ollama is running and `ollama pull nomic-embed-text`; index must be built with `--embed`.

**Q: Full paid article text is visible without unlock**  
A: Verify no active subscription/point unlock; unauthorized users should only see previews.

**Q: PostgreSQL connection failed**  
A: Check `POSTGRES_*` in `.env`; ensure the DB service is running and database `cheeseoo` exists.

---

## Appendix: Course Deliverables

| Deliverable | Maps to this doc |
|-------------|------------------|
| Readme.pdf | §3 Running the project |
| Documentation.pdf | §1 Features + §2 Architecture (export this file to PDF) |
| Evaluation.pdf | Use `run_agent_eval` (complete before final submission) |

**GitHub**: https://github.com/youngvan12845/DSS5105  
**Code directory**: `Final_project/blog/`

---

*Maintained by Group 4 · Update this file and README.md when features change.*
