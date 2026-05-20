from django.contrib import admin

from final_summary.models import Factory





# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

@admin.register(Factory)
class FactoryAdmin(admin.ModelAdmin):
    list_display  = ("name", "buyer", "code", "country", "is_active")
    list_filter   = ("buyer", "is_active", "country")
    search_fields = ("name", "code", "buyer__name")
    autocomplete_fields = ("buyer",)

