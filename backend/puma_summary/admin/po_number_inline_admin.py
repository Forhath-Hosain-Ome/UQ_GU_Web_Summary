from django.contrib import admin
from puma_summary.models import PONumber


class PONumberInline(admin.TabularInline):
    model = PONumber
    extra = 0
    readonly_fields = ("number",)
    can_delete = False