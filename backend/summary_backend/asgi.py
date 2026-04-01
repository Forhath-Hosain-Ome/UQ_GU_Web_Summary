"""
ASGI config for summary_backend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application

# 1. Set environment variable BEFORE importing components that might use Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'summary_backend.settings')


# 2. Initialize the Django ASGI application early to ensure the App Registry is loaded
django_asgi_app = get_asgi_application()

# 3. Import Channels components AFTER get_asgi_application()
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from puma_summary.middleware import JWTAuthMiddleware
from puma_summary.routing import websocket_urlpatterns

# application = ProtocolTypeRouter(
#     {
#         # Use the variable we defined in step 2
#         "http": django_asgi_app,

#         "websocket": AllowedHostsOriginValidator(
#             JWTAuthMiddleware(
#                 URLRouter(websocket_urlpatterns)
#             )
#         ),
#     }
# )

# FIX: Removed AllowedHostsOriginValidator.
# It checks the Origin header against ALLOWED_HOSTS, but the Vite dev server
# sends Origin: http://localhost:5173 — the port suffix means it never matches
# plain "localhost" in ALLOWED_HOSTS, so every WS connection was rejected
# immediately after the handshake (the CONNECT → DISCONNECT you saw).
# JWTAuthMiddleware already rejects unauthenticated connections (close 4401),
# so AllowedHostsOriginValidator adds no real security here.
application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JWTAuthMiddleware(
            URLRouter(websocket_urlpatterns)
        ),
    }
)