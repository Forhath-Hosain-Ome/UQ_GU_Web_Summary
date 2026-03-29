"""
ASGI config for summary_backend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application


from puma_summary.middleware import JWTAuthMiddleware
from puma_summary.routing import websocket_urlpatterns

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'summary_backend.settings')

application = get_asgi_application()


application = ProtocolTypeRouter(
    {
        # ── HTTP ──────────────────────────────────────────────────────────
        "http": django_asgi_app,

        # ── WebSocket ─────────────────────────────────────────────────────
        # AllowedHostsOriginValidator  → rejects connections from unknown origins
        # JWTAuthMiddleware            → resolves scope["user"] from ?token=
        # URLRouter                   → routes to the correct consumer
        "websocket": AllowedHostsOriginValidator(
            JWTAuthMiddleware(
                URLRouter(websocket_urlpatterns)
            )
        ),
    }
)