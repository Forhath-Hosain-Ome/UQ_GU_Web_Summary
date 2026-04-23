"""
Management command to detect and handle stuck Top5 jobs.

Usage:
    python manage.py check_stuck_jobs [--timeout=300] [--auto-fix]
    
Options:
    --timeout=SECONDS  Time threshold for detecting stuck jobs (default: 300)
    --auto-fix         Automatically mark stuck jobs as FAILED (default: False)
"""
from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db.models import Q
from top_five.models import Top5Job
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Detect and handle Top5 jobs stuck in PROCESSING state"

    def add_arguments(self, parser):
        parser.add_argument(
            '--timeout',
            type=int,
            default=300,
            help='Timeout in seconds for detecting stuck jobs (default: 300)'
        )
        parser.add_argument(
            '--auto-fix',
            action='store_true',
            help='Automatically mark stuck jobs as FAILED'
        )

    def handle(self, *args, **options):
        timeout_seconds = options['timeout']
        auto_fix = options['auto_fix']
        
        self.stdout.write(f"Checking for jobs stuck >  {timeout_seconds}s...")

        # Find jobs stuck in PROCESSING state
        stuck_threshold = timezone.now() - timedelta(seconds=timeout_seconds)
        stuck_jobs = Top5Job.objects.filter(
            status=Top5Job.Status.PROCESSING,
            updated_at__lt=stuck_threshold
        )

        if not stuck_jobs.exists():
            self.stdout.write(self.style.SUCCESS("✓ No stuck jobs found."))
            return

        count = stuck_jobs.count()
        self.stdout.write(self.style.WARNING(f"⚠ Found {count} stuck job(s):"))

        for job in stuck_jobs:
            duration = timezone.now() - job.updated_at
            self.stdout.write(
                f"  - Job #{job.pk}: {job.input_file} "
                f"(stuck for {duration.total_seconds():.0f}s)"
            )

            if auto_fix:
                job.status = Top5Job.Status.FAILED
                job.error = (
                    f"Auto-marked as FAILED after {timeout_seconds}s timeout. "
                    "Celery worker likely crashed or hung."
                )
                job.save(update_fields=["status", "error", "updated_at"])
                logger.warning(
                    "Auto-fixed stuck job #%s: marked as FAILED", job.pk
                )
                self.stdout.write(
                    f"    → Fixed: marked as FAILED"
                )

        if auto_fix:
            self.stdout.write(
                self.style.SUCCESS(f"✓ Fixed {count} stuck job(s).")
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    "Run with --auto-fix to automatically mark these as FAILED"
                )
            )
