from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('a_agent', '0002_chatsession_llm_model_chatmessage_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='articlechunk',
            name='embedding',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='chatmessage',
            name='pending_action',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.CreateModel(
            name='ReadingListItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('article_id', models.PositiveIntegerField()),
                ('article_title', models.CharField(max_length=255)),
                ('article_url', models.CharField(blank=True, max_length=500)),
                ('is_free', models.BooleanField(default=True)),
                ('added_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='reading_list_items', to='auth.user')),
            ],
            options={
                'ordering': ['-added_at'],
                'unique_together': {('user', 'article_id')},
            },
        ),
    ]
