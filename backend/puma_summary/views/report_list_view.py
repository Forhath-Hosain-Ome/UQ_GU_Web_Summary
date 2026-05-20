import logging
from datetime import datetime
from pathlib import Path
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from puma_summary.models import InspectionReport
from puma_summary.serializers import InspectionReportListSerializer

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#     REPORT LIST
#     GET /api/reports/
#     Searchable by style, factory, customer, po, date_from, date_to.
#     Paginated (50 per page).
# ─────────────────────────────────────────────────────────────────────────────

class ReportListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class   = InspectionReportListSerializer

    def get_queryset(self):
        user = self.request.user
        qs = (
            InspectionReport.objects
            .select_related("batch")
            .prefetch_related("po_numbers")
        )
        if not user.is_staff:
            qs = qs.filter(created_by=user)
        qs = qs.order_by("-inspection_date", "style")
        p = self.request.query_params

        if p.get("style"):
            qs = qs.filter(style__icontains=p["style"])
        if p.get("factory"):
            qs = qs.filter(factory_code__icontains=p["factory"])
        if p.get("customer"):
            qs = qs.filter(final_customer__icontains=p["customer"])
        if p.get("po"):
            qs = qs.filter(po_numbers__number__icontains=p["po"])
        if p.get("date_from"):
            try:
                datetime.strptime(p["date_from"], "%Y-%m-%d")
                qs = qs.filter(inspection_date__gte=p["date_from"])
            except ValueError:
                logger.warning("Invalid date_from format: %s", p["date_from"])
        if p.get("date_to"):
            try:
                datetime.strptime(p["date_to"], "%Y-%m-%d")
                qs = qs.filter(inspection_date__lte=p["date_to"])
            except ValueError:
                logger.warning("Invalid date_to format: %s", p["date_to"])
        if p.get("batch"):
            qs = qs.filter(batch_id=p["batch"])

        return qs.distinct()
