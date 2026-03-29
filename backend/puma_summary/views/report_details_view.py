import logging
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from puma_summary.models import InspectionReport
from puma_summary.serializers import InspectionReportSerializer

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  7. REPORT DETAIL
#     GET /api/reports/<pk>/
#     Full report with PO numbers + certificate history.
# ─────────────────────────────────────────────────────────────────────────────

class ReportDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class   = InspectionReportSerializer

    def get_queryset(self):
        return (
            InspectionReport.objects
            .select_related("batch")
            .prefetch_related("po_numbers", "certificate_logs")
        )
