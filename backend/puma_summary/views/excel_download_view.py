import logging

from django.conf import settings
from django.http import FileResponse

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from puma_summary.models import InspectionBatch

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#     EXCEL DOWNLOAD
#     GET /api/batches/<pk>/excel/
#     Streams the Excel report for a batch.
#     File stays on disk so it can be re-downloaded.
# ─────────────────────────────────────────────────────────────────────────────

class ExcelDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            batch = InspectionBatch.objects.get(pk=pk)
        except InspectionBatch.DoesNotExist:
            return Response({"detail": "Batch not found."}, status=status.HTTP_404_NOT_FOUND)

        if not batch.excel_report_path:
            return Response(
                {"detail": "No Excel report has been generated for this batch."},
                status=status.HTTP_404_NOT_FOUND,
            )

        excel_path = settings.BASE_DIR / "media" / batch.excel_report_path
        if not excel_path.exists():
            return Response(
                {"detail": "Excel file not found on disk — it may have been deleted."},
                status=status.HTTP_404_NOT_FOUND,
            )

        logger.info(
            "Excel download: %s (batch #%s) | user: %s",
            excel_path.name, pk, request.user.username,
        )

        return FileResponse(
            open(excel_path, "rb"),
            as_attachment=True,
            filename=excel_path.name,
            content_type=(
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            ),
        )
