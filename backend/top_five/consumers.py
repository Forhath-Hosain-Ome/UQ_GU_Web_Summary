import json
import logging
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


class Top5JobProgressConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        user = self.scope.get("user")
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            await self.close(code=4401)
            return
        self.job_pk = self.scope["url_route"]["kwargs"]["pk"]
        self.group_name = f"top5_job_{self.job_pk}"
        exists = await self._job_exists(self.job_pk)
        if not exists:
            await self.close(code=4404)
            return
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        snapshot = await self._get_snapshot(self.job_pk)
        if snapshot:
            await self.send(text_data=json.dumps(snapshot))

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        pass

    async def top5_progress(self, event):
        await self.send(text_data=json.dumps({
            "event": "progress", "job_id": event["job_id"],
            "status": event["status"], "stage": event.get("stage", ""),
            "progress_percent": event.get("progress_percent", 0),
        }))

    async def top5_complete(self, event):
        await self.send(text_data=json.dumps({
            "event": "complete", "job_id": event["job_id"],
            "status": event["status"], "progress_percent": 100,
        }))

    async def top5_error(self, event):
        await self.send(text_data=json.dumps({
            "event": "error", "job_id": event["job_id"],
            "status": "FAILED", "error_message": event.get("error_message", "Unknown error"),
        }))

    @database_sync_to_async
    def _job_exists(self, pk):
        from top_five.models import Top5Job
        return Top5Job.objects.filter(pk=pk).exists()

    @database_sync_to_async
    def _get_snapshot(self, pk):
        from top_five.models import Top5Job
        try:
            job = Top5Job.objects.get(pk=pk)
        except Top5Job.DoesNotExist:
            return None
        done = job.status in (Top5Job.Status.DONE, Top5Job.Status.FAILED)
        base = {"job_id": job.pk, "status": job.status, "input_file": job.input_file}
        if done:
            return {**base, "event": "complete" if job.status == Top5Job.Status.DONE else "error", "error": job.error}
        return {**base, "event": "progress", "stage": "", "progress_percent": 0}