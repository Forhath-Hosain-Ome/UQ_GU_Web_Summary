from django.db import models
from django.contrib.auth.models import User
from shared.models import BaseModel
from .upload_batch import UploadBatch


class AuditReport(BaseModel):
    """
    One row per successfully extracted Excel audit file.
    Stores all fields from AuditRecord in a fully relational Django model.
    Lookup fields (factory, client, style_no, po_no, country) are stored
    as plain text — they are the "dimension" values used for filtering.
    """

    batch = models.ForeignKey(
        UploadBatch, on_delete=models.CASCADE, related_name="reports",
    )

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="audit_reports",
    )

    # Source file
    file_name = models.CharField(max_length=512, db_index=True)

    # ── Identity / header ─────────────────────────────────────────────────────
    factory         = models.CharField(max_length=255, blank=True, db_index=True)
    client          = models.CharField(max_length=255, blank=True, db_index=True)
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
    po_qty      = models.CharField(max_length=50, blank=True)   # raw string e.g. "1200 PCS"
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
    validation_errors     = models.TextField(blank=True)   # comma-joined
    blocking_errors       = models.TextField(blank=True)   # comma-joined

    # ── DO plan (JSON) ─────────────────────────────────────────────────────────
    # Stored as JSON text — preserves the list-of-dicts structure from AuditRecord
    do_orders_json = models.TextField(blank=True, default="[]")

    class Meta:
        ordering = ["-date_of_issue", "factory", "style_no"]
        verbose_name = "Audit Report"
        verbose_name_plural = "Audit Reports"

    def __str__(self):
        return f"{self.factory} | {self.style_no} | {self.date_of_issue}"