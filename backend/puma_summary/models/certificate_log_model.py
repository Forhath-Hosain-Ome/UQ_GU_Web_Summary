from django.db import models
from django.contrib.auth.models import User
from .inspection_report_model import InspectionReport
from shared.models import BaseModel

class CertificateLog(BaseModel):
    """
    Audit log — records THAT a certificate was generated and downloaded,
    NOT the file itself.

    The DOCX is generated on-demand, served for download, then deleted from disk.
    This row is the only permanent record of the event.
    """

    report = models.ForeignKey(
        InspectionReport, on_delete=models.CASCADE, related_name="certificate_logs"
    )

    generated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="certificate_logs",
    )

    generated_at   = models.DateTimeField(auto_now_add=True)
    downloaded_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-generated_at"]
        verbose_name = "Certificate Log"
        verbose_name_plural = "Certificate Logs"

    def __str__(self):
        return f"Cert for {self.report.style} @ {self.generated_at:%Y-%m-%d %H:%M}"

    @property
    def was_downloaded(self):
        return self.downloaded_at is not None