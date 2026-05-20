"""
-------
URL routing for the final_summary app.

Endpoint map
------------
Registration (must be done before uploading):
  GET/POST   buyers/                   List / create buyers
  GET/PUT    buyers/<pk>/              Retrieve / update buyer
  GET/POST   factories/                List / create factories (?buyer=<id>)
  GET/PUT    factories/<pk>/           Retrieve / update factory
  GET/POST   pairs/                    List / create buyer–factory pairs
  GET/PUT    pairs/<pk>/               Retrieve / update pair
  GET        pairs/options/            Upload form dropdown data

Upload:
  POST       upload/                   Upload Excel files for a pair + date

Batch tracking:
  GET        batches/                  List upload batches (paginated)
  GET        batches/<pk>/             Batch detail with nested reports

Retry (Stage 3):
  GET        retry/search/             Search blocked records (date + style)
   GET        retry/<int:batch_id>/download/      Download error JSON for a batch
  POST       retry/upload/             Upload fixed error JSON

Export:
  GET        export/                   Generate and download summary Excel

Filter options (for export form):
  GET        options/                  Distinct factories, buyers, dates

Top-5 report:
  POST       top-5/                    Generate top-5 defect report
"""

from django.urls import path

from final_summary.views import (
    # Registration
    BuyerListCreateView,
    BuyerDetailView,
    FactoryListCreateView,
    FactoryDetailView,
    PairListCreateView,
    PairDetailView,
    PairOptionsView,
    # Upload
    AuditUploadView,
    # Batch
    AuditBatchListView,
    AuditBatchDetailView,
    # Retry
    RetrySearchView,
    RetryDownloadView,
    RetryUploadView,
    # Export
    AuditExportView,
    # Filter options
    AuditFilterOptionsView,
    # Top-5
    AuditReportGenerateView,
)

app_name = "final_summary"

urlpatterns = [

    # ── Registration ──────────────────────────────────────────────────────────
    path("buyers/",             BuyerListCreateView.as_view(),   name="buyer_list"),
    path("buyers/<int:pk>/",    BuyerDetailView.as_view(),       name="buyer_detail"),

    path("factories/",          FactoryListCreateView.as_view(), name="factory_list"),
    path("factories/<int:pk>/", FactoryDetailView.as_view(),     name="factory_detail"),

    path("pairs/",              PairListCreateView.as_view(),    name="pair_list"),
    path("pairs/<int:pk>/",     PairDetailView.as_view(),        name="pair_detail"),
    path("pairs/options/",      PairOptionsView.as_view(),       name="pair_options"),

    # ── Upload ────────────────────────────────────────────────────────────────
    path("upload/",             AuditUploadView.as_view(),       name="upload"),

    # ── Batch tracking ────────────────────────────────────────────────────────
    path("batches/",            AuditBatchListView.as_view(),    name="batch_list"),
    path("batches/<int:pk>/",   AuditBatchDetailView.as_view(),  name="batch_detail"),

    # ── Retry / Fix & Retry ───────────────────────────────────────────────────
    path("retry/search/",              RetrySearchView.as_view(),   name="retry_search"),
    path("retry/<int:batch_id>/download/",   RetryDownloadView.as_view(), name="retry_download"),
    path("retry/upload/",              RetryUploadView.as_view(),   name="retry_upload"),

    # ── Export ────────────────────────────────────────────────────────────────
    path("export/",             AuditExportView.as_view(),       name="export"),

    # ── Filter options ────────────────────────────────────────────────────────
    path("options/",            AuditFilterOptionsView.as_view(), name="filter_options"),

    # ── Top-5 report ─────────────────────────────────────────────────────────
    path("top-5/",              AuditReportGenerateView.as_view(), name="top_5"),
]