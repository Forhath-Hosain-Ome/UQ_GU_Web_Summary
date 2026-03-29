import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  JWT AUTH MIDDLEWARE FOR DJANGO CHANNELS
#
#  Usage in asgi.py:
#      application = JWTAuthMiddleware(
#          URLRouter(websocket_urlpatterns)
#      )
#
#  React connects with:
#      const ws = new WebSocket(`ws://host/ws/batches/${id}/progress/?token=${accessToken}`)
#
#  The middleware resolves the JWT access token from the query string,
#  validates it with simplejwt, and sets scope["user"] before the consumer
#  is instantiated — so the consumer only needs to check
#  `self.scope["user"].is_authenticated`.
# ─────────────────────────────────────────────────────────────────────────────


@database_sync_to_async
def _get_user_from_token(token_key: str):
    """
    Validate a simplejwt access token and return the corresponding User.
    Returns AnonymousUser on any failure.
    """
    from django.contrib.auth.models import User
    from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
    from rest_framework_simplejwt.tokens import AccessToken

    try:
        token    = AccessToken(token_key)
        user_id  = token["user_id"]
        return User.objects.get(pk=user_id)
    except (InvalidToken, TokenError) as exc:
        logger.debug("WS JWT invalid: %s", exc)
        return AnonymousUser()
    except User.DoesNotExist:
        logger.debug("WS JWT user_id not found.")
        return AnonymousUser()
    except Exception as exc:
        logger.warning("WS JWT unexpected error: %s", exc)
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """
    Channels middleware that reads ?token=<jwt> from the WS handshake query
    string and populates scope["user"].

    Must wrap the URLRouter in asgi.py — NOT the Django ASGI app.
    """

    async def __call__(self, scope, receive, send):
        # Only run for WebSocket connections
        if scope["type"] == "websocket":
            query_string = scope.get("query_string", b"").decode()
            params       = parse_qs(query_string)
            token_list   = params.get("token", [])

            if token_list:
                scope["user"] = await _get_user_from_token(token_list[0])
            else:
                scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)