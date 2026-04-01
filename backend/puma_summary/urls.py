from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

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
#  AUTH
#  POST /api/auth/token/           → obtain access + refresh tokens
#  POST /api/auth/token/refresh/   → exchange refresh token for new access token
# ─────────────────────────────────────────────────────────────────────────────

# auth_urlpatterns = [
#     path("auth/token/",         TokenObtainPairView.as_view(), name="token_obtain"),
#     path("auth/token/refresh/", TokenRefreshView.as_view(),    name="token_refresh"),
# ]


# ─────────────────────────────────────────────────────────────────────────────
#  BATCHES
#  POST   /api/batches/upload/         → upload PDFs, create batch, fire task
#  GET    /api/batches/                → paginated batch list
#  GET    /api/batches/<pk>/           → full batch detail + nested reports
#  POST   /api/batches/<pk>/retry/     → re-run failed PDFs only
#  GET    /api/batches/<pk>/logs/      → structured {filename, reason} log
#  GET    /api/batches/<pk>/excel/     → stream Excel download
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