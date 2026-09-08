from django.conf import settings
from django.db import models


class ChatSession(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='agent_sessions',
    )
    title = models.CharField(max_length=120, blank=True, default='New chat')
    llm_model = models.CharField(max_length=64, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.user.username} — {self.title}'


class ChatMessage(models.Model):
    ROLE_USER = 'user'
    ROLE_ASSISTANT = 'assistant'
    ROLE_CHOICES = [
        (ROLE_USER, 'User'),
        (ROLE_ASSISTANT, 'Assistant'),
    ]

    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    image = models.ImageField(upload_to='agent_uploads/%Y/%m/', blank=True, null=True)
    citations = models.JSONField(default=list, blank=True)
    tool_trace = models.JSONField(default=list, blank=True)
    pending_action = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.role}: {self.content[:40]}'


class ArticleChunk(models.Model):
    """Indexed article text for retrieval (keyword now; vectors later)."""

    article_id = models.PositiveIntegerField(db_index=True)
    article_title = models.CharField(max_length=255)
    article_url = models.CharField(max_length=500, blank=True)
    chunk_index = models.PositiveIntegerField(default=0)
    content = models.TextField()
    is_free = models.BooleanField(default=True)
    required_points = models.PositiveIntegerField(default=0)
    tags = models.CharField(max_length=500, blank=True)
    embedding = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('article_id', 'chunk_index')
        ordering = ['article_id', 'chunk_index']

    def __str__(self):
        return f'{self.article_title} #{self.chunk_index}'


class ReadingListItem(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reading_list_items',
    )
    article_id = models.PositiveIntegerField()
    article_title = models.CharField(max_length=255)
    article_url = models.CharField(max_length=500, blank=True)
    is_free = models.BooleanField(default=True)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'article_id')
        ordering = ['-added_at']

    def __str__(self):
        return f'{self.user.username} — {self.article_title}'


class AgentActionLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='agent_actions',
    )
    action_type = models.CharField(max_length=64)
    payload = models.JSONField(default=dict, blank=True)
    confirmed = models.BooleanField(default=False)
    executed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
