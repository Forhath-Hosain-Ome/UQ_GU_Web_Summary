from rest_framework import serializers
import os

# Maximum file size: 50MB
MAX_FILE_SIZE = 50 * 1024 * 1024

# Valid image extensions
VALID_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'}


# ─────────────────────────────────────────────────────────────────────────────
#  FOLDER UPLOAD  (write — multipart)
# ─────────────────────────────────────────────────────────────────────────────

class FolderUploadSerializer(serializers.Serializer):
    """
    Validates both the files and their relative directory paths.
    
    Usage in view:
        data = {
            "files": request.FILES.getlist("files"),
            "paths": request.POST.getlist("paths")
        }
        s = FolderUploadSerializer(data=data)
        s.is_valid(raise_exception=True)
    """
    files = serializers.ListField(
        child=serializers.FileField(
            max_length=512,
            allow_empty_file=False,
            use_url=False,
        ),
        allow_empty=False,
        error_messages={"empty": "At least one image file is required."},
    )
    # New field to capture the folder structure
    paths = serializers.ListField(
        child=serializers.CharField(max_length=1024),
        allow_empty=False,
        help_text="List of relative paths corresponding to each file."
    )

    def validate(self, data):
        files = data.get('files', [])
        paths = data.get('paths', [])
        errors = []

        # 1. Ensure parity between files and paths
        if len(files) != len(paths):
            raise serializers.ValidationError("The number of files and paths must match.")

        # 2. Validate individual files and their paths
        for f, path in zip(files, paths):
            # Extension check - only allow image files
            ext = os.path.splitext(path)[1].lower()
            if ext not in VALID_IMAGE_EXTENSIONS:
                errors.append(f"{path}: Only image files (JPG, JPEG, PNG, BMP, GIF, TIFF, WEBP) are accepted.")
            
            # Size check
            if f.size > MAX_FILE_SIZE:
                errors.append(f"{path}: Exceeds the 50 MB limit.")
            
            # Basic security check for path traversal
            if ".." in path or path.startswith("/"):
                errors.append(f"{path}: Invalid directory path.")

        if errors:
            raise serializers.ValidationError(errors)

        return data
