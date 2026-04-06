import logging
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from image_processor.models import FolderReport
from image_processor.serializers import FolderReportSerializer

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#     FOLDER REPORT DETAIL
#     GET /api/folder/reports/<pk>/
#     Full folder report detail.
# ─────────────────────────────────────────────────────────────────────────────

class FolderReportDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class   = FolderReportSerializer

    def get_queryset(self):
        return (
            FolderReport.objects
            .filter(batch__created_by=self.request.user)
            .select_related("batch", "batch__created_by")
        )
