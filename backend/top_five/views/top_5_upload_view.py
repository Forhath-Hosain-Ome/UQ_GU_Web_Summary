"""
top5/views.py
--------------

POST /top5/upload/
    Accepts a single .xlsx file.
    Creates Top5Job, fires Celery task, returns { job_id }.
"""
import logging
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from top_five.models import Top5Job
from top_five.tasks import run_top5_job
from top_five.serializers import Top5UploadSerializer

logger = logging.getLogger(__name__)

class Top5UploadView(APIView):
    """
    POST /top5/upload/
    Field: "file"  (.xlsx only)
    
    Authentication: Required (401 if not authenticated)
    """
    permission_classes = [IsAuthenticated]
    parser_classes     = [MultiPartParser, FormParser]

    def post(self, request):
        # Verify user is authenticated
        if not request.user or not request.user.is_authenticated:
            return Response(
                {"detail": "Authentication required. Please log in."},
                status=401
            )

        serializer = Top5UploadSerializer(data=request.FILES)
        
        if not serializer.is_valid():
            return Response({
                "detail": "Upload validation failed",
                "errors": serializer.errors
            }, status=400)

        uploaded = serializer.validated_data["file"]
        file_bytes = uploaded.read()

        try:
            job = Top5Job.objects.create(
                created_by = request.user,
                input_file = uploaded.name,
                status     = Top5Job.Status.PENDING,
            )

            # Pass bytes as hex string — Celery JSON serialiser can't handle raw bytes
            from top_five.tasks import run_top5_job
            task_result = run_top5_job.delay(job.pk, file_bytes.hex(), uploaded.name)

            logger.info(
                "✓ top5 upload created — job_id=%s task_id=%s file=%s user=%s",
                job.pk, task_result.id, uploaded.name, request.user
            )

             # Return plain dict response – avoid serializer misuse that drops fields
            return Response({"job_id": job.pk, "status": job.status}, status=201)
            
        except Exception as exc:
            logger.exception("✗ top5 upload failed: %s", exc)
            return Response({
                "detail": "Upload failed",
                "error": str(exc)
            }, status=500)
