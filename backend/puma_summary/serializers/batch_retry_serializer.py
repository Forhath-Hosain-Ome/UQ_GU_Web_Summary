from rest_framework import serializers
from puma_summary.models import InspectionBatch, BatchFailedPDF


# ─────────────────────────────────────────────────────────────────────────────
#  BATCH RETRY  (write)
# ─────────────────────────────────────────────────────────────────────────────

class BatchRetrySerializer(serializers.Serializer):
    """
    Triggers a retry for specific failed PDFs within an existing batch.

    Body (optional):
        filenames: ["file1.pdf", "file2.pdf"]   ← retry only these
        (omit or send [] to retry ALL unretried failures)

    Validates that:
      - the batch is not currently processing
      - each requested filename exists as an unretried BatchFailedPDF row
      - at least one retryable file exists
    """

    filenames = serializers.ListField(
        child=serializers.CharField(max_length=512),
        allow_empty=True,
        required=False,
        default=list,
        help_text=(
            "Specific PDF filenames to retry. "
            "Omit or send an empty list to retry all unretried failures."
        ),
    )

    def validate(self, attrs):
        batch = self.context.get("batch")
        if batch is None:
            raise serializers.ValidationError("Batch context is required.")

        if batch.status == InspectionBatch.Status.PROCESSING:
            raise serializers.ValidationError(
                "Batch is currently processing — wait for it to finish before retrying."
            )

        all_unretried = batch.batch_failed_pdfs.filter(retried=False)
        if not all_unretried.exists():
            raise serializers.ValidationError(
                "No unretried failed PDFs found for this batch."
            )

        requested = attrs.get("filenames", [])

        if requested:
            # Validate every requested filename is actually an unretried failure
            unretried_names = set(all_unretried.values_list("filename", flat=True))
            unknown = [fn for fn in requested if fn not in unretried_names]
            if unknown:
                raise serializers.ValidationError(
                    {
                        "filenames": [
                            f"Not found as an unretried failure: {fn}"
                            for fn in unknown
                        ]
                    }
                )
            unretried_qs = all_unretried.filter(filename__in=requested)
        else:
            # No filter — retry all unretried failures
            unretried_qs = all_unretried

        attrs["unretried_qs"] = unretried_qs
        return attrs