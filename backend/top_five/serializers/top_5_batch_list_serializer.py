"""
Serializer for Top5Job list endpoint.
Returns a subset of job fields for list display.
"""
from rest_framework import serializers
from top_five.models import Top5Job


class Top5BatchListSerializer(serializers.ModelSerializer):
    """
    Serializes Top5Job instances for list view.
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
            'created_at',
            'created_by_username',
        ]
        read_only_fields = fields
