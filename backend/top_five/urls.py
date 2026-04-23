from django.urls import path
from top_five.views import Top5UploadView, Top5JobStatusView, Top5DownloadView

app_name = "top5"

urlpatterns = [
    # POST  multipart/form-data, field "file" (.xlsx)
    path("upload/",                  Top5UploadView.as_view(),     name="upload"),

    # GET   job status — poll until DONE or FAILED
    path("jobs/<int:pk>/",           Top5JobStatusView.as_view(),  name="job_status"),

    # GET   download result Excel (only valid ~5 min after DONE)
    path("jobs/<int:pk>/download/",  Top5DownloadView.as_view(),   name="download"),
]