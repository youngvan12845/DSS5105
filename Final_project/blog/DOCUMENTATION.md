# CheeseO Blog Reading Co-Pilot — 项目文档

**课程**：DSS5105 Capstone · Group 4 · Track 5（Custom）  
**项目名称**：Blog Reading Co-Pilot Agent  
**代码路径**：`Final_project/blog/`  
**最后更新**：2026-09-08  

**English documentation**: [DOCUMENTATION_EN.md](./DOCUMENTATION_EN.md)

---

## 1. 功能介绍

### 1.1 项目概述

CheeseO 是一个基于 Django + Wagtail 的博客平台，并在其之上集成了 **Reading Assistant（阅读助手）**——一个具备专用工具（Tools）、可追溯引用（Citations）和确认后执行（Confirm-before-action）能力的 Agent 系统。

与普通 ChatGPT 对话框不同，本系统的回答**优先来自站内文章检索结果**，而非模型自由生成；涉及付费内容、阅读列表变更、评论发布等操作均有明确规则与审计记录。

**目标用户**：博客读者——希望快速找文、提问、规划阅读顺序、管理待读清单的用户。

---

### 1.2 博客平台基础功能

在 Agent 之外，站点本身已具备完整的博客与会员能力：

| 模块 | 功能 |
|------|------|
| `a_blog` | 文章发布、标签、评论、Wagtail CMS 管理 |
| `a_users` | 注册登录、个人资料、**浏览历史**（Browsing History） |
| `a_order` | 会员订阅、积分充值 |
| `a_points` | 每日签到、积分记录 |
| Paywall | 免费/付费文章、积分解锁、订阅全文访问 |

Agent 直接复用上述模块的数据与权限逻辑，无需重复建设用户体系。

---

### 1.3 Reading Assistant 六大核心能力

与项目 Proposal（`PROJECT_OVERVIEW.md` §4）对齐：

#### （1）检索与溯源（Retrieval & Tracing）

- 支持三种检索方式：**关键词搜索**（Wagtail）、**分块全文检索**、**向量语义检索**（Ollama embedding）。
- 回答附带 **Citation 卡片**，可点击跳转原文。
- 在文章详情页可进入 **Article Focus（文章聚焦）** 模式，仅基于当前文章作答。

**示例**：「What is RAG?」「Summarize this article」

#### （2）推荐与发现（Judgement & Discovery）

- 根据用户 **Browsing History** 与文章 **标签重叠度** 推荐下一篇阅读。
- 打开 Assistant 的空会话时，自动展示 **Continue Reading** 提示（最近浏览 + 推荐文章快捷按钮）。

**示例**：「What should I read next?」「Recommend articles about Python」

#### （3）阅读路径规划（Reading Path Planning）

- 路径由 `a_agent/data/reading_paths.json` **人工策展**（按主题/标签匹配）。
- Agent 识别学习意图后返回有序文章列表及说明。

**示例**：「I want to learn machine learning. What reading path should I follow?」

#### （4）主动协助（Proactive Assistance — v1）

- **会话内**主动提示：新会话首次进入时展示欢迎语、最近阅读、推荐与快捷 Chip。
- **不包含**邮件/Push 定时提醒（v1 范围外）。

#### （5）确认后执行（Confirmed Actions）

所有有副作用的操作均 **先提议 → 用户 Confirm → 再执行**，并写入 `AgentActionLog` 审计日志：

| 操作 | 流程 |
|------|------|
| 加入阅读列表 | Agent 识别意图 → 展示待确认卡片 → Confirm 后写入 `ReadingListItem` |
| 移出阅读列表 | 同上，Confirm 后删除 |
| 评论草稿 | Agent 生成草稿 → Confirm 后发布到 `a_blog` 评论系统 |

未确认前，**不会**修改数据库或发表评论。

#### （6）Paywall 感知问答（Paywall-aware Q&A）

- 检索层根据用户身份（未登录 / 免费 / 订阅 / 积分已解锁）决定可见文本范围。
- 付费文章未解锁时，返回 **预览片段**，不泄漏全文；LLM 系统提示亦禁止输出付费正文。
- 对不存在于站内的主题（如「量子计算文章」），应明确拒绝而非编造。

---

### 1.4 用户界面与入口

| 入口 | URL | 说明 |
|------|-----|------|
| 首页 | `/home/` | CheeseO 品牌首页 |
| 文章列表 | `/blog/` | 全部文章 |
| Reading Assistant | `/agent/` | 主聊天界面（需登录） |
| 阅读列表 | `/agent/reading-list/` | 独立待读清单页 |
| 文章页 Agent 面板 | 文章页右侧/移动端抽屉 | 单篇文章聚焦问答 |
| Wagtail CMS | `/blog/cms/` | 内容管理（管理员） |
| 浏览历史 | `/profile/browsing-history/` | 用户阅读记录 |

导航栏 **Reading Assistant** 与用户下拉菜单 **Reading List** 均可进入 Agent 相关功能。

---

### 1.5 其他功能特性

- **多会话管理**：新建、切换、删除 Chat Session；每篇文章可有独立会话。
- **LLM 后端可切换**：默认本地 Ollama；可配置 OpenAI；离线时回退到规则式检索摘要。
- **可选视觉输入**：支持上传图片提问（需 vision 模型，如 `qwen2.5vl:7b`）。
- **自动索引更新**：Wagtail 发布/下架文章时，自动 rebuild 该文的检索索引。
- **英文 UI**：Agent 及主要站点界面为英文（CMS 内历史中文内容需自行替换）。

---

## 2. 代码架构介绍

### 2.1 技术栈

| 层级 | 技术 |
|------|------|
| Web 框架 | Django 5.1 |
| CMS | Wagtail 7.0 |
| 前端交互 | HTMX + Tailwind CSS |
| 数据库 | PostgreSQL |
| LLM | Ollama（默认）/ OpenAI API |
| Embedding | Ollama `nomic-embed-text` |
| 向量存储 | PostgreSQL JSONField（`ArticleChunk.embedding`） |

---

### 2.2 项目目录结构

```
blog/
├── a_core/              # Django 项目配置、根 URL
├── a_home/              # 首页、About、Help
├── a_blog/              # Wagtail 文章、评论、文章页模板
├── a_users/             # 用户、资料、浏览历史
├── a_order/             # 订阅与充值
├── a_points/            # 积分与签到
├── a_agent/             # ★ Reading Assistant 核心应用
│   ├── models.py        # 会话、消息、索引块、阅读列表、审计日志
│   ├── views.py         # Chat / 确认操作 / 阅读列表页
│   ├── urls.py
│   ├── signals.py       # 文章发布/下架 → 自动索引
│   ├── services/
│   │   ├── orchestrator.py    # Agent 编排（意图 → 工具 → LLM）
│   │   ├── llm.py             # Ollama / OpenAI 调用
│   │   ├── embeddings.py      # 向量 embedding
│   │   ├── article_index.py   # 索引构建逻辑
│   │   ├── article_text.py    # HTML → 纯文本、分块
│   │   └── proactive.py       # 会话主动提示
│   ├── tools/             # Agent 工具层（每个 tool 单一职责）
│   │   ├── keyword_search.py
│   │   ├── chunk_search.py
│   │   ├── vector_search.py
│   │   ├── article_scope.py
│   │   ├── browsing_history.py
│   │   ├── recommend.py
│   │   ├── reading_paths.py
│   │   ├── reading_list.py
│   │   ├── comment_draft.py
│   │   └── access.py          # Paywall 权限判断
│   ├── data/
│   │   ├── reading_paths.json
│   │   └── eval_tasks.json    # 评估任务集（交作业时使用）
│   ├── eval/              # 评估 runner + baseline A/B/C
│   ├── templates/a_agent/ # Chat UI、Partials
│   └── management/commands/
│       ├── build_article_index.py
│       ├── seed_demo_content.py
│       └── run_agent_eval.py
├── templates/           # 全站公共模板（header 等）
├── scripts/
│   ├── run_local.sh
│   └── setup_ollama.sh
├── manage.py
├── requirements.txt
└── .env.example
```

---

### 2.3 系统架构与数据流

```
┌─────────────┐     HTMX      ┌──────────────────┐
│   用户浏览器  │ ◄──────────► │  a_agent/views   │
└─────────────┘               └────────┬─────────┘
                                       │
                                       ▼
                            ┌──────────────────────┐
                            │ services/orchestrator │
                            │  1. 意图分类           │
                            │  2. 调用 Tools         │
                            │  3. 组装 Prompt        │
                            │  4. LLM 生成 / Fallback│
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
                            │ ArticleChunk (索引)   │
                            │ Wagtail ArticlePage   │
                            │ BrowsingHistory       │
                            └──────────────────────┘
```

**一次问答的典型流程**：

1. 用户通过 HTMX POST 发送消息 → `send_message_view`
2. 消息写入 `ChatMessage`，调用 `handle_user_message()`
3. Orchestrator 根据关键词匹配 **意图集合**（检索 / 推荐 / 路径 / 历史 / 动作等）
4. 并行调用对应 **Tools**，收集 hits、history、reading path 等结构化结果
5. 若有写操作意图，创建 `AgentActionLog` 作为 **pending_action**（不立即执行）
6. LLM 基于 tool results 生成自然语言回答；若无 LLM 则 `_fallback_answer()` 规则输出
7. 助手消息连同 citations、pending_action 渲染到前端；用户点击 Confirm 触发 `confirm_action_view`

