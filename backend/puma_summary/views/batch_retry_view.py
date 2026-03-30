import logging
from django.conf import settings
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from puma_summary.models import InspectionBatch
from puma_summary.serializers import BatchRetrySerializer
from puma_summary.tasks import retry_failed_pdfs

logger = logging.getLogger(__name__)



# ─────────────────────────────────────────────────────────────────────────────
#  4. BATCH RETRY
#     POST /api/batches/<pk>/retry/
#     Re-runs only the failed PDFs (retried=False) from the original batch.
#     Creates a sibling Celery task — does NOT create a new batch row.
# ─────────────────────────────────────────────────────────────────────────────

class BatchRetryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        batch = self._get_batch(pk)
        if isinstance(batch, Response):
            return batch

        serializer = BatchRetrySerializer(
            data=request.data,
            context={"batch": batch},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        unretried_qs  = serializer.validated_data["unretried_qs"]
        failed_names  = list(unretried_qs.values_list("filename", flat=True))

        # Reset batch status so the WS consumer resumes sending updates
        batch.status = InspectionBatch.Status.PENDING
        batch.retry_count += 1
        batch.save(update_fields=["status", "retry_count"])

        task = retry_failed_pdfs.delay(batch.pk, failed_names)
        batch.celery_task_id = task.id
        batch.save(update_fields=["celery_task_id"])

        logger.info(
            "Retry #%s for Batch #%s | %d files | task %s | user: %s",
            batch.retry_count, batch.pk, len(failed_names), task.id, request.user.username,
        )

        return Response(
            {
                "batch_id":      batch.pk,
                "retry_count":   batch.retry_count,
                "files_retrying": failed_names,
                "task_id":       task.id,
                "ws_channel":    f"batch_{batch.pk}",
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @staticmethod
    def _get_batch(pk):
        try:
            return InspectionBatch.objects.prefetch_related("batch_failed_pdfs").get(pk=pk)
        except InspectionBatch.DoesNotExist:
            return Response(
                {"detail": "Batch not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
