Let me plan the complete file structure first before writing any code.Here is the complete plan before we write a single line of code. Confirm before I proceed to Step 1.

---

## Step plan

**Step 1 — Models** (4 files)
- `buyer.py` — `Buyer(name, code)`
- `factory.py` — `Factory(name, code, buyer FK, report_type choices, available_reports M2M-like JSONField)`
- `buyer_factory_pair.py` — `BuyerFactoryPair(buyer FK, factory FK, report_type, available_reports, unique_together)`
- `upload_batch.py` — adds `buyer_factory_pair FK`, removes `format_type` free field (now derived from pair)
- `audit_report.py` — adds `buyer_factory_pair FK`
- `models/__init__.py` — clean exports

**Step 2 — Extraction core** (`extraction/core/`)
- `cell_grid.py` — unchanged
- `sheet_reader.py` — unchanged
- `proximity.py` — unchanged
- `normalise.py` — all value normalisation (date/time/int/float/str) in one place
- `label_map.py` — all synonyms dict (replaces `label_config.py` + `field_enums.py`)

**Step 3 — Per-field extractors** (`extraction/fields/`)
Each file exports one function: `extract(grid, path=None) -> str | None`
- `factory_name.py`, `report_no.py`, `item_name.py`, `style_no.py`, `po_no.py`
- `inspection_type.py`, `dates.py`, `times.py`, `quantities.py`
- `defects.py` (replaces `defect_extractor.py` — supports both PQC and SPI layouts)
- `personnel.py`, `do_table.py`
- `__init__.py` — exports all as a flat dict `FIELD_EXTRACTORS`

**Step 4 — Format extractors** (`extraction/formats/`)
- `base.py` — `BaseExtractor(grid, path, sheet_name)` with `extract() -> AuditRecord`
- `knit_35.py`, `woven_37.py`, `woven_78.py`, `sweater_37.py` — inherit base, override only what differs
- `__init__.py` — `FORMAT_REGISTRY = {"KNIT_35": Knit35Extractor, ...}` + `get_extractor(pair)`

**Step 5 — Validation** (`extraction/validation/`)
- `date_time.py` — date/time formatting and cleaning
- `rules.py` — field-level validation rules
- `blocking.py` — blocking validation (required fields, defect sum check)
- `__init__.py`

**Step 6 — Views** (`views/`)
- `buyer_factory_views.py` — CRUD for Buyer, Factory, BuyerFactoryPair registration
- `upload_view.py` — user selects pair + date, file upload
- `batch_views.py` — batch list/detail
- `retry_view.py` — search (date+style), last 20 list, download JSON, upload fixed JSON (3 endpoints)
- `export_view.py` — unchanged logic, pair drives template
- `filter_options_view.py` — unchanged

**Step 7 — Tasks + Utils**
- `tasks/process_audit_upload.py` — uses pair to pick extractor, injects date
- `utils/summary_writer.py` — already done
- `utils/error_json.py` — error JSON read/write
- `utils/sheet_resolver.py` — keyword-based sheet picker

---

Confirm to start Step 1, or let me know any changes to the plan.