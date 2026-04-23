import logging
<<<<<<< HEAD

=======
from django.db.models import Min, Max
>>>>>>> feature/final-summary
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

<<<<<<< HEAD
from final_summary.utils.config import DB_PATH
from final_summary.db.db_manager import DBManager
=======
from final_summary.models import AuditReport
>>>>>>> feature/final-summary

logger = logging.getLogger(__name__)


<<<<<<< HEAD
class FinalSummaryFilterOptionsView(APIView):
=======
class AuditFilterOptionsView(APIView):
    """
    GET /api/audit/options/

    Returns all distinct dimension values that exist in the DB, scoped to
    the current user's batches (staff see everything).

    Response shape:
      {
        "factories":  [...],
        "clients":    [...],
        "min_date":   "YYYY-MM-DD" | null,
        "max_date":   "YYYY-MM-DD" | null,
        "styles":     [...],
        "po_numbers": [...]
      }
    """
>>>>>>> feature/final-summary
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
<<<<<<< HEAD
            with DBManager(DB_PATH) as db:
                factories = db.get_all_factories()
                buyers = db.get_all_clients()
                min_date, max_date = db.get_date_range()
        except Exception as exc:
            logger.exception("Could not load final summary filter options: %s", exc)
            return Response({"detail": "Could not load filter options."}, status=500)

        return Response(
            {
                "factories": factories,
                "buyers": buyers,
                "min_date": min_date,
                "max_date": max_date,
            }
        )
=======
            qs = AuditReport.objects.all()
            if not request.user.is_staff:
                qs = qs.filter(batch__created_by=request.user)

            factories  = sorted(
                qs.exclude(factory="").values_list("factory",  flat=True).distinct()
            )
            clients    = sorted(
                qs.exclude(client="").values_list("client",    flat=True).distinct()
            )
            styles     = sorted(
                qs.exclude(style_no="").values_list("style_no", flat=True).distinct()
            )
            po_numbers = sorted(
                qs.exclude(po_no="").values_list("po_no",      flat=True).distinct()
            )

            date_range = qs.filter(date_of_issue__isnull=False).aggregate(
                min_date=Min("date_of_issue"),
                max_date=Max("date_of_issue"),
            )

            return Response({
                "factories":  factories,
                "clients":    clients,
                "min_date":   date_range["min_date"],
                "max_date":   date_range["max_date"],
                "styles":     styles,
                "po_numbers": po_numbers,
            })

        except Exception as exc:
            logger.exception("Filter options error: %s", exc)
            return Response({"detail": "Could not load filter options."}, status=500)
>>>>>>> feature/final-summary
