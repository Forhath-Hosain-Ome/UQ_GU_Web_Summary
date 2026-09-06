# backend/image_processor/views/folder_upload_view.py
import logging
import os
import uuid
from pathlib import Path, PurePosixPath

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction

from image_processor.serializers import FolderUploadSerializer
from image_processor.models import FolderBatch
from image_processor.tasks import process_folder_task
from utils import normalize_filename
from image_processor.upload_paths import (
    contained_upload_path,
    validate_upload_destinations,
)

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

        validated_files = serializer.validated_data["files"]
        normalized_paths = serializer.validated_data["paths"]
        style = serializer.validated_data["style"]

        # Preserve the existing saved filenames and logical folder identities.
        # Plan flat uploads in their final folder, eliminating unsafe renames.
        destinations = [
            str(PurePosixPath(path).parent / normalize_filename(file_obj.name))
            for file_obj, path in zip(validated_files, normalized_paths)
        ]
        if all("/" not in path for path in destinations):
            destinations = [f"{style or 'uploaded'}/{path}" for path in destinations]
        validate_upload_destinations(destinations)

        upload_base = Path("/tmp") / "batch_uploads"
        upload_base.mkdir(parents=True, exist_ok=True)
        root = upload_base.resolve() / str(uuid.uuid4())
        temp_dir = str(root)
        root_created = False

        try:
            # Never reuse a pre-existing directory or follow a planted root link.
            root.mkdir(mode=0o700)
            root_created = True
            for file_obj, relative_path in zip(validated_files, destinations):
                full_path = contained_upload_path(root, relative_path)
                full_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                full_path = contained_upload_path(root, relative_path)
                # Exclusive creation refuses existing files and final symlinks.
                with open(full_path, "xb") as dest:
                    for chunk in file_obj.chunks():
                        dest.write(chunk)

            # ── Discover folders ──────────────────────────────────────────
            folders = [
                f for f in os.listdir(temp_dir)
                if os.path.isdir(os.path.join(temp_dir, f))
            ]

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
                if root_created:
                    shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass
            if isinstance(exc, (ValidationError, FileExistsError)):
                return Response(
                    {"detail": "Invalid or conflicting upload destination."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {"error": f"Upload failed: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
