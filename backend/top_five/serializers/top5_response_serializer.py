"""
Serializers for API responses.
Handles standardized response formats for Top5 endpoints.
"""
from rest_framework import serializers
from top_five.models import Top5Job


class Top5UploadResponseSerializer(serializers.Serializer):
    """
    Response serializer for upload endpoint.
    Returns created job ID and initial status.
    """
    job_id = serializers.IntegerField(help_text="Unique job identifier")
    status = serializers.CharField(help_text="Initial job status (PENDING)")


class Top5JobResponseSerializer(serializers.Serializer):
    """
    Response serializer for job status endpoint.
    Returns complete job details.
    """
    id = serializers.IntegerField(help_text="Job ID")
    status = serializers.CharField(help_text="Current job status")
    input_file = serializers.CharField(help_text="Original filename")
    error = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        help_text="Error message if job failed"
    )
    created_at = serializers.DateTimeField(help_text="Job creation timestamp")
    updated_at = serializers.DateTimeField(help_text="Job last update timestamp")


class Top5DownloadResponseSerializer(serializers.Serializer):
    """
    Response metadata for download endpoint.
    Actual file is streamed as binary attachment.
    """
    filename = serializers.CharField(help_text="Output Excel filename")
    job_id = serializers.IntegerField(help_text="Associated job ID")
