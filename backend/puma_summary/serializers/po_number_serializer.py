from rest_framework import serializers
from puma_summary.models import PONumber


# ─────────────────────────────────────────────────────────────────────────────
#  PO NUMBER
# ─────────────────────────────────────────────────────────────────────────────

class PONumberSerializer(serializers.ModelSerializer):
    class Meta:
        model  = PONumber
        fields = ["id", "number"]
