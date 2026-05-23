"""
top5/views.py
--------------
GET  /top5/jobs/<pk>/
    Returns job status and details.
"""
import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from top_five.models import Top5Job
from top_five.serializers import Top5JobResponseSerializer

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


class Top5JobStatusView(APIView):
    """
    GET /top5/jobs/<pk>/
    
    Returns current job status and details.
    Authentication: Required (401 if not authenticated)
    Permission: User can only see their own jobs (unless staff)
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
            # Non-staff users can only see their own jobs
            if not request.user.is_staff:
                qs = qs.filter(created_by=request.user)
            job = qs.get(pk=pk)
        except Top5Job.DoesNotExist:
            return Response({
                "detail": f"Job #{pk} not found or access denied."
            }, status=404)

        # Serialize job using the model instance directly (not a dict)
        serializer = Top5JobResponseSerializer(job)
        
        logger.debug("top5 job status — job_id=%s status=%s user=%s", 
                    pk, job.status, request.user)
        
        return Response(serializer.data)
