"""
Script to build comprehensive Prerequisite DAG, Concept Bridges, and Senior Engineering Pitfalls
for all 75 Git & GitHub Master Course articles, ensuring 100% adherence to monotonicity and verification.
"""

import json

with open("git_topics_list.json", "r", encoding="utf-8") as f:
    chapters_data = json.load(f)

# Difficulty mapping
DIFF_MAP = {
    1: "beginner",
    2: "beginner",
    3: "beginner",
    4: "beginner",     # default
    5: "intermediate", # default
    6: "intermediate", # default
    7: "advanced",     # default
}

# Override specific advanced / intermediate topics
TOPIC_DIFF_OVERRIDE = {
    # Chapter 4
    "git-restore-files-to-working-tree-git-restore": "intermediate",
    "git-undo-changes-git-reset": "intermediate",
    "git-delete-files-git-rm": "intermediate",
    # Chapter 5
    "git-fast-forward-merge": "intermediate",
    "git-non-fast-forward-merge-no-option": "intermediate",
    "git-non-fast-forward-merge-no-ff-option": "intermediate",
    "git-squash-merge": "advanced",
    "git-rebase-branch-git-rebase": "advanced",
    "git-managing-conflict": "advanced",
    "git-stash-changes-git-stash": "intermediate",
    # Chapter 6
    "git-request-for-review-and-merge-pull-request": "advanced",
    "git-merge-operation-using-github": "advanced",
}

RANK = {"beginner": 1, "intermediate": 2, "advanced": 3}

# Curated pitfall and tradeoff insights
PITFALLS = {
    "git-what-is-git": (
        "Treating Git as cloud storage rather than a content-addressable DAG snapshot engine leads to confusing commit histories and detached HEAD states.",
        "Distributed VCS (Git) vs Centralized VCS (Perforce / SVN): In enterprise monorepos exceeding 100 GB, how do you handle large binary asset bloat with Git LFS?"
    ),
    "git-how-to-save-versions-in-git": (
        "Relying on working directory backups instead of commits means unstaged changes cannot be recovered once overwritten by checkout or reset.",
        "Fine-grained atomic commits vs large squashed feature commits: Which strategy provides better git bisect regression isolation?"
    ),
    "git-github-basic-life-cycle": (
        "Committing sensitive API secrets or private keys directly to a local repo; even if deleted in a later commit, keys remain visible in historical tree blobs.",
        "Local-first autonomy vs centralized trunk governance: How do asynchronous distributed teams balance immediate local iteration with global merge gating?"
    ),
    "git-user-settings-git-config": (
        "Committing to corporate repositories using personal email addresses in user.email, leaking employee identities or failing enterprise commit-signature hooks.",
        "Global gitconfig vs directory-scoped includeIf configuration: How do multi-client consultants isolate corporate SSH signing keys and emails cleanly?"
    ),
    "git-add-files-to-staging-area-git-add": (
        "Carelessly executing 'git add .' without a configured .gitignore stages virtualenvs, node_modules, and secret credentials.",
        "Interactive staging ('git add -p') vs bulk staging: How much granular hunk-level staging overhead is justified in fast-paced production cycles?"
    ),
    "git-commit-files-git-commit": (
        "Vague commit messages like 'fixed bug' or 'update' break auditability, making git bisect and automated release changelog generation impossible.",
        "Conventional Commits (feat/fix/chore) enforcement via commitlint vs unrestricted developer autonomy: Does rigid commit formatting hinder delivery speed?"
    ),
    "git-undo-changes-git-reset": (
        "Running 'git reset --hard' destroys uncommitted working tree modifications irrecoverably, as Git never tracked those file blobs in the object database.",
        "git reset vs git revert: In published team branches, why is git revert the only mathematically safe undo strategy for upstream collaboration?"
    ),
    "git-create-branch-and-check-branch-status-git-branch": (
        "Long-lived feature branches drifting weeks behind the main branch accumulate silent integration incompatibilities and painful merge conflict resolution.",
        "Trunk-Based Development (short-lived feature branches < 24h) vs GitFlow (develop/release/hotfix): When does branch isolation become team inertia?"
    ),
    "git-fast-forward-merge": (
        "Fast-forward merges skip creating a merge commit, losing context of when a feature branch began and ended, making full feature rollbacks difficult.",
        "Fast-forward merge vs '--no-ff' merge commit: How do teams preserve visual branch history in commit DAG graphs without cluttering linear git log output?"
    ),
    "git-squash-merge": (
        "Squash-merging collapses all intermediate commit messages, destroying fine-grained bisectability and attributing all changes to a single author timestamp.",
        "Squash merge for clean main history vs rebase merge for full WIP provenance: How to decide repo merge policy across microservices?"
    ),
    "git-rebase-branch-git-rebase": (
        "Rebasing a public shared remote branch changes SHA-1 commit hashes, breaking all teammates' local tracking branches and creating duplicate commit chains.",
        "Interactive rebase ('git rebase -i') for curating feature branches vs leaving messy WIP commits: How much time should engineers spend polishing commit logs?"
    ),
    "git-managing-conflict": (
        "Blindly accepting 'incoming change' or 'current change' in merge conflicts without validating runtime dependencies can introduce silent logical bugs that pass syntax checks.",
        "Three-way merge (diff3 / zdiff3) vs standard two-way conflict markers: How does showing common ancestor code accelerate conflict diagnosis?"
    ),
    "git-upload-to-remote-repository-git-push": (
        "Running 'git push --force' overwrites remote upstream commits made by teammates; always use 'git push --force-with-lease' to prevent accidental clobbering.",
        "Direct branch pushing vs pull request peer gating: At what team scale does automated CI branch protection become mandatory?"
    ),
    "git-download-remote-repository-and-merge-to-local-repository-git-pull": (
        "Default 'git pull' creates unexpected recursive merge commits when local and remote branches diverge; configure 'git config pull.rebase true' or 'pull.ff only'.",
        "git pull vs git fetch + git merge: Why do production DevOps pipelines favor explicit fetching and inspected merging over automated pull?"
    ),
    "git-request-for-review-and-merge-pull-request": (
        "Submitting gigantic PRs with 1,000+ line diffs leads to rubber-stamping ('looks good to me') instead of rigorous architectural and edge-case review.",
        "Stacked PRs (small dependent pull requests) vs monolithic PRs: How to streamline review throughput while managing dependent branch rebases?"
    ),
}

# Build map of all topics
all_topics = []
topic_by_slug = {}
for ch in chapters_data:
    ch_idx = ch["chapter_idx"]
    for t in ch["topics"]:
        slug = t["slug"]
        diff = TOPIC_DIFF_OVERRIDE.get(slug, DIFF_MAP[ch_idx])
        t_entry = {
            "slug": slug,
            "title": t["title"],
            "chapter_idx": ch_idx,
            "chapter_name": ch["chapter_name"],
            "difficulty": diff,
            "rank": RANK[diff],
        }
        all_topics.append(t_entry)
        topic_by_slug[slug] = t_entry

print(f"Total topics compiled: {len(all_topics)}")

git_graph = {}

for idx, item in enumerate(all_topics):
    slug = item["slug"]
    title = item["title"]
    diff = item["difficulty"]
    rank = item["rank"]
    ch_idx = item["chapter_idx"]

    prereqs = []

    # 1. Intra-chapter or inter-chapter prerequisite link
    if idx > 0:
        prev_item = all_topics[idx - 1]
        # Only attach if monotonicity holds (prev rank <= current rank)
        if prev_item["rank"] <= rank:
            prereqs.append({
                "slug": prev_item["slug"],
                "title": prev_item["title"],
                "key_concept": f"Foundational concepts from {prev_item['title']}",
                "bridge_summary": f"Mastering {prev_item['title']} provides the prerequisite mental model needed for {title}.",
            })
        else:
            # Look backwards for the nearest topic that satisfies rank <= current rank
            for b_item in reversed(all_topics[:idx]):
                if b_item["rank"] <= rank:
                    prereqs.append({
                        "slug": b_item["slug"],
                        "title": b_item["title"],
                        "key_concept": f"Foundational concepts from {b_item['title']}",
                        "bridge_summary": f"Understanding {b_item['title']} is essential before tackling {title}.",
                    })
                    break

    # 2. Key structural cross-chapter prerequisite links
    if ch_idx >= 5 and "rebase" in slug:
        c4_commit = topic_by_slug.get("git-commit-files-git-commit")
        if c4_commit and c4_commit["rank"] <= rank and not any(p["slug"] == c4_commit["slug"] for p in prereqs):
            prereqs.append({
                "slug": c4_commit["slug"],
                "title": c4_commit["title"],
                "key_concept": "Commit Object Structure and SHA Identifiers",
                "bridge_summary": "Rebase manipulates commit DAG history; understanding how commit objects are formed is critical.",
            })

    if ch_idx >= 6 and "pull" in slug:
        c5_branch = topic_by_slug.get("git-merge-branches-git-merge")
        if c5_branch and c5_branch["rank"] <= rank and not any(p["slug"] == c5_branch["slug"] for p in prereqs):
            prereqs.append({
                "slug": c5_branch["slug"],
                "title": c5_branch["title"],
                "key_concept": "Branch Merging Mechanics",
                "bridge_summary": "Git pull is a combination of fetch and merge; understanding local branch merge mechanics is required.",
            })

    # Pitfall and tradeoff
    pitfall_text, tradeoff_text = PITFALLS.get(slug, (
        f"In production workflows, misapplying {title} without proper working tree verification can lead to uncommitted change losses or branch drift.",
        f"Speed vs safety tradeoff: Balancing fast local developer iteration with rigorous team code verification in {title}."
    ))

    # Next milestone
    next_milestones = []
    if idx + 1 < len(all_topics):
        next_item = all_topics[idx + 1]
        next_milestones.append({
            "slug": next_item["slug"],
            "title": next_item["title"],
            "reason": f"Continue to the next curriculum milestone: {next_item['title']}.",
        })

    git_graph[slug] = {
        "title": title,
        "series": "git-github-mastery",
        "difficulty": diff,
        "prerequisites": prereqs,
        "intermediate_insights": {
            "production_pitfall": pitfall_text,
            "tradeoff_challenge": tradeoff_text,
        },
        "next_milestones": next_milestones,
    }

# Read existing graph and merge
with open("a_agent/data/prerequisites_graph.json", "r", encoding="utf-8") as f:
    existing_graph = json.load(f)

print(f"Existing graph articles: {len(existing_graph)}")
existing_graph.update(git_graph)
print(f"Merged graph articles: {len(existing_graph)}")

with open("a_agent/data/prerequisites_graph.json", "w", encoding="utf-8") as f:
    json.dump(existing_graph, f, ensure_ascii=False, indent=2)

print("Saved updated prerequisites_graph.json successfully!")
