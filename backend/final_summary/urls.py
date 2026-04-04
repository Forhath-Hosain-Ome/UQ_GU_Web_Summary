from django.urls import path

from final_summary.views import (
    FinalSummaryExcelUploadView,
    FinalSummaryExportView,
    FinalSummaryFilterOptionsView,
)

app_name = "final_summary"

urlpatterns = [
    path("uploads/excel/", FinalSummaryExcelUploadView.as_view(), name="excel_upload"),
    path("reports/export/", FinalSummaryExportView.as_view(), name="report_export"),
    path("options/", FinalSummaryFilterOptionsView.as_view(), name="filter_options"),
]


