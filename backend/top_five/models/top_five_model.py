from django.db import models
from django.conf import settings


class Top5Job(models.Model):
    class Status(models.TextChoices):
        PENDING    = "PENDING",    "Pending"
        PROCESSING = "PROCESSING", "Processing"
        DONE       = "DONE",       "Done"
        FAILED     = "FAILED",     "Failed"

    created_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="top5_jobs",
    )
    input_file   = models.CharField(max_length=255)          # original filename
    status       = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    error        = models.TextField(blank=True, default="")
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Top5Job #{self.pk} — {self.input_file} [{self.status}]"