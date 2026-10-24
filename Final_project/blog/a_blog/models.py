from django.db import models
from wagtail.models import Page
from wagtail.fields import RichTextField
from wagtail.admin.panels import FieldPanel
from wagtail.search import index
from taggit.models import TaggedItemBase
from modelcluster.fields import ParentalKey
from modelcluster.contrib.taggit import ClusterTaggableManager
from datetime import date
from django.shortcuts import redirect
from django.http import JsonResponse, HttpResponseForbidden
from taggit.models import Tag
from django.template.response import TemplateResponse  # 确保引入 TemplateResponse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger  # 导入分页相关类
from django.contrib.auth.models import User


class BlogPage(Page):
    body = RichTextField(blank=True)
    content_panels = Page.content_panels + [
        FieldPanel('body'),
    ]
    
    template = "a_blog/blog_page.html"
    
    def get_template(self, request, *args, **kwargs):
        if self.slug == "series":
            return "a_blog/series_page.html"
        return "a_blog/blog_page.html"

    def get_context(self, request): 
        if self.slug == "series":
            track = request.GET.get("track", "").strip().lower()
            query = request.GET.get("query", "").strip()
            
            series_articles = ArticlePage.objects.child_of(self).live()
            if query:
                series_articles = series_articles.filter(
                    models.Q(title__icontains=query) | models.Q(intro__icontains=query)
                )

            course_meta = [
                {
                    "slug": "git",
                    "title": "Git & GitHub Master Course",
                    "subtitle": "7 Chapters · 75 Lessons · Comprehensive Version Control Mastery",
                    "badge": "Version Control Track",
                    "icon": "🐙",
                    "color": "pink",
                    "description": "A systematic, hands-on curriculum from Git key concepts, staging, and commit lifecycle to advanced branching, rebase vs merge, and GitHub remote team collaboration.",
                },
                {
                    "slug": "docker",
                    "title": "Docker Basics Course",
                    "subtitle": "6 Chapters · 27 Lessons · Container Architecture & Compose Deployment",
                    "badge": "Container Track",
                    "icon": "🐳",
                    "color": "sky",
                    "description": "Master containerization, Dockerfile multi-stage builds, networking, persistent storage volumes, and multi-service Docker Compose deployment.",
                },
            ]

            courses = []
            for meta in course_meta:
                if track and track != meta["slug"]:
                    continue
                
                c_articles = series_articles.filter(series_slug=meta["slug"]).order_by("chapter_number", "lesson_number", "path")
                if not c_articles.exists() and query:
                    continue
                
                chapters_dict = {}
                for art in c_articles:
                    ch_num = art.chapter_number or 1
                    ch_title = art.chapter_title or f"Chapter {ch_num}"
                    if ch_num not in chapters_dict:
                        chapters_dict[ch_num] = {
                            "number": ch_num,
                            "title": ch_title,
                            "lessons": []
                        }
                    chapters_dict[ch_num]["lessons"].append(art)
                
                sorted_chapters = [chapters_dict[k] for k in sorted(chapters_dict.keys())]
                total_lessons = sum(len(c["lessons"]) for c in sorted_chapters)
                
                courses.append({
                    **meta,
                    "chapters": sorted_chapters,
                    "lesson_count": total_lessons,
                    "chapter_count": len(sorted_chapters),
                })
            
            context = super().get_context(request)
            context["courses"] = courses
            context["active_track"] = track
            context["query"] = query
            return context

        # Regular Blog context
        tag = request.GET.get("tag")
        articles = ArticlePage.objects.child_of(self).live()
        if tag:
            articles = articles.filter(tags__name=tag)
            
        articles = articles.order_by("-first_published_at")
            
        # 获取当前分类下的标签 (排除 chapter 内部标签)
        all_tags = Tag.objects.filter(
            articlepage__in=ArticlePage.objects.child_of(self).live()
        ).exclude(name__startswith='chapter-').distinct()
        if not all_tags.exists():
            all_tags = Tag.objects.exclude(name__startswith='chapter-')
        
        paginator = Paginator(articles, 12)
        page = request.GET.get('page')
        
        try:
            paginated_articles = paginator.page(page)
        except PageNotAnInteger:
            paginated_articles = paginator.page(1)
        except EmptyPage:
            paginated_articles = paginator.page(paginator.num_pages)
            
        context = super().get_context(request)
        context['articles'] = paginated_articles
        context['paginator'] = paginator
        context["tag"] = tag
        context['all_tags'] = all_tags
        return context


class Comment(models.Model):
    """评论模型"""
    article = models.ForeignKey('ArticlePage', on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField(verbose_name="评论内容")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, verbose_name="是否显示")
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "评论"
        verbose_name_plural = "评论"
    
    def __str__(self):
        return f'{self.author.username} - {self.content[:50]}'
    
    @property
    def is_reply(self):
        return self.parent is not None


