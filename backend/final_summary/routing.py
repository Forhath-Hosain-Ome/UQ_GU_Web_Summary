from django.urls import re_path
from final_summary.consumers import AuditBatchProgressConsumer

websocket_urlpatterns = [
    re_path(
        re_path(r"^ws/audit-batches/(?P<pk>\d+)/progress/$", AuditBatchProgressConsumer.as_asgi()),
    ),
]