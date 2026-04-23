import json
import logging
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


class AuditBatchProgressConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        user = self.scope.get("user")
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            await self.close(code=4401)
            return
        self.batch_pk   = self.scope["url_route"]["kwargs"]["pk"]
        self.group_name = f"audit_batch_{self.batch_pk}"
        exists = await self._batch_exists(self.batch_pk)
        if not exists:
            await self.close(code=4404)
            return
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        snapshot = await self._get_snapshot(self.batch_pk)
        if snapshot:
            await self.send(text_data=json.dumps(snapshot))

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        pass

    async def audit_progress(self, event):
        await self.send(text_data=json.dumps({
            "event": "progress", "batch_id": event["batch_id"],
            "status": event["status"], "stage": event.get("stage", ""),
            "progress_percent": event["progress_percent"],
            "processed": event["processed"], "total": event["total"], "failed": event["failed"],
        }))

    async def audit_complete(self, event):
        await self.send(text_data=json.dumps({
            "event": "complete", "batch_id": event["batch_id"],
            "status": event["status"], "progress_percent": 100,
            "processed": event["processed"], "total": event["total"],
            "failed": event["failed"], "report_count": event.get("report_count", 0),
        }))

    async def audit_error(self, event):
        await self.send(text_data=json.dumps({
            "event": "error", "batch_id": event["batch_id"],
            "status": "FAILED", "error_message": event.get("error_message", "Unknown error"),
        }))

    @database_sync_to_async
    def _batch_exists(self, pk):
        from final_summary.models import UploadBatch
        return UploadBatch.objects.filter(pk=pk).exists()

    @database_sync_to_async
    def _get_snapshot(self, pk):
        from final_summary.models import UploadBatch
        try:
            batch = UploadBatch.objects.get(pk=pk)
        except UploadBatch.DoesNotExist:
            return None
        done = batch.status in (UploadBatch.Status.COMPLETED, UploadBatch.Status.PARTIAL, UploadBatch.Status.FAILED)
        base = {"batch_id": batch.pk, "status": batch.status,
                "progress_percent": batch.progress_percent,
                "processed": batch.processed_files, "total": batch.total_files, "failed": batch.failed_files}
        if done:
            return {**base, "event": "complete", "report_count": batch.reports.count()}
        return {**base, "event": "progress", "stage": ""}