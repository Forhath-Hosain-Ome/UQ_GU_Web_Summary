from rest_framework import serializers
from image_processor.models import FolderFailedPDF


# ─────────────────────────────────────────────────────────────────────────────
#  FOLDER FAILED PDF
# ─────────────────────────────────────────────────────────────────────────────

class FolderFailedPDFSerializer(serializers.ModelSerializer):
    """
    Structured log entry for each folder that failed during processing.
    """
    class Meta:
        model  = FolderFailedPDF
        fields = [
            "id",
            "batch",
            "folder_name",
            "reason",
            "created_at",
        ]
        read_only_fields = fields
