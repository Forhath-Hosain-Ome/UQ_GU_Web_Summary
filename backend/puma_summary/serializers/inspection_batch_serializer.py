from rest_framework import serializers
from puma_summary.models import InspectionBatch
from .inspection_report_serializer import InspectionReportListSerializer
from .batch_failed_pdf_serializer import BatchFailedPDFSerializer


# ─────────────────────────────────────────────────────────────────────────────
#  INSPECTION BATCH
# ─────────────────────────────────────────────────────────────────────────────

class InspectionBatchSerializer(serializers.ModelSerializer):
    """
    Full batch detail — includes nested reports and failed PDFs.
    Used for the batch detail/status endpoint.
    """
    reports          = InspectionReportListSerializer(many=True, read_only=True)
    failed_pdf_records = BatchFailedPDFSerializer(many=True, read_only=True, source='batch_failed_pdfs')
    failed_pdfs_count = serializers.IntegerField(source='failed_pdfs', read_only=True)
    success_rate     = serializers.FloatField(read_only=True)
    progress_percent = serializers.IntegerField(read_only=True)

    class Meta:
        model  = InspectionBatch
        fields = [
            "id",
            "status",
            "factory_code",
            "total_pdfs",
            "processed_pdfs",
            "failed_pdf_records",
            "failed_pdfs_count",
            "success_rate",
            "progress_percent",
            "error_log",
            "excel_report_path",
            "retry_count",
            "celery_task_id",
            "created_at",
            "updated_at",
            "reports",
        ]
        read_only_fields = fields


class InspectionBatchListSerializer(serializers.ModelSerializer):
    """
    Lightweight version for the batch list endpoint — no nested reports.
    """
    success_rate     = serializers.FloatField(read_only=True)
    progress_percent = serializers.IntegerField(read_only=True)
    report_count     = serializers.SerializerMethodField()
    failed_pdf_count = serializers.SerializerMethodField()

    class Meta:
        model  = InspectionBatch
        fields = [
            "id",
            "status",
            "factory_code",
            "total_pdfs",
            "processed_pdfs",
            "success_rate",
            "progress_percent",
            "retry_count",
            "report_count",
            "failed_pdf_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_report_count(self, obj):
        # Uses prefetch_related cache if available — no extra query
        return obj.reports.count()

    def get_failed_pdf_count(self, obj):
        return obj.batch_failed_pdfs.count()
