import logging
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from image_processor.models import FolderBatch, FolderFailedPDF
from image_processor.serializers import FolderFailedPDFSerializer

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#     FOLDER BATCH LOGS
#     GET /api/folder/batches/<pk>/logs/
#     Structured {folder_name, reason} log for failed folders.
# ─────────────────────────────────────────────────────────────────────────────

class FolderBatchLogsView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class   = FolderFailedPDFSerializer

    def get_queryset(self):
        batch_pk = self.kwargs["pk"]
        return (
            FolderFailedPDF.objects
            .filter(batch_id=batch_pk, batch__created_by=self.request.user)
            .select_related("batch")
        )
