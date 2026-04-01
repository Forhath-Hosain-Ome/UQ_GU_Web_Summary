import logging
import os
from pathlib import Path

from django.conf import settings
from django.http import FileResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from puma_summary.models import InspectionReport

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#     RENAMED PDF DOWNLOAD
#     GET /api/reports/<pk>/pdf/
#
#     Serves the renamed PDF for a single InspectionReport.
#     The PDF lives in batch.source_folder under its renamed filename.
#     The renamed filename is re-derived from the report record using the
#     same build_renamed_pdf_name() logic used at processing time — so no
#     extra DB field is needed.
# ─────────────────────────────────────────────────────────────────────────────

class ReportPDFDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from services.file_manager.build_renamed_pdf_name import build_renamed_pdf_name

        try:
            report = (
                InspectionReport.objects
                .select_related("batch")
                .prefetch_related("po_numbers")
                .get(pk=pk)
            )
        except InspectionReport.DoesNotExist:
            return Response({"detail": "Report not found."}, status=status.HTTP_404_NOT_FOUND)

        source_folder = report.batch.source_folder
        if not source_folder:
            return Response(
                {"detail": "Source folder not recorded for this batch."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Reconstruct the renamed filename using the same function used at processing time
        record = {
            "style":          report.style,
            "factory_code":   report.factory_code,
            "final_customer": report.final_customer,
            "po_numbers":     list(report.po_numbers.values_list("number", flat=True)),
        }
        renamed_filename = build_renamed_pdf_name(record)

        # Resolve and validate the path
        pdf_path = os.path.normpath(os.path.join(source_folder, renamed_filename))
        folder_norm = os.path.normpath(source_folder)

        if not pdf_path.startswith(folder_norm):
            logger.warning("Path traversal attempt for report #%s", pk)
            return Response({"detail": "Invalid file path."}, status=status.HTTP_400_BAD_REQUEST)

        if not os.path.exists(pdf_path):
            return Response(
                {"detail": "Renamed PDF not found on disk — it may not have been processed yet."},
                status=status.HTTP_404_NOT_FOUND,
            )

        logger.info(
            "PDF download: %s (report #%s) | user: %s",
            renamed_filename, pk, request.user.username,
        )

        file_handle = open(pdf_path, "rb")
        response = FileResponse(
            file_handle,
            as_attachment=True,
            filename=renamed_filename,
            content_type="application/pdf",
        )
        original_close = response.close
        def close_with_file():
            original_close()
            file_handle.close()
        response.close = close_with_file
        return response