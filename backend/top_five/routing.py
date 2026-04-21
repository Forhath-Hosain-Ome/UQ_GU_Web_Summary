from django.urls import re_path
from top_five.consumers import Top5JobProgressConsumer


websocket_urlpatterns = [
    re_path(r"^ws/top-five/jobs/(?P<pk>\d+)/progress/$", Top5JobProgressConsumer.as_asgi()),
]