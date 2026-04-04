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

    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except RuntimeError as e:
            if "cannot schedule new futures after interpreter shutdown" in str(e):
                return Response({"detail": "Server is shutting down"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            else:
                raise

    def post(self, request):
        try:
            files = request.FILES.getlist('files')
            # The frontend must send 'paths' as a list corresponding to each file
            paths = request.POST.getlist('paths') or request.POST.getlist('paths[]')
            # Date from calendar picker
            date = request.POST.get('date', '')
            # Optional style name
            style = request.POST.get('style', '').strip()

            paths = [p.replace('\\', '/') for p in paths]
            serializer = FolderUploadSerializer(data={"files": files, "paths": paths, "style": style})
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            # Create a temporary directory to store uploaded files
            temp_dir = tempfile.mkdtemp()
            
            try:
                # Save files to temporary directory maintaining folder structure
                for i, file_obj in enumerate(files):
                    relative_path = paths[i] if i < len(paths) else file_obj.name
                    relative_path = relative_path.replace('\\', '/').lstrip('./')
                    
                    # Clean path to prevent directory traversal attacks
                    safe_path = os.path.normpath(relative_path).lstrip(os.sep)
                    full_path = os.path.join(temp_dir, safe_path)
                    
                    # Ensure the subdirectories exist
                    os.makedirs(os.path.dirname(full_path), exist_ok=True)
                    
                    # Save the file
                    with open(full_path, 'wb+') as destination:
                        for chunk in file_obj.chunks():
                            destination.write(chunk)
                
                # Find folders or create fallback
                folders = [f for f in os.listdir(temp_dir) if os.path.isdir(os.path.join(temp_dir, f))]
                if not folders:
                    # No folder structure; create a single folder with all files
                    default_folder_name = style or "uploaded"
                    
                    default_folder_path = os.path.join(temp_dir, default_folder_name)
                    os.makedirs(default_folder_path, exist_ok=True)
                    
                    # Move all files to the default folder
                    for item in os.listdir(temp_dir):
                        item_path = os.path.join(temp_dir, item)
                        if os.path.isfile(item_path):
                            os.rename(item_path, os.path.join(default_folder_path, item))
                    
                    folders = [default_folder_name]
                
                # Create a FolderBatch record
                batch = FolderBatch.objects.create(
                    created_by=request.user,
                    total_folders=len(folders),
                    status=FolderBatch.Status.PENDING
                )
                
                # Fire the Celery task
                process_folder_task.delay(batch.id, temp_dir, date)
                
                return Response({
                    "batch_id": batch.id,
                    "total_folders": len(folders),
                    "message": f"Uploaded {len(files)} files into {len(folders)} folder(s)"
                })
            
            except Exception as e:
                logger.error(f"Error processing upload: {e}")
                # Clean up temp dir
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
                return Response({"error": "Failed to process upload"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        except Exception as e:
            logger.error(f"Unexpected error in upload: {e}")
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
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