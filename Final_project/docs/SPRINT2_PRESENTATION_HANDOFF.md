# Sprint 2 演示材料 — 第 4 组，Track 5

幻灯片和视频以这份文件为准。其他说明里的数字或完成状态若与这里不一致，以这里为准。

同一份内容写两遍：先中文，后英文。幻灯片和口播用英文，从后半部分抄。

---

# 中文

## 要交什么

| 项目 | 要求 |
|---|---|
| 时间 | 2026 年 10 月 30 日周五下午 3:00。迟交收到下午 7:00。 |
| 幻灯片 | `Presentation_Group04_Sprint2.pptx` 或 `.pdf` |
| 视频 | `Presentation_Group04_Sprint2.mp4`，同时上传 YouTube |
| 长度 | 短于 5:00。录到 5:00 必须停。大约 3 分钟讲幻灯片，2 分钟演示。 |
| 现场 | 问答必须到场。从第 22 组倒序，晚上 7:00，LT29。 |
| 代码 | https://github.com/youngvan12845/DSS5105 的 `main` |

Track 5 不加 Track 1 / Track 2 的电话调度那一页。

## 分工

做幻灯片的人按下面的文字做技术选型和功能状态页。一个人用做好的幻灯片加上文中的演示路径录视频。

本文不写姓名。幻灯片第 1 页的姓名、学号和出勤，从 Sprint 1 提交材料原样抄上，不要猜学号。功能表里的负责人也按 Sprint 1 的名单填写。

## 第 1 页 — 标题

- DSS5105 Capstone，Group 4，Track 5（Custom）
- 项目：CheeseO，Blog Reading Co-Pilot
- 每位成员：全名、学号、出勤
- 公开仓库：https://github.com/youngvan12845/DSS5105
- 演示链接：要能打开你们实际演示的那个版本的系列课页面。录之前确认。若 Sprint 1 的网站落后于 `main`，不要继续用那个链接。

## 第 2 页 — 目标，以及 Sprint 1 之后改了什么

目标：读者看着一篇技术文章，就能看到难度、这篇在讲什么、以及可以先打开哪一篇，不用离开当前页。

Sprint 1 的共读助手跑在一小批演示文章上，先修关系写在 `prerequisites_graph.json` 里。

已经在 `main` 上的 Sprint 2 改动：

- Git 课 75 篇、Docker 课 27 篇，系列页在 `/blog/series/`。
- 宽窗口里，文章助手在右侧；窄窗口里，用 Ask AI 抽屉。
- 发布文章时不调用模型。命令 `analyze_learning_paths` 把结果写入 `a_agent/data/learning_analysis.json`。之后若改正文，旧结果标成过期。
- 某篇文章没有分析记录时，面板仍用手写图谱。

这些还没做，幻灯片不要说已经做了：

- 三人对照基础 RAG 的偏好实验
- 同一天、同一个模型上重跑聊天的四档对照
- 量过“得到可用解释的中位时间小于一分钟”

## 第 3 页 — 架构，并写出替代方案

只画这条路径。它和 `main` 上的代码一致。

1. 读者登录后打开一篇系列课。未登录时不显示这个面板。
2. 页面按这篇文章的当前版本去查学习分析文件。
3. 结果为 `ready` 时，显示 Beginner、Intermediate 或 Advanced，以及本文概念和先修概念。概念的措辞对得上某篇真实文章标题时才变成链接。对不上就只留文字，不给链接。
4. 文章过短、模型结果不可用、或结果已过期，显示 Unavailable。此时不退回 Beginner，也不显示“没有先修”。
5. 完全没有分析记录时，退回手写的 `prerequisites_graph.json`。

完整聊天页 `/agent/` 是另一条路径。它用编排器、检索和 `reading_paths.json`。30/33 这个分数属于这条路径，不属于右侧面板。

替代方案用一句话写上：也可以让一次对话直接编造先修链接。面板不这样做。链接要对照线上标题，没有分析结果时仍用手写图谱。

