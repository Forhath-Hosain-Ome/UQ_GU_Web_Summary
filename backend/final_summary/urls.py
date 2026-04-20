from django.urls import path
from final_summary.views import (
    AuditUploadView,
    AuditBatchListView,
    AuditBatchDetailView,
    AuditFilterOptionsView,
    AuditExportView,
    AuditRetryView,
    AuditBatchLogsView,
    AuditBatchErrorJsonView,
    AuditReportGenerateView,
)

app_name = "final_summary"

urlpatterns = [
    # ── 1. Bulk upload ─────────────────────────────────────────────────────────
    # POST  multipart/form-data, field "files" (one or many .xlsx/.xls)
    path("upload/",           AuditUploadView.as_view(),        name="upload"),

    # ── 2. Download summary ────────────────────────────────────────────────────
    # GET   ?factory=X&client=Y&date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    #       &style=optional&po=optional
    # Returns .xlsx file download
    path("export/",           AuditExportView.as_view(),        name="export"),

    # ── 3. Retry (upload fixed JSON) ───────────────────────────────────────────
    # POST  JSON body: { batch_id: int, records: [...] }
    # Download the error JSON first via GET batches/<pk>/logs/error-json/
    path("retry/",            AuditRetryView.as_view(),          name="retry"),

    # ── Batch tracking ─────────────────────────────────────────────────────────
    path("batches/",          AuditBatchListView.as_view(),     name="batch_list"),
    path("batches/<int:pk>/", AuditBatchDetailView.as_view(),   name="batch_detail"),

    # ── 4. Logs ────────────────────────────────────────────────────────────────
    # GET structured error log
    path("batches/<int:pk>/logs/",            AuditBatchLogsView.as_view(),      name="batch_logs"),
    # GET downloadable error JSON for retry
    path("batches/<int:pk>/logs/error-json/", AuditBatchErrorJsonView.as_view(), name="batch_error_json"),

    # ── Filter options (for export form dropdowns) ─────────────────────────────
    path("options/",          AuditFilterOptionsView.as_view(), name="filter_options"),


    path("top-5", AuditReportGenerateView.as_view(), name="top-5",
    ),
]