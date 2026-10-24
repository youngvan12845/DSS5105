import os
import sys
import json
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "a_core.settings")
django.setup()

from a_blog.models import ArticlePage, ArticleTag
from taggit.models import Tag

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    git_json_path = os.path.join(base_dir, "git_topics_list.json")
    docker_json_path = os.path.join(base_dir, "docker_topics_list.json")

    with open(git_json_path, "r", encoding="utf-8") as f:
        git_data = json.load(f)

    with open(docker_json_path, "r", encoding="utf-8") as f:
        docker_data = json.load(f)

    print("=== 1. Backfilling Git Course Articles ===")
    git_updated = 0
    lesson_counter = 1
    for ch in git_data:
        ch_idx = ch["chapter_idx"]
        ch_name = ch["chapter_name"]
        for topic in ch["topics"]:
            slug = topic["slug"]
            article = ArticlePage.objects.filter(slug=slug).first()
            if article:
                article.series_slug = "git"
                article.series_title = "Git & GitHub Master Course"
                article.chapter_number = ch_idx
                article.chapter_title = ch_name
                article.lesson_number = lesson_counter
                article.save(update_fields=[
                    "series_slug", "series_title", "chapter_number", "chapter_title", "lesson_number"
                ])
                # Also update latest revision so Wagtail admin stays in sync
                rev = article.get_latest_revision()
                if rev:
                    rev_content = rev.content
                    rev_content["series_slug"] = "git"
                    rev_content["series_title"] = "Git & GitHub Master Course"
                    rev_content["chapter_number"] = ch_idx
                    rev_content["chapter_title"] = ch_name
                    rev_content["lesson_number"] = lesson_counter
                    rev.content = rev_content
                    rev.save()
                git_updated += 1
                lesson_counter += 1
            else:
                print(f"  [WARN] Git article not found: {slug}")

    print(f"Git articles updated: {git_updated}/75")

    print("\n=== 2. Backfilling Docker Course Articles ===")
    docker_updated = 0
    lesson_counter = 1
    for ch in docker_data:
        ch_idx = ch["chapter_idx"]
        ch_name = ch["chapter_name"]
        for topic in ch["topics"]:
            slug = topic["slug"]
            article = ArticlePage.objects.filter(slug=slug).first()
            if article:
                article.series_slug = "docker"
                article.series_title = "Docker Basics Course"
                article.chapter_number = ch_idx
                article.chapter_title = ch_name
                article.lesson_number = lesson_counter
                article.save(update_fields=[
                    "series_slug", "series_title", "chapter_number", "chapter_title", "lesson_number"
                ])
                rev = article.get_latest_revision()
                if rev:
                    rev_content = rev.content
                    rev_content["series_slug"] = "docker"
                    rev_content["series_title"] = "Docker Basics Course"
                    rev_content["chapter_number"] = ch_idx
                    rev_content["chapter_title"] = ch_name
                    rev_content["lesson_number"] = lesson_counter
                    rev.content = rev_content
                    rev.save()
                docker_updated += 1
                lesson_counter += 1
            else:
                print(f"  [WARN] Docker article not found: {slug}")

    print(f"Docker articles updated: {docker_updated}/27")

    print("\n=== 3. Removing chapter-* tags from all articles ===")
    ch_article_tags = ArticleTag.objects.filter(tag__name__startswith="chapter-")
    count_tagged = ch_article_tags.count()
    ch_article_tags.delete()
    print(f"Deleted {count_tagged} ArticleTag records linking to chapter-* tags.")

    ch_tags = Tag.objects.filter(name__startswith="chapter-")
    ch_tag_names = list(ch_tags.values_list("name", flat=True))
    ch_tags.delete()
    print(f"Deleted {len(ch_tag_names)} Tag records: {ch_tag_names}")

    # Verify
    remaining_ch_tags = Tag.objects.filter(name__startswith="chapter-").count()
    remaining_art_tags = ArticleTag.objects.filter(tag__name__startswith="chapter-").count()
    print(f"Remaining chapter- tags in DB: {remaining_ch_tags} Tags, {remaining_art_tags} ArticleTags")
    print("\n=== Done! ===")

if __name__ == "__main__":
    main()
