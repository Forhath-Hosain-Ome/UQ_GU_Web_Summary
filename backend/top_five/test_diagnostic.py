"""
Diagnostic test for Top5 upload flow - checks for permission and stuck job issues.

Usage:
    python manage.py shell < test_top5_flow.py
    
Or in Django shell:
    >>> from django.core.management import execute_from_command_line
    >>> exec(open('test_top5_flow.py').read())
"""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'summary_backend.settings')

import django
django.setup()

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from rest_framework.test import APIClient
from top_five.models import Top5Job
import json

print("=" * 80)
print("TOP-5 UPLOAD FLOW DIAGNOSTIC TEST")
print("=" * 80)

# Test 1: Authentication
print("\n[TEST 1] Authentication Check")
print("-" * 80)

client = APIClient()

# Try to upload without authentication
print("→ Testing upload WITHOUT authentication...")
response = client.post('/api/top5/upload/', {}, format='multipart')
if response.status_code == 401:
    print("✓ PASS: Returns 401 (Unauthorized)")
else:
    print(f"✗ FAIL: Expected 401, got {response.status_code}")
    print(f"  Response: {response.data}")

# Create test user
test_user = User.objects.filter(username='test_user').first()
if not test_user:
    test_user = User.objects.create_user(
        username='test_user',
        email='test@example.com',
        password='testpass123'
    )
    print(f"✓ Created test user: {test_user.username}")
else:
    print(f"✓ Using existing test user: {test_user.username}")

# Authenticate client
client.force_authenticate(user=test_user)
print("✓ Client authenticated")

# Test 2: File Validation
print("\n[TEST 2] File Validation")
print("-" * 80)

# Try to upload invalid file type
print("→ Testing upload with INVALID file type (txt)...")
response = client.post(
    '/api/top5/upload/',
    {'file': ContentFile(b'test content', name='test.txt')},
    format='multipart'
)
if response.status_code == 400:
    print("✓ PASS: Returns 400 for invalid file type")
    print(f"  Error: {response.data}")
else:
    print(f"✗ FAIL: Expected 400, got {response.status_code}")

# Try to upload valid file (create minimal Excel-like file)
print("→ Testing upload with VALID file type (xlsx)...")
try:
    import openpyxl
    from io import BytesIO
    
    # Create a minimal Excel workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws['A1'] = "Test"
    
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    xlsx_content = buffer.getvalue()
    
    response = client.post(
        '/api/top5/upload/',
        {'file': ContentFile(xlsx_content, name='test.xlsx')},
        format='multipart'
    )
    
    if response.status_code == 201:
        print("✓ PASS: Returns 201 (Created)")
        data = response.json()
        job_id = data.get('job_id')
        print(f"  Job ID: {job_id}")
        print(f"  Status: {data.get('status')}")
        
        # Test 3: Job Status Polling
        print("\n[TEST 3] Job Status Polling")
        print("-" * 80)
        
        response = client.get(f'/api/top5/jobs/{job_id}/')
        if response.status_code == 200:
            print("✓ PASS: Returns 200 (OK)")
            job_data = response.json()
            print(f"  Status: {job_data.get('status')}")
            print(f"  Created at: {job_data.get('created_at')}")
            
            # Verify job status is PENDING (not PROCESSING immediately)
            if job_data.get('status') == 'PENDING':
                print("✓ PASS: Job status is PENDING (Celery task queued)")
            else:
                print(f"⚠ WARNING: Expected PENDING, got {job_data.get('status')}")
        else:
            print(f"✗ FAIL: Expected 200, got {response.status_code}")
    else:
        print(f"✗ FAIL: Expected 201, got {response.status_code}")
        print(f"  Response: {response.data}")
        
except ImportError:
    print("⚠ SKIP: openpyxl not installed")

# Test 4: Permission Control
print("\n[TEST 4] Permission Control (Job Isolation)")
print("-" * 80)

# Create another user
other_user = User.objects.filter(username='other_user').first()
if not other_user:
    other_user = User.objects.create_user(
        username='other_user',
        email='other@example.com',
        password='otherpass123'
    )
    print(f"✓ Created other user: {other_user.username}")

# Get first job created by test_user
test_job = Top5Job.objects.filter(created_by=test_user).first()
if test_job:
    print(f"→ Testing access to Job #{test_job.pk} by different user...")
    
    # Try to access with other_user
    other_client = APIClient()
    other_client.force_authenticate(user=other_user)
    response = other_client.get(f'/api/top5/jobs/{test_job.pk}/')
    
    if response.status_code == 404:
        print("✓ PASS: Permission check works - other user cannot access")
    else:
        print(f"✗ FAIL: Expected 404, got {response.status_code}")
else:
    print("⚠ SKIP: No test job available")

# Test 5: Stuck Job Detection
print("\n[TEST 5] Stuck Job Detection")
print("-" * 80)

from top_five.utils.health_monitor import Top5HealthMonitor
from django.utils import timezone
from datetime import timedelta

# Create a manually stuck job for testing
stuck_job = Top5Job.objects.create(
    created_by=test_user,
    input_file='stuck_test.xlsx',
    status=Top5Job.Status.PROCESSING,
)
# Manually set updated_at to 10 minutes ago
stuck_job.updated_at = timezone.now() - timedelta(minutes=10)
stuck_job.save()

print(f"→ Created job #{stuck_job.pk} stuck in PROCESSING...")

stuck_jobs = Top5HealthMonitor.check_stuck_jobs(timeout=300)
if stuck_job.pk in [job[0] for job in stuck_jobs]:
    print("✓ PASS: Stuck job detection works")
    print(f"  Found {len(stuck_jobs)} stuck job(s)")
else:
    print("✗ FAIL: Stuck job not detected")

# Test 6: Health Report
print("\n[TEST 6] Health Report")
print("-" * 80)

report = Top5HealthMonitor.get_health_report()
print(f"✓ Health Report:")
print(f"  Status: {report['health'].upper()}")
print(f"  Queue: {report['queue_status']}")
print(f"  Jobs: {report['job_statistics']}")

# Cleanup
print("\n[CLEANUP]")
print("-" * 80)
stuck_job.delete()
print("✓ Cleaned up test data")

print("\n" + "=" * 80)
print("DIAGNOSTIC TEST COMPLETE")
print("=" * 80)
