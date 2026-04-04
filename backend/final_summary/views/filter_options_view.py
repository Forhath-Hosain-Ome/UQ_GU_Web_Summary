import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from final_summary.utils.config import DB_PATH
from final_summary.db.db_manager import DBManager

logger = logging.getLogger(__name__)


class FinalSummaryFilterOptionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
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
