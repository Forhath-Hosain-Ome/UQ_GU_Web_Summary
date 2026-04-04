from rest_framework import serializers
from image_processor.models import FolderBatch
from .folder_report_serializer import FolderReportListSerializer
from .folder_failed_pdf_serializer import FolderFailedPDFSerializer


# ─────────────────────────────────────────────────────────────────────────────
#  FOLDER BATCH
# ─────────────────────────────────────────────────────────────────────────────

class FolderBatchSerializer(serializers.ModelSerializer):
    """
    Full batch detail — includes nested reports and failed folders.
    Used for the batch detail/status endpoint.
    """
    reports             = FolderReportListSerializer(many=True, read_only=True)
    failed_folder_records  = FolderFailedPDFSerializer(many=True, read_only=True, source="batch_failed_folders")
    failed_folders_count   = serializers.IntegerField(source="failed_folders", read_only=True)
    success_rate        = serializers.FloatField(read_only=True)
    progress_percent    = serializers.IntegerField(read_only=True)
    created_by          = serializers.SerializerMethodField()

    class Meta:
        model  = FolderBatch
        fields = [
            "id",
            "status",
            "total_folders",
            "processed_folders",
            "failed_folder_records",
            "failed_folders_count",
            "success_rate",
            "progress_percent",
            "error_log",
            "retry_count",
            "celery_task_id",
            "created_by",
            "created_at",
            "updated_at",
            "reports",
        ]
        read_only_fields = fields

    def get_created_by(self, obj):
        user = obj.created_by
        if user is None:
            return None
        return {"id": user.pk, "username": user.username}


class FolderBatchListSerializer(serializers.ModelSerializer):
    """
    Lightweight version for the batch list endpoint — no nested reports.
    """
    success_rate     = serializers.FloatField(read_only=True)
    progress_percent = serializers.IntegerField(read_only=True)
    report_count     = serializers.SerializerMethodField()
    failed_folder_count = serializers.SerializerMethodField()
    created_by       = serializers.SerializerMethodField()

    class Meta:
        model  = FolderBatch
        fields = [
            "id",
            "status",
            "total_folders",
            "processed_folders",
            "success_rate",
            "progress_percent",
            "retry_count",
            "report_count",
            "failed_folder_count",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_report_count(self, obj):
        try:
            return obj.reports.count()
        except RuntimeError as e:
            if "cannot schedule new futures after interpreter shutdown" in str(e):
                return 0
            else:
                raise

    def get_failed_folder_count(self, obj):
        try:
            return obj.batch_failed_folders.count()
        except RuntimeError as e:
            if "cannot schedule new futures after interpreter shutdown" in str(e):
                return 0
            else:
                raise

    def get_created_by(self, obj):
        user = obj.created_by
        if user is None:
            return None
        return {"id": user.pk, "username": user.username}
