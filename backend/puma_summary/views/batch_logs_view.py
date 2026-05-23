import logging
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from puma_summary.models import InspectionBatch
from puma_summary.serializers import BatchFailedPDFSerializer

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  5. BATCH LOGS
#     GET /api/batches/<pk>/logs/
#     Returns structured list of {filename, reason, retried} for every
#     failed PDF in the batch. Also includes the raw error_log dump.
# ─────────────────────────────────────────────────────────────────────────────

class BatchLogsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        user = request.user
        try:
            qs = InspectionBatch.objects.prefetch_related("batch_failed_pdfs")
            if not user.is_staff:
                qs = qs.filter(created_by=user)
            batch = qs.get(pk=pk)
        except InspectionBatch.DoesNotExist:
            return Response({"detail": "Batch not found."}, status=status.HTTP_404_NOT_FOUND)

        failed_pdfs = batch.batch_failed_pdfs.all()
        return Response(
            {
                "batch_id":    batch.pk,
                "status":      batch.status,
                "retry_count": batch.retry_count,
                "error_log":   batch.error_log,   # raw dump kept for debugging
                "failed_pdfs": BatchFailedPDFSerializer(failed_pdfs, many=True).data,
                "total_failed": failed_pdfs.count(),
                "unretried":   failed_pdfs.filter(retried=False).count(),
            }
        )
