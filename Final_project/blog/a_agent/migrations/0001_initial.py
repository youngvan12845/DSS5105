# Generated manually for a_agent initial models

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AgentActionLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action_type', models.CharField(max_length=64)),
                ('payload', models.JSONField(blank=True, default=dict)),
                ('confirmed', models.BooleanField(default=False)),
                ('executed', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='agent_actions', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='ArticleChunk',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('article_id', models.PositiveIntegerField(db_index=True)),
                ('article_title', models.CharField(max_length=255)),
                ('article_url', models.CharField(blank=True, max_length=500)),
                ('chunk_index', models.PositiveIntegerField(default=0)),
                ('content', models.TextField()),
                ('is_free', models.BooleanField(default=True)),
                ('required_points', models.PositiveIntegerField(default=0)),
                ('tags', models.CharField(blank=True, max_length=500)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['article_id', 'chunk_index'], 'unique_together': {('article_id', 'chunk_index')}},
        ),
        migrations.CreateModel(
            name='ChatSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(blank=True, default='新对话', max_length=120)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='agent_sessions', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-updated_at']},
        ),
        migrations.CreateModel(
            name='ChatMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('user', 'User'), ('assistant', 'Assistant')], max_length=20)),
                ('content', models.TextField()),
                ('citations', models.JSONField(blank=True, default=list)),
                ('tool_trace', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='a_agent.chatsession')),
            ],
            options={'ordering': ['created_at']},
        ),
    ]
