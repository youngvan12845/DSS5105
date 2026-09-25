# Learning Path Navigator & Prerequisite Diagnostic Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the blog AI assistant into an active, adaptive Learning Path Navigator with real-time prerequisite gap diagnosis, in-page concept bridging, intermediate/senior peer adaptability, and a 4-track automated evaluation suite.

**Architecture:** 
- A structured JSON repository (`prerequisites_graph.json`) defining prerequisite dependencies, bridge summaries, senior production pitfalls, and next milestones for all 22 articles across 4 tracks.
- A service layer (`a_agent/services/navigator.py`) computing user-specific readiness against `BrowsingHistory` and session overrides.
- Integration into `a_agent/orchestrator.py` and `a_agent/views.py` (`article_panel_view`, `/agent/bridge/<slug>/`, `/agent/master-prerequisite/`).
- Sidebar UI in `article_panel.html` rendering real-time readiness status badges (🟢/🟡/🔴), 1-minute in-page bridge cards, and 1-click senior overrides.
- Automated multi-dimensional evaluation command (`manage.py run_navigator_eval`) and unit test suite.

**Tech Stack:** Python 3.12, Django 5.0, Wagtail, HTMX, Tailwind CSS, Cloudflare Workers AI / Qwen 2.5 Coder 32B.

---

## File Structure & Responsibilities

1. **`a_agent/data/prerequisites_graph.json`** [NEW]
   - Source of truth for 22 articles: prerequisite links, core concepts, 1-minute bridge summaries, intermediate pitfalls/trade-offs, and downstream milestones.
2. **`a_agent/services/navigator.py`** [NEW]
   - Business logic: loading graph, diffing against `BrowsingHistory`, calculating readiness score (0-100%), generating bridge summaries, and recording mastered topics.
3. **`a_agent/tests/test_navigator.py`** [NEW]
   - Unit tests for readiness logic, gap detection, senior overrides, and graph integrity.
4. **`a_agent/urls.py` & `a_agent/views.py`** [MODIFY]
   - Add endpoints:
     - `POST /agent/master-prerequisite/`: stores user's "I already know this" preference.
     - `GET /agent/bridge/<slug>/`: returns snippet HTML for in-sidebar 1-minute bridging.
   - Update `article_panel_view`: inject `readiness` context into `article_panel.html`.
5. **`a_agent/templates/a_agent/partials/article_panel.html`** [MODIFY]
   - Insert Readiness Diagnostic Panel at sidebar top with 🟢/🟡/🔴 badge, missing prerequisite list, `[ ⚡ 1分鐘側邊架橋 ]` button, and `[ ⚡ 我已有背景知識 ]` button.
6. **`a_agent/orchestrator.py`** [MODIFY]
   - Teach agent system prompt about learning path navigation, prerequisite checks, and adaptive tone (novice vs. senior peer).
7. **`a_agent/management/commands/run_navigator_eval.py`** [NEW]
   - Automated 4-track evaluation: Prerequisite gap recall, path monotonicity, bridge faithfulness, and token compression ratio.

---

## Bite-Sized Implementation Tasks

### Task 1: Prerequisite Graph Data Layer (`prerequisites_graph.json`)

**Files:**
- Create: `Final_project/blog/a_agent/data/prerequisites_graph.json`
- Test: `Final_project/blog/a_agent/tests/test_navigator.py`

- [ ] **Step 1: Write the failing unit test for graph loading and validation**
- [ ] **Step 2: Run test to verify it fails** (`python manage.py test a_agent.tests.test_navigator`)
- [ ] **Step 3: Create `prerequisites_graph.json` covering all 22 live articles across 4 tracks**
- [ ] **Step 4: Run test to verify graph schema validation passes**
- [ ] **Step 5: Git commit**

---

### Task 2: Navigator Service Layer (`services/navigator.py`)

**Files:**
- Create: `Final_project/blog/a_agent/services/navigator.py`
- Modify: `Final_project/blog/a_agent/services/__init__.py`
- Test: `Final_project/blog/a_agent/tests/test_navigator.py`

- [ ] **Step 1: Write failing unit tests for readiness calculation (Green, Yellow, Orange states)**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement `calculate_article_readiness()`, `get_concept_bridge()`, and `mark_prerequisite_mastered()`**
- [ ] **Step 4: Run unit tests to verify all readiness and override tests pass**
- [ ] **Step 5: Git commit**

---

### Task 3: API Endpoints & Session Management (`views.py` & `urls.py`)

**Files:**
- Modify: `Final_project/blog/a_agent/urls.py`
- Modify: `Final_project/blog/a_agent/views.py`
- Test: `Final_project/blog/a_agent/tests/test_navigator.py`

- [ ] **Step 1: Write test for `/agent/master-prerequisite/` and `/agent/bridge/<slug>/` views**
- [ ] **Step 2: Run test to verify endpoint 404 failure**
- [ ] **Step 3: Implement `master_prerequisite_view` and `concept_bridge_view` and update `article_panel_view`**
- [ ] **Step 4: Run tests to verify endpoints return 200 with correct JSON/HTML**
- [ ] **Step 5: Git commit**

---

### Task 4: Sidebar Diagnostic Panel & Interactive Bridging UI

**Files:**
- Modify: `Final_project/blog/a_agent/templates/a_agent/partials/article_panel.html`
- Create: `Final_project/blog/a_agent/templates/a_agent/partials/concept_bridge_card.html`

- [ ] **Step 1: Create partial template `concept_bridge_card.html` for clean in-page callout**
- [ ] **Step 2: Embed Diagnostic Header in `article_panel.html` with readiness badge and gap items**
- [ ] **Step 3: Add HTMX / JS interactions for 1-click bridge expansion and senior override**
- [ ] **Step 4: Manual browser/HTTP check of sidebar rendering on article pages**
- [ ] **Step 5: Git commit**

---

### Task 5: Agent Prompt & Orchestrator Adaptive Persona

**Files:**
- Modify: `Final_project/blog/a_agent/orchestrator.py`
- Modify: `Final_project/blog/a_agent/prompts.py` (or system prompt in orchestrator)

- [ ] **Step 1: Write test checking agent response incorporates prerequisite diagnosis when queried**
- [ ] **Step 2: Inject prerequisite context and adaptive persona instructions into system prompt**
- [ ] **Step 3: Verify with test query**
- [ ] **Step 4: Git commit**

---

### Task 6: 4-Track Automated Evaluation Command (`run_navigator_eval`)

**Files:**
- Create: `Final_project/blog/a_agent/management/commands/run_navigator_eval.py`

- [ ] **Step 1: Implement Track 1 (Gap Recall & Monotonicity check across all 22 articles)**
- [ ] **Step 2: Implement Track 2 (Bridge Faithfulness & citation check)**
- [ ] **Step 3: Implement Track 3 (Simulated Novice vs. Senior user trajectories)**
- [ ] **Step 4: Implement Track 4 (Token reduction comparison calculation)**
- [ ] **Step 5: Run `python manage.py run_navigator_eval` and verify 100% metrics output**
- [ ] **Step 6: Git commit and push to remote branch**
