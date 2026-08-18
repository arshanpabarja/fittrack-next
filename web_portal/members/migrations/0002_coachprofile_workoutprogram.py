import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("members", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CoachProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("specialty", models.CharField(blank=True, max_length=160)),
                ("bio", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("allowed_plans", models.ManyToManyField(blank=True, related_name="coaches", to="members.plan")),
                ("user", models.OneToOneField(limit_choices_to={"role": "coach"}, on_delete=django.db.models.deletion.CASCADE, related_name="coach_profile", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="WorkoutProgram",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=180)),
                ("exercises", models.TextField()),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("coach", models.ForeignKey(limit_choices_to={"role": "coach"}, on_delete=django.db.models.deletion.CASCADE, related_name="authored_workout_programs", to=settings.AUTH_USER_MODEL)),
                ("member", models.ForeignKey(limit_choices_to={"role": "member"}, on_delete=django.db.models.deletion.CASCADE, related_name="workout_programs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="workoutprogram",
            constraint=models.UniqueConstraint(fields=("coach", "member"), name="uq_current_program_per_coach_member"),
        ),
    ]
