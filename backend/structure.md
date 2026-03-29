puma_inspection_platform/
│
├── config/                          # Project-level config (not app-level)
│   ├── settings/
│   │   ├── base.py                  # Shared settings (DB, Celery, logging, queues)
│   │   ├── development.py           # SQLite fallback, debug toolbar
│   │   └── production.py            # HTTPS, security headers
│   ├── celery.py                    # Celery app + autodiscovery
│   └── urls.py                      # Root URL router (each app plugs in here)
│
├── apps/
│   ├── shared/                      # Reusable across all 3 services
│   │   ├── models.py                # TimeStampedModel, SoftDeleteModel (abstract)
│   │   ├── exceptions.py            # ExtractionError, CertificateGenerationError, etc.
│   │   └── mixins.py                # AjaxResponseMixin
│   │
│   ├── puma_summary/                # YOUR PRIMARY APP
│   │   ├── models.py                # InspectionBatch → InspectionReport → PONumber → GeneratedFile
│   │   ├── tasks.py                 # Celery tasks (routed to "puma_summary" queue)
│   │   ├── views.py                 # Upload + status polling + list views
│   │   ├── forms.py                 # FolderUploadForm
│   │   ├── admin.py                 # Full admin with filters
│   │   ├── services/
│   │   │   ├── extractor.py         # PDF parsing (replaces your extract_reports())
│   │   │   ├── builder.py           # Excel generation (replaces build_tables())
│   │   │   ├── certificate.py       # DOCX cert generation (replaces replace_text_in_document())
│   │   │   └── file_manager.py      # PDF rename/copy (replaces shutil section)
│   │   └── utils/
│   │       ├── constants.py         # All regex patterns + FACTORY_ENUM (one place to update)
│   │       ├── pdf_parser.py        # pdfplumber isolation
│   │       └── validators.py        # Folder validation
│   │
│   ├── core/                        # Dashboard + auth landing page
│   └── [service_b]/ [service_c]/    # Your other 2 services slot in here
│
├── workers/
│   └── celery_worker.py             # Worker entrypoint
│
└── requirements/
    ├── base.txt                     # Django, Celery, Redis, pdfplumber, pandas, python-docx
    ├── development.txt              # + debug-toolbar, pytest, coverage
    └── production.txt               # + sentry-sdk