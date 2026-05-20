"""
List view for Top5Job objects.
"""
import logging
import os
from django.http import FileResponse
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from top_five.models import Top5Job
from top_five.serializers import Top5BatchListSerializer

logger = logging.getLogger(__name__)


class Top5JobListView(generics.ListAPIView):
    """
    GET /top5/jobs/
    Returns a list of Top5Job objects filtered by user.
    Staff users see all jobs; regular users see only their own.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = Top5BatchListSerializer

    def get_queryset(self):
        try:
            user = self.request.user
            qs = Top5Job.objects.all().select_related("created_by")
            if not user.is_staff:
                qs = qs.filter(created_by=user)
            return qs.order_by("-created_at")
        except RuntimeError as e:
            if "cannot schedule new futures after interpreter shutdown" in str(e):
                return Top5Job.objects.none()
            else:
                raise

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except RuntimeError as e:
            if "cannot schedule new futures after interpreter shutdown" in str(e):
                return Response([], status=status.HTTP_200_OK)
            raise
