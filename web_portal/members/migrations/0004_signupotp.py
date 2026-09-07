from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0003_workoutprogram_weekly_schedule"),
    ]

    operations = [
        migrations.CreateModel(
            name="SignupOTP",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("mobile", models.CharField(db_index=True, max_length=11, unique=True)),
                ("code_digest", models.CharField(max_length=64)),
                ("expires_at", models.DateTimeField()),
                ("last_sent_at", models.DateTimeField()),
                ("window_started_at", models.DateTimeField()),
                ("send_count", models.PositiveSmallIntegerField(default=1)),
                ("failed_attempts", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
