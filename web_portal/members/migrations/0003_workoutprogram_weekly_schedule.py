from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0002_coachprofile_workoutprogram"),
    ]

    operations = [
        migrations.AddField(
            model_name="workoutprogram",
            name="duration_weeks",
            field=models.PositiveSmallIntegerField(default=4),
        ),
        migrations.AddField(
            model_name="workoutprogram",
            name="schedule_json",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