class ArticlePage(Page):
    intro = models.CharField(max_length=80)
    body = RichTextField(blank=True)
    date = models.DateField("Post date", default=date.today)
    image = models.ForeignKey(
        'wagtailimages.Image', on_delete=models.SET_NULL, null=True, related_name='+'
    )
    caption = models.CharField(blank=True, max_length=80)
    
    tags = ClusterTaggableManager(through='ArticleTag', blank=True)
    
    # 專屬系列學習與章節欄位（取代以 tag 表示 chapter）
    series_slug = models.CharField(max_length=50, blank=True, default='', db_index=True, verbose_name="系列代稱")
    series_title = models.CharField(max_length=120, blank=True, default='', verbose_name="系列名稱")
    chapter_number = models.PositiveIntegerField(default=0, db_index=True, verbose_name="章節編號")
    chapter_title = models.CharField(max_length=150, blank=True, default='', verbose_name="章節名稱")
    lesson_number = models.PositiveIntegerField(default=0, verbose_name="課時編號")

    views = models.PositiveIntegerField(default=0, editable=False)
    likes = models.PositiveIntegerField(default=0, verbose_name="点赞数")

    is_free = models.BooleanField(default=True, verbose_name="是否为免费页面")
    required_points = models.PositiveIntegerField(default=0, verbose_name="所需积分")
    
    @property
    def is_series_article(self):
        return bool(self.series_slug)

    def get_clean_tags(self):
        """返回乾淨的標籤列表（過濾掉內部的 chapter- 標籤）"""
        return [tag for tag in self.tags.all() if not tag.name.startswith('chapter-')]

    def get_prev_lesson(self):
        """獲取同一系列中的上一課"""
        if not self.series_slug:
            return None
        return (
            ArticlePage.objects.live()
            .filter(series_slug=self.series_slug)
            .filter(
                models.Q(chapter_number__lt=self.chapter_number) |
                models.Q(chapter_number=self.chapter_number, lesson_number__lt=self.lesson_number)
            )
            .order_by('-chapter_number', '-lesson_number')
            .first()
        )

    def get_next_lesson(self):
        """獲取同一系列中的下一課"""
        if not self.series_slug:
            return None
        return (
            ArticlePage.objects.live()
            .filter(series_slug=self.series_slug)
            .filter(
                models.Q(chapter_number__gt=self.chapter_number) |
                models.Q(chapter_number=self.chapter_number, lesson_number__gt=self.lesson_number)
            )
            .order_by('chapter_number', 'lesson_number')
            .first()
        )

    def increment_view_count(self):
        self.views += 1
        self.save(update_fields=["views"])
    
    def increment_like_count(self):
        self.likes += 1
        self.save(update_fields=["likes"])
    
    def image_url(self):
        return self.image.get_rendition('fill-1200x675|jpegquality-80').url
    
    def get_context(self, request):
        context = super().get_context(request)
        context["image_url"] = self.image_url()
        
        # 添加评论相关的上下文
        comments = self.comments.filter(is_active=True, parent=None).order_by('-created_at')
        context['comments'] = comments
        context['comment_count'] = self.comments.filter(is_active=True).count()
        
        # 標籤與系列課程上一篇/下一篇導航
        context['clean_tags'] = self.get_clean_tags()
        if self.series_slug:
            context['prev_lesson'] = self.get_prev_lesson()
            context['next_lesson'] = self.get_next_lesson()
            
        return context
    
    def get_tags(self):
        return ", ".join(tag.name for tag in self.tags.all())
    
    def get_author(self):
        return self.owner.profile.name
    
    def get_author_username(self):
        return self.owner.username

    def _record_browsing_history(self, request):
        if request.user.is_authenticated:
            from a_users.models import BrowsingHistory
            page_url = self.get_url(request) or self.url
            if page_url:
                article_url = request.build_absolute_uri(page_url)
                BrowsingHistory.add_or_update_history(
                    user=request.user,
                    article_id=self.pk,
                    article_title=self.title,
                    article_url=article_url,
                )

    def serve(self, request):
        session_key = f'article_viewed_{self.pk}'
        if not request.session.get(session_key, False):
            self.increment_view_count()
            request.session[session_key] = True

        profile = request.user.profile if request.user.is_authenticated else None

        # 免费页面：所有用户都可以访问
        if self.is_free:
            self._record_browsing_history(request)
            return super().serve(request)

        # 会员用户可以免费访问
        if profile and profile.has_valid_subscription():
            self._record_browsing_history(request)
            return super().serve(request)

        # 检查是否已支付积分
        if request.session.get(f"article_access_{self.pk}", False):
            self._record_browsing_history(request)
            return super().serve(request)

        # 非会员用户需要消耗积分
        if profile and profile.points >= self.required_points:
            if request.method == "POST":  # 用户确认扣除积分
                profile.deduct_points(self.required_points, description="Article purchase")
                request.session[f"article_access_{self.pk}"] = True  # 标记已支付
                self._record_browsing_history(request)
                return super().serve(request)
            else:  # 显示预览页面
                context = self.get_context(request)
                context["show_preview"] = True
                context["points_required"] = self.required_points
                return TemplateResponse(request, self.get_template(request), context)

        # 积分不足，提示充值或成为会员
        context = self.get_context(request)
        context["show_preview"] = True
        context["points_required"] = self.required_points
        context["insufficient_points"] = True
        return TemplateResponse(request, self.get_template(request), context)
    
    search_fields = Page.search_fields + [
        index.SearchField('title', partial_match=True, boost=10),
        index.SearchField('intro', partial_match=True, boost=5),
        index.SearchField('body', partial_match=True, boost=3),
        index.SearchField('get_tags'),  # 确保标签可搜索
        index.AutocompleteField('title'),  # 新增自动完成字段
        index.AutocompleteField('intro'),
    ]
    
    content_panels = Page.content_panels + [
        FieldPanel('intro'),
        FieldPanel('image'),
        FieldPanel('caption'),
        FieldPanel('body'),
        FieldPanel('date'),
        FieldPanel('tags'),
        FieldPanel('series_slug'),
        FieldPanel('series_title'),
        FieldPanel('chapter_number'),
        FieldPanel('chapter_title'),
        FieldPanel('lesson_number'),
        FieldPanel('likes'),
        FieldPanel('is_free'),
        FieldPanel('required_points'),
    ]
    
class ArticleTag(TaggedItemBase):
    content_object = ParentalKey(ArticlePage, on_delete=models.CASCADE, related_name='tagged_items')