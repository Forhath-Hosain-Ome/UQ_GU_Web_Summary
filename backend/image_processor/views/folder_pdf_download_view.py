import logging
import os
from pathlib import Path
from django.conf import settings
from django.http import FileResponse, Http404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from image_processor.models import FolderReport

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#     FOLDER PDF DOWNLOAD
#     GET /api/folder/reports/<pk>/pdf/
#     Stream the generated PDF for a specific folder report.
# ─────────────────────────────────────────────────────────────────────────────

class FolderPDFDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            report = (
                FolderReport.objects
                .select_related("batch", "batch__created_by")
                .get(pk=pk, batch__created_by=request.user)
            )
        except FolderReport.DoesNotExist:
            raise Http404("Report not found.")

        if not report.pdf_output_path:
            return Response(
                {"detail": "No PDF output available for this report."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Normalize path to prevent path traversal
        full_path = os.path.normpath(
            settings.BASE_DIR / "media" / report.pdf_output_path
        )
        media_root = os.path.normpath(str(settings.BASE_DIR / "media"))

        # Ensure the path is within MEDIA_ROOT
        if not full_path.startswith(media_root):
            logger.warning(
                "Path traversal attempt detected for report #%s: %s",
                pk, report.pdf_output_path,
            )
            return Response(
                {"detail": "Invalid file path."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not os.path.exists(full_path):
            logger.error(
                "PDF file not found on disk for report #%s: %s",
                pk, full_path,
            )
            return Response(
                {"detail": "PDF file not found on disk."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Stream the file
        filename = os.path.basename(full_path)
        response = FileResponse(
            open(full_path, "rb"),
            content_type="application/pdf",
            as_attachment=True,
            filename=filename,
        )

        logger.info(
            "PDF download | report #%s | batch #%s | user: %s | file: %s",
            report.pk, report.batch_id, request.user.username, filename,
        )

        return response
