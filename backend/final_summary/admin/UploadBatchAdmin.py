
from django.contrib import admin
from django.utils.html import format_html

from final_summary.models import (
    UploadBatch,
    AuditReport,
)

# ---------------------------------------------------------------------------
# UploadBatch
# ---------------------------------------------------------------------------

class AuditReportInline(admin.TabularInline):
    model  = AuditReport
    extra  = 0
    fields = (
        "file_name", "inspection_type", "style_no", "report_no",
        "audit_result", "has_validation_errors",
    )
    readonly_fields = fields
    show_change_link = True
    can_delete = False
    max_num    = 0


@admin.register(UploadBatch)
class UploadBatchAdmin(admin.ModelAdmin):
    list_display  = (
        "id", "pair", "inspection_date", "status",
        "progress_display", "created_by", "created_at",
    )
    list_filter   = ("status", "pair__report_type", "pair__buyer")
    search_fields = ("pair__buyer__name", "pair__factory__name", "celery_task_id")
    readonly_fields = (
        "celery_task_id", "processed_files", "failed_files",
        "total_files", "success_rate", "progress_percent",
        "error_log", "created_at", "updated_at",
    )
    inlines = [AuditReportInline]

    @admin.display(description="Progress")
    def progress_display(self, obj):
        pct = obj.progress_percent
        color = "#28a745" if pct == 100 else "#ffc107" if pct > 0 else "#dc3545"
        return format_html(
            '<span style="color:{}">{}/{} ({}%)</span>',
            color, obj.processed_files, obj.total_files, pct,
        )

