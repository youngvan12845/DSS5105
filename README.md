# DSS5105 — Group 4 Capstone

NUS DSS5105 capstone project: **Blog Reading Co-Pilot Agent** (Track 5 · CheeseO).

**GitHub**: https://github.com/youngvan12845/DSS5105  
**Clone URL**: `https://github.com/youngvan12845/DSS5105.git`

---

## Teammate onboarding — clone & run (start here)

### Step 0 — Accept the GitHub invite

If you were added as a collaborator, GitHub shows **Pending Invite** until you accept.

1. Check your **email** for an invite from GitHub, **or**
2. Open https://github.com/youngvan12845/DSS5105 — you should see an **Accept invitation** banner  
3. After accepting, refresh the repo page — you should see the code, not “404”

### Step 1 — Clone the repository

**Option A — Terminal (recommended)**

```bash
git clone https://github.com/youngvan12845/DSS5105.git
cd DSS5105/Final_project/blog
```

**Option B — GitHub website**

1. Open https://github.com/youngvan12845/DSS5105  
2. Click the green **Code** button  
3. Copy the HTTPS URL: `https://github.com/youngvan12845/DSS5105.git`  
4. Paste into terminal: `git clone <paste-url>`  
5. `cd DSS5105/Final_project/blog`

**Already cloned? Pull latest:**

```bash
cd DSS5105
git pull origin main
cd Final_project/blog
```

### Step 2 — Prerequisites (install once)

| Tool | Notes |
|------|-------|
| [Git](https://git-scm.com/downloads) | Clone & pull |
| Python **3.10+** | `python3.10 --version` |
| [Ollama](https://ollama.com/download) | **Required for full AI Q&A** (local LLM) |
| [PostgreSQL](https://www.postgresql.org/download/) | **Optional** if you use the team shared Supabase DB (see Step 3A) |

### Step 3A — Team shared database (recommended)

The team runs one **Supabase** project so everyone sees the same articles, images, and test data.

1. `git pull origin main` (merge from 2026-09-25 includes Supabase support)
2. `cp .env.example .env`
3. **Copy the `DATABASE_URL` + `SUPABASE_S3_*` block from the team group chat** into `.env`  
   (credentials are **never** committed to GitHub — only shared in chat)
4. Keep your existing email / Ollama lines in `.env`
5. Install deps and run:

```bash
cd DSS5105/Final_project/blog
python3.10 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate        # only if a new migration was merged; ask in chat first
./scripts/setup_ollama.sh
python manage.py build_article_index --embed
./scripts/run_local.sh
```

6. **Login**: register at `/accounts/signup/` or use a test account shared in chat  
7. Details: [SUPABASE.md](./Final_project/blog/SUPABASE.md)

### Step 3B — Local-only database (optional)

Use this if you do **not** want the shared Supabase project:

```bash
# you should already be in DSS5105/Final_project/blog

cp .env.example .env          # edit .env — set POSTGRES_* only (leave DATABASE_URL commented)
python3.10 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo_content          # optional demo articles
./scripts/setup_ollama.sh                   # download local models (required for AI)
python manage.py build_article_index --embed
./scripts/run_local.sh
```

Open:

- Home: http://127.0.0.1:8000/home/
- Reading Assistant: http://127.0.0.1:8000/agent/
- Reading list: http://127.0.0.1:8000/agent/reading-list/

**Verify AI works:** top-right badge on `/agent/` should say **`Ollama · … (local)`**, not `Ollama offline · rule-based fallback`.

More detail: [DOCUMENTATION_EN.md](./Final_project/blog/DOCUMENTATION_EN.md) · [DOCUMENTATION.md](./Final_project/blog/DOCUMENTATION.md)（中文）

---

## Documentation

| Document | Language | Description |
|----------|----------|-------------|
| [Final_project/PROJECT_OVERVIEW.md](./Final_project/PROJECT_OVERVIEW.md) | English | High-level proposal & progress checklist |
| [Final_project/项目说明.md](./Final_project/项目说明.md) | 中文 | 项目说明与进度 |
| [Final_project/blog/DOCUMENTATION_EN.md](./Final_project/blog/DOCUMENTATION_EN.md) | English | **Full docs**: features, architecture, setup |
| [Final_project/blog/DOCUMENTATION.md](./Final_project/blog/DOCUMENTATION.md) | 中文 | **完整文档**：功能、架构、运行 |
| [Final_project/blog/README.md](./Final_project/blog/README.md) | English | Blog quick reference |
| [Final_project/blog/SUPABASE.md](./Final_project/blog/SUPABASE.md) | English | Optional shared Supabase database and media storage |
| [DEVLOG.md](./DEVLOG.md) | English | Development log for the `renqian/dev` branch |

---

## Project status (2026-09-25)

**Implemented**: Reading Assistant (`/agent/`), RAG + citations, paywall-aware Q&A, reading paths, recommendations, confirm-before-action, **Learning Path Navigator** (readiness panel + concept bridges), **article likes**, shared **Supabase** DB + media, optional **Cloudflare Workers AI**, eval framework + baselines A/B/C, eval v1 results (DOCUMENTATION §10).

**Still pending (grading deliverables)**: 3-person user study, final report / demo video polish.

---

## Ollama setup (teammates — full AI Q&A)

Default is **local Ollama**, not a cloud API. See [blog/README.md](./Final_project/blog/README.md#ollama-setup--required-for-full-ai-qa) for the checklist, or [DOCUMENTATION.md](./Final_project/blog/DOCUMENTATION.md) §3.2 (中文).

Quick version:

1. Install [Ollama](https://ollama.com/download) and keep it running  
2. `cd Final_project/blog && ./scripts/setup_ollama.sh`  
3. `python manage.py build_article_index --embed`  
4. Verify `/agent/` shows **Ollama (local)**, not fallback  

---

## Quick start (summary)

**Shared team DB (recommended):** follow **Step 3A** — paste Supabase vars from group chat into `.env`.

**Local-only fallback:**

```bash
git clone https://github.com/youngvan12845/DSS5105.git
cd DSS5105/Final_project/blog

cp .env.example .env   # POSTGRES_* only — no DATABASE_URL
python3.10 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate && python manage.py createsuperuser
python manage.py seed_demo_content
./scripts/setup_ollama.sh
python manage.py build_article_index --embed
./scripts/run_local.sh
```

---

## Repository layout

```
DSS5105/
├── README.md                    ← you are here
└── Final_project/
    ├── PROJECT_OVERVIEW.md      ← proposal summary (EN)
    ├── 项目说明.md               ← proposal summary (ZH)
    └── blog/                    ← Django/Wagtail + a_agent app
```
