import logging
import os
from pathlib import Path
from django.conf import settings
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from puma_summary.models import InspectionBatch
from puma_summary.serializers import InspectionBatchSerializer

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _excel_exists(batch: InspectionBatch) -> bool:
    if not batch.excel_report_path:
        return False
    # Normalize path to prevent path traversal
    full = os.path.normpath(settings.BASE_DIR / "media" / batch.excel_report_path)
    media_root = os.path.normpath(str(settings.BASE_DIR / "media"))
    # Ensure the path is within MEDIA_ROOT
    if not full.startswith(media_root):
        logger.warning("Path traversal attempt detected: %s", batch.excel_report_path)
        return False
    return os.path.exists(full)



# ─────────────────────────────────────────────────────────────────────────────
#     BATCH DETAIL
#     GET /api/batches/<pk>/
#     Full batch with nested reports + failed PDFs.
# ─────────────────────────────────────────────────────────────────────────────

class BatchDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class   = InspectionBatchSerializer

    def get_queryset(self):
        return (
            InspectionBatch.objects
            .prefetch_related("reports__po_numbers", "batch_failed_pdfs")
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data
        # Append live Excel availability flag (not stored in DB)
        data["excel_available"] = _excel_exists(instance)
        return Response(data)
