import logging
import os
import tempfile
from pathlib import Path
from django.conf import settings
from django.http import FileResponse, Http404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from image_processor.models import FolderReport
from services.file_manager.converter_docx_to_pdf import convert_docx_to_pdf

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#     FOLDER PDF DOWNLOAD
#     GET /api/folder/reports/<pk>/pdf/
#     Convert DOCX to PDF on-demand and stream for download.
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

        docx_path = os.path.normpath(
            settings.MEDIA_ROOT / report.pdf_output_path
        )
        media_root = os.path.normpath(str(settings.MEDIA_ROOT))

        if not docx_path.startswith(media_root):
            logger.warning(
                "Path traversal attempt detected for report #%s: %s",
                pk, report.pdf_output_path,
            )
            return Response(
                {"detail": "Invalid file path."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not os.path.exists(docx_path):
            logger.error(
                "DOCX file not found on disk for report #%s: %s",
                pk, docx_path,
            )
            return Response(
                {"detail": "DOCX file not found on disk."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Create temp file for PDF conversion
        temp_dir = tempfile.mkdtemp()
        pdf_filename = os.path.splitext(os.path.basename(docx_path))[0] + ".pdf"
        pdf_path = os.path.join(temp_dir, pdf_filename)

        try:
            convert_docx_to_pdf(docx_path, pdf_path)

            if not os.path.exists(pdf_path):
                return Response(
                    {"detail": "PDF conversion failed."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            response = FileResponse(
                open(pdf_path, "rb"),
                content_type="application/pdf",
                as_attachment=True,
                filename=pdf_filename,
            )

            logger.info(
                "PDF download | report #%s | batch #%s | user: %s | file: %s",
                report.pk, report.batch_id, request.user.username, pdf_filename,
            )

            return response

        except Exception as e:
            logger.error(
                "Error converting PDF for report #%s: %s",
                pk, str(e)
            )
            return Response(
                {"detail": "Error converting to PDF."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        finally:
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)
            if os.path.exists(temp_dir):
                os.rmdir(temp_dir)
