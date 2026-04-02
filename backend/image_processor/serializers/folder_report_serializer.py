from rest_framework import serializers
from image_processor.models import FolderReport


# ─────────────────────────────────────────────────────────────────────────────
#  FOLDER REPORT
# ─────────────────────────────────────────────────────────────────────────────

class FolderReportSerializer(serializers.ModelSerializer):
    """
    Full folder report detail.
    """
    # Resolved from batch FK — read-only convenience field
    created_by = serializers.SerializerMethodField()

    class Meta:
        model  = FolderReport
        fields = [
            "id",
            "batch",
            "folder_name",
            "pdf_output_path",
            "status",
            "error_message",
            "image_count",
            "metadata",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_created_by(self, obj):
        user = obj.batch.created_by
        if user is None:
            return None
        return {"id": user.pk, "username": user.username}


class FolderReportListSerializer(serializers.ModelSerializer):
    """
    Lightweight version for list endpoints — omits metadata
    to keep response size small when paginating 50+ rows.
    """
    created_by = serializers.SerializerMethodField()

    class Meta:
        model  = FolderReport
        fields = [
            "id",
            "batch",
            "folder_name",
            "pdf_output_path",
            "status",
            "error_message",
            "image_count",
            "created_by",
            "created_at",
        ]
        read_only_fields = fields

    def get_created_by(self, obj):
        user = obj.batch.created_by
        if user is None:
            return None
        return {"id": user.pk, "username": user.username}
