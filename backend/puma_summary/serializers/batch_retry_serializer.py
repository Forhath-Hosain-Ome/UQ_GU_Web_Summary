from rest_framework import serializers
from puma_summary.models import InspectionBatch

# ─────────────────────────────────────────────────────────────────────────────
#  BATCH RETRY  (write)
# ─────────────────────────────────────────────────────────────────────────────

class BatchRetrySerializer(serializers.Serializer):
    """
    Triggers a retry run for the failed PDFs of an existing batch.
    No body fields required — the batch pk comes from the URL.
    Validates that the batch actually has retryable failures.
    """

    def validate(self, attrs):
        batch = self.context.get("batch")
        if batch is None:
            raise serializers.ValidationError("Batch context is required.")

        if batch.status == InspectionBatch.Status.PROCESSING:
            raise serializers.ValidationError(
                "Batch is currently processing — wait for it to finish before retrying."
            )

        unretried = batch.failed_pdfs.filter(retried=False)
        if not unretried.exists():
            raise serializers.ValidationError(
                "No unretried failed PDFs found for this batch."
            )

        attrs["unretried_qs"] = unretried
        return attrs
