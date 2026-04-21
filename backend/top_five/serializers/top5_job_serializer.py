"""
Serializer for Top5Job model.
Handles serialization of job instances for API responses.
"""
from rest_framework import serializers
from top_five.models import Top5Job


class Top5JobSerializer(serializers.ModelSerializer):
    """
    Serializes Top5Job instances.
    Used for retrieving job status and details.
    """
    created_by_username = serializers.CharField(
        source='created_by.username',
        read_only=True,
        allow_null=True
    )
    
    class Meta:
        model = Top5Job
        fields = [
            'id',
            'status',
            'input_file',
            'error',
            'created_at',
            'updated_at',
            'created_by_username',
        ]
        read_only_fields = [
            'id',
            'status',
            'error',
            'created_at',
            'updated_at',
            'created_by_username',
        ]
