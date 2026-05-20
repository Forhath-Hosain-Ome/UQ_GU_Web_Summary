"""
---------------------
POST /api/final-summary/upload/

User must select:
  - pair_id        : BuyerFactoryPair.pk
  - inspection_date: YYYY-MM-DD
  - files          : one or more .xlsx / .xls files

The pair drives:
  - Which extractor class is used (via FORMAT_REGISTRY)
  - Which Excel template is used at export time
  - Which inspection types are permitted (pair.available_reports)

date_of_issue is NEVER extracted from the Excel files.
It is set to inspection_date on every AuditReport in this batch.
"""

import logging
import os
import tempfile
from datetime import date
from pathlib import Path

from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from final_summary.models import BuyerFactoryPair, UploadBatch
from final_summary.tasks import process_audit_upload
from final_summary.serializers import UploadBatchListSerializer

logger = logging.getLogger(__name__)

VALID_EXTENSIONS = {".xlsx", ".xls"}
MAX_FILE_SIZE    = 50 * 1024 * 1024   # 50 MB


class AuditUploadView(APIView):
    """
    POST /api/final-summary/upload/

    Multipart form fields:
      pair_id         (required) BuyerFactoryPair pk
      inspection_date (required) YYYY-MM-DD
      files           (required) one or more Excel files
    """
    permission_classes = [IsAuthenticated]
    parser_classes     = [MultiPartParser, FormParser]

    def post(self, request):

        # ── 1. Validate pair ──────────────────────────────────────────────
        pair_id = request.data.get("pair_id")
        if not pair_id:
            return Response(
                {"pair_id": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            pair = BuyerFactoryPair.objects.select_related(
                "buyer", "factory"
            ).get(pk=pair_id, is_active=True)
        except BuyerFactoryPair.DoesNotExist:
            return Response(
                {"pair_id": [f"No active buyer–factory pair found with id={pair_id}."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── 2. Validate inspection_date ───────────────────────────────────
        raw_date = request.data.get("inspection_date", "").strip()
        if not raw_date:
            return Response(
                {"inspection_date": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        inspection_date = parse_date(raw_date)
        if not inspection_date:
            return Response(
                {"inspection_date": ["Must be a valid date in YYYY-MM-DD format."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── 3. Validate files ─────────────────────────────────────────────
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

        # ── 4. Save files to shared temp dir ──────────────────────────────
        SHARED_TEMP = "/tmp/batch_uploads"
        os.makedirs(SHARED_TEMP, exist_ok=True)
        temp_dir = tempfile.mkdtemp(dir=SHARED_TEMP)

        try:
            saved_names = []
            for f in files:
                dest = os.path.join(temp_dir, f.name)
                # Handle duplicate filenames
                base, ext = os.path.splitext(dest)
                counter   = 1
                while os.path.exists(dest):
                    dest = f"{base}_{counter}{ext}"
                    counter += 1

                with open(dest, "wb") as out:
                    for chunk in f.chunks():
                        out.write(chunk)
                saved_names.append(os.path.basename(dest))

            # ── 5. Create batch ───────────────────────────────────────────
            batch = UploadBatch.objects.create(
                created_by      = request.user,
                pair            = pair,
                inspection_date = inspection_date,
                total_files     = len(files),
                status          = UploadBatch.Status.PENDING,
            )

            # ── 6. Fire Celery task ───────────────────────────────────────
            task = process_audit_upload.delay(batch.pk, temp_dir)

            batch.celery_task_id = task.id
            batch.save(update_fields=["celery_task_id"])

            logger.info(
                "Upload | batch #%s | pair=%s | date=%s | %d file(s) | task=%s | user=%s",
                batch.pk, pair, inspection_date,
                len(files), task.id, request.user.username,
            )

            return Response(
                {
                    "batch_id":       batch.pk,
                    "pair":           str(pair),
                    "buyer":          pair.buyer.name,
                    "factory":        pair.factory.name,
                    "report_type":    pair.report_type,
                    "inspection_date": str(inspection_date),
                    "total_files":    len(files),
                    "files":          saved_names,
                    "ws_channel":     f"audit_batch_{batch.pk}",
                    "message":        f"{len(files)} file(s) uploaded. Processing started.",
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as exc:
            logger.exception("Upload error: %s", exc)
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            return Response(
                {"error": f"Upload failed: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )