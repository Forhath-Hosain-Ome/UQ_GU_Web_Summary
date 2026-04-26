import logging
import os
from pathlib import Path

from django.conf import settings
from django.http import FileResponse

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from puma_summary.models import InspectionBatch

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#     EXCEL DOWNLOAD
#     GET /api/batches/<pk>/excel/
#     Streams the Excel report for a batch.
#     File stays on disk so it can be re-downloaded.
# ─────────────────────────────────────────────────────────────────────────────

class ExcelDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        user = request.user
        try:
            qs = InspectionBatch.objects.all()
            if not user.is_staff:
                qs = qs.filter(created_by=user)
            batch = qs.get(pk=pk)
        except InspectionBatch.DoesNotExist:
            return Response({"detail": "Batch not found."}, status=status.HTTP_404_NOT_FOUND)

        if not batch.excel_report_path:
            return Response(
                {"detail": "No Excel report has been generated for this batch."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Normalize path to prevent path traversal
        excel_path = os.path.normpath(settings.BASE_DIR / "media" / batch.excel_report_path)
        media_root = os.path.normpath(str(settings.BASE_DIR / "media"))
        # Ensure the path is within MEDIA_ROOT
        if not excel_path.startswith(media_root):
            logger.warning("Path traversal attempt detected: %s", batch.excel_report_path)
            return Response(
                {"detail": "Invalid file path."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not os.path.exists(excel_path):
            return Response(
                {"detail": "Excel file not found on disk — it may have been deleted."},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        # Convert back to Path object for FileResponse
        excel_path = Path(excel_path)

        logger.info(
            "Excel download: %s (batch #%s) | user: %s",
            excel_path.name, pk, request.user.username,
        )

        # Use context manager to ensure file is properly closed
        file_handle = open(excel_path, "rb")
        response = FileResponse(
            file_handle,
            as_attachment=True,
            filename=excel_path.name,
            content_type=(
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            ),
        )
        # Ensure file handle is closed when response is closed
        original_close = response.close
        def close_with_file():
            original_close()
            file_handle.close()
        response.close = close_with_file
        return response