---

### 2.4 Agent 编排层（Orchestrator）

文件：`a_agent/services/orchestrator.py`

| 步骤 | 说明 |
|------|------|
| `_classify_intents()` | 基于关键词启发式识别用户意图（可叠加多个 intent） |
| Tool 调用 | 按 intent 调用对应 tool，结果写入 `tool_trace` 便于调试与评估 |
| Article Scope | 若传入 `article_id`，强制限定检索范围为单篇文章 |
| LLM Prompt | System prompt 要求仅依据 tool results 作答、英文回复、禁止泄漏付费正文 |
| Fallback | Ollama 不可用时，用检索片段拼接可读回答 |

**主要意图与工具映射**：

| Intent | 工具 |
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

### 2.5 核心数据模型

文件：`a_agent/models.py`

| 模型 | 用途 |
|------|------|
| `ChatSession` | 用户聊天会话（标题、所选 LLM 模型） |
| `ChatMessage` | 单条消息；存储 citations、tool_trace、pending_action（JSON） |
| `ArticleChunk` | 文章分块索引 + 可选 embedding 向量 |
| `ReadingListItem` | 用户待读清单条目 |
| `AgentActionLog` | 待确认/已执行的操作审计记录 |

---

### 2.6 工具层设计原则

每个 Tool 文件对应一类能力，输入/输出结构清晰，便于 Capstone 文档中的 Tool Specification 表格：

- **Retrieval**：`keyword_search` / `chunk_search` / `vector_search` / `article_scope`
- **Personalization**：`browsing_history` / `recommend`
- **Planning**：`reading_paths`
- **Action**：`reading_list` / `comment_draft`
- **Access Control**：`access`（被其他 retrieval tools 调用）

Paywall 逻辑集中在 `access.py` 的 `can_user_read_full()`，避免在多处重复判断。

---

### 2.7 索引与 Wagtail 集成

- **手动全量索引**：`python manage.py build_article_index [--embed]`
- **自动增量索引**：`a_agent/signals.py` 监听 `page_published` / `page_unpublished`
- 索引逻辑封装于 `services/article_index.py` 的 `index_article()`

---

## 3. 运行指导

### 3.1 环境要求

