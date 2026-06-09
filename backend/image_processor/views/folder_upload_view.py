# backend/image_processor/views/folder_upload_view.py
import logging
import os
import uuid
from pathlib import Path

from django.conf import settings
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction

from image_processor.serializers import FolderUploadSerializer
from image_processor.models import FolderBatch
from image_processor.tasks import process_folder_task

logger = logging.getLogger(__name__)


class FolderUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes     = [MultiPartParser, FormParser]

    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except RuntimeError as e:
            if "cannot schedule new futures after interpreter shutdown" in str(e):
                return Response(
                    {"detail": "Server is shutting down"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            raise

    def post(self, request):
        files           = request.FILES.getlist("files")
        paths           = request.POST.getlist("paths") or request.POST.getlist("paths[]")
        date            = request.POST.get("date", "").strip()
        style           = request.POST.get("style", "").strip()
        is_renamed_file = request.POST.get("is_renamed_file") == "true"

        paths = [p.replace("\\", "/") for p in paths]

        # ── Validate + normalize filenames via serializer ─────────────────
        serializer = FolderUploadSerializer(
            data={
                "files":           files,
                "paths":           paths,
                "style":           style,
                "is_renamed_file": is_renamed_file,
            }
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Use NORMALIZED paths from validated_data (01.jpg, 02.jpg …)
        validated_files = serializer.validated_data["files"]
        normalized_paths = serializer.validated_data["paths"]

        upload_base = Path("/tmp") / "batch_uploads"
        upload_base.mkdir(parents=True, exist_ok=True)
        temp_dir = str(upload_base / str(uuid.uuid4()))

        try:
            # ── Save files with normalized names, preserving folder structure ──
            for file_obj, relative_path in zip(validated_files, normalized_paths):
                # Strip leading slashes/dots — already clean from serializer
                safe_path = os.path.normpath(relative_path).lstrip(os.sep)
                full_path = os.path.join(temp_dir, safe_path)

                os.makedirs(os.path.dirname(full_path), exist_ok=True)

                with open(full_path, "wb+") as dest:
                    for chunk in file_obj.chunks():
                        dest.write(chunk)

            # ── Discover folders ──────────────────────────────────────────
            folders = [
                f for f in os.listdir(temp_dir)
                if os.path.isdir(os.path.join(temp_dir, f))
            ]

            if not folders:
                # Flat upload — move all files into one named folder
                default_folder_name = style or "uploaded"
                default_folder_path = os.path.join(temp_dir, default_folder_name)
                os.makedirs(default_folder_path, exist_ok=True)

                for item in os.listdir(temp_dir):
                    item_path = os.path.join(temp_dir, item)
                    if os.path.isfile(item_path):
                        os.rename(item_path, os.path.join(default_folder_path, item))

                folders = [default_folder_name]

            # ── Create FolderBatch ────────────────────────────────────────
            batch = FolderBatch.objects.create(
                created_by    = request.user,
                total_folders = len(folders),
                status        = FolderBatch.Status.PENDING,
                source_folder = temp_dir,
            )

            # ── Fire Celery task after DB commit ──────────────────────────
            def on_commit_callback():
                result = process_folder_task.delay(
                    batch.id, temp_dir, date,
                    is_renamed_file=is_renamed_file,
                )
                batch.celery_task_id = result.id
                batch.save(update_fields=["celery_task_id"])
                logger.info(
                    "Folder upload | batch #%s | user: %s | folders: %s | task: %s",
                    batch.id, request.user.username, folders, result.id,
                )

            transaction.on_commit(on_commit_callback)

            return Response(
                {
                    "batch_id":      batch.id,
                    "total_folders": len(folders),
                    "message": (
                        f"Uploaded {len(files)} file(s) into "
                        f"{len(folders)} folder(s). Processing started."
                    ),
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as exc:
            logger.exception("Folder upload error: %s", exc)
            try:
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass
            return Response(
                {"error": f"Upload failed: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )