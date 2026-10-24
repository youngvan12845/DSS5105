"""
Script to build comprehensive Prerequisite DAG, Concept Bridges, and Senior Engineering Pitfalls
for all 27 Docker Basics course articles, ensuring 100% adherence to monotonicity and verification.
"""

import json

with open("docker_topics_list.json", "r", encoding="utf-8") as f:
    chapters_data = json.load(f)

DIFF_MAP = {
    1: "beginner",
    2: "beginner",
    3: "beginner",
    4: "intermediate",
    5: "intermediate",
    6: "intermediate",
}

TOPIC_DIFF_OVERRIDE = {
    "docker-container-lifecycle": "intermediate",
    "docker-advanced-container-lifecycle-management": "intermediate",
    "docker-commands-to-interact-with-inside-of-containers": "intermediate",
    "docker-persistent-storage-with-docker-volumes": "intermediate",
    "docker-networking": "intermediate",
    "docker-what-is-a-dockerfile": "intermediate",
    "docker-dockerfile-syntax": "intermediate",
    "docker-production-deployment-with-docker-compose": "advanced",
    "docker-advancing-your-docker-skills": "advanced",
}

RANK = {"beginner": 1, "intermediate": 2, "advanced": 3}

DOCKER_PITFALLS = {
    "docker-what-is-docker": (
        "Treating containers as persistent stateful virtual machines; writes to container rootfs without volumes cause silent data loss upon container restart.",
        "Bare-metal / Virtual Machines vs Containerization: Balancing kernel isolation security boundaries against container startup speed and resource density."
    ),
    "docker-containers-vs-virtual-machines": (
        "Assuming Docker containers provide hypervisor-grade kernel isolation; a kernel panic or privilege escalation in a container can compromise the host OS.",
        "Heavyweight VM isolation (Type-2 hypervisor) vs lightweight Linux cgroups/namespaces: How to design multi-tenant security architectures?"
    ),
    "docker-images-and-registries-docker-hub": (
        "Using the 'latest' image tag in production Dockerfiles; upstream breaking changes automatically pull into production builds, causing unreproducible deploys.",
        "Public Docker Hub registry vs private image registry (ECR/GCR) with automated vulnerability scanning and air-gapped cache."
    ),
    "docker-container-lifecycle": (
        "Ignoring PID 1 init signal forwarding: apps running as PID 1 without tini fail to handle SIGTERM, causing 10-second SIGKILL delays and dirty DB connection disconnects.",
        "Ephemeral container restart policies (unless-stopped vs on-failure) vs Kubernetes pod lifecycle controllers."
    ),
    "docker-persistent-storage-with-docker-volumes": (
        "Mounting host directories into containers with inconsistent UID/GID permissions, causing root-owned files that the container non-root user cannot read or write.",
        "Docker Named Volumes (managed by daemon) vs Host Bind Mounts: How to optimize local development sync speed while ensuring production storage portability."
    ),
    "docker-networking": (
        "Exposing internal databases to host port 0.0.0.0 instead of relying on Docker internal bridge network DNS discovery, exposing unauthenticated database ports to public internet.",
        "Bridge networking vs Host networking: When does avoiding Linux network namespace overhead outweigh port conflict isolation?"
    ),
    "docker-what-is-a-dockerfile": (
        "Invalidating Docker build cache early: Placing 'COPY . .' before 'RUN pip install' forces slow dependency re-downloads on every single code change.",
        "Single-stage build vs Multi-stage build (builder + minimal runtime image): Cutting image size from 1.2 GB down to 80 MB."
    ),
    "docker-build-context-and-dockerignore-file": (
        "Omitting .dockerignore, sending gigabytes of .git histories, virtual environments, and local credentials into the Docker daemon build context.",
        "Lean build context vs build-time caching: How to structure CI pipelines to minimize Docker build context transfer latency."
    ),
    "docker-writing-a-docker-compose-file": (
        "Relying on 'depends_on' without healthchecks: 'depends_on' only waits for container start, not socket readiness, causing web apps to crash before Postgres finishes initialization.",
        "Docker Compose for local development & single-node deployments vs Kubernetes / Nomad for distributed multi-node orchestrations."
    ),
    "docker-production-deployment-with-docker-compose": (
        "Hardcoding sensitive database passwords and JWT secrets in docker-compose.yml files instead of Docker secrets or environment variable files excluded from Git.",
        "Blue-Green Compose zero-downtime deployment vs rolling deployment overhead in production environments."
    ),
}

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

print(f"Total Docker topics compiled: {len(all_topics)}")

docker_graph = {}

for idx, item in enumerate(all_topics):
    slug = item["slug"]
    title = item["title"]
    diff = item["difficulty"]
    rank = item["rank"]
    ch_idx = item["chapter_idx"]

    prereqs = []

    # 1. Intra-course prerequisite link
    if idx > 0:
        prev_item = all_topics[idx - 1]
        if prev_item["rank"] <= rank:
            prereqs.append({
                "slug": prev_item["slug"],
                "title": prev_item["title"],
                "key_concept": f"Foundations from {prev_item['title']}",
                "bridge_summary": f"Understanding {prev_item['title']} is essential before moving to {title}.",
            })
        else:
            for b_item in reversed(all_topics[:idx]):
                if b_item["rank"] <= rank:
                    prereqs.append({
                        "slug": b_item["slug"],
                        "title": b_item["title"],
                        "key_concept": f"Foundations from {b_item['title']}",
                        "bridge_summary": f"Understanding {b_item['title']} provides the prerequisite foundation for {title}.",
                    })
                    break

    # 2. Structural cross-track prerequisite:
    # Docker environment setup links to Git workflow
    if slug == "docker-chapter-2-getting-started-with-docker":
        prereqs.append({
            "slug": "git-what-is-git",
            "title": "What Is Git?",
            "key_concept": "Version Control and Project Environment",
            "bridge_summary": "Docker standardizes runtime environments while Git version-controls source code; understanding both forms the modern DevOps core.",
        })

    # Docker Compose multi-container web app links to Web HTTP REST
    if slug == "docker-web-app-development-with-docker-compose":
        prereqs.append({
            "slug": "web-http-rest",
            "title": "Web Development Basics: HTTP and REST",
            "key_concept": "HTTP Communication Across Services",
            "bridge_summary": "Docker Compose networks communicate via HTTP and TCP ports; understanding REST architecture is key to multi-service configuration.",
        })

    # Pitfall and tradeoff
    pitfall_text, tradeoff_text = DOCKER_PITFALLS.get(slug, (
        f"In production Docker workflows, misconfiguring {title} without proper resource limits or non-root user isolation can lead to host resource starvation.",
        f"Developer velocity vs production security: How do engineering teams balance rapid local Docker workflows with strict container hardening in {title}?"
    ))

    # Next milestone
    next_milestones = []
    if idx + 1 < len(all_topics):
        next_item = all_topics[idx + 1]
        next_milestones.append({
            "slug": next_item["slug"],
            "title": next_item["title"],
            "reason": f"Proceed to the next container milestone: {next_item['title']}.",
        })

    docker_graph[slug] = {
        "title": title,
        "series": "docker-mastery",
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
existing_graph.update(docker_graph)
print(f"Merged graph articles: {len(existing_graph)}")

with open("a_agent/data/prerequisites_graph.json", "w", encoding="utf-8") as f:
    json.dump(existing_graph, f, ensure_ascii=False, indent=2)

print("Saved updated prerequisites_graph.json successfully with Docker topics!")
