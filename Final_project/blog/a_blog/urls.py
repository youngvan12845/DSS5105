from django.urls import path, include
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls
from wagtail import urls as wagtail_urls

from .views import *

urlpatterns = [
    path('', article_search, name='home'),  
    path('cms/', include(wagtailadmin_urls)),
    path('documents/', include(wagtaildocs_urls)),
    path('search/', article_search, name='article_search'),
    
    # 评论相关URL
    path('comment/add/<int:article_id>/', add_comment, name='add_comment'),
    path('comment/delete/<int:comment_id>/', delete_comment, name='delete_comment'),
    path('comment/ajax/<int:article_id>/', get_comments_ajax, name='get_comments_ajax'),
    
    path('', include(wagtail_urls)),
]