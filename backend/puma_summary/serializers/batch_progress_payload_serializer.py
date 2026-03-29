from rest_framework import serializers
from .batch_failed_pdf_serializer import BatchFailedPDFSerializer


# ─────────────────────────────────────────────────────────────────────────────
#  WEBSOCKET PROGRESS PAYLOAD  (not a model serializer — used by the consumer)
# ─────────────────────────────────────────────────────────────────────────────

class BatchProgressPayloadSerializer(serializers.Serializer):
    """
    Validates + shapes the JSON pushed over the WebSocket channel.
    Used by the Celery task and the WS consumer to ensure consistent payloads.

    event types:
        progress  — incremental update while PROCESSING
        complete  — final summary when COMPLETED / PARTIAL / FAILED
        error     — unexpected task crash
    """
    event            = serializers.ChoiceField(choices=["progress", "complete", "error"])
    batch_id         = serializers.IntegerField()
    status           = serializers.CharField()
    stage            = serializers.CharField(allow_blank=True, default="")
    progress_percent = serializers.IntegerField(min_value=0, max_value=100)
    processed        = serializers.IntegerField(min_value=0)
    total            = serializers.IntegerField(min_value=0)
    failed           = serializers.IntegerField(min_value=0)
    success_rate     = serializers.FloatField()
    # Populated only on "complete" event
    report_count     = serializers.IntegerField(min_value=0, default=0)
    failed_details   = BatchFailedPDFSerializer(many=True, default=list)
    excel_available  = serializers.BooleanField(default=False)
    error_message    = serializers.CharField(allow_blank=True, default="")