# Feature Design Specification: Blog Learning Path Navigator & Prerequisite Diagnostic Agent

**Document ID**: `SPEC-2026-09-19-NAVIGATOR`  
**Author**: Antigravity & Engineering Team  
**Status**: Approved / In Implementation  
**Target Sprint**: DSS5105 Capstone Sprint 1-2  

---

## 1. Executive Summary & Problem Statement

### 1.1 The Core Problem
Conventional LLM integrations on technical content platforms suffer from the **"Passive Answering Machine" anti-pattern**:
- They act as simple Q&A bots that wait for user prompts.
- Learners suffer from the **"You Don't Know What You Don't Know"** syndrome: when tackling advanced topics (e.g., linear regression practice, asynchronous caching, or GPU matrix multiplication), beginners cannot diagnose their own missing prerequisites and abandon reading out of frustration.
- Conversely, intermediate/senior developers are annoyed by patronizing elementary explanations.

### 1.2 The Solution: Contextual Learning Path Navigator
We transform CheeseO Co-Pilot into an **active, adaptive Learning Path Navigator**:
1. **Prerequisite Dependency Graph**: Structured metadata defining foundational dependencies for all 22 articles across 4 core technical tracks.
2. **Contextual Readiness Diagnostic**: Real-time diff between the article's prerequisites and the user's `BrowsingHistory`, rendering a 🟢/🟡/🔴 readiness score.
3. **In-Page Concept Bridging (1-Minute Quick Bridge)**: Pointers to concise concept chunks from prerequisite articles directly inside the sidebar, avoiding disruptive context switching.
4. **Adaptive Persona (Intermediate & Senior Fast-Track)**: Non-intrusive UI with a 1-click `"I Already Know This"` override, switching the Agent from a "Foundational Tutor" to a "Senior Peer Reviewer" focusing on production pitfalls and architecture trade-offs.
5. **Rigorous Multi-Dimensional Evaluation**: Quantitative benchmarking covering prerequisite accuracy, path monotonicity, faithfulness, and token economy.

---

## 2. Architecture & Data Model

### 2.1 Prerequisite Graph Schema (`a_agent/data/prerequisites_graph.json`)

Each article is registered with its dependencies and downstream milestones:

```json
{
  "linear-regression-practice": {
    "title": "線性迴歸實戰：從損失函數到 Sklearn 建模指標",
    "series": "machine-learning",
    "difficulty": "intermediate",
    "prerequisites": [
      {
        "slug": "ml-supervised-unsupervised",
        "title": "機器學習總覽：監督 vs 非監督學習核心範式",
        "key_concept": "監督學習與標籤回歸定義",
        "bridge_summary": "線性迴歸屬於監督學習，目標是找到最佳擬合超平面以預測連續型目標值 y。"
      },
      {
        "slug": "gradient-descent-intuition",
        "title": "梯度下降直覺：如何找到最佳解？",
        "key_concept": "損失函數與梯度更新步伐",
        "bridge_summary": "透過計算損失函數 MSE 對權重 w 的偏微分（負梯度方向），以學習率步步逼近極小值。"
      }
    ],
    "intermediate_insights": {
      "production_pitfall": "Sklearn 的 LinearRegression 採用 SVD 閉式解，當維度大於 10,000 或資料集過大時易造成記憶體暴增，實務中應改用 SGDRegressor 進行 mini-batch 增量訓練。",
      "tradeoff_challenge": "如果特徵間存在高度多重共線性（Multicollinearity），單純最小平方法會導致權重估計方差失真，此時應考慮 Ridge (L2) 還是 Lasso (L1)？"
    },
    "next_milestones": [
      {
        "slug": "a-4-gb-laptop-gpu-beats-a-12-core-cpu-by-43x-",
        "title": "4 GB 筆電 GPU 比 12 核 CPU 快 43 倍：矩陣計算底層優化",
        "reason": "當迴歸模型數據擴展至百萬筆時，善用 GPU 向量化並行加速訓練流程。"
      }
    ]
  }
}
```

### 2.2 Dynamic Readiness Calculation Engine (`a_agent/services/navigator.py`)

