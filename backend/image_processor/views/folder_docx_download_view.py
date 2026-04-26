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
#     Stream a zip file containing the DOCX file for a specific folder report.
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_docx_path(stored_path: str) -> Path | None:
    """
    Resolve the stored pdf_output_path to an absolute path on disk.

    Handles these cases:
      1. Absolute path already:   /app/media/output/defect_image/59/.../file.docx
      2. Relative to MEDIA_ROOT:  output/defect_image/59/.../file.docx
      3. Relative to BASE_DIR:    media/output/defect_image/59/.../file.docx

    Returns the resolved Path if it exists on disk, else None.
    """
    media_root = Path(settings.MEDIA_ROOT)   # /app/media
    base_dir   = Path(settings.BASE_DIR)     # /app

    candidates = [
        Path(stored_path),                    # absolute or as-is
        media_root / stored_path,             # relative to /app/media
        base_dir   / stored_path,             # relative to /app
    ]

    for path in candidates:
        resolved = path.resolve()
        if resolved.exists():
            # Security: must still be inside MEDIA_ROOT
            try:
                resolved.relative_to(media_root.resolve())
                return resolved
            except ValueError:
                logger.warning("Path outside MEDIA_ROOT rejected: %s", resolved)
                continue

    return None


class FolderDOCXDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        # ── Fetch report (ownership check) ────────────────────────────────────
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

        # ── Resolve file path ─────────────────────────────────────────────────
        full_path = _resolve_docx_path(report.pdf_output_path)

        if full_path is None:
            logger.error(
                "DOCX file not found on disk for report #%s. "
                "Stored path: %s  |  MEDIA_ROOT: %s",
                pk, report.pdf_output_path, settings.MEDIA_ROOT,
            )
            return Response(
                {
                    "detail": "DOCX file not found on disk.",
                    "stored_path": report.pdf_output_path,   # helpful for debugging
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # ── Build zip and stream ──────────────────────────────────────────────
        zip_filename = f"Defect_Pictures_Style_{report.folder_name}.zip"
        temp_dir  = tempfile.mkdtemp()
        zip_path  = os.path.join(temp_dir, zip_filename)

        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(str(full_path), full_path.name)

            response = FileResponse(
                open(zip_path, "rb"),
                content_type="application/zip",
                as_attachment=True,
            )
            response["Content-Disposition"] = (
                f'attachment; filename="{zip_filename}"'
            )

            logger.info(
                "DOCX download | report #%s | batch #%s | user: %s | file: %s",
                report.pk, report.batch_id, request.user.username, full_path.name,
            )

            return response

        except Exception as exc:
            logger.error(
                "Error creating zip for report #%s: %s", pk, exc
            )
            return Response(
                {"detail": "Error creating download file."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        finally:
            # Clean up temp files regardless of success/failure
            try:
                if os.path.exists(zip_path):
                    os.unlink(zip_path)
                if os.path.exists(temp_dir):
                    os.rmdir(temp_dir)
            except Exception:
                pass
