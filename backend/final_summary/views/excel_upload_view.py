import logging
import uuid
from pathlib import Path

from django.conf import settings
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from final_summary.tasks.process_excel_upload import process_excel_upload

logger = logging.getLogger(__name__)


class FinalSummaryExcelUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        files = request.FILES.getlist("files")
        if not files:
            return Response(
                {"files": ["At least one Excel file is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        upload_root = (
            settings.BASE_DIR
            / "media"
            / "uploads"
            / "final_summary"
            / uuid.uuid4().hex
        )
        upload_root.mkdir(parents=True, exist_ok=True)

        saved_files = []
        for f in files:
            if not f.name.lower().endswith((".xlsx", ".xls")):
                return Response(
                    {"files": [f"Unsupported file type: {f.name}"]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            dest = upload_root / f.name
            with open(dest, "wb") as out:
                for chunk in f.chunks():
                    out.write(chunk)
            saved_files.append(dest.name)

        task = process_excel_upload.delay(str(upload_root))
        logger.info(
            "Excel upload received: %s files saved to %s, task=%s",
            len(saved_files),
            upload_root,
            task.id,
        )

        return Response(
            {
                "upload_id": upload_root.name,
                "task_id": task.id,
                "message": "Excel upload received and processing started.",
                "files": saved_files,
            },
            status=status.HTTP_201_CREATED,
        )
