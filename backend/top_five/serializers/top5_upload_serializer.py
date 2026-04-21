"""
Serializer for file upload requests.
Validates Excel files before processing.
"""
from rest_framework import serializers


class Top5UploadSerializer(serializers.Serializer):
    """
    Validates uploaded Excel files.
    Accepts .xlsx or .xls files only.
    """
    file = serializers.FileField(
        required=True,
        help_text="Excel file (.xlsx or .xls) to process"
    )
    
    def validate_file(self, value):
        """
        Validate that uploaded file is an Excel file.
        """
        allowed_extensions = ('.xlsx', '.xls')
        filename = value.name.lower()
        
        if not filename.endswith(allowed_extensions):
            raise serializers.ValidationError(
                f"Only {', '.join(allowed_extensions)} files are accepted."
            )
        
        # Max 50 MB
        max_size = 50 * 1024 * 1024
        if value.size > max_size:
            raise serializers.ValidationError(
                f"File size exceeds the {max_size / (1024 * 1024):.0f} MB limit."
            )
        
        return value
