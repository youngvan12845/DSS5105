from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.urls import reverse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger  # 新增导入
from taggit.models import Tag  # 新增导入

from .models import ArticlePage, Comment
from operator import attrgetter

# from a_users.models import BrowsingHistory

def article_search(request):
    search_query = request.GET.get('query', '').strip()
    tag = request.GET.get('tag')
    
    if search_query:
        # 使用 Wagtail 的 autocomplete 进行更宽松的搜索
        articles = ArticlePage.objects.live().autocomplete(search_query)
        
        # 如果没有结果，尝试普通搜索
        if not articles:
            articles = ArticlePage.objects.live().search(search_query)
    else:
        articles = ArticlePage.objects.live()
    
    # 标签过滤
    if tag:
        articles = articles.filter(tags__name=tag)
    
    # 排序处理（转换为列表后排序）
    articles = sorted(
        articles,
        key=lambda x: x.first_published_at,
        reverse=True
    )
    
    # 分页
    paginator = Paginator(articles, 12)
    page = request.GET.get('page')
    
    try:
        paginated_articles = paginator.page(page)
    except PageNotAnInteger:
        paginated_articles = paginator.page(1)
    except EmptyPage:
        paginated_articles = paginator.page(paginator.num_pages)
    
    # 获取所有标签
    all_tags = Tag.objects.all()
    
    context = {
        'articles': paginated_articles,
        'search_query': search_query,
        'tag': tag,
        'all_tags': all_tags,
        'paginator': paginator,
    }
    return render(request, 'a_blog/blog_page.html', context)


@login_required
@require_POST
def add_comment(request, article_id):
    """添加评论"""
    article = get_object_or_404(ArticlePage, id=article_id)
    content = request.POST.get('content', '').strip()
    parent_id = request.POST.get('parent_id')
    
    if not content:
        messages.error(request, '评论内容不能为空')
        return redirect(article.get_url())
    
    # 创建评论
    comment = Comment.objects.create(
        article=article,
        author=request.user,
        content=content,
        parent_id=parent_id if parent_id else None
    )
    
    messages.success(request, '评论发表成功！')
    return redirect(article.get_url() + '#comments')


@login_required
@require_POST
def delete_comment(request, comment_id):
    """删除评论"""
    comment = get_object_or_404(Comment, id=comment_id)
    
    # 只允许评论作者或文章作者删除评论
    if request.user == comment.author or request.user == comment.article.owner:
        comment.delete()
        messages.success(request, '评论已删除')
    else:
        messages.error(request, '您没有权限删除此评论')
    
    return redirect(comment.article.get_url() + '#comments')


def get_comments_ajax(request, article_id):
    """AJAX获取评论列表"""
    article = get_object_or_404(ArticlePage, id=article_id)
    comments = article.comments.filter(is_active=True, parent=None).order_by('-created_at')
    
    comments_data = []
    for comment in comments:
        comment_data = {
            'id': comment.id,
            'author': comment.author.profile.name if hasattr(comment.author, 'profile') else comment.author.username,
            'author_avatar': comment.author.profile.avatar if hasattr(comment.author, 'profile') and comment.author.profile.avatar else '',
            'content': comment.content,
            'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M'),
            'can_delete': request.user == comment.author or request.user == article.owner,
            'replies': []
        }
        
        # 获取回复
        for reply in comment.replies.filter(is_active=True).order_by('created_at'):
            reply_data = {
                'id': reply.id,
                'author': reply.author.profile.name if hasattr(reply.author, 'profile') else reply.author.username,
                'author_avatar': reply.author.profile.avatar if hasattr(reply.author, 'profile') and reply.author.profile.avatar else '',
                'content': reply.content,
                'created_at': reply.created_at.strftime('%Y-%m-%d %H:%M'),
                'can_delete': request.user == reply.author or request.user == article.owner,
            }
            comment_data['replies'].append(reply_data)
        
        comments_data.append(comment_data)
    
    return JsonResponse({
        'comments': comments_data,
        'total_count': article.comments.filter(is_active=True).count()
    })

# from a_users.models import BrowsingHistory

# 添加一个新的视图来处理文章详情页面（如果还没有的话）
def article_detail_view(request, article_id):
    """文章详情页面"""
    article = get_object_or_404(ArticlePage, id=article_id)
    
    # 记录浏览历史（只对已登录用户）
    # if request.user.is_authenticated:
    #     BrowsingHistory.add_or_update_history(
    #         user=request.user,
    #         article_id=article.id,
    #         article_title=article.title,
    #         article_url=article.get_url()
    #     )
    
    # 获取评论
    comments = article.comments.filter(is_active=True, parent=None).order_by('-created_at')
    
    context = {
        'article': article,
        'comments': comments,
    }
    
    return render(request, 'a_blog/article_page.html', context)

# def record_article_view(request, article):
#     """记录文章浏览历史的辅助函数"""
#     if request.user.is_authenticated:
#         BrowsingHistory.add_or_update_history(
#             user=request.user,
#             article_id=article.id,
#             article_title=article.title,
#             article_url=article.get_url()
#         )