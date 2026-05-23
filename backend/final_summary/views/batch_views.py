"""
---------------------
GET /api/final-summary/batches/        — paginated list of upload batches
GET /api/final-summary/batches/<pk>/   — full batch with nested reports
"""

import logging

from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from final_summary.models import UploadBatch
from final_summary.serializers import UploadBatchListSerializer

logger = logging.getLogger(__name__)


class AuditBatchListView(generics.ListAPIView):
    """
    GET /api/final-summary/batches/

    Returns a paginated list of upload batches.
    Staff see all batches; regular users see only their own.

    Query params (all optional):
      buyer    : filter by buyer name (partial, case-insensitive)
      factory  : filter by factory name (partial, case-insensitive)
      status   : PENDING | PROCESSING | COMPLETED | PARTIAL | FAILED
    """
    permission_classes = [IsAuthenticated]
    serializer_class   = UploadBatchListSerializer

    def get_queryset(self):
        user = self.request.user
        qs = (
            UploadBatch.objects
            .select_related("pair", "pair__buyer", "pair__factory", "created_by")
            .prefetch_related("reports")
        )

        if not user.is_staff:
            qs = qs.filter(created_by=user)

        buyer   = self.request.query_params.get("buyer", "").strip()
        factory = self.request.query_params.get("factory", "").strip()
        status  = self.request.query_params.get("status", "").strip().upper()

        if buyer:
            qs = qs.filter(pair__buyer__name__icontains=buyer)
        if factory:
            qs = qs.filter(pair__factory__name__icontains=factory)
        if status and status in UploadBatch.Status.values:
            qs = qs.filter(status=status)

        return qs.order_by("-created_at")


class AuditBatchDetailView(generics.RetrieveAPIView):
    """
    GET /api/final-summary/batches/<pk>/

    Returns full batch details including nested report list.
    """
    permission_classes = [IsAuthenticated]
    serializer_class   = UploadBatchListSerializer

    def get_queryset(self):
        user = self.request.user
        qs = (
            UploadBatch.objects
            .select_related("pair", "pair__buyer", "pair__factory", "created_by")
            .prefetch_related("reports")
        )
        if not user.is_staff:
            qs = qs.filter(created_by=user)
        return qs