付费正文在进模型之前会去掉，除非当前用户可以读全文。

## 第 4 页 — 功能与状态

负责人不写在本文里。幻灯片上的负责人栏，按 Sprint 1 的名单填。

| 功能 | 状态 |
|---|---|
| 系列课页面、Git 与 Docker 导入、英文界面 | 已完成，在 `main` |
| 文章助手面板 | 已完成，在 `main` |
| 学习分析面板和 `learning_analysis.json` | 已完成，在 `main` |
| 33 题聊天评测 | 已完成，结果在 `main` |
| 中文回答，以及 Ollama 不在线时改走 Cloudflare | 只在尚未合并的分支上。这次演示不用。 |
| 由模型写的进阶提示和下一阶段 | 计划中。面板里这两项仍来自手写图谱。 |
| 三名读者的偏好实验 | 计划中。还没做。 |

## 第 5 页 — 验证

讲的时候说明这是两次不同的检查。

### 聊天助手

- 评测集：`a_agent/data/eval_tasks.json` 里 33 题（21 题 dev，12 题 holdout）。课程要求至少 30 题。
- `main` 上最近一次完整运行：通过 30 题，未通过 3 题。
- 未通过的是 `qa-004`（`git add` 是做什么的）、`rec-002`（容器网络，以及重启后状态怎么保留）、`rec-003`（Docker Compose 上生产环境下一步该读什么）。
- 更早一次运行的 baseline，和这次 30/33 不是同一次：闭卷 5/33，关键词检索 7/33，朴素向量 RAG 17/33。
- 幻灯片上要标明 baseline 是更早一次的结果。

### 学习面板

2026 年 10 月 27 日，对照 `main` 和线上文章检查。Git、Docker 各 10 篇，按章节散开抽。

| 检查 | Git 抽查 | Docker 抽查 |
|---|---|---|
| 只有分析成功才显示难度 | 10/10 为 ready，难度是 Beginner 或 Intermediate | 10/10 为 ready，难度是 Beginner 或 Intermediate |
| 只有概念对得上真实标题才出现链接 | 抽到的链接都能对上。没有编造的链接。 | 抽到的链接都能对上。没有编造的链接。 |
| 对不上标题的概念 | 1 个，只显示文字、没有链接：master branch | 12 个，只显示文字、没有链接。例子：microservices、DevOps |
| 后面的课被列成前面那课的先修 | 5 条。我们只计数。模型给出的顺序不是教学大纲。 | 0 条 |

整门系列的数字放在讲稿里，不要当成第二个分数：Git 73/75 为 ready，40 条先修链接指向更后面的课（同章 22 条，后面章节 18 条），21 个概念没有链接。Docker 27/27 为 ready，没有链接指向更后面的课，33 个概念没有链接。编造的链接：0。

结果文件的覆盖数量，不是质量分数：124 篇线上文章里 121 篇 ready，3 篇 Unavailable。

### 幻灯片上的难例

1. 顺序反了。打开 `/blog/series/git-chapter-4-edit-commit/`。这篇是第 4 章，面板把第 5 章的分支课列成先修。幻灯片说明：我们计数，不按这个顺序来教。
2. 对不上文章。打开 `/blog/series/docker-what-is-docker/`。“virtual machines”链到 Containers vs. Virtual Machines。“microservices”“cloud computing”“DevOps”只留文字，没有链接。
3. 分析不可用。打开 `/blog/series/git-fork-vs-clone/`。面板显示 Unavailable。这篇正文很长。这里的 Unavailable 表示分析失败，不是页面是空的。线上没有短于 80 字的文章，所以不要把这个难例说成空页面。

## 幻灯片不要写这些

- 124/124 都是 ready。有 3 篇线上文章是 Unavailable。另一条分支上有人直接改了结果文件，没有重新分析就把它们写成 ready。不要用那份文件。
- 助手界面只在 `feature/assistant-ui`。它已经在 `main`。
- 学习面板的分数是 30/33。30/33 是聊天助手的分数。
- 7450 个 token 降到 1180 是在 124 篇文章上新测的。同一组数字是 9 月导航器的结果。没有新的测量之前，这一页不要写它。
- 模型给出的顺序就是课程大纲。

