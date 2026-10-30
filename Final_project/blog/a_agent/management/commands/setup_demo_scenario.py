from __future__ import annotations

from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from a_blog.models import ArticlePage
from a_points.models import PointsRecord
from a_users.models import BrowsingHistory, Profile


User = get_user_model()


class Command(BaseCommand):
    help = "Seeds reproducible demo personas and state for Capstone end-to-end evaluation."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Reset points and browsing history for demo accounts.",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Setting up Capstone Presentation Demo Scenarios..."))

        # 1. Setup Demo Free Student Account
        free_user, _ = User.objects.get_or_create(username="demo_free", defaults={"email": "demo_free@example.com"})
        free_user.set_password("demopass123")
        free_user.save()

        free_profile, _ = Profile.objects.get_or_create(user=free_user)
        free_profile.displayname = "Alex (Learner)"
        free_profile.is_subscribed = False
        free_profile.subscription_end_date = None
        free_profile.points = 30  # Exactly 30 points to test paywall unlock
        free_profile.save()

        # Points log
        PointsRecord.objects.filter(user=free_user).delete()
        PointsRecord.objects.create(
            user=free_user,
            points=20,
            type="earn",
            description="Welcome bonus on registration",
            created_at=timezone.now() - timedelta(days=2),
        )
        PointsRecord.objects.create(
            user=free_user,
            points=10,
            type="earn",
            description="Daily login reward",
            created_at=timezone.now() - timedelta(hours=3),
        )

        # Browsing history for demo_free
        BrowsingHistory.objects.filter(user=free_user).delete()
        docker_intro = ArticlePage.objects.filter(slug="docker-chapter-1-docker-introduction").first()
        git_intro = ArticlePage.objects.filter(slug="git-chapter-1-git-github-overview").first()
        if docker_intro:
            BrowsingHistory.add_or_update_history(
                user=free_user,
                article_id=docker_intro.pk,
                article_title=docker_intro.title,
                article_url=docker_intro.url or f"/blog/series/{docker_intro.slug}/",
            )
        if git_intro:
            BrowsingHistory.add_or_update_history(
                user=free_user,
                article_id=git_intro.pk,
                article_title=git_intro.title,
                article_url=git_intro.url or f"/blog/series/{git_intro.slug}/",
            )

        # 2. Setup Demo Pro Engineer Account
        pro_user, _ = User.objects.get_or_create(username="demo_pro", defaults={"email": "demo_pro@example.com"})
        pro_user.set_password("demopass123")
        pro_user.save()

        pro_profile, _ = Profile.objects.get_or_create(user=pro_user)
        pro_profile.displayname = "Sarah (Pro Staff)"
        pro_profile.is_subscribed = True
        pro_profile.subscription_date = timezone.now().date() - timedelta(days=30)
        pro_profile.subscription_end_date = timezone.now().date() + timedelta(days=335)
        pro_profile.points = 150
        pro_profile.save()

        # Points log for pro_user
        PointsRecord.objects.filter(user=pro_user).delete()
        PointsRecord.objects.create(
            user=pro_user,
            points=100,
            type="earn",
            description="Pro annual subscription grant",
            created_at=timezone.now() - timedelta(days=30),
        )

        # Browsing history for demo_pro
        BrowsingHistory.objects.filter(user=pro_user).delete()
        advanced_git = ArticlePage.objects.filter(slug="git-non-fast-forward-merge-no-option").first()
        if advanced_git:
            BrowsingHistory.add_or_update_history(
                user=pro_user,
                article_id=advanced_git.pk,
                article_title=advanced_git.title,
                article_url=advanced_git.url or f"/blog/series/{advanced_git.slug}/",
            )

        # Print Output Summary for Presentation
        self.stdout.write(self.style.SUCCESS("\n[SUCCESS] Demo accounts and scenario initialized successfully!\n"))
        self.stdout.write("=================================================================")
        self.stdout.write("  CAPSTONE END-TO-END DEMO PERSONAS & PLAYBOOK CREDENTIALS")
        self.stdout.write("=================================================================")
        self.stdout.write("1. Persona: Anonymous Guest")
        self.stdout.write("   - Auth: Incognito window / Not logged in")
        self.stdout.write("   - Test URL: /blog/series/")
        self.stdout.write("   - Paywall Target: /blog/series/git-non-fast-forward-merge-no-option/")
        self.stdout.write("   - Action: Experience dual-track series, hit Paywall preview, prompt login.\n")

        self.stdout.write("2. Persona: Free Registered Student")
        self.stdout.write("   - Username: demo_free | Password: demopass123")
        self.stdout.write("   - Status: 30 Points, 2 recent articles in browsing history")
        self.stdout.write("   - AI Assistant Query: 'I want to learn Docker Compose, what should I study first?'")
        self.stdout.write("   - Expected Agent Response: DAG prerequisite bridging -> recommends Git & Docker CLI")
        self.stdout.write("   - Paywall Action: Spends 30 points to unlock advanced Git Merge lesson.\n")

        self.stdout.write("3. Persona: Pro Senior Engineer")
        self.stdout.write("   - Username: demo_pro | Password: demopass123")
        self.stdout.write("   - Status: Pro Active Subscriber (unlimited access)")
        self.stdout.write("   - AI Assistant Query: 'Compare Git detached HEAD state with Docker detached container mode'")
        self.stdout.write("   - Expected Agent Response: Multi-hop synthesis across Git & Docker tracks with exact citations")
        self.stdout.write("   - Action: Add to reading list via two-phase confirmation.\n")
        self.stdout.write("=================================================================\n")
