import logging
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from image_processor.models import FolderBatch
from image_processor.serializers import FolderBatchListSerializer

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#     FOLDER BATCH LIST
#     GET /api/folder/batches/
#     Paginated list of all folder batches for the authenticated user.
# ─────────────────────────────────────────────────────────────────────────────

class FolderBatchListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class   = FolderBatchListSerializer

    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except RuntimeError as e:
            if "cannot schedule new futures after interpreter shutdown" in str(e):
                return Response({"detail": "Server is shutting down"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            else:
                raise

    def get_queryset(self):
        try:
            return (
                FolderBatch.objects
                .filter(created_by=self.request.user)
                .select_related("created_by")
            )
        except RuntimeError as e:
            if "cannot schedule new futures after interpreter shutdown" in str(e):
                return FolderBatch.objects.none()
            else:
                raise

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except RuntimeError as e:
            if "cannot schedule new futures after interpreter shutdown" in str(e):
                return Response([], status=status.HTTP_200_OK)
            else:
                raise
