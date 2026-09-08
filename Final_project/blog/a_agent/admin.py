from django.contrib import admin

from .models import AgentActionLog, ArticleChunk, ChatMessage, ChatSession, ReadingListItem


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'title', 'updated_at')
    search_fields = ('title', 'user__username')


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'role', 'created_at')
    list_filter = ('role',)


@admin.register(ArticleChunk)
class ArticleChunkAdmin(admin.ModelAdmin):
    list_display = ('article_id', 'article_title', 'chunk_index', 'is_free', 'updated_at')
    search_fields = ('article_title', 'content', 'tags')


@admin.register(ReadingListItem)
class ReadingListItemAdmin(admin.ModelAdmin):
    list_display = ('user', 'article_title', 'is_free', 'added_at')
    search_fields = ('article_title', 'user__username')


@admin.register(AgentActionLog)
class AgentActionLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'action_type', 'confirmed', 'executed', 'created_at')
    list_filter = ('action_type', 'confirmed', 'executed')
