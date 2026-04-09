import logging
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from final_summary.models import UploadBatch
from final_summary.serializers import UploadBatchListSerializer, UploadBatchDetailSerializer

logger = logging.getLogger(__name__)


class AuditBatchListView(generics.ListAPIView):
    """GET /api/final-summary/batches/ — paginated list of upload batches."""
    permission_classes = [IsAuthenticated]
    serializer_class   = UploadBatchListSerializer

    def get_queryset(self):
        return (
            UploadBatch.objects
            .filter(created_by=self.request.user)
            .prefetch_related("reports")
            .order_by("-created_at")
        )


class AuditBatchDetailView(generics.RetrieveAPIView):
    """GET /api/final-summary/batches/<pk>/ — full batch with nested reports."""
    permission_classes = [IsAuthenticated]
    serializer_class   = UploadBatchDetailSerializer

    def get_queryset(self):
        return (
            UploadBatch.objects
            .filter(created_by=self.request.user)
            .prefetch_related("reports")
        )