## 视频

先讲大约 3 分钟幻灯片，再录大约 2 分钟屏幕。即使一句话没说完，到 5:00 也停。

| 时间 | 画面 | 讲什么 |
|---|---|---|
| 0:00–0:20 | 第 1 页 | 第 4 组，Track 5，CheeseO。指出 GitHub 链接和演示链接。 |
| 0:20–1:00 | 第 2 页 | Sprint 1 在短文章上用手写先修列表。Sprint 2 读 Git 和 Docker 系列，并在文章上显示核对过的指导。 |
| 1:00–1:40 | 第 3 页 | 按五步讲。替代方案：模型不编造链接。 |
| 1:40–2:10 | 第 4 页 | 读已完成的行。说明中文回答那条分支和读者实验不在这次演示里。 |
| 2:10–3:00 | 第 5 页 | 两个分数。聊天：33 题里 30 题，baseline 是更早一次。面板：10 加 10 的抽查，带上三个难例。 |
| 3:00–4:30 | 下面的演示 | 先走一遍读者路径，再做一个难例。 |
| 4:30–5:00 | 停止 | 停在难例上。不要再打开新功能。 |

### 演示

窗口宽度至少 1024 像素。

1. 先登录。未登录的访客看不到面板。用一个普通成员账号。密码不要写进幻灯片，也不要写进这个文件。
2. 打开 `/blog/series/`，让人看到 Git 和 Docker 两条系列。这就是读者路径：先选课，再选一篇。
3. 打开 `/blog/series/docker-what-is-docker/`。右侧面板要露出难度、“AI learning guidance”、一条真实的先修链接，以及没有链接的那些概念。
4. 若还有时间，打开 `/blog/series/git-chapter-4-edit-commit/`，指出先修里的第 5 章标题。说明这是顺序反了的例子，不是教学大纲。

在本机从 `Final_project/blog` 启动：

```bash
./scripts/run_local.sh
```

然后打开 http://127.0.0.1:8000/blog/series/ 。这台机器的 `.env` 里要有小组的数据库设置。不要提交 `.env`。

## 文件做好之后

1. 把视频上传到 YouTube。幻灯片还能改的话，把链接放进第 1 页；已经导出的话，把链接写在 Canvas 提交说明里。
2. 按上面的文件名，把两个文件交到 Canvas。
3. 第 1 页上出现的人参加现场问答。

---

# English

Use this file as the source for the slides and the video. If another note disagrees with the numbers or the status below, use this file.

The same content appears twice: Chinese first, English second. The slide deck and the spoken video are in English. Copy from this half.

## What to deliver

| Item | Requirement |
|---|---|
| When | Friday 30 October 2026, 3:00 PM. Late submissions are accepted until 7:00 PM. |
| Slides | `Presentation_Group04_Sprint2.pptx` or `.pdf` |
| Video | `Presentation_Group04_Sprint2.mp4`, also uploaded to YouTube |
| Length | Under 5:00. The recording must stop at 5:00. Plan about 3 minutes of slides and 2 minutes of demo. |
| Live session | Q&A attendance is required. Groups present in reverse order from Group 22, 7:00 PM, LT29. |
| Code | https://github.com/youngvan12845/DSS5105 on `main` |

Track 5 does not add the Track 1 / Track 2 phone-dispatcher slide.

## Who does what

The person making the slides builds the technical-choice comparison and the feature-status slide from the text below. One person records the video from the finished slides plus the demo path.

This file names nobody. Copy every member’s full name, NUS ID, and attendance onto slide 1 from the Sprint 1 submission. Do not guess an ID. Fill the owner column on the feature slide from that same Sprint 1 list.

## Slide 1 — title

