import logging
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from image_processor.models import FolderReport
from image_processor.serializers import FolderReportListSerializer

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#     FOLDER REPORT LIST
#     GET /api/folder/reports/
#     Paginated list of all folder reports for the authenticated user.
# ─────────────────────────────────────────────────────────────────────────────

class FolderReportListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class   = FolderReportListSerializer

    def get_queryset(self):
        return (
            FolderReport.objects
            .filter(batch__created_by=self.request.user)
            .select_related("batch", "batch__created_by")
        )
