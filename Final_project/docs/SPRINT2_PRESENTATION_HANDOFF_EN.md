# Sprint 2 presentation handoff — Group 4, Track 5

Use this file as the source for the slides and the video. If another note disagrees with the numbers or the status below, use this file.

The slide deck and the spoken video are in English. The Chinese copy is `SPRINT2_PRESENTATION_HANDOFF_ZH.md` in the same folder.

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
