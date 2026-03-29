import logging
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from puma_summary.models import CertificateLog
from puma_summary.serializers import CertificateLogSerializer

logger = logging.getLogger(__name__)



# ─────────────────────────────────────────────────────────────────────────────
#      CERTIFICATE LOG LIST
#      GET /api/reports/<pk>/certificates/
#      Returns all certificate generation events for one report.
# ─────────────────────────────────────────────────────────────────────────────

class CertificateLogListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class   = CertificateLogSerializer

    def get_queryset(self):
        return (
            CertificateLog.objects
            .filter(report_id=self.kwargs["pk"])
            .order_by("-generated_at")
        )