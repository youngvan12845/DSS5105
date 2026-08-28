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
    
    def get_context(self, request): 
        tag = request.GET.get("tag")
        if tag:
            articles = ArticlePage.objects.filter(tags__name=tag).live().order_by('-first_published_at')
        else:     
            articles = self.get_children().live().order_by('-first_published_at')
            
        # 获取所有标签
        all_tags = Tag.objects.all()
        
        # 添加分页逻辑
        paginator = Paginator(articles, 12)  # 每页显示12篇文章
        page = request.GET.get('page')
        
        try:
            paginated_articles = paginator.page(page)
        except PageNotAnInteger:
            # 如果页码不是整数，返回第一页
            paginated_articles = paginator.page(1)
        except EmptyPage:
            # 如果页码超出范围，返回最后一页
            paginated_articles = paginator.page(paginator.num_pages)
            
        context = super().get_context(request)
        context['articles'] = paginated_articles  # 使用分页后的文章列表
        context['paginator'] = paginator  # 添加分页器到上下文
        context["tag"] = tag
        context['all_tags'] = all_tags  # 将所有标签传递到模板
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
    
    views = models.PositiveIntegerField(default=0, editable=False)

    is_free = models.BooleanField(default=True, verbose_name="是否为免费页面")
    required_points = models.PositiveIntegerField(default=0, verbose_name="所需积分")
    
    def increment_view_count(self):
        self.views += 1
        self.save(update_fields=["views"])
    
    def image_url(self):
        return self.image.get_rendition('fill-1200x675|jpegquality-80').url
    
    def get_context(self, request):
        context = super().get_context(request)
        context["image_url"] = self.image_url()
        
        # 添加评论相关的上下文
        comments = self.comments.filter(is_active=True, parent=None).order_by('-created_at')
        context['comments'] = comments
        context['comment_count'] = self.comments.filter(is_active=True).count()
        
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
                profile.deduct_points(self.required_points,description="购买文章")
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
        FieldPanel('is_free'),
        FieldPanel('required_points'),
    ]
    
class ArticleTag(TaggedItemBase):
    content_object = ParentalKey(ArticlePage, on_delete=models.CASCADE, related_name='tagged_items')