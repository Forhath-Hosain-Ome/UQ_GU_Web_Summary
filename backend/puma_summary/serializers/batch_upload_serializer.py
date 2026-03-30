from rest_framework import serializers

# Maximum file size: 50MB
MAX_FILE_SIZE = 50 * 1024 * 1024


# ─────────────────────────────────────────────────────────────────────────────
#  BATCH UPLOAD  (write — multipart)
# ─────────────────────────────────────────────────────────────────────────────

class BatchUploadSerializer(serializers.Serializer):
    """
    Validates files pulled from request.FILES.getlist("files").
    DRF ListField(child=FileField) cannot traverse Django's MultiValueDict
    from multipart requests, so the view passes the list explicitly.
 
    Usage in view:
        files = request.FILES.getlist("files")
        s = BatchUploadSerializer(data={"files": files})
        s.is_valid(raise_exception=True)
        files = s.validated_data["files"]
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
            if f.size > MAX_FILE_SIZE:
                errors.append(f"{f.name}: exceeds the 50 MB limit.")
        if errors:
            raise serializers.ValidationError(errors)
        return files