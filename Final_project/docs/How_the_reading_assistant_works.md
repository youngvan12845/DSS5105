# How the reading assistant works

Group 4, Track 5. This is a plain-English note for the Sprint 2 talk. It explains the website behind the blog, what happens after a reader asks a question, and which online models we use.

## What the product is

CheeseO is a blog of programming lessons. Most lessons are a Git series or a Docker series.

A reader who is logged in can ask a question on an article, or open a full chat. The assistant answers from the articles on this site. It can also suggest what to read next. If the reader wants to save an article, or post a comment, the assistant only prepares that step. Nothing is saved until the reader presses Confirm.

A visitor who is not logged in can read the article. They do not see the assistant.

## What the agent is

The agent is not a chatbot that can talk about anything. It is a reading assistant for this blog. It answers from the lessons on the site, and it can help with a few reading tasks. If the topic is not on the site, the first reply says it cannot find an article. It does not fill that gap from its own general knowledge. In the full chat, it then asks whether to look outside the blog. An outside note is labeled as not a lesson on this site, and it is not listed under SOURCES.

Every reply follows the same three steps:

1. Rules read the question and decide which tools to call. This step is not the model.
2. The tools fetch facts: search the lessons, look at what this person has opened, load a reading path, or prepare a change.
3. The online model writes the reply from those results only. If the results are empty, it says the blog has nothing on that topic.

That is the difference from a search box. A search box returns links. This agent picks the tools first, then the model turns the results into an answer, and the answer keeps links to the lessons it used. Each reply also stores which tools ran, so we can see later why it answered that way.

Changes to the site are stricter. Adding to the reading list, removing an item, and posting a comment are only placed on a card. They are saved when the reader presses Confirm.

The learning panel is not part of this question-answering agent. The difficulty and the concepts on the panel were computed earlier and saved in a file. Opening the page does not call the model again.

## What it can do

- Explain or summarize one lesson. If the question is sent from that lesson's page, the agent looks only inside that lesson.
- Find a topic across the whole blog, such as Git or Docker, and say which lessons cover it.
- Suggest what to read next from the lessons this person opened recently. The suggestion comes from matching tags, not from the model picking a title on its own.
- Say what this person read recently, so they can continue.
- Give a reading path that was written ahead of time. The paths we have are Git for beginners, Git branching, Docker, Python basics, Python web, and a machine-learning introduction.
- Show the reader's own reading list.
- Prepare three actions: add a lesson to the list, remove one, or write a comment. All three wait for Confirm.
- In the full chat, when no lesson matches, ask before looking outside the blog. If the reader agrees, show one short public note and label it as not a lesson on this site.

## What it will not do

- It does not pretend a missing lesson exists. The Helm question is the example. The first reply says the blog has no such article. It does not say "the article explains it like this."
- It does not search outside the blog until the reader agrees. The button sends the sentence "Yes, look outside the blog". Typing that same sentence does the same thing.
- It does not put an outside note under SOURCES, and it does not call that note a CheeseO lesson.
- It does not copy the body of a paid lesson. A reader who has not unlocked it only sees a short note that the lesson is paid.
- It does not give company revenue, passwords, or secret keys. Those questions get one fixed refusal and are never sent to the model.
- It does not change the reading list or post a comment before the reader confirms. If the article number does not exist, it does not prepare the action either.
- When it cannot find a lesson, it does not offer a different lesson on this site as a substitute.
- On an article page, a question about another topic does not get a summary of the lesson that is open. The reply says this panel only covers that lesson and points to the full chat.

## The website behind it

The site is built with Django. Django is the Python framework that runs the pages, the login, and the assistant. The articles themselves are managed in Wagtail, which is the editing tool: we write a lesson there and press publish.

The code is split into a few parts:

- The blog holds the lessons, the comments, and whether a lesson is free or paid.
- The assistant holds the chat, the search, the learning panel, and the Confirm button.
- Accounts hold the login, the reader profile, and which articles that person has opened. People log in with email and password.
- Membership and points decide who can open a paid lesson.
- The home pages are the rest of the public site.

When a reader sends a question, only the assistant box updates. The whole page does not reload.

Articles, users, chat, and search results are stored in PostgreSQL. The shared team database is on Supabase. Pictures on the shared site are also stored on Supabase. We do not use a separate database just for search.

## What the reader sees

On a wide screen, the assistant sits in a column on the right of the article. On a phone, the reader opens it from Ask AI. The full chat is a separate page, at `/agent/`.

That column does two things. The learning panel shows how hard the lesson is, the ideas in it, and links to lessons that come before or after. The chat box is where the reader types a question.

## What happens after a question

Every question goes through the same steps. The model writes the reply only at the end. It does not search the blog by itself.

1. If the question comes from an article page, the assistant stays on that article. "Summarize this article" summarizes that lesson. A question that names a different topic, such as a Helm lesson while another article is open, does not get a summary of the open page. The reply says this panel only covers the open lesson and points to `/agent/`. If the article is missing, it says so and stops.

2. Simple rules read the question and decide what kind of request it is. This is not the model. The rules notice things like "what does this mean", "what should I read next", "what have I already read", "add this to my list", or "post a comment".

3. The assistant then searches.
   - Keyword search looks for the same words in titles and text.
   - Passage search looks through short pieces cut from the articles.
   - Meaning search turns the question into a list of numbers, and compares it with the same kind of list stored for each passage. A closer list means a closer meaning. This comparison happens in our own code. The numbers are stored next to the passages in PostgreSQL.
   - Other lookups read what this person has opened, their reading list, and a prepared path through a topic.
   - On an article page, search stays inside that article. In the full chat, search can look across the whole blog.

4. Paid text is removed before the model sees it. If this reader has not unlocked the lesson, the paid paragraphs are replaced with a short note that the lesson is paid. The model is told not to copy that hidden text.

5. Some questions never reach the model. The reply is a fixed sentence.
   - Questions about company revenue, passwords, or secret keys are refused.
   - "Paste the whole paid article" is refused. The reply says the lesson is paid and only a short preview is allowed.
   - "Add article 999999" does nothing if that number is not a real lesson. The reply says it does not exist.

6. Saving and posting wait for Confirm. "Add this to my reading list", "remove this", and "post a comment" only prepare a card. The change is saved when the reader presses Confirm. Cancel throws it away.

7. If the full chat finds no lesson, the reply is a fixed sentence, not a model answer: "I cannot find any article about that topic in the blog corpus. Should I look outside the blog?" Nothing is fetched yet. The original question is kept for this conversation. A button, **Look outside the blog**, sends the sentence "Yes, look outside the blog".

8. That confirmation does not search the blog again. The assistant asks DuckDuckGo's public instant-answer interface for one short abstract. DuckDuckGo is a search engine. This step calls one interface, and it does not open the website or crawl other pages. If that abstract is missing, it asks the English Wikipedia search interface for one page title, then the Wikipedia summary interface for the opening extract. For the Helm question, DuckDuckGo returned nothing, and the note came from the Wikipedia page "Helm (package manager)". The model may rewrite that extract into two or three sentences. It is told to use only that extract. The reply is labeled **Outside the blog** (not a lesson on this site). The note is not a source. If both interfaces fail, time out, or return only a very short extract, the reply says no usable public note was found. The model does not invent one.

9. When the blog does have matching lessons, the online model receives the question and those search results, and it writes the reply. It is told to use only those results. The reply keeps links back to the lessons it used.

10. If the online model cannot be reached, the assistant still shows the search results in plain text. It does not invent an answer. The outside note is the same: if the model cannot rewrite the extract, the raw public extract is shown under the same label.

## The models

This version uses online models on Cloudflare Workers AI. The website sends the question to Cloudflare, and Cloudflare sends the reply back. The demo does not need a model running on the laptop.

Two online models do the work:

- Chat, and the job that reads a lesson for the learning panel, both use Qwen 2.5 Coder 32B. The full name is `@cf/qwen/qwen2.5-coder-32b-instruct`. Chat is the reply the reader sees. The learning-panel job runs separately, before the reader opens the page. It is not called on every visit.
- Search by meaning uses bge-m3. The full name is `@cf/baai/bge-m3`. This model does not write sentences. It turns a paragraph into a list of numbers so two paragraphs can be compared.

An earlier version ran smaller models on the same laptop, through a program called Ollama: Qwen2.5-VL 7B for chat, Qwen2.5 7B for the learning panel, and nomic-embed-text for the number lists. This version does not use those.

## The learning panel is prepared ahead of time

Opening a lesson does not ask the model to decide the difficulty on the spot. Those notes are already saved in a file, `learning_analysis.json`. A separate command asks the online model to read each lesson and write that file.

The panel shows the notes only when the file says the lesson is ready and the concept lists are properly filled in. The reader then sees the difficulty and links to related lessons. If the check failed, or the lesson was edited after the check, the panel says Unavailable. Publishing a lesson marks the old notes as out of date. It does not call the model again by itself. Someone has to run the command again.

If a lesson has no notes yet, the panel can use a hand-written file, `prerequisites_graph.json`, when that lesson is listed there. Otherwise it says Unavailable. A third file, `reading_paths.json`, is used when a reader asks for a path through a topic.

## What is stored

In the database:

- The lesson pages.
- The short passages used for search, the number list for each passage, and a mark for paid text.
- Users, membership, points, and which lessons each person opened.
- Chat conversations. Each assistant reply can store the lesson links, which searches ran, and a change that is still waiting for Confirm.
- Reading-list items.
- A record of each prepared change: whether the reader confirmed it, and whether it was actually saved.

Next to the database are the three files named above. They are prepared notes, not a second database.

## One comparison, if someone asks whether it works

On 13 September the full assistant and three simpler systems answered the same 33 questions. That round used the earlier local chat model. The gap comes from the search and the tools, which are the same in this online version.

- The plain model, with no articles: 5/33.
- Keyword search only: 7/33.
- Meaning search only: 17/33.
- The full assistant, with all three searches, the other tools, and the Confirm step: 25/33.

25/33 is about 76%. The goal we set was 85%, so this round is below that goal. On the same round, meaning-search-only copied paid lesson text on 2 trick questions. The full assistant did not.

A later run asked the online Qwen 32B model the same kind of questions and it passed 26/33. That run did not include the three simpler systems, so the comparison to quote is still 25 against 5, 7, and 17.

The outside-lookup step above was added after that comparison. The Helm question in that round was scored on the refusal alone. The first reply still refuses. The public note appears only after the reader agrees, and it is not counted as a lesson on this site.
