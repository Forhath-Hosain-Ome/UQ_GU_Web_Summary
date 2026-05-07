from django.contrib import admin

from final_summary.models import (
    Buyer,
    Factory
)


# ---------------------------------------------------------------------------
# Buyer
# ---------------------------------------------------------------------------

class FactoryInline(admin.TabularInline):
    model   = Factory
    extra   = 1
    fields  = ("name", "code", "country", "is_active")
    show_change_link = True


@admin.register(Buyer)
class BuyerAdmin(admin.ModelAdmin):
    list_display  = ("name", "code", "factory_count", "is_active", "created_at")
    list_filter   = ("is_active",)
    search_fields = ("name", "code")
    inlines       = [FactoryInline]

    @admin.display(description="Factories")
    def factory_count(self, obj):
        return obj.factories.count()
