from rest_framework import serializers
from puma_summary.models import InspectionReport
from .po_number_serializer import PONumberSerializer
from .certificate_log_serializer import CertificateLogSerializer


# ─────────────────────────────────────────────────────────────────────────────
#  INSPECTION REPORT
# ─────────────────────────────────────────────────────────────────────────────

class InspectionReportSerializer(serializers.ModelSerializer):
    po_numbers       = PONumberSerializer(many=True, read_only=True)
    certificate_logs = CertificateLogSerializer(many=True, read_only=True)
    style_with_pos   = serializers.CharField(read_only=True)
    # Resolved from batch FK — read-only convenience field
    created_by       = serializers.SerializerMethodField()

    class Meta:
        model  = InspectionReport
        fields = [
            "id",
            "batch",
            "pdf_filename",
            "report_number",
            "report_date",
            "inspection_date",
            "style",
            "description",
            "sample_size",
            "po_qty",
            "actual_qty",
            "inspected_qty",
            "major_defect",
            "minor_defect",
            "factory_code",
            "factory_name",
            "final_customer",
            "po_numbers",
            "certificate_logs",
            "style_with_pos",
            "created_by",
            "created_at",
        ]
        read_only_fields = fields

    def get_created_by(self, obj):
        user = obj.batch.created_by
        if user is None:
            return None
        return {"id": user.pk, "username": user.username}


class InspectionReportListSerializer(serializers.ModelSerializer):
    """
    Lightweight version for list endpoints — omits certificate_logs
    to keep response size small when paginating 50+ rows.
    """
    po_numbers     = PONumberSerializer(many=True, read_only=True)
    style_with_pos = serializers.CharField(read_only=True)
    created_by     = serializers.SerializerMethodField()

    class Meta:
        model  = InspectionReport
        fields = [
            "id",
            "batch",
            "pdf_filename",
            "report_number",
            "report_date",
            "inspection_date",
            "style",
            "description",
            "factory_code",
            "factory_name",
            "final_customer",
            "po_qty",
            "actual_qty",
            "inspected_qty",
            "major_defect",
            "minor_defect",
            "po_numbers",
            "style_with_pos",
            "created_by",
        ]
        read_only_fields = fields

    def get_created_by(self, obj):
        user = obj.batch.created_by
        if user is None:
            return None
        return {"id": user.pk, "username": user.username}