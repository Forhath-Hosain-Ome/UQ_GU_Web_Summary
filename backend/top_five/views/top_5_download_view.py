"""
top5/views.py
--------------
GET  /top5/jobs/<pk>/download/
    Streams the result Excel file from cache.
    Returns 404 if result has expired (>5 min) or job not done.
"""
import logging
from pathlib import Path

from django.core.cache import cache
from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from top5.models import Top5Job

logger = logging.getLogger(__name__)

class Top5DownloadView(APIView):
    """
    GET /top5/jobs/<pk>/download/
    
    Streams the result Excel file from cache.
    Cache is valid for 5 minutes after job completion.
    
    Authentication: Required (401 if not authenticated)
    Permission: User can only download their own jobs (unless staff)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        # Verify user is authenticated
        if not request.user or not request.user.is_authenticated:
            return Response(
                {"detail": "Authentication required."},
                status=401
            )

        try:
            qs = Top5Job.objects.all()
            # Non-staff users can only download their own jobs
            if not request.user.is_staff:
                qs = qs.filter(created_by=request.user)
            job = qs.get(pk=pk)
        except Top5Job.DoesNotExist:
            return Response({
                "detail": f"Job #{pk} not found or access denied."
            }, status=404)

        # Job must be in DONE status
        if job.status != Top5Job.Status.DONE:
            return Response({
                "detail": f"Job is not ready for download.",
                "current_status": job.status,
                "message": "Please wait for the job to complete."
            }, status=400)

        # Retrieve result from cache (5 minute TTL)
        cache_key = f"top5_result_{pk}"
        result_bytes = cache.get(cache_key)

        if not result_bytes:
            return Response({
                "detail": "Result file has expired (cache TTL exceeded).",
                "message": "Please re-upload and process the file again.",
                "job_id": pk
            }, status=404)

        # Generate output filename
        stem = Path(job.input_file).stem
        filename = f"Audit_Result_{stem}.xlsx"

        # Stream file response
        response = HttpResponse(
            content=result_bytes,
            content_type=(
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        
        logger.info("✓ top5 download — job_id=%s file=%s user=%s", 
                   pk, filename, request.user)
        
        return response