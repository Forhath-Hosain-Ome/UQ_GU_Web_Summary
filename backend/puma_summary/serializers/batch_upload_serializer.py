from rest_framework import serializers


# ─────────────────────────────────────────────────────────────────────────────
#  BATCH UPLOAD  (write — multipart)
# ─────────────────────────────────────────────────────────────────────────────

class BatchUploadSerializer(serializers.Serializer):
    """
    Accepts one or more PDF files from a multipart/form-data POST.
    Validated files are passed to the view for saving + Celery dispatch.
    """
    files = serializers.ListField(
        child=serializers.FileField(
            max_length=512,
            allow_empty_file=False,
            use_url=False,
        ),
        allow_empty=False,
        error_messages={"empty": "At least one PDF file is required."},
    )

    def validate_files(self, files):
        errors = []
        for f in files:
            if not f.name.lower().endswith(".pdf"):
                errors.append(f"{f.name}: only PDF files are accepted.")
            # 50 MB per file guard
            if f.size > 50 * 1024 * 1024:
                errors.append(f"{f.name}: file exceeds the 50 MB limit.")
        if errors:
            raise serializers.ValidationError(errors)
        return files
