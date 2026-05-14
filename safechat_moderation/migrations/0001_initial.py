import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("zerver", "0001_squashed_0569"),
    ]

    operations = [
        migrations.CreateModel(
            name="FlaggedMessage",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("content_preview", models.TextField()),
                ("classifier", models.CharField(max_length=100)),
                ("score", models.FloatField()),
                ("label", models.CharField(max_length=50)),
                ("stream_id", models.IntegerField(blank=True, null=True)),
                ("stream_name", models.TextField(blank=True)),
                ("topic_name", models.TextField(blank=True)),
                ("is_dm", models.BooleanField(default=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("dismissed", "Dismissed"),
                            ("actioned", "Actioned"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "message",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="zerver.message",
                    ),
                ),
                (
                    "realm",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="zerver.realm",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_flags",
                        to="zerver.userprofile",
                    ),
                ),
                (
                    "sender",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sent_flags",
                        to="zerver.userprofile",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
