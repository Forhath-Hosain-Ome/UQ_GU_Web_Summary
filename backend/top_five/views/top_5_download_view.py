"""
top5/views.py
--------------
GET  /top5/jobs/<pk>/download/
    Streams the result Excel file.
    Returns 404 if file missing or job not successful.
"""
import logging
import os
from pathlib import Path

from django.core.cache import cache
from django.http import FileResponse, HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from top_five.models import Top5Job

logger = logging.getLogger(__name__)

class Top5DownloadView(APIView):
    """
    GET /top5/jobs/<pk>/download/
    Streams the result Excel from storage (with cache fallback).
    """
    permission_classes = [IsAuthenticated]
 
    def get(self, request, pk):
        logger.info("Download requested for Top5 job #%s by user %s", pk, request.user)
        try:
            qs = Top5Job.objects.all()
            if not request.user.is_staff:
                qs = qs.filter(created_by=request.user)
            job = qs.get(pk=pk)
        except (Top5Job.DoesNotExist, ValueError):
            logger.warning("Top5 job #%s not found for user %s", pk, request.user)
            return Response({"detail": "Job not found or access denied."}, status=404)
        except RuntimeError as e:
            if "cannot schedule new futures after interpreter shutdown" in str(e):
                return Response({"detail": "Server is shutting down."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            raise
 
        try:
            # Check job status - handle both SUCCESS and DONE naming conventions
            # We check multiple variations to be safe against different model implementations
            allowed_statuses = ['SUCCESS', 'DONE']
            if hasattr(Top5Job, 'Status'):
                if hasattr(Top5Job.Status, 'SUCCESS'): allowed_statuses.append(Top5Job.Status.SUCCESS)
                if hasattr(Top5Job.Status, 'DONE'):    allowed_statuses.append(Top5Job.Status.DONE)
            
            current_status = str(job.status).upper()
            
            if job.status not in allowed_statuses and current_status not in ['SUCCESS', 'DONE']:
                return Response(
                    {"detail": f"Download unavailable. Job status is '{job.status}'."},
                    status=400,
                )
    
            # 1. Primary: Try common file field names (output_file, result_file, or file)
            output_file = (
                getattr(job, 'output_file', None) or 
                getattr(job, 'result_file', None) or 
                getattr(job, 'file', None)
            )
            
            if output_file and output_file.name:
                if os.path.exists(output_file.path):
                    logger.info("Serving Top5 job #%s from storage", pk)
                    filename = os.path.basename(output_file.name)
                    return FileResponse(
                        output_file.open('rb'),
                        as_attachment=True,
                        filename=filename,
                        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    )
                else:
                    logger.warning("Top5 output_file recorded but missing on disk for job %s: %s", pk, output_file.path)
    
            # 2. Fallback: Try cache (handles transient processing or legacy jobs)
            cache_key = f"top5_result_{pk}"
            result_bytes = cache.get(cache_key)
     
            if result_bytes:
                logger.info("Serving Top5 job #%s from cache", pk)
                
                # Handle input_file whether it's a string or a FileField object
                input_name = getattr(job.input_file, 'name', str(job.input_file))
                stem = Path(input_name).stem
                filename = f"Top5_Result_{stem}.xlsx"
                response = HttpResponse(
                    content=result_bytes,
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                response["Content-Disposition"] = f'attachment; filename="{filename}"'
                return response
    
            logger.error("No result file or cache found for successful Top5 job #%s", pk)
            return Response(
                {"detail": "Result file not found or has expired. Please re-process the file."},
                status=404,
            )
        except Exception as exc:
            logger.exception("Unexpected error in Top5DownloadView for job #%s: %s", pk, exc)
            return Response(
                {"detail": "An internal error occurred while serving the file."},
                status=500
            )