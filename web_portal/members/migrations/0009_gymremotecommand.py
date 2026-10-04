from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('members', '0008_alter_plan_name')]

    operations = [
        migrations.CreateModel(
            name='GymRemoteCommand',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(max_length=16)),
                ('local_id', models.PositiveBigIntegerField()),
                ('data', models.JSONField(default=dict)),
                ('create', models.BooleanField(default=False)),
                ('status', models.CharField(choices=[('pending', 'در انتظار دریافت باشگاه'), ('applied', 'اعمال‌شده'), ('failed', 'ناموفق')], db_index=True, default='pending', max_length=12)),
                ('error', models.CharField(blank=True, max_length=500)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('web_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='members.user')),
                ('selected_plan', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='members.plan')),
            ],
            options={'ordering': ['id']},
        ),
    ]
