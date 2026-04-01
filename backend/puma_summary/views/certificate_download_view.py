# import logging
# import tempfile
# from pathlib import Path
# from django.conf import settings
# from django.http import FileResponse, Http404
# from django.utils import timezone
# from rest_framework import status
# from rest_framework.permissions import IsAuthenticated
# from rest_framework.response import Response
# from rest_framework.views import APIView
# from puma_summary.models import (
#     CertificateLog,
#     InspectionReport,
# )

# logger = logging.getLogger(__name__)


# # ─────────────────────────────────────────────────────────────────────────────
# #     CERTIFICATE DOWNLOAD
# #     GET /api/reports/<pk>/certificate/
# #     Generates DOCX on-demand, streams it, deletes from disk.
# #     Logs the event in CertificateLog (permanent DB record).
# # ─────────────────────────────────────────────────────────────────────────────

# class CertificateDownloadView(APIView):
#     permission_classes = [IsAuthenticated]

#     def get(self, request, pk):
#         from services.certificate import generate_certificate

#         try:
#             report = (
#                 InspectionReport.objects
#                 .prefetch_related("po_numbers")
#                 .get(pk=pk)
#             )
#         except InspectionReport.DoesNotExist:
#             return Response({"detail": "Report not found."}, status=status.HTTP_404_NOT_FOUND)

#         puma          = settings.PUMA_SETTINGS
#         template_path = Path(puma["CERTIFICATE_TEMPLATE_PATH"])
#         if not template_path.exists():
#             raise Http404("Certificate template not found on server.")

#         record = {
#             "style":           report.style,
#             "inspection_date": str(report.inspection_date or ""),
#             "po_qty":          report.po_qty,
#             "actual_qty":      report.actual_qty,
#             "inspected_qty":   report.inspected_qty,
#             "factory_name":    report.factory_name,
#             "factory_code":    report.factory_code,
#             "final_customer":  report.final_customer,
#             "po_numbers":      list(report.po_numbers.values_list("number", flat=True)),
#         }

#         with tempfile.TemporaryDirectory() as tmp_dir:
#             cert_path = generate_certificate(record, template_path, Path(tmp_dir))

#             log_entry = CertificateLog.objects.create(
#                 report=report,
#                 generated_by=request.user.username,
#             )

#             cert_bytes = cert_path.read_bytes()
#             filename   = cert_path.name

#         log_entry.downloaded_at = timezone.now()
#         log_entry.save(update_fields=["downloaded_at"])

#         logger.info(
#             "Certificate served: %s (report #%s) | user: %s",
#             filename, pk, request.user.username,
#         )

#         # Validate file size to prevent memory issues
#         if len(cert_bytes) > 10 * 1024 * 1024:  # 10MB limit
#             logger.warning("Certificate file too large: %s bytes", len(cert_bytes))
#             return Response(
#                 {"detail": "Generated certificate is too large."},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             )

#         response = FileResponse(
#             iter([cert_bytes]),
#             as_attachment=True,
#             filename=filename,
#             content_type=(
#                 "application/vnd.openxmlformats-officedocument"
#                 ".wordprocessingml.document"
#             ),
#         )
#         return response
import logging
import tempfile
from pathlib import Path
from django.conf import settings
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from puma_summary.models import CertificateLog, InspectionReport

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#     CERTIFICATE DOWNLOAD
#     GET /api/reports/<pk>/certificate/
#     Generates DOCX on-demand, streams it, deletes from disk.
#     Logs the event in CertificateLog (permanent DB record).
#
#     The certificate filename uses report.report_date (fixed at report
#     creation time) — NOT the current datetime — so the filename is stable
#     across multiple downloads.
# ─────────────────────────────────────────────────────────────────────────────

class CertificateDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from services.certificate import generate_certificate

        try:
            report = (
                InspectionReport.objects
                .prefetch_related("po_numbers")
                .get(pk=pk)
            )
        except InspectionReport.DoesNotExist:
            return Response({"detail": "Report not found."}, status=status.HTTP_404_NOT_FOUND)

        puma          = settings.PUMA_SETTINGS
        template_path = Path(puma["CERTIFICATE_TEMPLATE_PATH"])
        if not template_path.exists():
            raise Http404("Certificate template not found on server.")

        record = {
            "style":           report.style,
            "inspection_date": str(report.inspection_date or ""),
            "report_date":     str(report.report_date),   # fixed — not datetime.now()
            "po_qty":          report.po_qty,
            "actual_qty":      report.actual_qty,
            "inspected_qty":   report.inspected_qty,
            "factory_name":    report.factory_name,
            "factory_code":    report.factory_code,
            "final_customer":  report.final_customer,
            "po_numbers":      list(report.po_numbers.values_list("number", flat=True)),
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            cert_path = generate_certificate(record, template_path, Path(tmp_dir))

            log_entry = CertificateLog.objects.create(
                report=report,
                generated_by=request.user.username,
            )

            cert_bytes = cert_path.read_bytes()
            filename   = cert_path.name

        log_entry.downloaded_at = timezone.now()
        log_entry.save(update_fields=["downloaded_at"])

        logger.info(
            "Certificate served: %s (report #%s) | user: %s",
            filename, pk, request.user.username,
        )

        if len(cert_bytes) > 10 * 1024 * 1024:  # 10 MB guard
            logger.warning("Certificate file too large: %s bytes", len(cert_bytes))
            return Response(
                {"detail": "Generated certificate is too large."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return FileResponse(
            iter([cert_bytes]),
            as_attachment=True,
            filename=filename,
            content_type=(
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            ),
        )