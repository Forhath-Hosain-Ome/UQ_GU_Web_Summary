from django.contrib import admin

from final_summary.models import (
    AuditReport,
    DefectEntry,
)


# ---------------------------------------------------------------------------
# AuditReport
# ---------------------------------------------------------------------------

class DefectEntryInline(admin.TabularInline):
    model   = DefectEntry
    extra   = 0
    fields  = ("category", "item", "major", "minor", "comment")
    readonly_fields = fields
    can_delete = False
    max_num    = 0


@admin.register(AuditReport)
class AuditReportAdmin(admin.ModelAdmin):
    list_display  = (
        "file_name", "factory", "client", "style_no", "date_of_issue",
        "inspection_type", "audit_result", "has_validation_errors",
    )
    list_filter   = (
        "inspection_type", "audit_result", "has_validation_errors",
        "batch__pair__report_type", "batch__pair__buyer",
    )
    search_fields = ("file_name", "factory", "style_no", "po_no", "report_no")
    readonly_fields = (
        "batch", "file_name", "factory_extracted", "client_extracted",
        "cross_check_warnings", "date_of_issue", "report_type", "template_file",
        "has_validation_errors", "validation_errors", "blocking_errors",
        "created_at", "updated_at",
    )
    inlines = [DefectEntryInline]

    fieldsets = (
        ("Source", {
            "fields": ("batch", "file_name", "report_type", "template_file"),
        }),
        ("Cross-check", {
            "fields": ("factory_extracted", "client_extracted", "cross_check_warnings"),
            "classes": ("collapse",),
        }),
        ("Identity", {
            "fields": (
                "factory", "client", "date_of_issue", "inspection_type",
                "report_no", "audit_report", "item_name", "style_no",
                "po_no", "country",
            ),
        }),
        ("Times", {
            "fields": (
                "factory_in_time", "factory_out_time", "factory_total_hours",
                "audit_start_time", "audit_end_time", "audit_total_hours",
            ),
            "classes": ("collapse",),
        }),
        ("Quantities", {
            "fields": (
                "po_qty", "po_qty_pcs", "po_qty_pack", "po_qty_set",
                "do_qty", "ship_qty", "audit_qty",
            ),
            "classes": ("collapse",),
        }),
        ("Dates", {
            "fields": ("exf", "po_edt", "po_wh", "plan_edt", "plan_wh"),
            "classes": ("collapse",),
        }),
        ("Defects", {
            "fields": (
                "defect_qty", "acceptable_defect_qty", "defect_percentage",
            ),
        }),
        ("Personnel & checks", {
            "fields": (
                "person", "inspector", "carton",
                "needle_detector", "remarks", "do_set_col_size",
            ),
            "classes": ("collapse",),
        }),
        ("Validation", {
            "fields": (
                "has_validation_errors", "validation_errors", "blocking_errors",
            ),
            "classes": ("collapse",),
        }),
    )