| 依赖 | 版本/说明 |
|------|-----------|
| Python | 3.10+ |
| PostgreSQL | 本地安装，需先创建数据库 |
| Git | 克隆代码 |
| Ollama（**组员推荐必装**） | 本地 LLM + Embedding；完整 AI 问答依赖此项；[下载](https://ollama.com/download) |
| OpenAI（可选） | 设置 `AGENT_LLM_PROVIDER=openai` 与 API Key，无需下载本地模型 |

---

### 3.2 组员必做：Ollama 安装清单（完整 AI 问答）

**默认使用本地 Ollama，不是线上 API。** 组员要用自然语言 AI 回答（而非规则检索 fallback），请逐项完成：

- [ ] 安装 [Ollama](https://ollama.com/download)，并保持后台运行
- [ ] 在 `blog/` 目录执行：`./scripts/setup_ollama.sh`（下载对话 + embedding 模型）
- [ ] 执行：`python manage.py build_article_index --embed`（向量检索依赖 Ollama）
- [ ] 启动：`./scripts/run_local.sh`
- [ ] 打开 `/agent/`，右上角应显示 **`Ollama · … (local)`**，而不是 `Ollama offline · rule-based fallback`

**默认会下载的模型：**

| 模型 | 用途 | 体积（约） |
|------|------|-----------|
| `qwen2.5vl:7b` | 对话 / 可选图片问答 | 数 GB |
| `nomic-embed-text` | 向量语义检索 | 较小 |

**更轻量的对话模型（可选）：** 在 `.env` 设置 `OLLAMA_MODEL=qwen2.5:7b`，再执行 `ollama pull qwen2.5:7b`。

**不装 Ollama 会怎样？** 网站能跑，但 Assistant 只有检索片段拼接，**没有流畅 LLM 总结**，不适合 demo。

**替代方案：OpenAI（不用下本地模型）**

```env
AGENT_LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

需要付费 API Key；付费文章片段可能发送到 OpenAI。若不装 Ollama，向量检索可改用 `build_article_index`（不加 `--embed`），语义搜索会变弱。

---

### 3.3 首次安装（逐步）

> **组员 Clone 教程**见仓库根目录 [README.md](../../README.md#teammate-onboarding--clone--run-start-here) 或本文 [项目说明.md](../项目说明.md) §0。

```bash
# 0. Clone（若尚未 clone）
git clone https://github.com/youngvan12845/DSS5105.git
cd DSS5105/Final_project/blog

# 1. 进入项目目录（若已 clone，只需这一步）
cd Final_project/blog

# 2. 创建虚拟环境并安装依赖
python3.10 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，至少设置 POSTGRES_PASSWORD 和 DJANGO_SECRET_KEY

# 4. 创建 PostgreSQL 数据库（在 psql 或 pgAdmin 中）
# CREATE DATABASE cheeseoo;

# 5. 数据库迁移
python manage.py migrate

# 6. 创建管理员账号
python manage.py createsuperuser

# 7. （可选）导入 Demo 文章
python manage.py seed_demo_content

# 8. 安装 Ollama 模型（完整 AI 问答必做，见 §3.2）
./scripts/setup_ollama.sh

# 9. 构建检索索引（需在 Ollama 运行后执行）
python manage.py build_article_index --embed
```

---

### 3.4 日常启动

```bash
cd Final_project/blog
source .venv/bin/activate

# 确保 PostgreSQL 与 Ollama 已运行
./scripts/run_local.sh
```

浏览器访问：

- 站点：http://127.0.0.1:8000/home/
- Reading Assistant：http://127.0.0.1:8000/agent/
- CMS：http://127.0.0.1:8000/blog/cms/

---

### 3.5 常用管理命令

| 命令 | 说明 |
|------|------|
| `python manage.py runserver` | 启动开发服务器 |
| `python manage.py seed_demo_content` | 写入 Demo 文章（首次开发用） |
| `python manage.py build_article_index` | 重建全文索引（不含向量） |
| `python manage.py build_article_index --embed` | 重建索引 + Ollama 向量 |
| `python manage.py run_agent_eval` | 运行 Agent 评估（交作业前） |
| `python manage.py run_agent_eval --variant all --no-fail-exit` | 对比 Full Agent vs Baseline A/B/C |

> **说明**：在 Wagtail CMS 发布/更新文章后，系统会**自动** rebuild 该文索引；仅在首次部署或批量导入后需手动执行 `build_article_index --embed`。

---

### 3.6 环境变量说明

详见 `.env.example`：

| 变量 | 说明 |
|------|------|
| `POSTGRES_*` | PostgreSQL 连接信息 |
| `DJANGO_DEBUG` | 开发模式（生产环境设为 `False`） |
| `DJANGO_SECRET_KEY` | Django 密钥 |
| `AGENT_LLM_PROVIDER` | `ollama`（默认）或 `openai` |
| `OLLAMA_MODEL` | 对话模型，如 `qwen2.5vl:7b` |
| `OLLAMA_EMBED_MODEL` | Embedding 模型，如 `nomic-embed-text` |
| `OPENAI_API_KEY` | 使用 OpenAI 时必填 |
| `OPENAI_MODEL` | 如 `gpt-4o-mini` |

---

### 3.7 演示建议流程

登录后按以下顺序演示 Agent 能力（适合 Sprint 视频）：

1. 打开 `/agent/`，展示 Continue Reading 主动提示
2. 提问「What is RAG?」→ 展示 citations
3. 进入某篇文章，使用右侧 Agent 面板「Summarize this article」
4. 「Add the RAG article to my reading list」→ 展示 Confirm → 在 `/agent/reading-list/` 查看
5. 打开一篇付费文章（未解锁），提问全文 → 展示 paywall 不泄漏
6. 提问不存在的主题（如 quantum computing）→ 展示拒绝回答

---

### 3.8 常见问题

**Q：Assistant 显示「Ollama offline · rule-based fallback」**  
A：启动 Ollama 应用，或运行 `./scripts/setup_ollama.sh` 拉取模型；也可改用 OpenAI。

**Q：Agent 回答「article is not indexed yet」**  
A：运行 `python manage.py build_article_index --embed`；或在 CMS 重新发布该文章触发自动索引。

**Q：向量搜索无结果**  
A：确认 Ollama 在运行且已 `ollama pull nomic-embed-text`；索引需带 `--embed` 参数构建。

**Q：付费文章仍能看全文**  
A：确认未订阅/未用积分解锁；Agent 对未授权用户只应返回预览片段。

**Q：PostgreSQL 连接失败**  
A：检查 `.env` 中 `POSTGRES_*` 配置，确认数据库服务已启动且 `cheeseoo` 库已创建。

---

## 附录：与课程交付物的关系

| 交付文件 | 本文档对应章节 |
|----------|----------------|
| Readme.pdf | §3 运行指导 |
| Documentation.pdf | §1 功能 + §2 架构（可导出本文档为 PDF） |
| Evaluation.pdf | 使用 `run_agent_eval`（评估部分交作业前补充） |

**GitHub**：https://github.com/youngvan12845/DSS5105  
**代码目录**：`Final_project/blog/`

---

*文档维护：Group 4 · 如有功能变更请同步更新本节与 README.md。*
