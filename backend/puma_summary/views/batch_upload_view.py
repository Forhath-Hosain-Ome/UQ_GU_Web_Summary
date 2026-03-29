import logging
from django.conf import settings

from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from puma_summary.models import InspectionBatch

from puma_summary.serializers import BatchUploadSerializer

from puma_summary.tasks import process_inspection_batch, retry_failed_pdfs

logger = logging.getLogger(__name__)




# ─────────────────────────────────────────────────────────────────────────────
#     BATCH UPLOAD
#     POST /api/batches/upload/
#     Accepts multipart/form-data with key "files" (one or many PDFs).
#     Saves files to a temp folder on disk, creates an InspectionBatch row,
#     fires the Celery task, returns the new batch id + WS channel name.
# ─────────────────────────────────────────────────────────────────────────────

class BatchUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes     = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = BatchUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        files = serializer.validated_data["files"]

        # Save uploaded PDFs to a dedicated temp folder that survives the request.
        # The Celery task reads from this folder; the retry task may also need it.
        puma      = settings.PUMA_SETTINGS
        upload_root = puma.get("UPLOAD_DIR", settings.BASE_DIR / "media" / "uploads")
        upload_root.mkdir(parents=True, exist_ok=True)

        # Each batch gets its own sub-folder named after the DB pk (created after save)
        batch = InspectionBatch.objects.create(
            status=InspectionBatch.Status.PENDING,
        )

        batch_folder = upload_root / str(batch.pk)
        batch_folder.mkdir(parents=True, exist_ok=True)

        for f in files:
            dest = batch_folder / f.name
            with open(dest, "wb") as out:
                for chunk in f.chunks():
                    out.write(chunk)

        # Persist folder path so the retry task can find individual files later
        batch.source_folder = str(batch_folder)
        batch.save(update_fields=["source_folder"])

        task = process_inspection_batch.delay(batch.pk)
        batch.celery_task_id = task.id
        batch.save(update_fields=["celery_task_id"])

        logger.info(
            "Batch #%s created | %d PDFs | task %s | user: %s",
            batch.pk, len(files), task.id, request.user.username,
        )

        return Response(
            {
                "batch_id":   batch.pk,
                "total_pdfs": len(files),
                "status":     batch.status,
                # React uses this to open the correct WS room
                "ws_channel": f"batch_{batch.pk}",
            },
            status=status.HTTP_201_CREATED,
        )
