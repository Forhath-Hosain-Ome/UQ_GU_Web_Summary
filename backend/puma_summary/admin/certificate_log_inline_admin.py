from django.contrib import admin
from puma_summary.models import CertificateLog



class CertificateLogInline(admin.TabularInline):
    model = CertificateLog
    extra = 0
    readonly_fields = ("generated_at", "downloaded_at", "generated_by", "was_downloaded")
    fields = readonly_fields
    can_delete = False

    @admin.display(description="Downloaded?", boolean=True)
    def was_downloaded(self, obj):
        return obj.was_downloaded


@admin.register(CertificateLog)
class CertificateLogAdmin(admin.ModelAdmin):
    list_display  = ("report", "generated_at", "downloaded_at", "generated_by", "downloaded_badge")
    list_filter   = ("generated_at",)
    readonly_fields = ("generated_at",)

    @admin.display(description="Downloaded?", boolean=True)
    def downloaded_badge(self, obj):
        return obj.was_downloaded