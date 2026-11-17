# Generated for LifeBox desktop observability and signed manual updates.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('members', '0014_password_reset_challenge')]

    operations = [
        migrations.CreateModel(
            name='DesktopDevice',
            fields=[
                ('source', models.CharField(max_length=80, primary_key=True, serialize=False)),
                ('app_version', models.CharField(blank=True, max_length=40)),
                ('platform', models.CharField(blank=True, max_length=120)),
                ('state_size', models.PositiveBigIntegerField(default=0)),
                ('free_disk', models.PositiveBigIntegerField(default=0)),
                ('database_ok', models.BooleanField(default=True)),
                ('pending_sync', models.PositiveIntegerField(default=0)),
                ('process_id', models.PositiveIntegerField(default=0)),
                ('last_seen_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['-last_seen_at']},
        ),
        migrations.CreateModel(
            name='DesktopRelease',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('version', models.CharField(max_length=40, unique=True)),
                ('notes', models.TextField(blank=True)),
                ('package', models.FileField(upload_to='desktop-releases/%Y/%m/')),
                ('sha256', models.CharField(max_length=64)),
                ('signature', models.TextField(help_text='امضای Ed25519 فایل manifest؛ نسخه بدون امضای معتبر منتشر نشود.')),
                ('package_size', models.PositiveBigIntegerField(default=0)),
                ('is_published', models.BooleanField(db_index=True, default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('published_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={'ordering': ['-created_at', '-id']},
        ),
        migrations.CreateModel(
            name='DesktopLogEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('local_id', models.PositiveBigIntegerField()),
                ('level', models.CharField(max_length=20)),
                ('logger', models.CharField(max_length=200)),
                ('message', models.TextField()),
                ('occurred_at', models.DateTimeField()),
                ('received_at', models.DateTimeField(auto_now_add=True)),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='log_events', to='members.desktopdevice')),
            ],
            options={
                'ordering': ['-occurred_at', '-id'],
                'constraints': [models.UniqueConstraint(fields=('device', 'local_id'), name='unique_desktop_log_event')],
            },
        ),
        migrations.CreateModel(
            name='DesktopUpdateAttempt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('downloading', 'در حال دانلود'), ('installing', 'در حال نصب'), ('succeeded', 'موفق'), ('failed', 'ناموفق'), ('rolled_back', 'بازگشت به نسخه قبلی')], max_length=20)),
                ('error', models.CharField(blank=True, max_length=1000)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='update_attempts', to='members.desktopdevice')),
                ('release', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attempts', to='members.desktoprelease')),
            ],
            options={'ordering': ['-updated_at', '-id']},
        ),
    ]
