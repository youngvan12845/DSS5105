from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('a_agent', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatsession',
            name='llm_model',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='chatmessage',
            name='image',
            field=models.ImageField(blank=True, null=True, upload_to='agent_uploads/%Y/%m/'),
        ),
    ]
