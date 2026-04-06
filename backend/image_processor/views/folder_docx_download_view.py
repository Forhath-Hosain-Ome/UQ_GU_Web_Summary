import logging
import os
import zipfile
import tempfile
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
#     FOLDER DOCX DOWNLOAD
#     GET /api/folder/reports/<pk>/docx/
#     Stream a zip file containing all DOCX files for a specific folder report.
# ─────────────────────────────────────────────────────────────────────────────

class FolderDOCXDownloadView(APIView):
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
                {"detail": "No DOCX output available for this report."},
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
                "DOCX directory not found on disk for report #%s: %s",
                pk, full_path,
            )
            return Response(
                {"detail": "DOCX files not found on disk."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Create a temporary zip file containing all DOCX files
        temp_dir = tempfile.mkdtemp()
        zip_filename = f"Defect_Pictures_Style_{report.folder_name}.zip"
        zip_path = os.path.join(temp_dir, zip_filename)

        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Walk through the output directory and add all DOCX files
                for root, dirs, files in os.walk(full_path):
                    for file in files:
                        if file.endswith('.docx'):
                            file_path = os.path.join(root, file)
                            # Add file to zip with just the filename (not full path)
                            arcname = os.path.basename(file)
                            zipf.write(file_path, arcname)

            # Stream the zip file
            response = FileResponse(
                open(zip_path, "rb"),
                content_type="application/zip",
                as_attachment=True,
                filename=zip_filename,
            )

            logger.info(
                "DOCX download | report #%s | batch #%s | user: %s | file: %s",
                report.pk, report.batch_id, request.user.username, zip_filename,
            )

            return response

        except Exception as e:
            logger.error(
                "Error creating zip file for report #%s: %s",
                pk, str(e)
            )
            return Response(
                {"detail": "Error creating download file."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        finally:
            # Clean up temporary zip file
            if os.path.exists(zip_path):
                os.unlink(zip_path)
            if os.path.exists(temp_dir):
                os.rmdir(temp_dir)
