# backend/image_processor/views/folder_pdf_download_view.py
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
#  Helper — resolve stored docx path to an absolute on-disk path
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_docx_path(stored_path: str) -> Path | None:
    """
    Accepts an absolute path OR a path relative to BASE_DIR/media.
    Returns the resolved Path if it exists inside MEDIA_ROOT, else None.
    """
    media_root = Path(settings.MEDIA_ROOT).resolve()
    base_dir   = Path(settings.BASE_DIR).resolve()

    candidates = [
        Path(stored_path),
        base_dir / "media" / stored_path,
        base_dir / stored_path,
    ]

    for candidate in candidates:
        resolved = candidate.resolve()
        if not resolved.exists():
            continue
        try:
            resolved.relative_to(media_root)   # security: must be inside MEDIA_ROOT
            return resolved
        except ValueError:
            logger.warning("Path outside MEDIA_ROOT rejected: %s", resolved)

    return None


# ─────────────────────────────────────────────────────────────────────────────
#  Streaming wrapper that deletes the temp file after the client receives it
# ─────────────────────────────────────────────────────────────────────────────

class _TempFileWrapper:
    """
    Wraps an open file handle.  When the WSGI/ASGI server closes the response
    (calls close()) the temp PDF and its parent directory are deleted.
    """

    def __init__(self, file_handle, pdf_path: str, temp_dir: str):
        self._fh       = file_handle
        self._pdf_path = pdf_path
        self._temp_dir = temp_dir

    # Delegate all file-like methods to the real handle
    def read(self, size=-1):
        return self._fh.read(size)

    def __iter__(self):
        return iter(self._fh)

    def close(self):
        try:
            self._fh.close()
        finally:
            self._cleanup()

    def _cleanup(self):
        for path in (self._pdf_path, self._temp_dir):
            try:
                if os.path.isfile(path):
                    os.unlink(path)
                elif os.path.isdir(path):
                    os.rmdir(path)
            except Exception as exc:
                logger.warning("Temp cleanup failed for %s: %s", path, exc)


# ─────────────────────────────────────────────────────────────────────────────
#     FOLDER PDF DOWNLOAD
#     GET /api/folder/reports/<pk>/pdf/
#     Converts DOCX → PDF on demand, streams it, then deletes the temp PDF.
#     The DOCX output file is NOT deleted (only the converted temp PDF is).
# ─────────────────────────────────────────────────────────────────────────────

class FolderPDFDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        # ── Fetch report (ownership check) ────────────────────────────────
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
                {"detail": "No output available for this report."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ── Resolve DOCX path ─────────────────────────────────────────────
        docx_path = _resolve_docx_path(report.pdf_output_path)

        if docx_path is None:
            logger.error(
                "DOCX not found on disk for report #%s — stored path: %s",
                pk, report.pdf_output_path,
            )
            return Response(
                {"detail": "Source DOCX file not found on disk."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ── Convert DOCX → PDF into a temp dir ───────────────────────────
        temp_dir     = tempfile.mkdtemp()
        pdf_filename = docx_path.stem + ".pdf"
        pdf_path     = os.path.join(temp_dir, pdf_filename)

        try:
            convert_docx_to_pdf(str(docx_path), pdf_path)
        except Exception as exc:
            logger.error("PDF conversion failed for report #%s: %s", pk, exc)
            # Clean up immediately — nothing to stream
            try:
                if os.path.exists(pdf_path):
                    os.unlink(pdf_path)
                os.rmdir(temp_dir)
            except Exception:
                pass
            return Response(
                {"detail": "PDF conversion failed."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if not os.path.exists(pdf_path):
            os.rmdir(temp_dir)
            return Response(
                {"detail": "PDF conversion produced no output."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # ── Stream PDF; temp file deleted after client receives it ────────
        wrapped = _TempFileWrapper(
            file_handle = open(pdf_path, "rb"),
            pdf_path    = pdf_path,
            temp_dir    = temp_dir,
        )

        response = FileResponse(
            wrapped,
            content_type  = "application/pdf",
            as_attachment = True,
            filename      = pdf_filename,
        )

        logger.info(
            "PDF download | report #%s | batch #%s | user: %s | file: %s",
            report.pk, report.batch_id, request.user.username, pdf_filename,
        )

        return response