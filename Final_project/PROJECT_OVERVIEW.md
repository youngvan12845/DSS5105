# DSS5105 Capstone — Project Overview

**Group 4 · Track 5 (Custom)**  
**Project name: Blog Reading Co-Pilot Agent**  
**Last updated: 2026-09-08**

> Chinese version: [项目说明.md](./项目说明.md)  
> **Full technical docs**: [blog/DOCUMENTATION_EN.md](./blog/DOCUMENTATION_EN.md) · [blog/DOCUMENTATION.md](./blog/DOCUMENTATION.md)

---

## 1. What This Project Is

We are building an **AI reading assistant (Agent)** on top of our **existing blog platform** to help readers:

- **Find content, ask questions, and view citations** across the article library
- **Get recommendations and continue-reading suggestions** based on reading history
- **Plan reading order by topic**
- **Perform actions** such as managing a reading list or drafting comments (with user confirmation)

This is **not** a simple ChatGPT chatbox. It is an Agent system with **purpose-built tools**, designed to match the depth of Track 1 (Factory Co-Pilot).

**This direction has been approved by Prof. Tan (Aug 2026).**

---

## 2. Why Track 5

| Advantage | Description |
|-----------|-------------|
| Existing platform | Blog already runs: articles, users, search, comments, membership/points |
| Real-world scenario | Grounded in real product needs on a blog platform |
| Differentiation | Paywall-aware Q&A is a feature other tracks do not have |

---

## 3. What the Blog Already Has

Code location: `Final_project/blog/`  
GitHub: https://github.com/youngvan12845/DSS5105

| Module | Existing features | Role for the Agent |
|--------|-------------------|--------------------|
| `a_blog` | Articles, tags, search, comments | Agent **knowledge base** and **Baseline B (keyword search)** |
| `a_users` | Login, profile, **browsing history** | Data source for **personalized recommendations and continue-reading** |
| Paywall logic | `is_free`, points, subscriptions | **Paywall-aware** Q&A rules |
| Frontend | Django + HTMX | Chat UI can be integrated into the same site |

**Agent layer (`a_agent`) — implemented:**

| Component | Status | Location |
|-----------|--------|----------|
| LLM / RAG / Agent orchestrator | Done | `blog/a_agent/services/orchestrator.py` |
| Vector index (embeddings) | Done | `ArticleChunk` + `build_article_index --embed` |
| Chat UI + article panel | Done | `/agent/`, HTMX templates |
| Reading list model + page | Done | `/agent/reading-list/` |
| Reading path configuration | Done | `blog/a_agent/data/reading_paths.json` |
| Eval scripts + 33-task set + baselines A/B/C | Done (framework) | `run_agent_eval`, `blog/a_agent/eval/` |
| Auto index on Wagtail publish | Done | `blog/a_agent/signals.py` |

**Still pending for final grading:** run baseline comparison experiments, 3-person user study, Evaluation.pdf / final report.

---

## 4. Six Core Capability Areas

Aligned with Track 1’s tool-design approach; these are the capabilities promised in our proposal:

### 4.1 Retrieval & Tracing

- Reader asks: “What does article X cover?” or “Which articles mention concept Y?”
- The Agent retrieves from the article corpus and returns answers with **source links / paragraph citations**
- Facts must come from tool retrieval, not LLM fabrication

### 4.2 Judgement & Discovery

- Recommend the next article using **browsing history + tags + article metadata**
- Surface related articles the user may have missed
- On login or when opening the assistant: “You were reading…”, “In the same topic, you haven’t read…”

### 4.3 Reading Path Planning

- User says “I want to learn machine learning” → returns an **ordered reading list**
- **v1:** paths **curated manually** by tag/topic (admin or JSON); the Agent selects and presents them
- Full automatic graph reasoning is out of scope for v1 (stretch goal)

### 4.4 Proactive Assistance

- Continue-reading suggestions based on `BrowsingHistory`
- **v1 does not** include email/push scheduled reminders (Celery not configured yet)
- Proactive prompts within **session / on login** are sufficient for v1

### 4.5 Confirmed Actions

- Add articles to a reading list
- Generate comment drafts (published only after user confirmation)
- **No action runs before confirm**; all executed actions are **audit-logged**

### 4.6 Paywall-aware Q&A

- Non-members asking for paid-article details → **no full text leaked**; summary or subscription prompt only
- Evaluation includes dedicated tests for **unauthorized paid-content leakage**

---

## 5. Technical Approach (Brief)

