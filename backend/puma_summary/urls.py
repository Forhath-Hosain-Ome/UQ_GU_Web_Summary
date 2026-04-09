from django.urls import path
from puma_summary.views import (
    BatchDetailView,
    BatchListView,
    BatchLogsView,
    BatchRetryView,
    BatchUploadView,
    CertificateDownloadView,
    CertificateLogListView,
    ExcelDownloadView,
    ReportDetailView,
    ReportListView,
    ReportPDFDownloadView,
)

app_name = "puma_summary"


# ─────────────────────────────────────────────────────────────────────────────
#  BATCHES
#  POST   /batches/upload/         → upload PDFs, create batch, fire task
#  GET    /batches/                → paginated batch list
#  GET    /batches/<pk>/           → full batch detail + nested reports
#  POST   /batches/<pk>/retry/     → re-run failed PDFs only
#  GET    /batches/<pk>/logs/      → structured {filename, reason} log
#  GET    /batches/<pk>/excel/     → stream Excel download
# ─────────────────────────────────────────────────────────────────────────────

batch_urlpatterns = [
    path("batches/upload/",          BatchUploadView.as_view(),  name="batch_upload"),
    path("batches/",                 BatchListView.as_view(),    name="batch_list"),
    path("batches/<int:pk>/",        BatchDetailView.as_view(),  name="batch_detail"),
    path("batches/<int:pk>/retry/",  BatchRetryView.as_view(),  name="batch_retry"),
    path("batches/<int:pk>/logs/",   BatchLogsView.as_view(),   name="batch_logs"),
    path("batches/<int:pk>/excel/",  ExcelDownloadView.as_view(),name="batch_excel_download"),
]


# ─────────────────────────────────────────────────────────────────────────────
#  REPORTS
#  GET    /api/reports/                       → paginated + filtered report list
#  GET    /api/reports/<pk>/                  → full report detail
#  GET    /api/reports/<pk>/certificate/      → generate + stream DOCX cert
#  GET    /api/reports/<pk>/certificates/     → certificate generation history
# ─────────────────────────────────────────────────────────────────────────────

report_urlpatterns = [
    path("reports/",                         ReportListView.as_view(),          name="report_list"),
    path("reports/<int:pk>/",                ReportDetailView.as_view(),        name="report_detail"),
    path("reports/<int:pk>/pdf/",            ReportPDFDownloadView.as_view(),   name="report_pdf_download"),
    path("reports/<int:pk>/certificate/",    CertificateDownloadView.as_view(), name="certificate_download"),
    path("reports/<int:pk>/certificates/",   CertificateLogListView.as_view(),  name="certificate_log_list"),
]


# ─────────────────────────────────────────────────────────────────────────────
#  COMBINED — imported by the root urls.py
#
#  In your project's config/urls.py add:
#
#      from django.urls import include, path
#      urlpatterns = [
#          path("api/", include("puma_summary.urls", namespace="puma_summary")),
#      ]
#
#  WebSocket routes live in puma_summary/routing.py and are wired in asgi.py
#  — they are NOT included here.
# ─────────────────────────────────────────────────────────────────────────────

urlpatterns = batch_urlpatterns + report_urlpatterns