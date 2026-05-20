"""
-----------------------
One row per successfully extracted Excel audit file.

Key changes from old model
---------------------------
- batch FK gives access to pair → buyer, factory, report_type.
- date_of_issue is always set from batch.inspection_date (user input),
  never extracted from the Excel file.
- factory / client are still stored as plain text for display and
  cross-checking against the registered pair names.
"""

from django.db import models
from shared.models import BaseModel
from .upload_batch import UploadBatch


class AuditReport(BaseModel):
    """One extracted Excel audit file linked to its upload batch."""

    batch = models.ForeignKey(
        UploadBatch,
        on_delete=models.CASCADE,
        related_name="reports",
    )

    # Source file
    file_name = models.CharField(max_length=512, db_index=True)

    # ── Cross-check fields (extracted, compared against pair registration) ────
    # These are extracted from the Excel and compared against batch.pair.
    # A mismatch produces a validation_warning, not a blocking error.
    factory_extracted = models.CharField(
        max_length=255, blank=True,
        help_text="Factory name as extracted from Excel (for cross-check).",
    )
    client_extracted = models.CharField(
        max_length=255, blank=True,
        help_text="Client/buyer name as extracted from Excel (for cross-check).",
    )

    # ── Identity / header ─────────────────────────────────────────────────────
    # factory / client stored for display — sourced from pair at save time
    factory         = models.CharField(max_length=255, blank=True, db_index=True)
    client          = models.CharField(max_length=255, blank=True, db_index=True)

    # date_of_issue is ALWAYS set from batch.inspection_date
    date_of_issue   = models.DateField(null=True, blank=True, db_index=True)
    inspection_type = models.CharField(max_length=100, blank=True)
    report_no       = models.CharField(max_length=100, blank=True)
    audit_report    = models.CharField(max_length=100, blank=True)
    item_name       = models.CharField(max_length=512, blank=True)
    style_no        = models.CharField(max_length=100, blank=True, db_index=True)
    po_no           = models.CharField(max_length=100, blank=True, db_index=True)
    country         = models.CharField(max_length=100, blank=True)

    # ── Time fields ────────────────────────────────────────────────────────────
    factory_in_time     = models.CharField(max_length=20, blank=True)
    factory_out_time    = models.CharField(max_length=20, blank=True)
    factory_total_hours = models.CharField(max_length=20, blank=True)
    audit_start_time    = models.CharField(max_length=20, blank=True)
    audit_end_time      = models.CharField(max_length=20, blank=True)
    audit_total_hours   = models.CharField(max_length=20, blank=True)

    # ── Audit outcome ──────────────────────────────────────────────────────────
    audit_result = models.CharField(max_length=20, blank=True, default="-")

    # ── Quantity fields ────────────────────────────────────────────────────────
    po_qty      = models.CharField(max_length=50, blank=True)
    po_qty_pcs  = models.PositiveIntegerField(default=0)
    po_qty_pack = models.PositiveIntegerField(default=0)
    po_qty_set  = models.PositiveIntegerField(default=0)
    do_qty      = models.PositiveIntegerField(default=0)
    ship_qty    = models.CharField(max_length=50, blank=True)
    audit_qty   = models.CharField(max_length=50, blank=True)

    # ── Shipment dates ─────────────────────────────────────────────────────────
    exf      = models.DateField(null=True, blank=True)
    po_edt   = models.DateField(null=True, blank=True)
    po_wh    = models.DateField(null=True, blank=True)
    plan_edt = models.DateField(null=True, blank=True)
    plan_wh  = models.DateField(null=True, blank=True)

    # ── Defect summary ─────────────────────────────────────────────────────────
    defect_qty            = models.CharField(max_length=20, blank=True)
    acceptable_defect_qty = models.CharField(max_length=20, blank=True, default="-")
    defect_percentage     = models.CharField(max_length=20, blank=True)

    # ── Personnel ──────────────────────────────────────────────────────────────
    person    = models.CharField(max_length=255, blank=True)
    inspector = models.CharField(max_length=255, blank=True)

    # ── Additional checks ──────────────────────────────────────────────────────
    carton          = models.CharField(max_length=512, blank=True)
    needle_detector = models.CharField(max_length=512, blank=True)
    remarks         = models.TextField(blank=True)
    do_set_col_size = models.CharField(max_length=512, blank=True)
    do_note         = models.TextField(blank=True)

    # ── Validation ─────────────────────────────────────────────────────────────
    has_validation_errors = models.BooleanField(default=False)
    validation_errors     = models.TextField(blank=True)
    blocking_errors       = models.TextField(blank=True)

    # Cross-check warning: factory/client in Excel ≠ registered pair names
    cross_check_warnings  = models.TextField(blank=True)

    # ── DO plan (JSON) ─────────────────────────────────────────────────────────
    do_orders_json = models.TextField(blank=True, default="[]")

    class Meta:
        ordering = ["-date_of_issue", "factory", "style_no"]
        verbose_name = "Audit Report"
        verbose_name_plural = "Audit Reports"

    def __str__(self) -> str:
        return (
            f"{self.factory} | {self.style_no} | {self.date_of_issue} "
            f"| {self.inspection_type}"
        )

    # ── Convenience accessors via batch.pair ──────────────────────────────────

    @property
    def pair(self):
        return self.batch.pair

    @property
    def report_type(self) -> str:
        return self.batch.pair.report_type

    @property
    def template_file(self) -> str:
        return self.batch.pair.template_file