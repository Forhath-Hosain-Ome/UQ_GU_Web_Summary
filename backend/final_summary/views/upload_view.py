import logging
import tempfile
import os
from pathlib import Path

from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from final_summary.models import UploadBatch
from final_summary.tasks import process_audit_upload
from final_summary.serializers import UploadBatchListSerializer

logger = logging.getLogger(__name__)

VALID_EXTENSIONS = {".xlsx", ".xls"}
MAX_FILE_SIZE    = 50 * 1024 * 1024   # 50 MB


class AuditUploadView(APIView):
    """
    POST /api/final-summary/upload/

    Accepts one or many Excel files, saves them to a temp directory,
    creates an UploadBatch, fires the Celery extraction task.

    Returns the new batch_id + WS channel name so the frontend
    can subscribe for live progress.
    """
    permission_classes = [IsAuthenticated]
    parser_classes     = [MultiPartParser, FormParser]

    def post(self, request):
        files = request.FILES.getlist("files")
        if not files:
            return Response(
                {"files": ["At least one Excel file is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        errors = []
        for f in files:
            ext = Path(f.name).suffix.lower()
            if ext not in VALID_EXTENSIONS:
                errors.append(f"{f.name}: only .xlsx and .xls files are accepted.")
            if f.size > MAX_FILE_SIZE:
                errors.append(f"{f.name}: exceeds the 50 MB limit.")

        if errors:
            return Response({"files": errors}, status=status.HTTP_400_BAD_REQUEST)

        # Get format selection (default to SPI if not provided)
        fmt = request.data.get("format_type", "SPI").upper()
        valid_formats = dict(UploadBatch.FORMAT_CHOICES).keys()
        if fmt not in valid_formats:
            fmt = "SPI"

        # Ensure shared temp directory exists (mounted volume for celery workers)
        SHARED_TEMP_DIR = '/tmp/batch_uploads'
        os.makedirs(SHARED_TEMP_DIR, exist_ok=True)
        temp_dir = tempfile.mkdtemp(dir=SHARED_TEMP_DIR)

        try:
            saved_names = []
            for f in files:
                dest = os.path.join(temp_dir, f.name)
                # Handle duplicate filenames
                counter = 1
                base, ext = os.path.splitext(dest)
                while os.path.exists(dest):
                    dest = f"{base}_{counter}{ext}"
                    counter += 1

                with open(dest, "wb") as out:
                    for chunk in f.chunks():
                        out.write(chunk)
                saved_names.append(os.path.basename(dest))

            batch = UploadBatch.objects.create(
                created_by    = request.user,
                total_files   = len(files),
                status        = UploadBatch.Status.PENDING,
                format_type   = fmt,
            )

            task = process_audit_upload.delay(batch.pk, temp_dir, fmt)

            batch.celery_task_id = task.id
            batch.save(update_fields=["celery_task_id"])

            logger.info(
                "Audit upload | batch #%s | %d files | task %s | user: %s",
                batch.pk, len(files), task.id, request.user.username,
            )

            return Response(
                {
                    "batch_id":    batch.pk,
                    "total_files": len(files),
                    "files":       saved_names,
                    "ws_channel":  f"audit_batch_{batch.pk}",
                    "message":     f"{len(files)} file(s) uploaded. Processing started.",
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as exc:
            logger.exception("Audit upload error: %s", exc)
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            return Response(
                {"error": f"Upload failed: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )