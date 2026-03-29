from django.contrib import admin
from django.utils.html import format_html
from puma_summary.models import InspectionReport, InspectionBatch, InspectionReport
from .certificate_log_inline_admin import CertificateLogInline
from .po_number_inline_admin import PONumberInline

class InspectionReportInline(admin.TabularInline):
    model = InspectionReport
    extra = 0
    readonly_fields = ("style", "factory_name", "inspection_date", "po_qty",
                       "actual_qty", "inspected_qty", "major_defect", "minor_defect")
    fields = readonly_fields
    can_delete = False
    show_change_link = True

@admin.register(InspectionBatch)
class InspectionBatchAdmin(admin.ModelAdmin):
    list_display   = ("id", "factory_code", "status_badge", "total_pdfs",
                      "processed_pdfs", "failed_pdfs", "success_rate_pct", "created_at")
    list_filter    = ("status", "factory_code")
    search_fields  = ("factory_code", "celery_task_id")
    readonly_fields = ("celery_task_id", "created_at", "updated_at", "success_rate_pct")
    inlines        = [InspectionReportInline]
    ordering       = ("-created_at",)

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        colours = {
            "PENDING":    "#6c757d",
            "PROCESSING": "#0d6efd",
            "COMPLETED":  "#198754",
            "PARTIAL":    "#fd7e14",
            "FAILED":     "#dc3545",
        }
        c = colours.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;'
            'border-radius:4px;font-size:11px;font-weight:600">{}</span>',
            c, obj.status,
        )

    @admin.display(description="Success %")
    def success_rate_pct(self, obj):
        return f"{obj.success_rate}%"

@admin.register(InspectionReport)
class InspectionReportAdmin(admin.ModelAdmin):
    list_display   = ("style", "factory_code", "factory_name", "inspection_date",
                      "po_qty", "actual_qty", "inspected_qty",
                      "major_defect", "minor_defect", "final_customer")
    list_filter    = ("factory_code", "final_customer", "inspection_date")
    search_fields  = ("style", "description", "factory_name", "po_numbers__number")
    readonly_fields = ("created_at", "style_with_pos")
    inlines        = [PONumberInline, CertificateLogInline]
    ordering       = ("-inspection_date", "style")
    date_hierarchy  = "inspection_date"


