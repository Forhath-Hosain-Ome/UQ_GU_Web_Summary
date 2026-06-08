import logging
import os
from pathlib import Path
from django.conf import settings
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from image_processor.models import FolderBatch
from image_processor.serializers import FolderBatchSerializer

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _pdf_exists(report) -> bool:
    """Check if the PDF output file exists on disk."""
    if not report.pdf_output_path:
        return False
    # Normalize path to prevent path traversal
    full = os.path.normpath(settings.MEDIA_ROOT / report.pdf_output_path)
    media_root = os.path.normpath(str(settings.MEDIA_ROOT))
    # Ensure the path is within MEDIA_ROOT
    if not full.startswith(media_root):
        logger.warning("Path traversal attempt detected: %s", report.pdf_output_path)
        return False
    return os.path.exists(full)


# ─────────────────────────────────────────────────────────────────────────────
#     FOLDER BATCH DETAIL
#     GET /api/folder/batches/<pk>/
#     Full batch with nested reports + failed folders.
# ─────────────────────────────────────────────────────────────────────────────

class FolderBatchDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class   = FolderBatchSerializer

    def get_queryset(self):
        return (
            FolderBatch.objects
            .prefetch_related("reports", "batch_failed_folders")
            .filter(created_by=self.request.user)
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data
        # Append live PDF availability flags for each report (not stored in DB)
        for report_data in data.get("reports", []):
            report_id = report_data.get("id")
            if report_id:
                try:
                    report = instance.reports.get(pk=report_id)
                    report_data["pdf_available"] = _pdf_exists(report)
                except Exception:
                    report_data["pdf_available"] = False
        return Response(data)
