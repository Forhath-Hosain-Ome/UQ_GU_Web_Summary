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


from top_five.models import Top5Job


logger = logging.getLogger(__name__)

class Top5DownloadView(APIView):
    """
    GET /top5/jobs/<pk>/download/
    Streams the result Excel from cache.
    """
    permission_classes = [IsAuthenticated]
 
    def get(self, request, pk):
        try:
            qs = Top5Job.objects.all()
            if not request.user.is_staff:
                qs = qs.filter(created_by=request.user)
            job = qs.get(pk=pk)
        except Top5Job.DoesNotExist:
            return Response({"detail": "Job not found."}, status=404)
 
        if job.status != Top5Job.Status.DONE:
            return Response(
                {"detail": f"Job is not ready (status: {job.status})."},
                status=400,
            )
 
        cache_key = f"top5_result_{pk}"
        result_bytes = cache.get(cache_key)
 
        if not result_bytes:
            return Response(
                {"detail": "Result has expired. Please re-upload and process the file."},
                status=404,
            )
 
        stem = Path(job.input_file).stem
        filename = f"Audit_Result_{stem}.xlsx"
 
        response = HttpResponse(
            content      = result_bytes,
            content_type = (
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response