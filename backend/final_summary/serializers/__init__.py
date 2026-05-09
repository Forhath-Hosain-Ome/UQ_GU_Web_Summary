"""
serializers/__init__.py
------------------------
All serializers for the final_summary app.
"""

from rest_framework import serializers
from final_summary.models import (
    Buyer, Factory, BuyerFactoryPair,
    UploadBatch, AuditReport, DefectEntry,
)


# ── Buyer ──────────────────────────────────────────────────────────────────────

class BuyerSerializer(serializers.ModelSerializer):
    factory_count = serializers.SerializerMethodField()

    class Meta:
        model  = Buyer
        fields = ["id", "name", "code", "is_active", "factory_count", "created_at"]

    def get_factory_count(self, obj):
        return obj.factories.count()


# ── Factory ────────────────────────────────────────────────────────────────────

class FactorySerializer(serializers.ModelSerializer):
    buyer_name = serializers.CharField(source="buyer.name", read_only=True)

    class Meta:
        model  = Factory
        fields = ["id", "buyer", "buyer_name", "name", "code", "country", "is_active"]


# ── BuyerFactoryPair ───────────────────────────────────────────────────────────

class BuyerFactoryPairSerializer(serializers.ModelSerializer):
    buyer_name       = serializers.CharField(source="buyer.name", read_only=True)
    factory_name     = serializers.CharField(source="factory.name", read_only=True)
    template_file    = serializers.CharField(read_only=True)
    defect_col_count = serializers.IntegerField(source="defect_column_count", read_only=True)

    class Meta:
        model  = BuyerFactoryPair
        fields = [
            "id", "buyer", "buyer_name", "factory", "factory_name",
            "report_type", "available_reports",
            "template_file", "defect_col_count",
            "is_active", "notes", "created_at",
        ]

    def validate(self, attrs):
        # Cross-validate buyer/factory consistency
        buyer   = attrs.get("buyer",   getattr(self.instance, "buyer",   None))
        factory = attrs.get("factory", getattr(self.instance, "factory", None))
        if buyer and factory and factory.buyer_id != buyer.pk:
            raise serializers.ValidationError(
                {"factory": f"Factory '{factory.name}' does not belong to buyer '{buyer.name}'."}
            )
        return attrs


# ── UploadBatch ────────────────────────────────────────────────────────────────

class UploadBatchListSerializer(serializers.ModelSerializer):
    buyer_name       = serializers.CharField(source="pair.buyer.name",    read_only=True)
    factory_name     = serializers.CharField(source="pair.factory.name",  read_only=True)
    report_type      = serializers.CharField(source="pair.report_type",   read_only=True)
    success_rate     = serializers.FloatField(read_only=True)
    progress_percent = serializers.IntegerField(read_only=True)
    report_count     = serializers.SerializerMethodField()
    created_by       = serializers.SerializerMethodField()

    class Meta:
        model  = UploadBatch
        fields = [
            "id", "pair", "buyer_name", "factory_name", "report_type",
            "inspection_date", "status",
            "total_files", "processed_files", "failed_files",
            "success_rate", "progress_percent", "report_count",
            "celery_task_id", "created_by", "created_at", "updated_at",
        ]

    def get_report_count(self, obj):
        return obj.reports.count()

    def get_created_by(self, obj):
        if not obj.created_by_id:
            return None
        return {"id": obj.created_by_id, "username": obj.created_by.username}


# ── AuditReport ────────────────────────────────────────────────────────────────

class DefectEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model  = DefectEntry
        fields = ["id", "category", "item", "major", "minor", "comment"]


class AuditReportListSerializer(serializers.ModelSerializer):
    report_type = serializers.CharField(source="batch.pair.report_type", read_only=True)

    class Meta:
        model  = AuditReport
        fields = [
            "id", "file_name", "factory", "client", "style_no", "po_no",
            "date_of_issue", "inspection_type", "audit_result", "report_no",
            "item_name", "country", "ship_qty", "audit_qty",
            "defect_qty", "defect_percentage", "acceptable_defect_qty",
            "has_validation_errors", "cross_check_warnings",
            "report_type", "created_at",
        ]