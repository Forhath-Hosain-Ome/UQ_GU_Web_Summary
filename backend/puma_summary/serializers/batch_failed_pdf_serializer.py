from rest_framework import serializers
from puma_summary.models import BatchFailedPDF


# ─────────────────────────────────────────────────────────────────────────────
#  BATCH FAILED PDF
# ─────────────────────────────────────────────────────────────────────────────

class BatchFailedPDFSerializer(serializers.ModelSerializer):
    class Meta:
        model  = BatchFailedPDF
        fields = ["id", "filename", "reason", "retried", "created_at"]
        read_only_fields = fields
