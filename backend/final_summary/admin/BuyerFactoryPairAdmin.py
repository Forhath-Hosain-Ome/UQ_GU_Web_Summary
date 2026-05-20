
from django.contrib import admin
from final_summary.models import BuyerFactoryPair

# ---------------------------------------------------------------------------
# BuyerFactoryPair
# ---------------------------------------------------------------------------

@admin.register(BuyerFactoryPair)
class BuyerFactoryPairAdmin(admin.ModelAdmin):
    list_display   = (
        "buyer", "factory", "report_type",
        "available_reports_display", "is_active",
    )
    list_filter    = ("report_type", "is_active", "buyer")
    search_fields  = ("buyer__name", "factory__name")
    autocomplete_fields = ("buyer", "factory")
    readonly_fields = ("template_file", "defect_column_count")

    fieldsets = (
        ("Registration", {
            "fields": ("buyer", "factory", "is_active", "notes"),
        }),
        ("Report configuration", {
            "fields": ("report_type", "available_reports", "template_file", "defect_column_count"),
            "description": (
                "report_type controls which Excel template is used. "
                "available_reports lists which inspection types can be uploaded."
            ),
        }),
    )

    @admin.display(description="Available reports")
    def available_reports_display(self, obj):
        return ", ".join(obj.available_reports) or "—"