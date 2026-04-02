import logging
import os
import tempfile
import zipfile
from django.core.files.storage import FileSystemStorage
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from image_processor.serializers import FolderUploadSerializer
from image_processor.models import FolderBatch
from image_processor.tasks import process_folder_task

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#     FOLDER UPLOAD
#     POST /image/folder/upload/
#     Accepts multipart/form-data with key "files" (one or many image files).
#     Saves files to a temp folder on disk, creates a FolderBatch row,
#     fires the Celery task, returns the new batch id.
# ─────────────────────────────────────────────────────────────────────────────

class FolderUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes     = [MultiPartParser, FormParser]

    def post(self, request):
        files = request.FILES.getlist('files')
        # The frontend must send 'paths' as a list corresponding to each file
        paths = request.POST.getlist('paths')
        # Date from calendar picker
        date = request.POST.get('date', '')

        serializer = FolderUploadSerializer(data={"files": files, "paths": paths})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Create a temporary directory to store uploaded files
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Save files to temporary directory maintaining folder structure
            for i, file_obj in enumerate(files):
                relative_path = paths[i] if i < len(paths) else file_obj.name
                
                # Clean path to prevent directory traversal attacks
                safe_path = os.path.normpath(relative_path).lstrip(os.sep)
                full_path = os.path.join(temp_dir, safe_path)
                
                # Ensure the subdirectories exist
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                
                # Save the file
                with open(full_path, 'wb+') as destination:
                    for chunk in file_obj.chunks():
                        destination.write(chunk)
            
            # Create zip files for each folder
            folder_zip_paths = []
            for folder_name in os.listdir(temp_dir):
                folder_path = os.path.join(temp_dir, folder_name)
                if os.path.isdir(folder_path):
                    zip_path = os.path.join(temp_dir, f"{folder_name}.zip")
                    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for root, dirs, files_in_folder in os.walk(folder_path):
                            for file in files_in_folder:
                                file_path = os.path.join(root, file)
                                arcname = os.path.relpath(file_path, folder_path)
                                zipf.write(file_path, arcname)
                    folder_zip_paths.append(zip_path)
            
            if not folder_zip_paths:
                return Response(
                    {"error": "No valid folders found in uploaded files."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create a FolderBatch record
            batch = FolderBatch.objects.create(
                created_by=request.user,
                total_folders=len(folder_zip_paths),
                status=FolderBatch.Status.PENDING
            )
            
            # Fire the Celery task
            task = process_folder_task.delay(
                folder_zip_paths=folder_zip_paths,
                date=date,
                batch_id=batch.id
            )
            
            # Update batch with task ID
            batch.celery_task_id = task.id
            batch.save()
            
            logger.info(
                "Folder upload | batch #%s | user: %s | folders: %s",
                batch.id, request.user.username, len(folder_zip_paths)
            )
            
            return Response({
                "batch_id": batch.id,
                "message": f"{len(folder_zip_paths)} folder(s) uploaded successfully. Processing started.",
                "total_folders": len(folder_zip_paths)
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error("Folder upload error: %s", str(e))
            return Response(
                {"error": f"Upload failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        finally:
            # Clean up temporary directory
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)