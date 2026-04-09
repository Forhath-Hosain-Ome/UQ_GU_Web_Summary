from django.urls import path
from final_summary.views import (
    AuditUploadView,
    AuditBatchListView,
    AuditBatchDetailView,
    AuditFilterOptionsView,
    AuditExportView,
)

app_name = "final_summary"

urlpatterns = [
    # ── Stage 1: Upload & track ────────────────────────────────────────────────
    path("upload/",           AuditUploadView.as_view(),        name="upload"),
    path("batches/",          AuditBatchListView.as_view(),     name="batch_list"),
    path("batches/<int:pk>/", AuditBatchDetailView.as_view(),   name="batch_detail"),

    # ── Stage 2: Export ────────────────────────────────────────────────────────
    path("options/",          AuditFilterOptionsView.as_view(), name="filter_options"),
    path("export/",           AuditExportView.as_view(),        name="export"),
]