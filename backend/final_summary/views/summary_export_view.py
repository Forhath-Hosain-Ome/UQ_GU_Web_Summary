import logging
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.http import FileResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..utils.config import DB_PATH
from ..db.db_manager import DBManager
from ..utils.summary_writer import write_summary

logger = logging.getLogger(__name__)


class FinalSummaryExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        style = request.query_params.get("style", "").strip()
        factory = request.query_params.get("factory", "").strip()
        buyer = request.query_params.get("buyer", "").strip()
        po = request.query_params.get("po", "").strip()
        date_from = request.query_params.get("date_from", "").strip()
        date_to = request.query_params.get("date_to", "").strip()

        try:
            with DBManager(DB_PATH) as db:
                records = db.query_records(
                    factory=factory,
                    client=buyer,
                    style=style,
                    po=po,
                    start_date=date_from,
                    end_date=date_to,
                )

                if not records:
                    return Response(
                        {"detail": "No records found for the requested filters."},
                        status=404,
                    )

                defect_map = db.query_defect_items_for_reports(
                    [r["report_id"] for r in records]
                )
        except Exception as exc:
            logger.exception("Final summary export failed: %s", exc)
            return Response({"detail": "Could not build final summary."}, status=500)

        output_dir = settings.BASE_DIR / "media" / "output" / "final_summary"
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"final_summary_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
        output_path = output_dir / filename

        try:
            write_summary(records, defect_map, output_path)
        except Exception as exc:
            logger.exception("Final summary Excel generation failed: %s", exc)
            return Response({"detail": "Could not generate Excel file."}, status=500)

        response = FileResponse(open(output_path, "rb"), as_attachment=True, filename=filename)
        return response
