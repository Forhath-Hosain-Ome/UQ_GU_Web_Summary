import logging
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
        qs = (
            InspectionReport.objects
            .select_related("batch")
            .prefetch_related("po_numbers")
            .order_by("-inspection_date", "style")
        )
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
            qs = qs.filter(inspection_date__gte=p["date_from"])
        if p.get("date_to"):
            qs = qs.filter(inspection_date__lte=p["date_to"])
        if p.get("batch"):
            qs = qs.filter(batch_id=p["batch"])

        return qs.distinct()
