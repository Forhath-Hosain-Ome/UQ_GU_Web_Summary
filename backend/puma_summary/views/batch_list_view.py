import logging
from django.conf import settings
from rest_framework import filters, generics
from rest_framework.permissions import IsAuthenticated
from puma_summary.models import InspectionBatch
from puma_summary.serializers import InspectionBatchListSerializer

logger = logging.getLogger(__name__)




# ─────────────────────────────────────────────────────────────────────────────
#     BATCH LIST
#     GET /api/batches/
#     Supports ?factory= and ?status= query params.
#     Paginated (20 per page via DEFAULT_PAGINATION_CLASS in settings).
# ─────────────────────────────────────────────────────────────────────────────

class BatchListView(generics.ListAPIView):
    permission_classes    = [IsAuthenticated]
    serializer_class      = InspectionBatchListSerializer
    filter_backends       = [filters.OrderingFilter]
    ordering_fields       = ["created_at", "factory_code", "status"]
    ordering              = ["-created_at"]

    def get_queryset(self):
        user = self.request.user
        qs = InspectionBatch.objects.prefetch_related("reports", "batch_failed_pdfs")
        if not user.is_staff:
            qs = qs.filter(created_by=user)
        factory = self.request.query_params.get("factory", "").strip()
        if factory:
            qs = qs.filter(factory_code__icontains=factory)

        batch_status = self.request.query_params.get("status", "").strip().upper()
        if batch_status and batch_status in InspectionBatch.Status.values:
            qs = qs.filter(status=batch_status)

        return qs