- DSS5105 Capstone, Group 4, Track 5 (Custom)
- Project: CheeseO, Blog Reading Co-Pilot
- Every member: full name, NUS ID, attendance
- Public GitHub: https://github.com/youngvan12845/DSS5105
- Demo link: a URL that opens the series page on the build you will show. Confirm it before recording. Do not leave the Sprint 1 link if that site is behind `main`.

## Slide 2 — objective, and what changed after Sprint 1

Objective: help a reader of one technical article see the difficulty, the concepts in that article, and which earlier article to open, without leaving the page.

Sprint 1 had a working co-pilot on a small set of demo posts, with prerequisites written by hand in `prerequisites_graph.json`.

Sprint 2 changes that are on `main`:

- The Git course (75 lessons) and the Docker course (27 lessons) are real series pages at `/blog/series/`.
- The article assistant is a right-hand panel on a wide window, and an Ask AI drawer on a narrow window.
- Publishing an article does not call the model. The command `analyze_learning_paths` writes `a_agent/data/learning_analysis.json`. A later edit marks an old result stale.
- If an article has no analysis record, the panel still uses the hand-written graph.

Not done, so the slide must not say these happened:

- A three-person preference study against basic RAG
- A same-day rerun of all four chat variants on one model
- A measured median time under one minute

## Slide 3 — architecture, with the alternative

Draw only this path. It matches the code on `main`.

1. The reader opens a series lesson while logged in. The panel is hidden for a visitor who is not logged in.
2. The page asks the learning-analysis file for that article’s current version.
3. A `ready` result shows Beginner, Intermediate, or Advanced, the article concepts, and the prerequisite concepts. A concept becomes a link only when its wording matches a real article title. Otherwise the words stay on the panel and there is no link.
4. A short article, a failed model result, or a stale result shows Unavailable. It does not fall back to Beginner or to “no prerequisites”.
5. No record at all falls back to the hand-written `prerequisites_graph.json`.

The chat box on the full `/agent/` page is a second path. It uses the orchestrator, retrieval, and `reading_paths.json`. The 30/33 score belongs to that path, not to the right-hand panel.

Alternative to state in one line: a single chat prompt that invents prerequisite links. The panel refuses that. Links are checked against live titles, and the hand-written graph remains the fallback when no analysis exists.

Paid article text is removed before it reaches the model unless that user can read the full article.

## Slide 4 — features and status

Owners are not written in this file. On the slide, fill the owner column from the Sprint 1 list.

| Feature | Status |
|---|---|
| Series pages, Git and Docker import, English interface | Done, on `main` |
| Article assistant panel | Done, on `main` |
| Learning-analysis panel and `learning_analysis.json` | Done, on `main` |
| 33-task chat evaluation | Done, results on `main` |
| Chinese answers, and Cloudflare fallback when Ollama is offline | On an unmerged branch only. Leave it out of this demo. |
| Model-written advanced insights and next milestones | Planned. The panel still uses the hand-written graph for those. |
| Three-reader preference study | Planned. Not done. |

## Slide 5 — validation

Say that these are two different checks.

### Chat agent

- Evaluation set: 33 tasks in `a_agent/data/eval_tasks.json` (21 dev, 12 holdout). The course minimum is 30 tasks.
- Latest full-agent result on `main`: **30 passed, 3 failed**.
- The 3 failures are `qa-004` (purpose of `git add`), `rec-002` (container networking and state after restart), and `rec-003` (what to read next for Docker Compose in production).
- Baselines from an earlier run, not the same run as 30/33: closed-book 5/33, keyword search 7/33, naive vector RAG 17/33.
- Label the baselines as an earlier run on the slide.

### Learning panel

Checked on 27 October 2026 against `main` and the live articles. Ten Git lessons and ten Docker lessons, spread across chapters.

| Check | Git sample | Docker sample |
|---|---|---|
| Difficulty appears only after a successful analysis | 10/10 ready, Beginner or Intermediate | 10/10 ready, Beginner or Intermediate |
| A link exists only when the concept matches a real title | Every sampled link matched. No invented link. | Every sampled link matched. No invented link. |
| A concept with no matching title | 1 concept, shown with no link: master branch | 12 concepts, shown with no link. Examples: microservices, DevOps |
| A later lesson listed as a prerequisite of an earlier one | 5 links. We count them. The model order is not the syllabus. | 0 links |

