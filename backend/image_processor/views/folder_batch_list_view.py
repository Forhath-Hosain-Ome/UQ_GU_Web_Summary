import logging
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
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

    def get_queryset(self):
        return (
            FolderBatch.objects
            .filter(created_by=self.request.user)
            .select_related("created_by")
        )