```python
def calculate_article_readiness(user, article_slug: str, session_mastered: list = None) -> dict:
    """
    Computes reading readiness based on user browsing history and explicit skill tags.
    """
    article_meta = PREREQUISITE_GRAPH.get(article_slug)
    if not article_meta or not article_meta.get("prerequisites"):
        return {"status": "green", "score": 100, "gaps": []}
    
    # Query user browsing history
    read_slugs = set()
    if user and user.is_authenticated:
        read_slugs = set(
            BrowsingHistory.objects.filter(user=user).values_list("article__slug", flat=True)
        )
    
    mastered_topics = set(session_mastered or [])

    prereqs = article_meta["prerequisites"]
    gaps = []
    for p in prereqs:
        if p["slug"] not in read_slugs and p["slug"] not in mastered_topics:
            gaps.append(p)
            
    if not gaps:
        return {"status": "green", "score": 100, "gaps": []}
    elif len(gaps) < len(prereqs):
        return {"status": "yellow", "score": 50, "gaps": gaps}
    else:
        return {"status": "orange", "score": 0, "gaps": gaps}
```

---

## 3. UI & Interaction Design

### 3.1 Sidebar Header Readiness Diagnostic Panel

Located at the top of the AI Co-Pilot sidebar in `article_page.html`:

```
+-------------------------------------------------------------+
| 🧭 學習路徑導航員 (Reading Co-Pilot)                         |
+-------------------------------------------------------------+
| 🎯 難度：中階實戰 · 依賴 2 項先修概念                        |
| 閱讀準備度：🟡 50% (發現 1 個潛在盲點)                      |
|                                                             |
|   ✓ 《機器學習總覽》 (已掌握 · 概念入門)                    |
|   ⚠ 《梯度下降直覺》 (站內尚未閱讀 · 影響第 3 節代碼理解)    |
|                                                             |
| [ ⚡ 1分鐘側邊架橋 ]  [ ➔ 跳轉先修篇 ]  [ ⚡ 我已有背景知識 ] |
+-------------------------------------------------------------+
```

### 3.2 Adaptive Persona Behavior

1. **Foundational Mode (Beginner / Default)**:
   - Yellow warning highlights missing prerequisite concepts.
   - Clicking `"1分鐘側邊架橋"` renders an inline callout card containing the core formula and concept diagram without leaving the article.
   - End-of-article roadmap recommends step-by-step intermediate progression.
2. **Senior Peer Mode (Intermediate / Clicked "I Already Know This")**:
   - Status instantly flips to 🟢 100%.
   - Persistent preference stored in session / profile.
   - Sidebar displays **"生產環境避坑 (Production Pitfalls)"** and **"架構權衡挑戰 (Trade-off Challenge)"** instead of remedial definitions.
   - End-of-article roadmap directs to hardcore flagship articles (`Hardcore Fast-Track`).

---

## 4. Multi-Dimensional Evaluation Framework

We institute 4 automated evaluation tracks:

### 4.1 Track 1: Prerequisite Gap Detection & Path Monotonicity
- **Gap Recall**: 100% detection rate when test profiles have missing history.
- **Monotonicity**: Recommended sequences must satisfy $D_1 \le D_2 \le D_3$ without retrograde difficulty jumps.
- **Override Safety**: Verifies that clicking `"I Already Know This"` silences yellow warnings for all sibling articles.

### 4.2 Track 2: Faithfulness & Inline Citation (RAGAS / G-Eval Standard)
- Automated verification that:
  - 100% of concept bridge snippets map directly to verified chunk texts in the database.
  - Zero out-of-context hallucinated external references.
  - All Markdown links resolve to active internal slugs.

### 4.3 Track 3: Simulated User Trajectory (Persona End-to-End)
- **Persona 1 (Novice)**: Accesses intermediate article -> Reads bridge chunk -> Completes QA.
- **Persona 2 (Senior Engineer)**: Skips beginner prerequisites -> Engages in edge-case discussion -> Navigates to flagship architecture.
- **Persona 3 (Adversarial Scraper)**: Attempts to bypass paywall -> Physically redacted chunks served (100% secure).

### 4.4 Track 4: Engineering & Cost Efficiency
- **Token Compression**: Retrieval chunks + concise bridge summaries consume $\le 1,200$ tokens per query (vs. 7,500 tokens for full article context), an 84% reduction.
- **Latency**: End-to-end edge inference on Cloudflare Workers AI 32B maintained at $P_{95} \le 2.5\text{s}$.