Whole series, for the speaker notes rather than a second score: Git 73/75 ready, 40 prerequisite links point at a later lesson (22 in the same chapter, 18 in a later chapter), 21 concepts have no link. Docker 27/27 ready, no link points at a later lesson, 33 concepts have no link. Invented links: 0.

Coverage of the file, not a quality score: 121 of 124 live articles are ready, 3 are Unavailable.

### Hard cases to put on the slide

1. Reversed order. Open `/blog/series/git-chapter-4-edit-commit/`. The panel lists Chapter 5 branch lessons as prerequisites of this Chapter 4 lesson. The slide says we count this and do not teach that order.
2. No matching article. Open `/blog/series/docker-what-is-docker/`. “virtual machines” links to Containers vs. Virtual Machines. “microservices”, “cloud computing”, and “DevOps” stay as text with no link.
3. Unusable analysis. Open `/blog/series/git-fork-vs-clone/`. The panel says Unavailable. This article is long. Unavailable here means the analysis failed, not that the page is empty. There is no live article shorter than 80 characters, so do not describe this case as an empty page.

## Do not put these claims on a slide

- 124/124 ready. Three live articles are Unavailable. Another branch has a hand edit that marks them ready without a new analysis. Do not use that file.
- The assistant UI exists only on `feature/assistant-ui`. It is on `main`.
- The learning panel scored 30/33. That score is the chat agent.
- The token drop from 7450 to 1180 is a new measurement on the 124-article corpus. The same pair of numbers is the September navigator figure. Leave it off this slide unless there is a new measurement.
- The model order is the course syllabus.

## Video

Record the slides for about 3 minutes, then the screen for about 2 minutes. Stop at 5:00 even if a sentence is unfinished.

| Time | What is on screen | What to say |
|---|---|---|
| 0:00–0:20 | Slide 1 | Group 4, Track 5, CheeseO. Point at the GitHub link and the demo link. |
| 0:20–1:00 | Slide 2 | Sprint 1 used a hand-written prerequisite list on short posts. Sprint 2 reads the Git and Docker series and shows checked guidance on the article. |
| 1:00–1:40 | Slide 3 | Follow the five steps. One alternative: the model does not invent links. |
| 1:40–2:10 | Slide 4 | Read the Done rows. Say the Chinese-reply branch and the reader study are not in this demo. |
| 2:10–3:00 | Slide 5 | Two scores. Chat: 30 of 33, baselines from an earlier run. Panel: the 10 plus 10 check, including the three hard cases. |
| 3:00–4:30 | Demo, below | User journey, then one hard case. |
| 4:30–5:00 | Stop | End on the hard case. Do not start a new feature. |

### Demo, on a window at least 1024 pixels wide

1. Log in. The panel does not render for a logged-out visitor. Use a normal member account. Keep the password out of the slides and out of this file.
2. Open `/blog/series/` and show the Git and Docker tracks. This is the journey: the reader picks a course, then a lesson.
3. Open `/blog/series/docker-what-is-docker/`. Show the right-hand panel: difficulty, “AI learning guidance”, one real prerequisite link, and the concepts that have no link.
4. If time remains, open `/blog/series/git-chapter-4-edit-commit/` and point at the Chapter 5 titles listed under prerequisites. Say that this is the reversed-order case and it is not the syllabus.

Local run, from `Final_project/blog`:

```bash
./scripts/run_local.sh
```

Then open http://127.0.0.1:8000/blog/series/ . The machine needs the team database settings in `.env`. Do not commit `.env`.

## After the files exist

1. Upload the video to YouTube and put that URL on slide 1 if the slide is still editable, or on the Canvas submission if the deck is already exported.
2. Submit both files on Canvas under the names above.
3. The people who appear on slide 1 attend the live Q&A.