```
User ←→ Chat UI (HTMX)
           ↓
      Agent Orchestrator (LLM routing: choose tools, compose answer)
           ↓
    ┌──────┼──────┬──────────┬────────────┐
    ↓      ↓      ↓          ↓            ↓
  RAG   Keyword  Browsing   Reading     Paywall
  search search   history    list        check
    ↓
 Embeddings in PostgreSQL JSONField ← auto-sync on Wagtail publish
    ↓
 PostgreSQL (existing blog database)
```

**Django app: `a_agent`** (live under `blog/a_agent/`)

---

## 6. Evaluation Plan (Required — Do Not Skip)

### 6.1 Test Set

At least **30 tasks** grounded in real blog articles, each with a **verified expected outcome**:

| Category | Approx. count | Example |
|----------|---------------|---------|
| Factual Q&A | 10 | “Summarize article X” |
| Cross-article lookup | 5 | “Which articles discuss Y?” |
| Recommendation / path | 5 | “What should I read first to learn XX?” |
| State / continue-reading | 5 | “Where did I leave off last time?” |
| Action | 5 | “Add these 3 articles to my list” |
| Adversarial / edge cases | ≥5 | Non-existent articles, ambiguous queries, paywall bait |

### 6.2 Baseline Comparison

| System | Description |
|--------|-------------|
| Baseline A | Plain LLM, no retrieval |
| Baseline B | Existing Wagtail keyword search + LLM summarization |
| Baseline C | Basic RAG (vector retrieval + LLM; no tools, personalization, or paywall) |
| **Full Agent** | Complete tool set (target: beat Baseline C) |

### 6.3 Key Metrics

- Answer accuracy
- Citation accuracy
- Hallucination rate
- Refusal accuracy (correctly declines when appropriate)
- Paywall leak rate (target: **0**)
- Recommendation Hit@K
- Unsafe action rate (actions without confirm; target: **0**)

### 6.4 Human Evaluation

At least **3 participants** (classmates OK): task completion time, subjective satisfaction, blind preference vs. baselines.

---

## 7. Development Phases (Suggested Order)

### Phase 1 — MVP (demo-ready)

- [x] Create `a_agent` app
- [x] Article chunking + vector index pipeline
- [x] Basic RAG Q&A with source links
- [x] Simple chat UI
- [x] Baseline B (keyword search) working

### Phase 2 — Agent capabilities

- [x] Tool layer (retrieval / history / paywall / action)
- [x] Recommendations from browsing history
- [x] Reading list + confirm flow + audit log
- [x] Paywall-aware filtering

### Phase 3 — Report and grading

- [x] Reading paths (manual curation version)
- [x] Session-based continue-reading prompts
- [x] 30+ task eval set (33 tasks in `eval_tasks.json`; refine gold labels as a team)
- [x] Run 3-baseline comparison experiments (v1 results: see [blog/DOCUMENTATION_EN.md §10](./blog/DOCUMENTATION_EN.md#10-evaluation-results-v1--2026-09-11))
- [ ] 3-person user study
- [ ] Final report + demo video

**Team participation (overview):**

1. Everyone runs `run_agent_eval` locally at least once (see DOCUMENTATION §10.5)
2. Then: manual FAIL review, optional `eval_tasks.json` refine, user study, Evaluation.pdf, demo video (§10.6)

---

## 8. FAQ

**Q: How is this different from a normal RAG chatbot?**  
A: We have **multiple tool types** (not just vector search), **personalization** (browsing history), **paywall rules**, **confirm-before-action** flows, and **baseline comparison evaluation**. The course expects Agent system design, not a single prompt wrapper.

**Q: What if we cannot finish every feature?**  
A: The proposal commits to **six capability areas**, not every detail. Phase 1–2 are must-haves; path planning and proactive features can ship in simplified form. **Eval and baselines cannot be cut.**

**Q: Where is the code? How do I run it?**  
A: GitHub repo https://github.com/youngvan12845/DSS5105 — code in `Final_project/blog/`. See [blog/DOCUMENTATION_EN.md](./blog/DOCUMENTATION_EN.md) §3 or run `./scripts/run_local.sh`.

---

## 9. Current team next steps

1. **Clone & run locally** — follow [blog/DOCUMENTATION_EN.md](./blog/DOCUMENTATION_EN.md) §3
2. **Demo the Agent** — `/agent/`, article panel, reading list, confirm actions, paywall
3. **Before final submission** — refine eval (optional JSON), 3-person user study, write Evaluation.pdf (baseline v1 done — DOCUMENTATION §10)
4. **Sprint video** — use demo flow in DOCUMENTATION §3.6

---

*Maintained by Group 4. For updates, see [项目说明.md](./项目说明.md) and [blog/DOCUMENTATION_EN.md](./blog/DOCUMENTATION_EN.md).*
