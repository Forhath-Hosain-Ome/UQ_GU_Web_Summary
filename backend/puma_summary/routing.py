from django.urls import re_path
from puma_summary.consumers import BatchProgressConsumer

websocket_urlpatterns = [
    # ws://host/ws/batches/<pk>/progress/?token=<jwt>
    re_path(
        r"^ws/batches/(?P<pk>\d+)/progress/$",
        BatchProgressConsumer.as_asgi(),
    ),
]