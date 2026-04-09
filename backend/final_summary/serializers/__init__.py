"""
final_summary/serializers/__init__.py
--------------------------------------
All serializers for the final_summary app.

Hierarchy
---------
  DefectEntrySerializer
  AuditReportListSerializer   — lightweight, used in batch detail + report lists
  AuditReportDetailSerializer — full record including nested defects + DO orders
  UploadBatchListSerializer   — lightweight batch rows
  UploadBatchDetailSerializer — batch + nested report list
"""

import json
from rest_framework import serializers

from final_summary.models import DefectEntry, AuditReport, UploadBatch


# ═════════════════════════════════════════════════════════════════════════════
#  DefectEntry
# ═════════════════════════════════════════════════════════════════════════════

class DefectEntrySerializer(serializers.ModelSerializer):

    class Meta:
        model  = DefectEntry
        fields = [
            "id",
            "category",
            "item",
            "major",
            "minor",
            "comment",
        ]
        read_only_fields = [
            "id",
            "category",
            "item",
            "major",
            "minor",
            "comment",
        ]


# ═════════════════════════════════════════════════════════════════════════════
#  AuditReport
# ═════════════════════════════════════════════════════════════════════════════

_AUDIT_REPORT_LIST_FIELDS = [
    "id",
    "file_name",
    "factory",
    "client",
    "style_no",
    "po_no",
    "date_of_issue",
    "inspection_type",
    "audit_result",
    "report_no",
    "item_name",
    "country",
    "ship_qty",
    "audit_qty",
    "defect_qty",
    "defect_percentage",
    "acceptable_defect_qty",
    "has_validation_errors",
    "created_at",
]


class AuditReportListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer — used inside UploadBatchDetailSerializer
    and any report-list endpoint.  No nested relations, no heavy fields.
    """

    class Meta:
        model            = AuditReport
        fields           = _AUDIT_REPORT_LIST_FIELDS
        read_only_fields = _AUDIT_REPORT_LIST_FIELDS


_AUDIT_REPORT_DETAIL_FIELDS = [
    # identifiers
    "id",
    "batch",
    "file_name",
    # header
    "factory",
    "client",
    "date_of_issue",
    "inspection_type",
    "report_no",
    "audit_report",
    "item_name",
    "style_no",
    "po_no",
    "country",
    # time
    "factory_in_time",
    "factory_out_time",
    "factory_total_hours",
    "audit_start_time",
    "audit_end_time",
    "audit_total_hours",
    # outcome
    "audit_result",
    # quantities
    "po_qty",
    "po_qty_pcs",
    "po_qty_pack",
    "po_qty_set",
    "do_qty",
    "ship_qty",
    "audit_qty",
    # shipment dates
    "exf",
    "po_edt",
    "po_wh",
    "plan_edt",
    "plan_wh",
    # defect summary
    "defect_qty",
    "acceptable_defect_qty",
    "defect_percentage",
    # personnel
    "person",
    "inspector",
    # extra checks
    "carton",
    "needle_detector",
    "remarks",
    "do_set_col_size",
    "do_note",
    # validation
    "has_validation_errors",
    "validation_errors",
    "blocking_errors",
    # computed / nested
    "do_orders",        # SerializerMethodField — parsed from do_orders_json
    "defect_entries",   # nested DefectEntrySerializer
    # timestamps
    "created_at",
    "updated_at",
]


class AuditReportDetailSerializer(serializers.ModelSerializer):
    """
    Full detail serializer.  Includes nested defect rows and parsed DO orders.
    Used by a future /api/audit/reports/<pk>/ endpoint.
    """
    defect_entries = DefectEntrySerializer(many=True, read_only=True)
    do_orders      = serializers.SerializerMethodField()

    class Meta:
        model            = AuditReport
        fields           = _AUDIT_REPORT_DETAIL_FIELDS
        read_only_fields = _AUDIT_REPORT_DETAIL_FIELDS

    def get_do_orders(self, obj):
        try:
            return json.loads(obj.do_orders_json or "[]")
        except (json.JSONDecodeError, TypeError):
            return []


# ═════════════════════════════════════════════════════════════════════════════
#  UploadBatch
# ═════════════════════════════════════════════════════════════════════════════

_BATCH_LIST_FIELDS = [
    "id",
    "status",
    "total_files",
    "processed_files",
    "failed_files",
    "success_rate",       # model @property
    "progress_percent",   # model @property
    "report_count",       # SerializerMethodField
    "celery_task_id",
    "created_by",         # SerializerMethodField — returns {id, username}
    "created_at",
    "updated_at",
]


class UploadBatchListSerializer(serializers.ModelSerializer):
    """
    Lightweight batch rows — used for GET /api/audit/batches/.
    No nested report list to keep response size small.
    """
    success_rate     = serializers.FloatField(read_only=True)
    progress_percent = serializers.IntegerField(read_only=True)
    report_count     = serializers.SerializerMethodField()
    created_by       = serializers.SerializerMethodField()

    class Meta:
        model            = UploadBatch
        fields           = _BATCH_LIST_FIELDS
        read_only_fields = _BATCH_LIST_FIELDS

    def get_report_count(self, obj):
        # Use prefetched queryset if available, otherwise hit DB
        if hasattr(obj, "_prefetched_objects_cache") and "reports" in obj._prefetched_objects_cache:
            return len(obj._prefetched_objects_cache["reports"])
        return obj.reports.count()

    def get_created_by(self, obj):
        if obj.created_by_id is None:
            return None
        return {
            "id":       obj.created_by_id,
            "username": obj.created_by.username,
        }


_BATCH_DETAIL_FIELDS = [
    "id",
    "status",
    "total_files",
    "processed_files",
    "failed_files",
    "success_rate",
    "progress_percent",
    "error_log",
    "celery_task_id",
    "created_by",
    "created_at",
    "updated_at",
    "reports",            # nested AuditReportListSerializer
]


class UploadBatchDetailSerializer(serializers.ModelSerializer):
    """
    Full batch detail — used for GET /api/audit/batches/<pk>/.
    Includes the nested list of extracted AuditReports.
    """
    success_rate     = serializers.FloatField(read_only=True)
    progress_percent = serializers.IntegerField(read_only=True)
    reports          = AuditReportListSerializer(many=True, read_only=True)
    created_by       = serializers.SerializerMethodField()

    class Meta:
        model            = UploadBatch
        fields           = _BATCH_DETAIL_FIELDS
        read_only_fields = _BATCH_DETAIL_FIELDS

    def get_created_by(self, obj):
        if obj.created_by_id is None:
            return None
        return {
            "id":       obj.created_by_id,
            "username": obj.created_by.username,
        }