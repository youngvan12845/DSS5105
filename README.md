# DSS5105 — Group 4 Capstone

NUS DSS5105 capstone project: **Blog Reading Co-Pilot Agent** (Track 5 · CheeseO).

**GitHub**: https://github.com/youngvan12845/DSS5105

---

## Documentation

| Document | Language | Description |
|----------|----------|-------------|
| [Final_project/PROJECT_OVERVIEW.md](./Final_project/PROJECT_OVERVIEW.md) | English | High-level proposal & progress checklist |
| [Final_project/项目说明.md](./Final_project/项目说明.md) | 中文 | 项目说明与进度 |
| [Final_project/blog/DOCUMENTATION_EN.md](./Final_project/blog/DOCUMENTATION_EN.md) | English | **Full docs**: features, architecture, setup |
| [Final_project/blog/DOCUMENTATION.md](./Final_project/blog/DOCUMENTATION.md) | 中文 | **完整文档**：功能、架构、运行 |
| [Final_project/blog/README.md](./Final_project/blog/README.md) | English | Blog quick reference |

---

## Project status (2026-09-08)

**Implemented**: Reading Assistant (`/agent/`), RAG retrieval + citations, paywall-aware Q&A, reading paths, recommendations, confirm-before-action (reading list & comments), reading list page, auto index on publish, eval framework + baselines A/B/C, English UI.

**Still pending (grading deliverables)**: run eval experiments, 3-person user study, final report PDFs.

---

## Ollama setup (teammates — full AI Q&A)

Default is **local Ollama**, not a cloud API. See [blog/README.md](./Final_project/blog/README.md#ollama-setup--required-for-full-ai-qa) for the checklist, or [DOCUMENTATION.md](./Final_project/blog/DOCUMENTATION.md) §3.2 (中文).

Quick version:

1. Install [Ollama](https://ollama.com/download) and keep it running  
2. `cd Final_project/blog && ./scripts/setup_ollama.sh`  
3. `python manage.py build_article_index --embed`  
4. Verify `/agent/` shows **Ollama (local)**, not fallback  

---

## Quick start

```bash
git clone https://github.com/youngvan12845/DSS5105.git
cd DSS5105/Final_project/blog

cp .env.example .env          # set POSTGRES_PASSWORD
python3.10 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo_content          # optional
./scripts/setup_ollama.sh                   # required for full AI Q&A
python manage.py build_article_index --embed
./scripts/run_local.sh
```

Open:

- Home: http://127.0.0.1:8000/home/
- Reading Assistant: http://127.0.0.1:8000/agent/
- Reading list: http://127.0.0.1:8000/agent/reading-list/

See [DOCUMENTATION_EN.md](./Final_project/blog/DOCUMENTATION_EN.md) for full setup and demo flow.

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
