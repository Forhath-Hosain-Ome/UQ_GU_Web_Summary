from rest_framework import serializers
from puma_summary.models import CertificateLog


# ─────────────────────────────────────────────────────────────────────────────
#  CERTIFICATE LOG
# ─────────────────────────────────────────────────────────────────────────────

class CertificateLogSerializer(serializers.ModelSerializer):
    was_downloaded = serializers.BooleanField(read_only=True)

    class Meta:
        model  = CertificateLog
        fields = [
            "id",
            "generated_at",
            "downloaded_at",
            "generated_by",
            "was_downloaded",
        ]
        read_only_fields = fields
