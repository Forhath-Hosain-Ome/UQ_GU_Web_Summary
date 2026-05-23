
---

## Step 1 — What was built and why

### `buyer.py`
Simple model with `name` (unique), `code` (short identifier for report numbers), `is_active`. One buyer has many factories via FK on Factory.

### `factory.py`
`Factory` belongs to one `Buyer` via FK. `unique_together = (buyer, name)` — the same factory name can exist under different buyers. No `report_type` here — that lives on the pair, not the factory alone.

### `buyer_factory_pair.py` — the central record
This is the key design decision. It holds:
- `report_type` — fixed choices (`KNIT_35`, `WOVEN_37`, `WOVEN_78`, `SWEATER_37`). One factory has one format — enforced by `unique_together = (buyer, factory)`.
- `available_reports` — JSON list of allowed inspection types (`FINAL`, `RE_FINAL`, `INLINE`, `SAMPLE`, `CMF`). Validated in `clean()` against `AvailableReport` choices.
- `template_file` property — derives the correct `.xlsx` filename from `report_type`, used by both upload and export.
- `defect_column_count` property — derives `35 / 37 / 78` for the extractor to use.
- `clean()` also validates that `factory.buyer == pair.buyer` so you can't create a cross-buyer pair.

### `upload_batch.py`
- `pair` FK replaces `format_type`. Everything the task needs (extractor class, template) comes from `pair`.
- `inspection_date` — set by the user at upload, applied to every report. No date extraction from Excel.
- `format_type` survives as a `@property` derived from `pair.report_type` for backward compatibility with any existing code that reads it.

### `audit_report.py`
- `factory` and `client` still stored as plain text for display and querying.
- `factory_extracted` and `client_extracted` — what was actually found in the Excel file. The task compares these against `batch.pair.factory.name` and `batch.pair.buyer.name` and writes any mismatch to `cross_check_warnings` (non-blocking).
- `date_of_issue` always comes from `batch.inspection_date`.
- `pair`, `report_type`, `template_file` are `@property` passthrough to the batch — no duplication.

### `migrations/0002`
- Creates Buyer, Factory, BuyerFactoryPair.
- Adds `pair` (nullable during migration) and `inspection_date` to UploadBatch, removes `format_type`.
- Adds `factory_extracted`, `client_extracted`, `cross_check_warnings` to AuditReport.

### `admin.py`
- Factory inline under Buyer — register both in one place.
- BuyerFactoryPair shows `template_file` and `defect_column_count` as readonly computed fields.
- UploadBatch shows progress with colour coding.
- AuditReport shows cross-check fields and defect entries inline.

---