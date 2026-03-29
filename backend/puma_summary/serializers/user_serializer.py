from rest_framework import serializers
from django.contrib.auth.models import User


# ─────────────────────────────────────────────────────────────────────────────
#  AUTH
# ─────────────────────────────────────────────────────────────────────────────

class UserSerializer(serializers.ModelSerializer):
    """Returned alongside JWT tokens on login."""

    class Meta:
        model  = User
        fields = ["id", "username", "email", "first_name", "last_name"]
        read_only_fields = fields
