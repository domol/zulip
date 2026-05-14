from django.db import models


class FlaggedMessage(models.Model):
    STATUS_PENDING = "pending"
    STATUS_DISMISSED = "dismissed"
    STATUS_ACTIONED = "actioned"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_DISMISSED, "Dismissed"),
        (STATUS_ACTIONED, "Actioned"),
    ]

    message = models.ForeignKey("zerver.Message", on_delete=models.CASCADE)
    realm = models.ForeignKey("zerver.Realm", on_delete=models.CASCADE)
    sender = models.ForeignKey(
        "zerver.UserProfile",
        null=True,
        on_delete=models.SET_NULL,
        related_name="sent_flags",
    )
    content_preview = models.TextField()
    classifier = models.CharField(max_length=100)
    score = models.FloatField()
    label = models.CharField(max_length=50)

    stream_id = models.IntegerField(null=True, blank=True)
    stream_name = models.TextField(blank=True)
    topic_name = models.TextField(blank=True)
    is_dm = models.BooleanField(default=False)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        "zerver.UserProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_flags",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
