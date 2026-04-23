"""
Health check and monitoring utilities for Top5 jobs.

Provides:
- Job status monitoring
- Celery worker health checks
- Queue depth monitoring
- Error logging and alerting
"""
import logging
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q, Count
from django.core.cache import cache
from top_five.models import Top5Job
from celery.app import current_app as celery_app

logger = logging.getLogger(__name__)


class Top5HealthMonitor:
    """Monitor Top5 job processing health and detect issues."""
    
    STUCK_JOB_TIMEOUT = 300  # 5 minutes
    CACHE_KEY_HEALTH = "top5_health_check"
    CACHE_TTL = 60  # 1 minute
    
    @classmethod
    def get_queue_status(cls):
        """Get Celery queue status."""
        try:
            inspect = celery_app.control.inspect()
            active = inspect.active()
            reserved = inspect.reserved()
            
            return {
                "active_tasks": sum(len(tasks) for tasks in (active or {}).values()),
                "reserved_tasks": sum(len(tasks) for tasks in (reserved or {}).values()),
                "workers": len(active or {}),
            }
        except Exception as exc:
            logger.error("Failed to get queue status: %s", exc)
            return {
                "active_tasks": 0,
                "reserved_tasks": 0,
                "workers": 0,
                "error": str(exc),
            }
    
    @classmethod
    def get_job_statistics(cls):
        """Get Top5 job statistics."""
        now = timezone.now()
        last_hour = now - timedelta(hours=1)
        
        stats = Top5Job.objects.aggregate(
            total_jobs=Count('id'),
            pending=Count('id', filter=Q(status=Top5Job.Status.PENDING)),
            processing=Count('id', filter=Q(status=Top5Job.Status.PROCESSING)),
            done=Count('id', filter=Q(status=Top5Job.Status.DONE)),
            failed=Count('id', filter=Q(status=Top5Job.Status.FAILED)),
            last_hour_created=Count(
                'id',
                filter=Q(created_at__gte=last_hour)
            ),
        )
        return stats
    
    @classmethod
    def check_stuck_jobs(cls, timeout=STUCK_JOB_TIMEOUT):
        """Detect jobs stuck in PROCESSING state."""
        stuck_threshold = timezone.now() - timedelta(seconds=timeout)
        stuck_jobs = Top5Job.objects.filter(
            status=Top5Job.Status.PROCESSING,
            updated_at__lt=stuck_threshold
        ).values_list('pk', 'input_file', 'updated_at')
        
        return list(stuck_jobs)
    
    @classmethod
    def check_failed_jobs_recent(cls, hours=1):
        """Get recently failed jobs."""
        threshold = timezone.now() - timedelta(hours=hours)
        failed_jobs = Top5Job.objects.filter(
            status=Top5Job.Status.FAILED,
            updated_at__gte=threshold
        ).values_list('pk', 'input_file', 'error', 'updated_at')
        
        return list(failed_jobs)
    
    @classmethod
    def get_health_report(cls):
        """Generate comprehensive health report."""
        # Get from cache if available
        cached_report = cache.get(cls.CACHE_KEY_HEALTH)
        if cached_report:
            return cached_report
        
        report = {
            "timestamp": timezone.now().isoformat(),
            "queue_status": cls.get_queue_status(),
            "job_statistics": cls.get_job_statistics(),
            "stuck_jobs": cls.check_stuck_jobs(),
            "recent_failures": cls.check_failed_jobs_recent(),
            "health": "healthy",
        }
        
        # Determine health status
        if report["stuck_jobs"]:
            report["health"] = "warning"
            logger.warning(
                "⚠ Health check: %d stuck jobs detected",
                len(report["stuck_jobs"])
            )
        
        if report["queue_status"].get("error"):
            report["health"] = "degraded"
            logger.error(
                "✗ Health check: Queue status error: %s",
                report["queue_status"]["error"]
            )
        
        # Cache the report
        cache.set(cls.CACHE_KEY_HEALTH, report, cls.CACHE_TTL)
        
        return report
    
    @classmethod
    def fix_stuck_job(cls, job_pk):
        """Attempt to fix a stuck job."""
        try:
            job = Top5Job.objects.get(pk=job_pk)
            
            if job.status != Top5Job.Status.PROCESSING:
                logger.warning("Job #%s is not in PROCESSING state", job_pk)
                return False
            
            job.status = Top5Job.Status.FAILED
            job.error = (
                "Auto-recovered from PROCESSING state timeout. "
                "Task likely crashed without updating job status."
            )
            job.save(update_fields=["status", "error", "updated_at"])
            
            logger.info("✓ Fixed stuck job #%s", job_pk)
            return True
            
        except Top5Job.DoesNotExist:
            logger.error("Job #%s not found", job_pk)
            return False
        except Exception as exc:
            logger.error("Failed to fix job #%s: %s", job_pk, exc)
            return False
