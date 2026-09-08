from django.urls import path

from . import views

app_name = 'a_agent'

urlpatterns = [
    path('', views.chat_view, name='chat'),
    path('reading-list/', views.reading_list_view, name='reading_list'),
    path(
        'reading-list/<int:article_id>/remove/',
        views.remove_reading_list_item_view,
        name='remove_reading_list_item',
    ),
    path('session/<int:session_id>/', views.chat_view, name='chat_session'),
    path('article/<int:article_id>/', views.chat_view, name='chat_article'),
    path('article/<int:article_id>/panel/', views.article_panel_view, name='article_panel'),
    path('article/<int:article_id>/send/', views.article_send_message_view, name='article_send_message'),
    path('session/new/', views.new_session_view, name='new_session'),
    path('session/<int:session_id>/delete/', views.delete_session_view, name='delete_session'),
    path('session/<int:session_id>/send/', views.send_message_view, name='send_message'),
    path('actions/<int:action_id>/confirm/', views.confirm_action_view, name='confirm_action'),
    path('actions/<int:action_id>/cancel/', views.cancel_action_view, name='cancel_action'),
]
