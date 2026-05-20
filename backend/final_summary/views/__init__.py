"""
views/__init__.py
------------------
Single import point for all final_summary views.

Usage anywhere in the app:
    from final_summary.views import AuditUploadView, RetrySearchView, ...
"""

# Registration
from .buyer_factory_views import (
    BuyerListCreateView,
    BuyerDetailView,
    FactoryListCreateView,
    FactoryDetailView,
    PairListCreateView,
    PairDetailView,
    PairOptionsView,
)

# Upload
from .upload_view import AuditUploadView

# Batch
from .batch_views import AuditBatchListView, AuditBatchDetailView

# Retry
from .retry_view import RetrySearchView, RetryDownloadView, RetryUploadView

# Export
from .export_view import AuditExportView

# Filter options
from .filter_options_view import AuditFilterOptionsView

# Top-5
from .top_5_view import AuditReportGenerateView  # noqa: F401

__all__ = [
    # Registration
    "BuyerListCreateView",
    "BuyerDetailView",
    "FactoryListCreateView",
    "FactoryDetailView",
    "PairListCreateView",
    "PairDetailView",
    "PairOptionsView",
    # Upload
    "AuditUploadView",
    # Batch
    "AuditBatchListView",
    "AuditBatchDetailView",
    # Retry
    "RetrySearchView",
    "RetryDownloadView",
    "RetryUploadView",
    # Export
    "AuditExportView",
    # Filter options
    "AuditFilterOptionsView",
    # Top-5
    "AuditReportGenerateView",
]