"""
------------------------------
GET /api/final-summary/options/

Returns distinct dimension values for the export form dropdowns,
scoped to the requesting user's batches (staff see everything).
"""

import logging

from django.db.models import Min, Max
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from final_summary.models import AuditReport

logger = logging.getLogger(__name__)


class AuditFilterOptionsView(APIView):
    """
    GET /api/final-summary/options/

    Response shape:
    {
      "factories":  [...],
      "clients":    [...],
      "styles":     [...],
      "po_numbers": [...],
      "min_date":   "YYYY-MM-DD" | null,
      "max_date":   "YYYY-MM-DD" | null
    }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            qs = AuditReport.objects.all()
            if not request.user.is_staff:
                qs = qs.filter(batch__created_by=request.user)

            factories  = sorted(
                qs.exclude(factory="")
                .values_list("factory", flat=True)
                .distinct()
            )
            clients    = sorted(
                qs.exclude(client="")
                .values_list("client", flat=True)
                .distinct()
            )
            styles     = sorted(
                qs.exclude(style_no="")
                .values_list("style_no", flat=True)
                .distinct()
            )
            po_numbers = sorted(
                qs.exclude(po_no="")
                .values_list("po_no", flat=True)
                .distinct()
            )

            date_range = qs.filter(
                date_of_issue__isnull=False
            ).aggregate(
                min_date=Min("date_of_issue"),
                max_date=Max("date_of_issue"),
            )

            return Response({
                "factories":  list(factories),
                "clients":    list(clients),
                "styles":     list(styles),
                "po_numbers": list(po_numbers),
                "min_date":   date_range["min_date"],
                "max_date":   date_range["max_date"],
            })

        except Exception as exc:
            logger.exception("Filter options error: %s", exc)
            return Response(
                {"detail": "Could not load filter options."},
                status=500,
            )
