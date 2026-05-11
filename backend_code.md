
# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\config.py

"""
config.py
---------
Central application configuration.

DB_PATH is the single fixed location of the SQLite database.
It is created once on first run and reused on every subsequent run,
enabling duplicate detection across all extraction sessions.

When packaged with PyInstaller the exe sits in C:\\AuditSystem\\
and the DB lives next to it at C:\\AuditSystem\\audit.db.
"""

from pathlib import Path

# Fixed app directory on the C drive
APP_DIR = Path(r"C:\AuditSystem")

# Single persistent database — never recreated, only appended to
DB_PATH = APP_DIR / "audit.db"


def ensure_app_dir() -> None:
    """
    Create C:\\AuditSystem\\ if it does not exist.
    Called once at startup by both scripts.
    Raises PermissionError if the directory cannot be created.
    """
    APP_DIR.mkdir(parents=True, exist_ok=True)

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\extractor_main.py

"""
extractor_main.py
-----------------
Script 1 — Audit Report Extractor.

Workflow
--------
1. User selects a root folder via GUI.
2. Excel files are discovered recursively at any depth.
3. Each file is extracted → enriched → validated.
4. Records are saved to the local SQLite DB (duplicates skipped).
5. All records for this run are exported to a JSON file (for manual correction).
6. A progress window shows live status.

Directory layout (any nesting is supported)
--------------------------------------------
  Root / file.xlsx
  Root / Month / file.xlsx
  Root / Month / Date / file.xlsx
  Root / Factory / Month / Date / file.xlsx

Output (written to Root/Summary/)
----------------------------------
  audit.db          – SQLite database (created once, appended on each run)
  summary_YYYYMMDD_HHMMSS.json  – JSON export for this run
  extraction_YYYYMMDD_HHMMSS.log
"""

import logging
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List

from core.folder_loader import find_xlsx_files, find_xlsx_files_with_stats
from core.sheet_reader import read_first_sheet
from core.cell_grid import CellGrid
from extraction.label_config import LABELS
from extraction.rule_extractor import extract_fields
from extraction.defect_extractor import extract_defect_table_from_file
from extraction.do_table_extractor import extract_do_table_to_record
from extraction.post_processor import refine_record, post_process_record
from models.audit_record import AuditRecord
from output.json_writer import write_json_output
from output.error_json_writer import write_error_json
from validation.validator import validate_all_records, validate_blocking_all
from db.db_manager import DBManager
from config import DB_PATH, ensure_app_dir


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(log_path: Path) -> None:
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_path, mode="w", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


# ---------------------------------------------------------------------------
# Single-file processor
# ---------------------------------------------------------------------------

def process_file(path: Path) -> AuditRecord:
    """
    Extract, enrich, and return an AuditRecord for a single Excel file.
    Raises on unrecoverable errors.
    """
    logging.info(f"Processing: {path.name}")

    df   = read_first_sheet(path)
    grid = CellGrid(df)

    extracted_data = extract_fields(grid, LABELS)

    # Build record; ignore keys not in AuditRecord
    known = set(AuditRecord.__dataclass_fields__.keys())  # type: ignore[attr-defined]
    safe_data = {k: v for k, v in extracted_data.items() if k in known and k != "file_name"}
    record = AuditRecord(file_name=path.name, **safe_data)

    # Auto-extract defect table
    defect_rows, defect_totals = extract_defect_table_from_file(path)
    record.defect_rows = defect_rows

    if not record.defect_qty and defect_totals.get("major") is not None:
        record.defect_qty = str(defect_totals["major"])

    # Post-process: derive, enrich, fill missing fields
    record = post_process_record(record, path)

    # Extract D.O. plan table
    extract_do_table_to_record(record, path)

    # Final clean-up
    record = refine_record(record)

    logging.info(
        f"  Done: {path.name} "
        f"[type={record.inspection_type}, defects={len(record.defect_rows)}, "
        f"client={record.client!r}]"
    )
    return record


# ---------------------------------------------------------------------------
# Progress window
# ---------------------------------------------------------------------------

class ProgressWindow:
    """Simple tkinter progress dialog shown during extraction."""

    def __init__(self, parent: tk.Tk, total: int) -> None:
        self.top = tk.Toplevel(parent)
        self.top.title("Extracting…")
        self.top.geometry("480x140")
        self.top.resizable(False, False)
        self.top.grab_set()

        self.total = total
        self.done  = 0

        tk.Label(self.top, text="Extracting audit reports…",
                 font=("Segoe UI", 11)).pack(pady=(14, 4))

        self.status_var = tk.StringVar(value="Starting…")
        tk.Label(self.top, textvariable=self.status_var,
                 font=("Segoe UI", 9), fg="#444").pack()

        self.bar = ttk.Progressbar(self.top, length=440, mode="determinate",
                                   maximum=total)
        self.bar.pack(pady=10, padx=20)

        self.top.update()

    def update(self, filename: str) -> None:
        self.done += 1
        self.bar["value"] = self.done
        self.status_var.set(f"({self.done}/{self.total})  {filename[:60]}")
        self.top.update()

    def close(self) -> None:
        self.top.destroy()


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------

def run_extractor(root: tk.Tk) -> None:
    """Run the full Extract → Validate → DB → JSON pipeline."""

    # ── Step 1: select root folder ────────────────────────────────────────────
    folder = filedialog.askdirectory(
        title="Select Root Folder (containing audit Excel files)",
        parent=root,
    )
    if not folder:
        return

    root_path      = Path(folder)
    summary_folder = root_path / "Summary"
    summary_folder.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path  = summary_folder / f"extraction_{timestamp}.log"
    json_path = summary_folder / f"summary_{timestamp}.json"

    # Fixed persistent DB — same file every run, enables duplicate detection
    ensure_app_dir()
    db_path = DB_PATH

    setup_logging(log_path)
    logging.info("=" * 60)
    logging.info("AUDIT EXTRACTOR — BATCH RUN")
    logging.info(f"Root folder : {root_path}")
    logging.info(f"Database    : {db_path}  (persistent)")
    logging.info("=" * 60)

    # ── Step 2: discover all Excel files recursively ──────────────────────────
    stats = find_xlsx_files_with_stats(root_path)
    all_files = stats["files"]

    if not all_files:
        messagebox.showinfo("No Files", "No Excel files found in the selected folder.")
        return

    logging.info(f"Found {stats['total']} Excel file(s) across "
                 f"{len(stats['by_folder'])} folder(s):")
    for folder_rel, files in stats["by_folder"].items():
        logging.info(f"  {folder_rel}: {len(files)} file(s)")

    # ── Step 3: initialise database ───────────────────────────────────────────
    db = DBManager(db_path)
    db.connect()
    db.init_db()

    # ── Step 4: extract all files ─────────────────────────────────────────────
    progress = ProgressWindow(root, total=len(all_files))

    all_records: List[AuditRecord] = []
    success_count = 0
    fail_count    = 0
    skip_count    = 0

    for file_path in all_files:
        progress.update(file_path.name)
        try:
            record = process_file(file_path)
            all_records.append(record)
            success_count += 1
        except Exception as exc:
            fail_count += 1
            logging.exception(f"FAILED: {file_path.name}: {exc}")

    progress.close()

    if not all_records:
        logging.error("No records extracted — aborting")
        messagebox.showerror("Error", "No records were extracted. Check the log for details.")
        db.close()
        return

    # ── Step 5: validate ──────────────────────────────────────────────────────
    logging.info("Running validation…")

    validated_records = validate_all_records(all_records)
    validated_records = validate_blocking_all(validated_records)

    # Split: records that pass blocking vs those that don't
    clean_records   = [r for r in validated_records if not r.blocking_errors]
    blocked_records = [r for r in validated_records if r.blocking_errors]

    # ── Step 6: save clean records to DB ─────────────────────────────────────
    logging.info(f"Saving {len(clean_records)} clean record(s) to database…")
    saved_count  = 0
    skip_count   = 0
    for record in clean_records:
        result = db.save_record(record)
        if result is None:
            skip_count += 1
        else:
            saved_count += 1

    db.close()

    # ── Step 7: write error JSON for blocked records ──────────────────────────
    error_json_path = None
    if blocked_records:
        error_json_path = summary_folder / f"errors_{timestamp}.json"
        write_error_json(blocked_records, error_json_path)
        logging.info(
            f"{len(blocked_records)} record(s) blocked — written to {error_json_path.name}"
        )

    # ── Step 8: export full JSON for all clean records ────────────────────────
    logging.info("Exporting JSON…")
    write_json_output(clean_records, json_path)

    # ── Step 9: done ──────────────────────────────────────────────────────────
    logging.info("=== EXTRACTION COMPLETE ===")
    logging.info(f"Total files   : {len(all_files)}")
    logging.info(f"Extracted     : {success_count}")
    logging.info(f"Failed        : {fail_count}")
    logging.info(f"Blocked       : {len(blocked_records)}")
    logging.info(f"Saved to DB   : {saved_count}")
    logging.info(f"Skipped (dup) : {skip_count}")

    error_note = ""
    if blocked_records and error_json_path:
        error_note = (
            f"\n\n⚠  {len(blocked_records)} record(s) blocked — see:\n"
            f"  {error_json_path.name}\n"
            f"Fix issues then use 'Upload & Fix Error JSON'."
        )

    messagebox.showinfo(
        "Extraction Complete",
        f"Files found      : {len(all_files)}\n"
        f"Extracted        : {success_count}\n"
        f"Failed           : {fail_count}\n"
        f"Blocked (errors) : {len(blocked_records)}\n"
        f"Saved to DB      : {saved_count}\n"
        f"Skipped (dup)    : {skip_count}"
        + error_note +
        f"\n\nDatabase : {DB_PATH}",
    )


# ---------------------------------------------------------------------------
# Upload & Fix Error JSON  (re-insert blocked records after user edits)
# ---------------------------------------------------------------------------

def run_upload_error_json(root: tk.Tk) -> None:
    """
    Let the user pick an error JSON file, re-validate each record, and
    attempt to insert the ones that now pass blocking validation.
    Records that still fail produce a new error JSON.
    """
    from output.error_json_writer import read_error_json, write_error_json
    from validation.validator import validate_all_records, validate_blocking_all

    path_str = filedialog.askopenfilename(
        parent=root,
        title="Select Error JSON to re-process",
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
    )
    if not path_str:
        return

    json_path = Path(path_str)
    out_folder = json_path.parent

    try:
        records = read_error_json(json_path)
    except Exception as exc:
        messagebox.showerror("Load Error", f"Could not read JSON:\n{exc}")
        return

    if not records:
        messagebox.showinfo("Empty", "No records found in the JSON file.")
        return

    # Re-validate
    records = validate_all_records(records)
    records = validate_blocking_all(records)

    clean_records   = [r for r in records if not r.blocking_errors]
    blocked_records = [r for r in records if r.blocking_errors]

    ensure_app_dir()
    if not DB_PATH.exists():
        messagebox.showerror(
            "No Database",
            f"Database not found at:\n{DB_PATH}\n\nRun extraction first.",
        )
        return

    db = DBManager(DB_PATH)
    db.connect()
    db.init_db()

    saved_count = 0
    skip_count  = 0
    for record in clean_records:
        result = db.save_record(record)
        if result is None:
            skip_count += 1
        else:
            saved_count += 1
    db.close()

    # Write new error JSON for records that still fail
    new_error_path = None
    if blocked_records:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_error_path = out_folder / f"errors_retry_{ts}.json"
        write_error_json(blocked_records, new_error_path)

    still_blocked_note = ""
    if blocked_records and new_error_path:
        still_blocked_note = (
            f"\n\n⚠  {len(blocked_records)} record(s) still blocked:\n"
            f"  {new_error_path.name}"
        )

    messagebox.showinfo(
        "Upload Complete",
        f"Records in file  : {len(records)}\n"
        f"Now inserted     : {saved_count}\n"
        f"Skipped (dup)    : {skip_count}\n"
        f"Still blocked    : {len(blocked_records)}"
        + still_blocked_note,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    root = tk.Tk()
    root.title("Audit Report Extractor")
    root.geometry("380x200")
    root.resizable(False, False)

    outer = tk.Frame(root, padx=30, pady=20)
    outer.pack(expand=True)

    tk.Label(outer, text="Audit Report Extractor",
             font=("Segoe UI", 13, "bold")).pack(pady=(0, 14))

    tk.Button(
        outer,
        text="  Select Folder & Extract  ",
        font=("Segoe UI", 11),
        bg="#2F5496", fg="white",
        activebackground="#1E3A6E",
        cursor="hand2",
        width=28,
        command=lambda: run_extractor(root),
    ).pack(pady=(0, 8))

    tk.Button(
        outer,
        text="  Upload & Fix Error JSON  ",
        font=("Segoe UI", 10),
        bg="#C65911", fg="white",
        activebackground="#8B3D0A",
        cursor="hand2",
        width=28,
        command=lambda: run_upload_error_json(root),
    ).pack()

    root.mainloop()


# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\ui_app.py

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
from tkcalendar import DateEntry

# ✅ added: dropdown values from enums/ui_field_enums.py
from enums.ui_field_enums import (
    ANALYSIS_TYPES,
    REPORT_FORMATS,
    DEFAULT_ANALYSIS_TYPE,
    DEFAULT_REPORT_FORMAT,
)


class AutoScrollbar(ttk.Scrollbar):
    """A scrollbar that hides itself if it's not needed."""
    def set(self, lo, hi):
        try:
            lo_f = float(lo)
            hi_f = float(hi)
        except ValueError:
            lo_f, hi_f = 0.0, 1.0

        if lo_f <= 0.0 and hi_f >= 1.0:
            self.grid_remove()
        else:
            self.grid()
        super().set(lo, hi)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Excel Summary Tool")
        self.geometry("1080x720")

        self.input_folder = None
        self.output_folder = None

        # ✅ changed: defaults now come from enums
        self.analysis_type = tk.StringVar(value=DEFAULT_ANALYSIS_TYPE)
        self.report_format = tk.StringVar(value=DEFAULT_REPORT_FORMAT)

        # Search Query Variables
        self.gmail_subject = tk.StringVar(value="Final Audit Report")
        self.report_date = tk.StringVar()
        self.attachment_name = tk.StringVar(value=".xlsx")
        self.generated_query = tk.StringVar()

        # Live Update Traces
        self.gmail_subject.trace_add("write", self.update_query_preview)
        self.report_date.trace_add("write", self.update_query_preview)
        self.attachment_name.trace_add("write", self.update_query_preview)

        # Root layout: 3 rows (top + content + footer), 3 cols (left/center/right)
        self.grid_rowconfigure(1, weight=1)  # content expands

        # Left column width control
        self.grid_columnconfigure(0, weight=0, minsize=250)

        # Center + right sizing (right wider)
        self.grid_columnconfigure(1, weight=2, minsize=420)  # center
        self.grid_columnconfigure(2, weight=5, minsize=350)  # right

        # Top
        self.top = ttk.Frame(self, padding=10)
        self.top.grid(row=0, column=0, columnspan=3, sticky="ew")
        self.top.grid_columnconfigure(6, weight=1)

        # Left
        self.left = ttk.Frame(self, padding=10)
        self.left.grid(row=1, column=0, sticky="nsew")
        self.left.configure(width=320)
        self.left.grid_propagate(False) # IMPORTANT: allow width to actually apply

        # Center
        self.center = ttk.Frame(self, padding=10)
        self.center.grid(row=1, column=1, sticky="nsew")

        # Right (wider)
        self.right = ttk.Frame(self, padding=10)
        self.right.grid(row=1, column=2, sticky="nsew")
        self.right.configure(width=520)

        # Let right panel stretch vertically
        self.right.grid_rowconfigure(3, weight=1)
        self.right.grid_rowconfigure(7, weight=1)
        self.right.grid_columnconfigure(0, weight=1)

        # Footer
        self.footer = ttk.Frame(self, padding=(10, 6))
        self.footer.grid(row=2, column=0, columnspan=3, sticky="ew")
        self.footer.grid_columnconfigure(0, weight=1)

        self._build_ui()
    
    def browse_client_secret(self):
        file = filedialog.askopenfilename(
            title="Select credentials.json",
            filetypes=[("JSON Files", "*.json")]
        )
        if file:
            self.client_secret_path.set(file)
            self.log(f"📂 Selected Gmail credentials: {file}")


    def test_gmail_connection(self):
        if not self.client_secret_path.get():
            messagebox.showerror("Missing", "Select client secret file first.")
            return

        self.log("🔐 Testing Gmail API connection...")
        # Later integrate real Gmail API authentication here
        self.log("✅ Gmail connection test successful (demo)")

    def build_gmail_query(self, suppress_errors=False):
        """Constructs the Gmail search query based on UI fields."""
        query_parts = []
        
        subject = self.gmail_subject.get().strip()
        attachment = self.attachment_name.get().strip()
        r_date = self.report_date.get().strip()

        if subject:
            query_parts.append(f"subject:{subject}")
        
        if attachment:
            query_parts.append(f"filename:{attachment}")
            
        if r_date:
            try:
                # Validate format YYYY/MM/DD
                datetime.strptime(r_date, "%Y/%m/%d")
                query_parts.append(f"after:{r_date}")
            except ValueError:
                if not suppress_errors:
                    messagebox.showerror("Invalid Date", f"The date '{r_date}' must be in YYYY/MM/DD format.")
                return ""

        # Always ensure attachments are present
        query_parts.append("has:attachment")

        return " ".join(query_parts)

    def update_query_preview(self, *args):
        """Callback for live query updates via traces."""
        # Suppress errors during live typing/selection
        query = self.build_gmail_query(suppress_errors=True)
        self.generated_query.set(query)

    def _build_ui(self):
        # ---------- TOP: dropdowns ----------
        ttk.Label(self.top, text="Analysis Type").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Combobox(
            self.top,
            textvariable=self.analysis_type,
            state="readonly",
            values=ANALYSIS_TYPES,
            width=24
        ).grid(row=0, column=1, sticky="w", padx=(0, 10))

        ttk.Label(self.top, text="Report Format").grid(row=0, column=3, sticky="w", padx=(0, 6))
        ttk.Combobox(
            self.top,
            textvariable=self.report_format,
            state="readonly",
            values=REPORT_FORMATS,
            width=20
        ).grid(row=0, column=4, sticky="w", padx=(0, 18))
        
        # ✅ Submit button placed beside Analysis Type (after the combobox)
        ttk.Button(self.top, text="Submit", command=self.on_submit).grid(
            row=0, column=5, sticky="w", padx=(0, 18)
        )

        ttk.Separator(self, orient="horizontal").grid(row=0, column=0, columnspan=3, sticky="ew", pady=(52, 0))

        # ---------- LEFT: Actions first, Steps below ----------
        ttk.Label(self.left, text="Actions", font=("Segoe UI", 12, "bold")).pack(anchor="w")

        self.btn1 = ttk.Button(self.left, text="Select Input Folder", command=self.step1_select_input)
        self.btn2 = ttk.Button(self.left, text="Select Output Folder", command=self.step2_select_output)
        self.btn3 = ttk.Button(self.left, text="Extract", command=self.step3_extract)
        self.btn4 = ttk.Button(self.left, text="Validate", command=self.step4_validate)
        self.btn5 = ttk.Button(self.left, text="Export", command=self.step5_export)

        for b in (self.btn1, self.btn2, self.btn3, self.btn4, self.btn5):
            b.pack(fill="x", pady=4)

        # lock later steps
        self.btn2.state(["disabled"])
        self.btn3.state(["disabled"])
        self.btn4.state(["disabled"])
        self.btn5.state(["disabled"])

        ttk.Separator(self.left, orient="horizontal").pack(fill="x", pady=(10, 10))

        ttk.Label(self.left, text="Steps", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.step_list = tk.Listbox(self.left, height=12)
        self.step_list.pack(fill="x", pady=(8, 0))
        for s in [
            "1) Select Input Folder",
            "2) Select Output Folder",
            "3) Extract",
            "4) Validate",
            "5) Export"
        ]:
            self.step_list.insert("end", s)

        # ---------- CENTER: Log ----------
        #ttk.Label(self.center, text="Log", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        #self.main_text = tk.Text(self.center, height=20)
        #self.main_text.pack(fill="both", expand=True, pady=8)

        # ---------- CENTER: TABS ----------
        self.notebook = ttk.Notebook(self.center)
        self.notebook.pack(fill="both", expand=True)

        # Tab 1: Downloadable Files
        self.tab_files = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_files, text="Downloadable Report Files")

        # Tab 2: Gmail API Config
        self.tab_gmail = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_gmail, text="Gmail API Config")

        # Tab 3: Log  ← RESTORED
        self.tab_log = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_log, text="Log")
        
        # =========================
        # TAB 1 - DOWNLOADABLE FILES
        # =========================
        ttk.Label(self.tab_files, text="All Downloadable Files",
                  font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(5, 5))

        self.download_list = tk.Listbox(self.tab_files)
        self.download_list.pack(fill="both", expand=True, pady=5)

        ttk.Button(
            self.tab_files,
            text="Refresh File List",
            command=self.refresh_right_panel  # reuse existing logic
        ).pack(anchor="e", pady=5)
        
        # =========================
        # TAB 2 - GMAIL CONFIG
        # =========================
        config_frame = ttk.Frame(self.tab_gmail, padding=15)
        config_frame.pack(fill="both", expand=True)

        config_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(config_frame, text="Gmail API Configuration",
                  font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 15))

        ttk.Label(config_frame, text="Client Secret File:").grid(row=1, column=0, sticky="w", pady=5)

        self.client_secret_path = tk.StringVar()
        ttk.Entry(config_frame, textvariable=self.client_secret_path).grid(
            row=1, column=1, sticky="ew", pady=5
        )

        ttk.Button(
            config_frame,
            text="Browse",
            command=self.browse_client_secret
        ).grid(row=1, column=2, padx=5)

        # --- NEW STRUCTURED SEARCH QUERY SECTION ---
        ttk.Separator(config_frame, orient="horizontal").grid(row=2, column=0, columnspan=3, sticky="ew", pady=15)
        
        ttk.Label(config_frame, text="Search Query", 
                  font=("Segoe UI", 12, "bold")).grid(row=3, column=0, columnspan=3, sticky="w", pady=(0, 10))

        # 1. Subject Contains
        ttk.Label(config_frame, text="Subject Contains:").grid(row=4, column=0, sticky="w", pady=5)
        ttk.Entry(config_frame, textvariable=self.gmail_subject).grid(row=4, column=1, columnspan=2, sticky="ew", padx=5, pady=5)

        # 2. Report Date (DateEntry)
        ttk.Label(config_frame, text="Report Date (After):").grid(row=5, column=0, sticky="w", pady=5)
        self.date_picker = DateEntry(config_frame, 
                                     textvariable=self.report_date,
                                     date_pattern='yyyy/mm/dd',
                                     width=12, background='darkblue', 
                                     foreground='white', borderwidth=2)
        self.date_picker.grid(row=5, column=1, sticky="w", padx=5, pady=5)

        # 3. Attachment Name Contains
        ttk.Label(config_frame, text="Attachment Contains:").grid(row=6, column=0, sticky="w", pady=5)
        ttk.Entry(config_frame, textvariable=self.attachment_name).grid(row=6, column=1, columnspan=2, sticky="ew", padx=5, pady=5)

        # 4. Live Query Preview
        ttk.Label(config_frame, text="Generated Gmail Query:", 
                  font=("Segoe UI", 9, "bold")).grid(row=7, column=0, sticky="w", pady=(15, 0))
        
        preview_entry = ttk.Entry(config_frame, textvariable=self.generated_query, state="readonly")
        preview_entry.grid(row=8, column=0, columnspan=3, sticky="ew", padx=5, pady=(2, 5))

        # Initial preview update
        self.update_query_preview()

        ttk.Button(
            config_frame,
            text="Test Gmail Connection",
            command=self.test_gmail_connection
        ).grid(row=9, column=0, columnspan=3, pady=20)
        
        # =========================
        # TAB 3 - LOG (Restored)
        # =========================
        ttk.Label(self.tab_log, text="Application Log",
                  font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(5, 5))

        self.main_text = tk.Text(self.tab_log)
        self.main_text.pack(fill="both", expand=True, pady=5)

        # ---------- RIGHT: folders + file lists with auto-hide scrollbars ----------
        ttk.Label(self.right, text="Folders & Files", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w")

        # Input path row
        in_row = ttk.Frame(self.right)
        in_row.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        in_row.grid_columnconfigure(1, weight=1)
        ttk.Label(in_row, text="Input:", width=8).grid(row=0, column=0, sticky="w")
        self.input_path_lbl = ttk.Label(in_row, text="(not selected)")
        self.input_path_lbl.grid(row=0, column=1, sticky="ew")

        ttk.Label(self.right, text="Input Files (.xlsx)", font=("Segoe UI", 10, "bold")).grid(
            row=2, column=0, sticky="w", pady=(6, 2)
        )

        # Input listbox + autohide scrollbar
        in_list_frame = ttk.Frame(self.right)
        in_list_frame.grid(row=3, column=0, sticky="nsew")
        in_list_frame.grid_rowconfigure(0, weight=1)
        in_list_frame.grid_columnconfigure(0, weight=1)

        self.in_scroll = AutoScrollbar(in_list_frame, orient="vertical")
        self.in_scroll.grid(row=0, column=1, sticky="ns")

        self.input_files = tk.Listbox(in_list_frame)
        self.input_files.grid(row=0, column=0, sticky="nsew")
        self.input_files.config(yscrollcommand=self.in_scroll.set)
        self.in_scroll.config(command=self.input_files.yview)

        # Output path row
        out_row = ttk.Frame(self.right)
        out_row.grid(row=4, column=0, sticky="ew", pady=(12, 4))
        out_row.grid_columnconfigure(1, weight=1)
        ttk.Label(out_row, text="Output:", width=8).grid(row=0, column=0, sticky="w")
        self.output_path_lbl = ttk.Label(out_row, text="(not selected)")
        self.output_path_lbl.grid(row=0, column=1, sticky="ew")

        ttk.Label(self.right, text="Output Files", font=("Segoe UI", 10, "bold")).grid(
            row=5, column=0, sticky="w", pady=(6, 2)
        )

        # Output listbox + autohide scrollbar
        out_list_frame = ttk.Frame(self.right)
        out_list_frame.grid(row=7, column=0, sticky="nsew")
        out_list_frame.grid_rowconfigure(0, weight=1)
        out_list_frame.grid_columnconfigure(0, weight=1)

        self.out_scroll = AutoScrollbar(out_list_frame, orient="vertical")
        self.out_scroll.grid(row=0, column=1, sticky="ns")

        self.output_files = tk.Listbox(out_list_frame)
        self.output_files.grid(row=0, column=0, sticky="nsew")
        self.output_files.config(yscrollcommand=self.out_scroll.set)
        self.out_scroll.config(command=self.output_files.yview)

        # trigger autohide check once initially
        self.in_scroll.set(0, 1)
        self.out_scroll.set(0, 1)

        # ---------- FOOTER ----------
        ttk.Separator(self.footer, orient="horizontal").grid(row=0, column=0, sticky="ew", pady=(0, 6))
        footer_text = "All rights reserved by PQC 2026 | Developed by Abdun Nur Tomal, Ome Hasan Forhad"
        ttk.Label(self.footer, text=footer_text).grid(row=1, column=0, sticky="e")

    # ---------- helpers ----------
    def on_submit(self):
        # do whatever you want on submit
        self.log(f"✅ Submitted | Analysis={self.analysis_type.get()} | Format={self.report_format.get()}")

    def log(self, msg: str):
        self.main_text.insert("end", msg + "\n")
        self.main_text.see("end")
        self.notebook.select(self.tab_log)  # auto switch to Log tab

    def _list_files(self, folder: str, exts=None):
        if not folder or not os.path.isdir(folder):
            return []
        items = []
        for root, _, files in os.walk(folder):
            for f in files:
                lf = f.lower()
                if exts is not None and not any(lf.endswith(e) for e in exts):
                    continue
                rel = os.path.relpath(os.path.join(root, f), folder)
                if os.path.basename(rel).startswith("~$"):
                    continue
                items.append(rel)
        items.sort()
        return items

    def refresh_right_panel(self):
        self.input_path_lbl.config(text=self.input_folder or "(not selected)")
        self.output_path_lbl.config(text=self.output_folder or "(not selected)")

        self.input_files.delete(0, "end")
        if self.input_folder:
            for f in self._list_files(self.input_folder, exts=[".xlsx"]):
                self.input_files.insert("end", f)

        self.output_files.delete(0, "end")
        if self.output_folder:
            for f in self._list_files(self.output_folder, exts=None):
                self.output_files.insert("end", f)

        # Force scrollbar recalculation
        self.update_idletasks()
        self.input_files.yview_moveto(0)
        self.output_files.yview_moveto(0)

    def select_step(self, index: int):
        self.step_list.selection_clear(0, "end")
        self.step_list.selection_set(index)

    # ---------- steps ----------
    def step1_select_input(self):
        folder = filedialog.askdirectory(title="Select INPUT (Mother) Folder")
        if not folder:
            return
        self.input_folder = folder
        self.log(f"✅ Input folder: {folder}")
        self.refresh_right_panel()
        self.btn2.state(["!disabled"])
        self.select_step(0)

    def step2_select_output(self):
        folder = filedialog.askdirectory(title="Select OUTPUT Folder")
        if not folder:
            return
        self.output_folder = folder
        self.log(f"✅ Output folder: {folder}")
        self.refresh_right_panel()
        self.btn3.state(["!disabled"])
        self.select_step(1)

    def step3_extract(self):
        if not self.input_folder:
            messagebox.showerror("Missing", "Select input folder first.")
            return
        if not self.output_folder:
            messagebox.showerror("Missing", "Select output folder first.")
            return
        self.log(f"🚀 Extracting... | Analysis={self.analysis_type.get()} | Format={self.report_format.get()}")
        self.log("✅ Extraction done (demo)")
        self.btn4.state(["!disabled"])
        self.select_step(2)
        self.refresh_right_panel()

    def step4_validate(self):
        self.log("🔍 Validating... (demo)")
        self.log("✅ Validation done (demo)")
        self.btn5.state(["!disabled"])
        self.select_step(3)
        self.refresh_right_panel()

    def step5_export(self):
        self.log("📦 Exporting... (demo)")
        self.log("✅ Export done (demo)")
        self.select_step(4)
        self.refresh_right_panel()


if __name__ == "__main__":
    App().mainloop()

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\writer_main.py

"""
writer_main.py
--------------
Script 2 — Summary Excel Generator.

GUI form with:
  - Factory   : dropdown populated from DB
  - Client    : dropdown populated from DB
  - Start Date: inline calendar date picker
  - End Date  : inline calendar date picker

Queries the fixed DB at C:\\AuditSystem\\audit.db and generates the
summary Excel in the reference layout.
"""

import logging
import tkinter as tk
from datetime import datetime, date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

from db.db_manager import DBManager
from output.summary_writer import write_summary
from config import DB_PATH, ensure_app_dir


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


# ---------------------------------------------------------------------------
# Inline calendar date-picker widget
# ---------------------------------------------------------------------------

class DatePicker(tk.Frame):
    """
    Compact inline calendar. Month/year nav + 7-col day grid.
    Selected date highlighted in blue; today underlined.
    """

    def __init__(self, parent: tk.Widget, label: str, **kwargs):
        super().__init__(parent, **kwargs)
        self._label    = label
        self._selected: Optional[date] = None
        self._viewing  = date.today().replace(day=1)
        self._build()

    # ── Public API ────────────────────────────────────────────────────────────

    def get_date(self) -> Optional[date]:
        return self._selected

    def get_iso(self) -> str:
        """Return YYYY-MM-DD or '' if nothing selected."""
        return self._selected.strftime("%Y-%m-%d") if self._selected else ""

    def set_date(self, d: date) -> None:
        self._selected = d
        self._viewing  = d.replace(day=1)
        self._refresh()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        tk.Label(self, text=self._label,
                 font=("Segoe UI", 9, "bold"), anchor="w").grid(
            row=0, column=0, columnspan=7, sticky="w", pady=(0, 1))

        self._disp_var = tk.StringVar(value="—")
        tk.Label(self, textvariable=self._disp_var,
                 font=("Segoe UI", 9), fg="#2F5496", anchor="w").grid(
            row=1, column=0, columnspan=7, sticky="w", pady=(0, 3))

        nav = tk.Frame(self)
        nav.grid(row=2, column=0, columnspan=7, sticky="ew")
        tk.Button(nav, text="◀", width=2, relief="flat",
                  command=self._prev_month).pack(side="left")
        self._month_var = tk.StringVar()
        tk.Label(nav, textvariable=self._month_var,
                 font=("Segoe UI", 9, "bold"), width=14).pack(side="left", expand=True)
        tk.Button(nav, text="▶", width=2, relief="flat",
                  command=self._next_month).pack(side="right")

        for col, day in enumerate(["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]):
            tk.Label(self, text=day, font=("Segoe UI", 8, "bold"),
                     width=3, fg="#555").grid(row=3, column=col)

        self._day_btns: List[tk.Button] = []
        for r in range(6):
            for c in range(7):
                btn = tk.Button(
                    self, text="", width=3, height=1,
                    relief="flat", font=("Segoe UI", 8),
                    command=lambda rb=r, cb=c: self._on_day(rb, cb),
                )
                btn.grid(row=4 + r, column=c, padx=1, pady=1)
                self._day_btns.append(btn)

        self._refresh()

    # ── Navigation ────────────────────────────────────────────────────────────

    def _prev_month(self) -> None:
        y, m = self._viewing.year, self._viewing.month - 1
        if m == 0:
            m, y = 12, y - 1
        self._viewing = date(y, m, 1)
        self._refresh()

    def _next_month(self) -> None:
        y, m = self._viewing.year, self._viewing.month + 1
        if m == 13:
            m, y = 1, y + 1
        self._viewing = date(y, m, 1)
        self._refresh()

    def _refresh(self) -> None:
        import calendar
        y, m   = self._viewing.year, self._viewing.month
        today  = date.today()
        cal    = calendar.monthcalendar(y, m)
        while len(cal) < 6:
            cal.append([0] * 7)

        self._month_var.set(self._viewing.strftime("%B %Y"))
        self._disp_var.set(
            self._selected.strftime("%m/%d/%Y") if self._selected else "—"
        )

        for r, week in enumerate(cal[:6]):
            for c, day_num in enumerate(week):
                btn = self._day_btns[r * 7 + c]
                if day_num == 0:
                    btn.config(text="", state="disabled",
                               bg="white", fg="#ccc", relief="flat")
                else:
                    d        = date(y, m, day_num)
                    is_sel   = (d == self._selected)
                    is_today = (d == today)
                    btn.config(
                        text   = str(day_num),
                        state  = "normal",
                        bg     = "#2F5496" if is_sel else "white",
                        fg     = "white" if is_sel else ("#2F5496" if is_today else "#000"),
                        font   = ("Segoe UI", 8, "bold" if is_today else "normal"),
                        relief = "flat",
                    )

    def _on_day(self, row: int, col: int) -> None:
        import calendar
        y, m = self._viewing.year, self._viewing.month
        cal  = calendar.monthcalendar(y, m)
        while len(cal) < 6:
            cal.append([0] * 7)
        if row < len(cal) and cal[row][col] > 0:
            self._selected = date(y, m, cal[row][col])
            self._refresh()


# ---------------------------------------------------------------------------
# Writer workflow
# ---------------------------------------------------------------------------

def run_writer(
    root: tk.Tk,
    factory: str,
    client: str,
    start_iso: str,
    end_iso: str,
) -> None:
    """Query DB and write summary Excel. All dates as YYYY-MM-DD."""
    ensure_app_dir()

    if not DB_PATH.exists():
        messagebox.showerror(
            "Database Not Found",
            f"No database found at:\n{DB_PATH}\n\n"
            "Run the Extractor first to populate data.",
        )
        return

    logging.info(f"Querying: factory={factory!r} client={client!r} "
                 f"{start_iso} → {end_iso}")

    try:
        with DBManager(DB_PATH) as db:
            records = db.query_records(
                factory    = factory,
                client     = client,
                start_date = start_iso,
                end_date   = end_iso,
            )
            if not records:
                messagebox.showinfo(
                    "No Records",
                    f"No audit records found for:\n"
                    f"  Factory : {factory or '(any)'}\n"
                    f"  Client  : {client or '(any)'}\n"
                    f"  Period  : {start_iso}  →  {end_iso}\n\n"
                    "Check that the Extractor has been run for this data.",
                )
                return

            defect_map = db.query_defect_items_for_reports(
                [r["report_id"] for r in records]
            )

    except Exception as exc:
        logging.exception(f"DB query failed: {exc}")
        messagebox.showerror("DB Error", f"Could not query database:\n{exc}")
        return

    logging.info(f"Found {len(records)} record(s)")

    def _safe(s: str) -> str:
        return "".join(
            c if c.isalnum() or c in " -_" else "_" for c in s
        ).strip() or "All"

    default_name = (
        f"{start_iso.replace('-','')}_{end_iso.replace('-','')}"
        f"_Summary_{_safe(factory)}_{_safe(client)}.xlsx"
    )

    save_path_str = filedialog.asksaveasfilename(
        parent=root, title="Save Summary As…",
        initialfile=default_name, defaultextension=".xlsx",
        filetypes=[("Excel Workbook", "*.xlsx")],
    )
    if not save_path_str:
        return

    try:
        write_summary(records, defect_map, Path(save_path_str))
        messagebox.showinfo(
            "Done",
            f"Summary written!\n\n"
            f"Records : {len(records)}\n"
            f"File    : {Path(save_path_str).name}",
        )
    except Exception as exc:
        logging.exception(f"Excel write failed: {exc}")
        messagebox.showerror("Write Error", f"Could not write Excel:\n{exc}")


# ---------------------------------------------------------------------------
# GUI application
# ---------------------------------------------------------------------------

class WriterApp:

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Audit Summary Writer")
        self.root.geometry("580x540")
        self.root.resizable(False, False)
        self._build_ui()
        self._load_db_values()

    def _build_ui(self) -> None:
        outer = tk.Frame(self.root, padx=20, pady=14)
        outer.pack(fill="both", expand=True)

        # Title
        tk.Label(outer, text="Audit Summary Writer",
                 font=("Segoe UI", 13, "bold")).pack(anchor="w")

        # DB indicator
        db_bar = tk.Frame(outer, bg="#EEF2FA", bd=1, relief="sunken")
        db_bar.pack(fill="x", pady=(5, 10), ipady=3, ipadx=6)
        tk.Label(db_bar, text="DB:", font=("Segoe UI", 8, "bold"),
                 bg="#EEF2FA", fg="#555").pack(side="left", padx=(4, 2))
        tk.Label(db_bar, text=str(DB_PATH),
                 font=("Segoe UI", 8), fg="#2F5496", bg="#EEF2FA").pack(side="left")

        ttk.Separator(outer).pack(fill="x", pady=(0, 8))

        # ── Dropdowns ────────────────────────────────────────────────────────
        grid = tk.Frame(outer)
        grid.pack(fill="x")

        tk.Label(grid, text="Factory:", font=("Segoe UI", 10),
                 width=9, anchor="w").grid(row=0, column=0, sticky="w", pady=4)
        self.factory_var = tk.StringVar()
        self.factory_cb  = ttk.Combobox(grid, textvariable=self.factory_var,
                                        font=("Segoe UI", 10), width=32)
        self.factory_cb.grid(row=0, column=1, sticky="ew", pady=4)

        tk.Label(grid, text="Client:", font=("Segoe UI", 10),
                 width=9, anchor="w").grid(row=1, column=0, sticky="w", pady=4)
        self.client_var = tk.StringVar()
        self.client_cb  = ttk.Combobox(grid, textvariable=self.client_var,
                                       font=("Segoe UI", 10), width=32)
        self.client_cb.grid(row=1, column=1, sticky="ew", pady=4)

        tk.Button(grid, text="↻  Refresh", font=("Segoe UI", 9),
                  relief="flat", cursor="hand2", fg="#2F5496",
                  command=self._load_db_values).grid(
            row=0, column=2, rowspan=2, padx=(10, 0))

        grid.columnconfigure(1, weight=1)

        tk.Label(outer, text="Leave blank to include all factories / clients.",
                 font=("Segoe UI", 8), fg="#888").pack(anchor="w", pady=(2, 8))

        ttk.Separator(outer).pack(fill="x", pady=(0, 10))

        # ── Date pickers ─────────────────────────────────────────────────────
        cal_row = tk.Frame(outer)
        cal_row.pack(fill="x")

        self.start_picker = DatePicker(cal_row, "Start Date")
        self.start_picker.pack(side="left", anchor="n", padx=(0, 30))

        self.end_picker = DatePicker(cal_row, "End Date")
        self.end_picker.pack(side="left", anchor="n")

        ttk.Separator(outer).pack(fill="x", pady=12)

        # ── Generate button ───────────────────────────────────────────────────
        tk.Button(
            outer,
            text="  Generate Summary Excel  ",
            font=("Segoe UI", 11, "bold"),
            bg="#2F5496", fg="white",
            activebackground="#1E3A6E",
            cursor="hand2",
            padx=10, pady=4,
            command=self._on_generate,
        ).pack()

    def _load_db_values(self) -> None:
        """Populate dropdowns and pre-set date pickers from DB."""
        ensure_app_dir()
        if not DB_PATH.exists():
            return
        try:
            with DBManager(DB_PATH) as db:
                db.init_db()
                factories = [""] + db.get_all_factories()
                clients   = [""] + db.get_all_clients()
                min_d, max_d = db.get_date_range()
        except Exception as exc:
            logging.warning(f"Could not load DB values: {exc}")
            return

        self.factory_cb["values"] = factories
        self.client_cb["values"]  = clients

        if min_d:
            try:
                self.start_picker.set_date(
                    datetime.strptime(min_d, "%Y-%m-%d").date()
                )
            except ValueError:
                pass
        if max_d:
            try:
                self.end_picker.set_date(
                    datetime.strptime(max_d, "%Y-%m-%d").date()
                )
            except ValueError:
                pass

    def _on_generate(self) -> None:
        start_iso = self.start_picker.get_iso()
        end_iso   = self.end_picker.get_iso()

        if not start_iso:
            messagebox.showerror("Missing Date", "Please select a Start Date.")
            return
        if not end_iso:
            messagebox.showerror("Missing Date", "Please select an End Date.")
            return

        run_writer(
            root      = self.root,
            factory   = self.factory_var.get().strip(),
            client    = self.client_var.get().strip(),
            start_iso = start_iso,
            end_iso   = end_iso,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    root = tk.Tk()
    WriterApp(root)
    root.mainloop()

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\core\cell_grid.py

"""
cell_grid.py
------------
Thin wrapper around a pandas DataFrame providing safe zero-based cell access
and label-search helpers used throughout the extraction pipeline.
"""

import re
from typing import Iterable, List, Tuple

import numpy as np
import pandas as pd


def normalize_text(value: str) -> str:
    """
    Lowercase, strip, collapse whitespace, and remove non-alphanumeric chars.

    Used for fuzzy label matching so that e.g.:
      "Factory Name:" == "factory name" == "FACTORY NAME"
    """
    text = value.lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class CellGrid:
    """
    Wraps a raw pandas DataFrame (loaded with header=None, dtype=str) and
    exposes safe, boundary-checked cell reads plus label-search utilities.

    Attributes
    ----------
    df    : the underlying DataFrame (NaN replaced with "")
    nrows : row count
    ncols : column count
    """

    def __init__(self, df: pd.DataFrame) -> None:
        self.df = df.replace({np.nan: ""})
        self.nrows, self.ncols = self.df.shape

    # ------------------------------------------------------------------
    # Cell access
    # ------------------------------------------------------------------

    def get(self, row: int, col: int) -> str:
        """Return the string value at (row, col), or "" if out of bounds."""
        if row < 0 or col < 0 or row >= self.nrows or col >= self.ncols:
            return ""
        value = self.df.iat[row, col]
        return "" if value is None else str(value).strip()

    # ------------------------------------------------------------------
    # Iteration
    # ------------------------------------------------------------------

    def iter_cells(self) -> Iterable[Tuple[int, int, str]]:
        """Yield (row, col, value) for every non-empty cell in reading order."""
        for row in range(self.nrows):
            for col in range(self.ncols):
                value = self.get(row, col)
                if value:
                    yield row, col, value

    # ------------------------------------------------------------------
    # Label searching
    # ------------------------------------------------------------------

    def find_label_positions(self, synonyms: List[str]) -> List[Tuple[int, int, str]]:
        """
        Find all cells whose normalised text exactly matches or starts with
        any of the given synonyms.

        Returns a list of (row, col, raw_cell_value) in discovery order.
        Empty strings in synonyms are silently ignored.
        """
        normalised_synonyms = [normalize_text(s) for s in synonyms if s]

        positions: List[Tuple[int, int, str]] = []

        for row, col, value in self.iter_cells():
            normalised_cell = normalize_text(value)
            for label in normalised_synonyms:
                if not label:
                    continue
                if normalised_cell == label or normalised_cell.startswith(label):
                    positions.append((row, col, value))
                    break

        return positions

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\core\folder_loader.py

"""
folder_loader.py
----------------
Recursively discovers Excel files starting from a root directory.

Strategy
--------
- Walk the directory tree recursively.
- At each level, if Excel files (.xlsx / .xls) are found, yield them.
- Skips temporary Office lock files (those beginning with "~$").
- Skips the "Summary" output folder to avoid re-processing outputs.

This handles any nesting depth:
  Mother / file.xlsx                         (flat)
  Mother / Month / file.xlsx                 (one level)
  Mother / Month / Date / file.xlsx          (two levels)
  Mother / Factory / Month / Date / file.xlsx (three levels)
"""

from pathlib import Path
from typing import Iterator


# Folder names to always skip during traversal
_SKIP_DIRS = {"summary", "Summary", "__pycache__", ".git"}


def find_xlsx_files(root: Path) -> Iterator[Path]:
    """
    Recursively yield all .xlsx and .xls files under *root*.

    Files are yielded in sorted order per directory for reproducibility.
    Temporary Office lock files (~$...) are silently skipped.
    The "Summary" output folder is excluded from traversal.
    """
    if not root.is_dir():
        return

    for item in sorted(root.iterdir()):
        if item.is_dir():
            if item.name in _SKIP_DIRS:
                continue
            yield from find_xlsx_files(item)

        elif item.is_file():
            if item.name.startswith("~$"):
                continue
            if item.suffix.lower() in (".xlsx", ".xls"):
                yield item


def find_xlsx_files_with_stats(root: Path) -> dict:
    """
    Scan *root* recursively and return a summary dict:
        {
            "files": [Path, ...],
            "total": int,
            "by_folder": {str: [Path, ...]}  # relative folder → files
        }
    """
    files = list(find_xlsx_files(root))
    by_folder: dict = {}

    for f in files:
        rel = str(f.parent.relative_to(root))
        by_folder.setdefault(rel, []).append(f)

    return {
        "files": files,
        "total": len(files),
        "by_folder": by_folder,
    }

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\core\sheet_reader.py

"""
sheet_reader.py
---------------
Thin wrappers around pandas.read_excel for consistent sheet loading.

All sheets are loaded with:
  - header=None  (no automatic header detection; row 0 is data row 0)
  - dtype=str    (everything comes in as strings; no type guessing)
  - fillna("")   (NaN replaced with empty string for safe .strip() calls)
"""

import logging
from pathlib import Path
from typing import List

import pandas as pd


def read_first_sheet(path: Path) -> pd.DataFrame:
    """
    Load only the first worksheet from *path*.
    Raises on file-read errors (caller is responsible for handling).
    """
    return pd.read_excel(path, sheet_name=0, header=None, dtype=str).fillna("")


def read_all_sheets(path: Path) -> List[pd.DataFrame]:
    """
    Load every worksheet from *path* and return them as a list of DataFrames.

    Falls back to reading just the first sheet if multi-sheet loading fails
    (e.g. corrupt or password-protected files).
    """
    try:
        xls = pd.read_excel(path, sheet_name=None, header=None, dtype=str)
        sheets = [df.fillna("") for df in xls.values()]
        logging.info(f"Loaded {len(sheets)} sheet(s) from '{path.name}'")
        return sheets
    except Exception as exc:  # BUG FIX: was 'except Exception:' — exc was unbound
        logging.warning(
            f"Multi-sheet read failed for '{path.name}' ({exc}); "
            "falling back to first sheet only."
        )
        return [read_first_sheet(path)]

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\core\__init__.py


# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\db\db_manager.py

"""
db_manager.py
-------------
All SQLite database operations for the audit extraction system.

Responsibilities
----------------
- Initialise the database (create tables from schema.sql)
- Upsert lookup rows (factories, clients, styles, purchase_orders)
- Insert / update audit_reports and all child tables
- Duplicate detection: block re-insertion of same file_name OR
  same (report_no + date_of_issue) combination
- Query helpers for the Writer script

Usage
-----
    from db.db_manager import DBManager

    db = DBManager("audit.db")
    db.init_db()
    db.save_record(audit_record)
    rows = db.query_records(factory="BABL Factory", client="BABL",
                            start_date="2026-01-01", end_date="2026-03-31")
    db.close()

All public methods wrap their work in a transaction. One bad record never
aborts the batch — errors are logged and re-raised to the caller.
"""

import logging
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from models.audit_record import AuditRecord


# ---------------------------------------------------------------------------
# Date normalisation for DB storage
# ---------------------------------------------------------------------------
# All dates are stored as YYYY-MM-DD so SQLite string comparison works
# correctly for range queries (>= / <=).
# The validator outputs MM/DD/YYYY; we convert here before INSERT.

def _to_iso_date(value: str) -> Optional[str]:
    """
    Convert any recognised date string to YYYY-MM-DD for DB storage.
    Returns None if blank or unparseable.

    Handles every format that Excel / the validator can produce:
      MM/DD/YYYY   01/05/2026  ← validator always outputs this
      YYYY-MM-DD   2026-01-05  ← already ISO
      YYYY/MM/DD   2026/01/05
      DD-MMM-YY    05-Jan-26
      DD-MMM-YYYY  05-Jan-2026
      MM-DD-YYYY   01-05-2026
      YYYY-MM-DD HH:MM:SS  (Excel datetime — time part stripped first)
    """
    if not value or not str(value).strip():
        return None

    from datetime import datetime as _dt

    s = str(value).strip()

    # Strip time component first: "2026-01-05 00:00:00" → "2026-01-05"
    # Handles space-separated and T-separated datetimes
    if len(s) > 10 and (s[10] in (" ", "T")):
        s = s[:10]

    # Try every known format in order of likelihood
    formats = [
        "%m/%d/%Y",   # 01/05/2026  ← validator always outputs this — FIRST
        "%Y-%m-%d",   # 2026-01-05  ← already ISO
        "%Y/%m/%d",   # 2026/01/05
        "%d-%b-%y",   # 05-Jan-26
        "%d-%b-%Y",   # 05-Jan-2026
        "%m-%d-%Y",   # 01-05-2026
        "%d/%m/%Y",   # 05/01/2026  ← LAST (ambiguous with MM/DD/YYYY)
    ]
    for fmt in formats:
        try:
            return _dt.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return s   # store as-is if nothing matches; never block an insert


# Resolve schema.sql path whether running as a script or frozen exe
if getattr(sys, 'frozen', False):
    # Running inside PyInstaller bundle — schema.sql is in the 'db' subfolder
    _SCHEMA_PATH = Path(sys._MEIPASS) / "db" / "schema.sql"  # type: ignore[attr-defined]
else:
    # Running as plain script — schema.sql is in the same directory as this file
    _SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class DBManager:
    """SQLite wrapper for the audit extraction system."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the database connection."""
        self._conn = sqlite3.connect(
            self.db_path,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL;")
        self._conn.execute("PRAGMA foreign_keys = ON;")

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "DBManager":
        self.connect()
        return self

    def __exit__(self, *_) -> None:
        self.close()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        return self._conn

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def init_db(self) -> None:
        """
        Create all tables, indexes, triggers, and views from schema.sql.
        Safe to call on an already-initialised database (IF NOT EXISTS).
        Also runs migrate_dates() to normalise any existing non-ISO dates.
        """
        if not _SCHEMA_PATH.exists():
            raise FileNotFoundError(f"Schema file not found: {_SCHEMA_PATH}")

        sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        with self.conn:
            self.conn.execute("PRAGMA foreign_keys = OFF")
            self.conn.executescript(sql)
            self.conn.execute("PRAGMA foreign_keys = ON")
        logging.info(f"Database initialised: {self.db_path}")

        # Load static defect master data if the file exists next to schema.sql
        _master_path = _SCHEMA_PATH.parent / "defect_master.sql"
        if _master_path.exists():
            master_sql = _master_path.read_text(encoding="utf-8")
            with self.conn:
                self.conn.executescript(master_sql)
            logging.info("Defect master data loaded from defect_master.sql")

        # Add any columns introduced after the DB was first created
        self.migrate_schema()
        # Always normalise dates — safe to run multiple times (idempotent)
        self.migrate_dates()
        # Migrate old defect_items rows into the new normalised tables
        self.migrate_defect_items()

    # ------------------------------------------------------------------
    # Schema migration  (idempotent ALTER TABLE for new columns)
    # ------------------------------------------------------------------

    def migrate_schema(self) -> None:
        """
        Idempotent ALTER TABLE migrations for columns added after the initial
        DB was first created.  Each entry checks whether the column already
        exists before issuing ALTER TABLE, so this is safe to call every startup.
        """
        _MIGRATIONS = [
            # (table, column, column_definition)
            (
                "audit_reports",
                "defect_template_id",
                "INTEGER REFERENCES defect_templates(id) ON DELETE SET NULL",
            ),
            (
                "audit_reports",
                "audit_report_no",
                "TEXT",
            ),
        ]

        existing: dict = {}
        for table, column, definition in _MIGRATIONS:
            if table not in existing:
                rows = self.conn.execute(
                    f"PRAGMA table_info({table})"
                ).fetchall()
                existing[table] = {row[1] for row in rows}
            if column not in existing[table]:
                self.conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
                )
                self.conn.commit()
                existing[table].add(column)
                logging.info(
                    f"migrate_schema: added column '{column}' to '{table}'"
                )

    # ------------------------------------------------------------------
    # Defect template matching
    # ------------------------------------------------------------------

    _TEMPLATE_TOLERANCE = 4   # ±4 items counts as a match

    def match_defect_template(self, defect_count: int) -> Optional[int]:
        """
        Given the number of defect items extracted from an Excel file,
        return the matching defect_templates.id (or None if no match).

        Matches within ±TEMPLATE_TOLERANCE of any template's item_count.
        When two templates are equally close, the smaller item_count wins.
        """
        rows = self.conn.execute(
            "SELECT id, item_count FROM defect_templates ORDER BY item_count"
        ).fetchall()

        best_id:   Optional[int] = None
        best_diff: int = self._TEMPLATE_TOLERANCE + 1

        for row in rows:
            diff = abs(defect_count - row["item_count"])
            if diff <= self._TEMPLATE_TOLERANCE and diff < best_diff:
                best_id   = row["id"]
                best_diff = diff

        if best_id:
            logging.info(
                f"  Defect template matched: id={best_id} "
                f"(extracted={defect_count}, tolerance=±{self._TEMPLATE_TOLERANCE})"
            )
        else:
            logging.info(
                f"  No defect template matched for count={defect_count}"
            )
        return best_id
    
    def _ensure_defect_entries_table(self):
        """Ensure defect_entries table exists before trying to insert."""
        try:
            self.conn.execute("SELECT 1 FROM defect_entries LIMIT 1").fetchone()
        except sqlite3.OperationalError:
            # Table doesn't exist - create it
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS defect_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    audit_report_id INTEGER NOT NULL,
                    defect_type_id INTEGER NOT NULL,
                    major INTEGER DEFAULT 0,
                    minor INTEGER DEFAULT 0,
                    comment TEXT,
                    FOREIGN KEY (audit_report_id) REFERENCES audit_reports(id) ON DELETE CASCADE,
                    FOREIGN KEY (defect_type_id) REFERENCES defect_types(id) ON DELETE CASCADE,
                    UNIQUE(audit_report_id, defect_type_id)
                )
            """)
            self.conn.commit()

    def get_defect_item_def_id(
        self,
        template_id: int,
        category_name: str,
        item_name: str,
    ) -> Optional[int]:
        """
        Look up defect_items_def.id for a given template + category + item name.
        Matching is case-insensitive and ignores leading/trailing whitespace.
        Returns None if not found (item will be saved to defect_types/entries
        without a static definition link).
        """
        row = self.conn.execute(
            """
            SELECT did.id
            FROM   defect_items_def  did
            JOIN   defect_categories dc  ON dc.id  = did.category_id
            JOIN   defect_templates  dt  ON dt.id  = dc.template_id
            WHERE  dt.id = ?
              AND  UPPER(TRIM(did.name))        = UPPER(TRIM(?))
            LIMIT 1
            """,
            (template_id, item_name),
        ).fetchone()
        return row["id"] if row else None

    def migrate_dates(self) -> None:
        """
        Convert any date fields stored in non-ISO formats to YYYY-MM-DD.

        Safe to run multiple times — records already in YYYY-MM-DD are
        left unchanged. Covers audit_reports.date_of_issue and all five
        date columns in shipment_dates.
        """
        _DATE_COLS_AUDIT    = ["date_of_issue"]
        _DATE_COLS_SHIPMENT = ["exf", "po_edt", "po_wh", "plan_edt", "plan_wh"]

        fixed_total = 0

        # ── audit_reports ─────────────────────────────────────────────────────
        rows = self.conn.execute(
            "SELECT id, date_of_issue FROM audit_reports "
            "WHERE date_of_issue IS NOT NULL"
        ).fetchall()

        updates = []
        for row in rows:
            original = row["date_of_issue"]
            converted = _to_iso_date(original)
            # Only update if the value actually changed
            if converted and converted != original:
                updates.append((converted, row["id"]))

        if updates:
            with self.conn:
                self.conn.executemany(
                    "UPDATE audit_reports SET date_of_issue = ? WHERE id = ?",
                    updates,
                )
            fixed_total += len(updates)
            logging.info(f"migrate_dates: fixed {len(updates)} audit_reports.date_of_issue rows")

        # ── shipment_dates ────────────────────────────────────────────────────
        for col in _DATE_COLS_SHIPMENT:
            rows = self.conn.execute(
                f"SELECT audit_report_id, {col} FROM shipment_dates "
                f"WHERE {col} IS NOT NULL"
            ).fetchall()

            updates = []
            for row in rows:
                original  = row[col]
                converted = _to_iso_date(original)
                if converted and converted != original:
                    updates.append((converted, row["audit_report_id"]))

            if updates:
                with self.conn:
                    self.conn.executemany(
                        f"UPDATE shipment_dates SET {col} = ? "
                        f"WHERE audit_report_id = ?",
                        updates,
                    )
                fixed_total += len(updates)
                logging.info(
                    f"migrate_dates: fixed {len(updates)} shipment_dates.{col} rows"
                )

        if fixed_total:
            logging.info(f"migrate_dates: total {fixed_total} date value(s) normalised to ISO")
        else:
            logging.debug("migrate_dates: all dates already in ISO format — nothing to do")

    def migrate_defect_items(self) -> None:
        """
        One-time migration: move data from the old defect_items table (if it
        exists and has rows) into the new defect_types + defect_entries tables.

        Safe to run multiple times — already-migrated rows are skipped via
        INSERT OR IGNORE on the UNIQUE constraint of defect_entries.
        Drops defect_items table after all rows are migrated.
        """
        # Check if the old table still exists
        old_exists = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='defect_items'"
        ).fetchone()
        if not old_exists:
            return

        rows = self.conn.execute(
            "SELECT audit_report_id, category, item, major_count, minor_count, comment "
            "FROM defect_items"
        ).fetchall()

        if not rows:
            # Nothing to migrate — drop the empty table
            with self.conn:
                self.conn.execute("DROP TABLE IF EXISTS defect_items")
            return

        migrated = 0
        with self.conn:
            for row in rows:
                cat     = (row["category"] or "").strip()
                item    = (row["item"] or "").strip()
                major   = int(row["major_count"] or 0)
                minor   = int(row["minor_count"] or 0)
                comment = row["comment"]
                report_id = row["audit_report_id"]

                if not cat or not item:
                    continue

                # Get-or-create defect_type
                self.conn.execute(
                    "INSERT OR IGNORE INTO defect_types (category, item_name, sort_order) "
                    "VALUES (?, ?, 0)",
                    (cat, item),
                )
                type_row = self.conn.execute(
                    "SELECT id FROM defect_types WHERE category = ? AND item_name = ?",
                    (cat, item),
                ).fetchone()
                if not type_row:
                    continue
                type_id = type_row["id"]

                # Insert entry (skip if already migrated)
                self.conn.execute(
                    "INSERT OR IGNORE INTO defect_entries "
                    "(audit_report_id, defect_type_id, major, minor, comment) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (report_id, type_id, major, minor, comment),
                )
                migrated += 1

        logging.info(f"migrate_defect_items: migrated {migrated} row(s) into defect_entries")

        # Drop the old table once migration is complete
        with self.conn:
            self.conn.execute("DROP TABLE IF EXISTS defect_items")
        logging.info("migrate_defect_items: defect_items table removed")
    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------

    def is_duplicate(self, file_name: str, report_no: str, date_of_issue: str) -> bool:
        """
        Return True if this audit record already exists in the DB.

        Duplicate criteria (checked separately, either is sufficient):
          1. Same file_name
          2. Same (report_no + date_of_issue) — catches re-named files
        """
        cur = self.conn.cursor()

        # Check 1: file_name
        cur.execute(
            "SELECT 1 FROM audit_reports WHERE file_name = ? LIMIT 1",
            (file_name,),
        )
        if cur.fetchone():
            logging.info(f"Duplicate (file_name): {file_name}")
            return True

        # Check 2: report_no + date_of_issue (normalise to ISO before comparing)
        if report_no and date_of_issue:
            iso = _to_iso_date(date_of_issue) or date_of_issue
            cur.execute(
                "SELECT 1 FROM audit_reports "
                "WHERE report_no = ? AND date_of_issue = ? LIMIT 1",
                (report_no, iso),
            )
            if cur.fetchone():
                logging.info(
                    f"Duplicate (report_no+date): {report_no} / {date_of_issue}"
                )
                return True

        return False

    # ------------------------------------------------------------------
    # Lookup upserts (get-or-create)
    # ------------------------------------------------------------------

    def _upsert_factory(self, name: str) -> int:
        """Return the factory.id for *name*, inserting if necessary."""
        name = (name or "UNKNOWN").strip()
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO factories(name) VALUES (?)", (name,)
            )
        row = self.conn.execute(
            "SELECT id FROM factories WHERE name = ?", (name,)
        ).fetchone()
        return row["id"]

    def _upsert_client(self, name: str) -> int:
        """Return the client.id for *name*, inserting if necessary."""
        name = (name or "UNKNOWN").strip()
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO clients(name) VALUES (?)", (name,)
            )
        row = self.conn.execute(
            "SELECT id FROM clients WHERE name = ?", (name,)
        ).fetchone()
        return row["id"]

    def _upsert_style(
        self,
        client_id: int,
        style_no: str,
        item_name: str,
        country: str,
    ) -> int:
        """Return style.id, inserting or updating item_name/country."""
        style_no = (style_no or "UNKNOWN").strip()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO styles(client_id, style_no, item_name, country)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(style_no) DO UPDATE SET
                    item_name = COALESCE(excluded.item_name, item_name),
                    country   = COALESCE(excluded.country,   country)
                """,
                (client_id, style_no, item_name or None, country or None),
            )
        row = self.conn.execute(
            "SELECT id FROM styles WHERE style_no = ?", (style_no,)
        ).fetchone()
        return row["id"]

    def _upsert_purchase_order(
        self,
        style_id: int,
        po_no: str,
        po_qty_raw: str,
        po_qty_pcs: int,
        po_qty_pack: int,
        po_qty_set: int,
    ) -> Optional[int]:
        """Return po.id, inserting or updating qty fields. Returns None if no po_no."""
        if not po_no or not po_no.strip():
            return None
        po_no = po_no.strip()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO purchase_orders
                    (style_id, po_no, po_qty_raw, po_qty_pcs, po_qty_pack, po_qty_set)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(po_no) DO UPDATE SET
                    po_qty_raw  = COALESCE(excluded.po_qty_raw,  po_qty_raw),
                    po_qty_pcs  = COALESCE(excluded.po_qty_pcs,  po_qty_pcs),
                    po_qty_pack = COALESCE(excluded.po_qty_pack, po_qty_pack),
                    po_qty_set  = COALESCE(excluded.po_qty_set,  po_qty_set)
                """,
                (style_id, po_no, po_qty_raw or None,
                 po_qty_pcs or None, po_qty_pack or None, po_qty_set or None),
            )
        row = self.conn.execute(
            "SELECT id FROM purchase_orders WHERE po_no = ?", (po_no,)
        ).fetchone()
        return row["id"]

    def _upsert_defect_type(self, category: str, item_name: str) -> int:
        """
        Return defect_types.id for the given (category, item_name) pair,
        inserting a new row if one does not already exist.

        sort_order is set to max+1 on first insert so new defect types
        always appear after the pre-seeded master list.
        """
        category  = (category  or "").strip()
        item_name = (item_name or "").strip()

        row = self.conn.execute(
            "SELECT id FROM defect_types WHERE category = ? AND item_name = ?",
            (category, item_name),
        ).fetchone()
        if row:
            return row["id"]

        max_row = self.conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) FROM defect_types"
        ).fetchone()
        next_sort = (max_row[0] or 0) + 1

        self.conn.execute(
            """
            INSERT OR IGNORE INTO defect_types (category, item_name, sort_order)
            VALUES (?, ?, ?)
            """,
            (category, item_name, next_sort),
        )

        row = self.conn.execute(
            "SELECT id FROM defect_types WHERE category = ? AND item_name = ?",
            (category, item_name),
        ).fetchone()
        return row["id"]

    # ------------------------------------------------------------------
    # Main record save
    # ------------------------------------------------------------------

    def save_record(self, record: AuditRecord) -> Optional[int]:
        """
        Persist a single AuditRecord to the database.

        Returns the new audit_reports.id, or None if:
          - record has blocking_errors  (user must fix via error JSON)
          - record is a duplicate

        Steps:
          1. Blocking check — return None with reason logged
          2. Duplicate check — return None if already present
          3. Upsert lookup rows (factory, client, style, PO)
          4. Detect defect template (28 / 35 / 78)
          5. Insert audit_reports row
          6. Insert audit_times, shipment_dates
          7. Insert defect_entries (linked to static defect_items_def if available)
          8. Insert delivery_orders
          9. Insert validation_errors (soft warnings)
        """
        # 1. Blocking check
        if record.blocking_errors:
            logging.info(
                f"SKIP (blocking errors) [{record.file_name}]: "
                + " | ".join(record.blocking_errors)
            )
            return None

        # 2. Duplicate check
        if self.is_duplicate(record.file_name, record.report_no, record.date_of_issue):
            return None

        # 2. Upsert lookups
        factory_id = self._upsert_factory(record.factory)
        client_id  = self._upsert_client(record.client)
        style_id   = self._upsert_style(
            client_id, record.style_no, record.item_name, record.country
        )
        po_id = self._upsert_purchase_order(
            style_id,
            record.po_no,
            record.po_qty,
            record.po_qty_pcs,
            record.po_qty_pack,
            record.po_qty_set,
        )

        # 4. Detect defect template from defect row count
        defect_count = len([
            d for d in record.defect_rows
            if isinstance(d, dict) and (
                int(d.get("major", 0) or 0) > 0 or
                int(d.get("minor", 0) or 0) > 0
            )
        ])
        # Use total rows (including zero-count) for template matching — the
        # template is determined by the Excel file's column structure, not
        # just the rows that happen to have defects.
        total_defect_rows = len([d for d in record.defect_rows if isinstance(d, dict)])
        template_id = self.match_defect_template(total_defect_rows) if total_defect_rows else None

        # Helper: convert "" to None for DB storage
        def _v(val: Any) -> Any:
            if val == "" or val == "-":
                return None
            return val

        # Helper: parse defect_percentage ("3.71%" → 3.71)
        def _pct(val: str) -> Optional[float]:
            if not val:
                return None
            try:
                return float(str(val).replace("%", "").strip())
            except (ValueError, TypeError):
                return None

        # Helper: safe int
        def _int(val: Any) -> Optional[int]:
            if val is None or val == "":
                return None
            try:
                return int(float(str(val).strip()))
            except (ValueError, TypeError):
                return None

        try:
            with self.conn:
                # 3. Insert audit_reports
                cur = self.conn.execute(
                    """
                    INSERT INTO audit_reports (
                        factory_id, client_id, style_id, po_id,
                        file_name, report_no, audit_report_no,
                        inspection_type, audit_result, date_of_issue,
                        do_qty, ship_qty, audit_qty,
                        defect_qty, acceptable_defect_qty, defect_percentage,
                        inspector, person,
                        carton, needle_detector, remarks, do_set_col_size, do_note,
                        has_validation_errors, defect_template_id
                    ) VALUES (
                        ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?
                    )
                    """,
                    (
                        factory_id, client_id, style_id, po_id,
                        record.file_name,
                        _v(record.report_no),
                        _v(record.audit_report),
                        _v(record.inspection_type),
                        _v(record.audit_result) or "-",
                        _to_iso_date(record.date_of_issue),
                        _int(record.do_qty),
                        _int(record.ship_qty),
                        _int(record.audit_qty),
                        _int(record.defect_qty),
                        _v(record.acceptable_defect_qty),
                        _pct(record.defect_percentage),
                        _v(record.inspector),
                        _v(record.person),
                        _v(record.carton),
                        _v(record.needle_detector),
                        _v(record.remarks),
                        _v(record.do_set_col_size),
                        _v(record.do_note),
                        1 if record.validation_errors else 0,
                        template_id,
                    ),
                )
                report_id = cur.lastrowid

                # 4. audit_times
                self.conn.execute(
                    """
                    INSERT INTO audit_times
                        (audit_report_id, factory_in, factory_out, factory_total_hours,
                         audit_start, audit_end, audit_total_hours)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report_id,
                        _v(record.factory_in_time),
                        _v(record.factory_out_time),
                        _v(record.factory_total_hours),
                        _v(record.audit_start_time),
                        _v(record.audit_end_time),
                        _v(record.audit_total_hours),
                    ),
                )

                # shipment_dates
                self.conn.execute(
                    """
                    INSERT INTO shipment_dates
                        (audit_report_id, exf, po_edt, po_wh, plan_edt, plan_wh)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report_id,
                        _to_iso_date(record.exf),
                        _to_iso_date(record.po_edt),
                        _to_iso_date(record.po_wh),
                        _to_iso_date(record.plan_edt),
                        _to_iso_date(record.plan_wh),
                    ),
                )

                # 5. defect_entries (via defect_types lookup/upsert)

                self._ensure_defect_entries_table()
                
                for d in record.defect_rows:
                    if not isinstance(d, dict):
                        continue
                    cat  = (d.get("category") or "").strip()
                    item = (d.get("item") or "").strip()
                    if not cat or not item:
                        continue

                    major   = int(d.get("major", 0) or 0)
                    minor   = int(d.get("minor", 0) or 0)
                    comment = d.get("comment") or None

                    # Skip rows with no data at all
                    if major == 0 and minor == 0 and not comment:
                        continue

                    # Get-or-create the defect_type master row
                    type_id = self._upsert_defect_type(cat, item)

                    # Insert the per-audit entry
                    self.conn.execute(
                        """
                        INSERT OR REPLACE INTO defect_entries
                            (audit_report_id, defect_type_id, major, minor, comment)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (report_id, type_id, major, minor, comment),
                    )

                # 6. delivery_orders
                for idx, do_row in enumerate(record.do_orders):
                    if not isinstance(do_row, dict):
                        continue
                    self.conn.execute(
                        """
                        INSERT INTO delivery_orders (
                            audit_report_id, do_date, po_qty, do_no, do_qty,
                            ship_qty, audit_qty, do_balance_and_extra, po_balance,
                            remarks, special_note, row_order
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            report_id,
                            do_row.get("date"),
                            do_row.get("po_qty"),
                            do_row.get("do_no"),
                            do_row.get("do_qty"),
                            do_row.get("ship_qty"),
                            do_row.get("audit_qty"),
                            do_row.get("do_balance_and_extra"),
                            do_row.get("po_balance"),
                            do_row.get("remarks"),
                            do_row.get("special_note"),
                            idx,
                        ),
                    )

                # 7. validation_errors
                for err in record.validation_errors:
                    self.conn.execute(
                        "INSERT INTO validation_errors (audit_report_id, error_message) "
                        "VALUES (?, ?)",
                        (report_id, err),
                    )

            logging.info(f"Saved record id={report_id}: {record.file_name}")
            return report_id

        except sqlite3.IntegrityError as exc:
            logging.warning(f"IntegrityError saving {record.file_name}: {exc}")
            return None
        except Exception as exc:
            logging.exception(f"Error saving {record.file_name}: {exc}")
            raise

    # ------------------------------------------------------------------
    # Query helpers (used by Writer script)
    # ------------------------------------------------------------------

    def query_records(
        self,
        factory: str = "",
        client: str = "",
        start_date: str = "",
        end_date: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Return audit rows matching the given filters as a list of dicts.

        All parameters are optional; omitting them returns all records.
        Dates should be in 'MM/DD/YYYY' or 'YYYY-MM-DD' format.
        """
        conditions = []
        params: List[Any] = []

        if factory:
            conditions.append("LOWER(factory) LIKE LOWER(?)")
            params.append(f"%{factory}%")

        if client:
            conditions.append("LOWER(client) LIKE LOWER(?)")
            params.append(f"%{client}%")

        if start_date:
            conditions.append("date_of_issue >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("date_of_issue <= ?")
            params.append(end_date)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"SELECT * FROM v_audit_full {where} ORDER BY date_of_issue, report_id"

        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def query_defect_items(self, report_id: int) -> List[Dict[str, Any]]:
        """Return all defect items for a given audit_reports.id.

        Queries defect_entries + defect_types (current schema) and returns
        legacy-compatible column names used by summary_writer.py:
            audit_report_id, category, item, major_count, minor_count, comment
        """
        rows = self.conn.execute(
            """
            SELECT
                de.audit_report_id,
                dt.category,
                dt.item_name        AS item,
                de.major            AS major_count,
                de.minor            AS minor_count,
                de.comment
            FROM defect_entries de
            JOIN defect_types   dt ON dt.id = de.defect_type_id
            WHERE de.audit_report_id = ?
            ORDER BY dt.sort_order, dt.category, dt.item_name
            """,
            (report_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def query_defect_items_for_reports(
        self, report_ids: List[int]
    ) -> Dict[int, List[Dict[str, Any]]]:
        """
        Batch-fetch defect items for multiple report IDs.
        Returns {report_id: [defect_item_dict, ...]}
        """
        if not report_ids:
            return {}
        placeholders = ",".join("?" * len(report_ids))
        rows = self.conn.execute(
            f"""
            SELECT
                de.audit_report_id,
                dt.category,
                dt.item_name        AS item,
                de.major            AS major_count,
                de.minor            AS minor_count,
                de.comment
            FROM defect_entries de
            JOIN defect_types   dt ON dt.id = de.defect_type_id
            WHERE de.audit_report_id IN ({placeholders})
            ORDER BY de.audit_report_id, dt.sort_order, dt.category, dt.item_name
            """,
            report_ids,
        ).fetchall()
        result: Dict[int, List[Dict[str, Any]]] = {}
        for r in rows:
            d = dict(r)
            result.setdefault(d["audit_report_id"], []).append(d)
        return result

    def get_all_factories(self) -> List[str]:
        """Return sorted list of all factory names in the DB."""
        rows = self.conn.execute(
            "SELECT name FROM factories ORDER BY name"
        ).fetchall()
        return [r["name"] for r in rows]

    def get_all_clients(self) -> List[str]:
        """Return sorted list of all client names in the DB."""
        rows = self.conn.execute(
            "SELECT name FROM clients ORDER BY name"
        ).fetchall()
        return [r["name"] for r in rows]

    def get_date_range(self) -> tuple:
        """
        Return (min_date, max_date) of date_of_issue across all records,
        both as YYYY-MM-DD strings. Returns ('', '') if no records exist.
        """
        row = self.conn.execute(
            "SELECT MIN(date_of_issue), MAX(date_of_issue) FROM audit_reports"
        ).fetchone()
        if row and row[0]:
            return row[0], row[1]
        return "", ""

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\db\__init__.py


# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\db_schema\db_loader.py

"""
db_loader.py
------------
Loads audit report data from summary.json into the PostgreSQL database.

Usage
-----
    python db_loader.py --json path/to/summary.json
    python db_loader.py --json path/to/summary.json --dry-run

Environment variables (or .env file)
--------------------------------------
    DB_HOST      (default: localhost)
    DB_PORT      (default: 5432)
    DB_NAME      (default: audit_db)
    DB_USER      (default: postgres)
    DB_PASSWORD  (required)

Upsert strategy
---------------
All inserts use ON CONFLICT DO UPDATE so the loader is fully idempotent —
running it twice on the same JSON file will update existing rows rather than
raise duplicate-key errors.

Transaction model
-----------------
Each audit report and all its children (times, shipment dates, defects,
delivery orders, validation errors) are written in a single transaction.
If any child insert fails the whole report is rolled back and logged; other
reports in the batch continue.
"""

import argparse
import json
import logging
import os
import sys
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB connection
# ---------------------------------------------------------------------------

def get_connection() -> psycopg2.extensions.connection:
    """Open and return a psycopg2 connection from environment variables."""
    return psycopg2.connect(
        host     = os.getenv("DB_HOST",     "localhost"),
        port     = int(os.getenv("DB_PORT", "5432")),
        dbname   = os.getenv("DB_NAME",     "audit_db"),
        user     = os.getenv("DB_USER",     "postgres"),
        password = os.getenv("DB_PASSWORD", ""),
    )


@contextmanager
def transaction(conn):
    """Context manager: commit on success, rollback on any exception."""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------

def _str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _int(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(float(str(v).replace(",", "").strip()))
    except (ValueError, TypeError):
        return None


def _float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _date(v: Any) -> Optional[date]:
    """
    Parse a date string (MM-DD-YYYY or MM/DD/YYYY) to a Python date object.
    Returns None if unparseable.
    """
    if not v:
        return None
    s = str(v).strip()
    for fmt in ("%m-%d-%Y", "%m/%d/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    log.debug(f"Unrecognised date format: '{s}'")
    return None


def _time(v: Any) -> Optional[str]:
    """
    Return a time string suitable for PostgreSQL TIME column.
    Accepts "HH:MM", "HH:MM AM/PM".  Returns None if unparseable.
    """
    if not v:
        return None
    s = str(v).strip()
    # Already in HH:MM 24-hour format
    import re
    if re.match(r"^\d{2}:\d{2}$", s):
        return s
    # 12-hour format e.g. "09:30 AM"
    for fmt in ("%I:%M %p", "%I:%M%p"):
        try:
            return datetime.strptime(s, fmt).strftime("%H:%M")
        except ValueError:
            continue
    return None


def _pct(v: Any) -> Optional[float]:
    """'3.71%' or 3.71 → 3.71.  None on failure."""
    if v is None:
        return None
    try:
        return float(str(v).replace("%", "").strip())
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Upsert helpers for lookup tables
# ---------------------------------------------------------------------------

def upsert_factory(cur, name: str) -> int:
    """Insert factory if not exists; return its id."""
    cur.execute(
        """
        INSERT INTO factories (name)
        VALUES (%s)
        ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
        RETURNING id
        """,
        (name,),
    )
    return cur.fetchone()[0]


def upsert_buyer(cur, name: str) -> int:
    """Insert buyer if not exists; return its id."""
    cur.execute(
        """
        INSERT INTO buyers (name)
        VALUES (%s)
        ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
        RETURNING id
        """,
        (name,),
    )
    return cur.fetchone()[0]


def upsert_style(
    cur,
    buyer_id: int,
    style_no: str,
    item_name: Optional[str],
    country: Optional[str],
) -> int:
    """Insert style if not exists; update item_name/country if changed. Return id."""
    cur.execute(
        """
        INSERT INTO styles (buyer_id, style_no, item_name, country)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (style_no) DO UPDATE SET
            item_name = COALESCE(EXCLUDED.item_name, styles.item_name),
            country   = COALESCE(EXCLUDED.country,   styles.country)
        RETURNING id
        """,
        (buyer_id, style_no, item_name, country),
    )
    return cur.fetchone()[0]


def upsert_purchase_order(
    cur,
    style_id: int,
    po_no: str,
    po_qty_raw:  Optional[str],
    po_qty_pcs:  int,
    po_qty_pack: int,
    po_qty_set:  int,
) -> int:
    """Insert PO if not exists; update quantities if changed. Return id."""
    cur.execute(
        """
        INSERT INTO purchase_orders
            (style_id, po_no, po_qty_raw, po_qty_pcs, po_qty_pack, po_qty_set)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (po_no) DO UPDATE SET
            po_qty_raw  = COALESCE(EXCLUDED.po_qty_raw,  purchase_orders.po_qty_raw),
            po_qty_pcs  = GREATEST(EXCLUDED.po_qty_pcs,  purchase_orders.po_qty_pcs),
            po_qty_pack = GREATEST(EXCLUDED.po_qty_pack, purchase_orders.po_qty_pack),
            po_qty_set  = GREATEST(EXCLUDED.po_qty_set,  purchase_orders.po_qty_set)
        RETURNING id
        """,
        (style_id, po_no, po_qty_raw, po_qty_pcs, po_qty_pack, po_qty_set),
    )
    return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Core audit report upsert
# ---------------------------------------------------------------------------

def upsert_audit_report(
    cur,
    factory_id: int,
    style_id:   int,
    po_id:      Optional[int],
    rec:        Dict[str, Any],
) -> int:
    """
    Insert or update the audit_reports row.
    Uses file_name as the natural unique key.
    Returns the row id.
    """
    cur.execute(
        """
        INSERT INTO audit_reports (
            factory_id, style_id, po_id,
            file_name,
            report_no, audit_report_no, inspection_type, audit_result, date_of_issue,
            do_qty, ship_qty, audit_qty, defect_qty, acceptable_defect_qty, defect_percentage,
            inspector, person,
            carton, needle_detector, remarks, do_set_col_size, do_note,
            has_validation_errors
        )
        VALUES (
            %s, %s, %s,
            %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s,
            %s, %s, %s, %s, %s,
            %s
        )
        ON CONFLICT (file_name) DO UPDATE SET
            factory_id            = EXCLUDED.factory_id,
            style_id              = EXCLUDED.style_id,
            po_id                 = COALESCE(EXCLUDED.po_id, audit_reports.po_id),
            report_no             = COALESCE(EXCLUDED.report_no,       audit_reports.report_no),
            audit_report_no       = COALESCE(EXCLUDED.audit_report_no, audit_reports.audit_report_no),
            inspection_type       = COALESCE(EXCLUDED.inspection_type, audit_reports.inspection_type),
            audit_result          = COALESCE(EXCLUDED.audit_result,    audit_reports.audit_result),
            date_of_issue         = COALESCE(EXCLUDED.date_of_issue,   audit_reports.date_of_issue),
            do_qty                = COALESCE(EXCLUDED.do_qty,          audit_reports.do_qty),
            ship_qty              = COALESCE(EXCLUDED.ship_qty,        audit_reports.ship_qty),
            audit_qty             = COALESCE(EXCLUDED.audit_qty,       audit_reports.audit_qty),
            defect_qty            = COALESCE(EXCLUDED.defect_qty,      audit_reports.defect_qty),
            acceptable_defect_qty = COALESCE(EXCLUDED.acceptable_defect_qty, audit_reports.acceptable_defect_qty),
            defect_percentage     = COALESCE(EXCLUDED.defect_percentage,     audit_reports.defect_percentage),
            inspector             = COALESCE(EXCLUDED.inspector,       audit_reports.inspector),
            person                = COALESCE(EXCLUDED.person,          audit_reports.person),
            carton                = COALESCE(EXCLUDED.carton,          audit_reports.carton),
            needle_detector       = COALESCE(EXCLUDED.needle_detector, audit_reports.needle_detector),
            remarks               = COALESCE(EXCLUDED.remarks,         audit_reports.remarks),
            do_set_col_size       = COALESCE(EXCLUDED.do_set_col_size, audit_reports.do_set_col_size),
            do_note               = COALESCE(EXCLUDED.do_note,         audit_reports.do_note),
            has_validation_errors = EXCLUDED.has_validation_errors,
            updated_at            = now()
        RETURNING id
        """,
        (
            factory_id, style_id, po_id,
            _str(rec.get("file_name")),
            _str(rec.get("report_no")),
            _str(rec.get("audit_report")),
            _str(rec.get("inspection_type")),
            _str(rec.get("audit_result")),
            _date(rec.get("date_of_issue")),
            _int(rec.get("do_qty")),
            _int(rec.get("ship_qty")),
            _int(rec.get("audit_qty")),
            _int(rec.get("defect_qty")),
            _int(rec.get("acceptable_defect_qty")),
            _pct(rec.get("defect_percentage")),
            _str(rec.get("inspector")),
            _str(rec.get("person")),
            _str(rec.get("carton")),
            _str(rec.get("needle_detector")),
            _str(rec.get("remarks")),
            _str(rec.get("do_set_col_size")),
            _str(rec.get("do_note")),
            bool(rec.get("validation", {}).get("has_errors", False)),
        ),
    )
    return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Child table writers
# ---------------------------------------------------------------------------

def write_audit_times(cur, report_id: int, rec: Dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO audit_times
            (audit_report_id, factory_in, factory_out, factory_total_hours,
             audit_start, audit_end, audit_total_hours)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (audit_report_id) DO UPDATE SET
            factory_in          = EXCLUDED.factory_in,
            factory_out         = EXCLUDED.factory_out,
            factory_total_hours = EXCLUDED.factory_total_hours,
            audit_start         = EXCLUDED.audit_start,
            audit_end           = EXCLUDED.audit_end,
            audit_total_hours   = EXCLUDED.audit_total_hours
        """,
        (
            report_id,
            _time(rec.get("factory_in")),
            _time(rec.get("factory_out")),
            _float(rec.get("factory_hours")),
            _time(rec.get("audit_start")),
            _time(rec.get("audit_end")),
            _float(rec.get("audit_hours")),
        ),
    )


def write_shipment_dates(cur, report_id: int, rec: Dict[str, Any]) -> None:
    # Dates may be nested under "shipment_dates" key or flat on the record
    sd = rec.get("shipment_dates") or {}
    cur.execute(
        """
        INSERT INTO shipment_dates
            (audit_report_id, exf, po_edt, po_wh, plan_edt, plan_wh)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (audit_report_id) DO UPDATE SET
            exf      = EXCLUDED.exf,
            po_edt   = EXCLUDED.po_edt,
            po_wh    = EXCLUDED.po_wh,
            plan_edt = EXCLUDED.plan_edt,
            plan_wh  = EXCLUDED.plan_wh
        """,
        (
            report_id,
            _date(rec.get("exf")      or sd.get("exf")),
            _date(rec.get("po_edt")   or sd.get("po_edt")),
            _date(rec.get("warehouse_date") or sd.get("po_wh")),
            _date(rec.get("plan_edt") or sd.get("plan_edt")),
            _date(rec.get("plan_wh")  or sd.get("plan_wh")),
        ),
    )


def write_defect_items(
    cur, report_id: int, defects: List[Dict[str, Any]]
) -> None:
    """
    Delete existing defect rows for this report then bulk-insert new ones.
    This is simpler than an upsert because defect rows have no natural key.
    """
    cur.execute(
        "DELETE FROM defect_items WHERE audit_report_id = %s",
        (report_id,),
    )

    if not defects:
        return

    rows = []
    for d in defects:
        # Support both new format {category, item, major, minor, comment}
        # and legacy format {label, severity, count}
        if "item" in d:
            category    = _str(d.get("category")) or ""
            item        = _str(d.get("item"))     or ""
            major_count = _int(d.get("major"))    or 0
            minor_count = _int(d.get("minor"))    or 0
            comment     = _str(d.get("comment"))
        else:
            category    = _str(d.get("label"))    or ""
            item        = ""
            severity    = _str(d.get("severity")) or "major"
            count       = _int(d.get("count"))    or 0
            major_count = count if severity == "major" else 0
            minor_count = count if severity == "minor" else 0
            comment     = None

        rows.append((report_id, category, item, major_count, minor_count, comment))

    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO defect_items
            (audit_report_id, category, item, major_count, minor_count, comment)
        VALUES %s
        """,
        rows,
    )


def write_delivery_orders(
    cur, report_id: int, do_orders: List[Dict[str, Any]]
) -> None:
    """Delete and re-insert D.O. rows (same reason as defect_items)."""
    cur.execute(
        "DELETE FROM delivery_orders WHERE audit_report_id = %s",
        (report_id,),
    )

    if not do_orders:
        return

    rows = []
    for i, do in enumerate(do_orders):
        rows.append((
            report_id,
            _date(do.get("date")),
            _int(do.get("po_qty")),
            _str(do.get("do_no")),
            _int(do.get("do_qty")),
            _int(do.get("ship_qty")),
            _int(do.get("audit_qty")),
            _int(do.get("do_balance_and_extra")),
            _int(do.get("po_balance")),
            _str(do.get("remarks")),
            _str(do.get("special_note")),
            i,   # row_order
        ))

    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO delivery_orders (
            audit_report_id, do_date, po_qty, do_no, do_qty, ship_qty,
            audit_qty, do_balance_and_extra, po_balance, remarks, special_note, row_order
        )
        VALUES %s
        """,
        rows,
    )


def write_validation_errors(
    cur, report_id: int, errors: List[str]
) -> None:
    """Delete and re-insert validation errors."""
    cur.execute(
        "DELETE FROM validation_errors WHERE audit_report_id = %s",
        (report_id,),
    )
    if not errors:
        return

    rows = [(report_id, str(e)) for e in errors if e]
    psycopg2.extras.execute_values(
        cur,
        "INSERT INTO validation_errors (audit_report_id, error_message) VALUES %s",
        rows,
    )


# ---------------------------------------------------------------------------
# Per-record loader
# ---------------------------------------------------------------------------

def _is_placeholder(rec: Dict[str, Any]) -> bool:
    """
    True if *rec* is a json_writer placeholder row (carton / shipment_dates /
    empty label rows) rather than a primary audit record.
    Placeholder rows have a 'label' key or only 'shipment_dates'.
    """
    if "label" in rec:
        return True
    keys = set(rec.keys())
    # A placeholder for shipment_dates only has file_name, factory, shipment_dates
    if keys <= {"file_name", "factory", "shipment_dates"}:
        return True
    return False


def load_record(conn, rec: Dict[str, Any], dry_run: bool = False) -> bool:
    """
    Load one primary audit record (and all its children) into the DB.

    Returns True on success, False on failure.
    """
    file_name    = _str(rec.get("file_name"))
    factory_name = _str(rec.get("factory"))
    style_no     = _str(rec.get("style_no"))
    buyer_name   = _str(rec.get("buyer")) or "UNKNOWN"   # buyer not always in JSON

    # Minimum required fields
    if not file_name or not factory_name:
        log.warning(f"Skipping record — missing file_name or factory: {rec}")
        return False

    # Fall back gracefully when style_no is missing
    if not style_no:
        style_no = "UNKNOWN"

    log.info(f"Loading: {file_name}")

    if dry_run:
        log.info(f"  [DRY RUN] Would insert factory='{factory_name}' "
                 f"style='{style_no}' po='{rec.get('po_no')}'")
        return True

    try:
        with transaction(conn):
            cur = conn.cursor()

            # ── Lookup / dimension rows ──────────────────────────────────────
            factory_id = upsert_factory(cur, factory_name)
            buyer_id   = upsert_buyer(cur, buyer_name)
            style_id   = upsert_style(
                cur,
                buyer_id  = buyer_id,
                style_no  = style_no,
                item_name = _str(rec.get("item_name")),
                country   = _str(rec.get("country")),
            )

            po_id = None
            po_no = _str(rec.get("po_no"))
            if po_no:
                po_id = upsert_purchase_order(
                    cur,
                    style_id    = style_id,
                    po_no       = po_no,
                    po_qty_raw  = _str(rec.get("po_qty")),
                    po_qty_pcs  = _int(rec.get("po_qty_pcs"))  or 0,
                    po_qty_pack = _int(rec.get("po_qty_pack")) or 0,
                    po_qty_set  = _int(rec.get("po_qty_set"))  or 0,
                )

            # ── Core audit report ────────────────────────────────────────────
            report_id = upsert_audit_report(cur, factory_id, style_id, po_id, rec)

            # ── Child tables (always delete + re-insert) ─────────────────────
            write_audit_times(cur, report_id, rec)
            write_shipment_dates(cur, report_id, rec)
            write_defect_items(cur, report_id, rec.get("defects", []))
            write_delivery_orders(cur, report_id, rec.get("do_orders", []))
            write_validation_errors(
                cur, report_id,
                rec.get("validation", {}).get("errors", []),
            )

            log.info(
                f"  → report_id={report_id} "
                f"defects={len(rec.get('defects', []))} "
                f"do_orders={len(rec.get('do_orders', []))}"
            )
            return True

    except Exception as exc:
        log.error(f"  FAILED to load '{file_name}': {exc}")
        return False


# ---------------------------------------------------------------------------
# Batch loader
# ---------------------------------------------------------------------------

def load_json(json_path: Path, dry_run: bool = False) -> None:
    """
    Read summary.json and load every primary record into the database.

    Skips placeholder rows emitted by json_writer.py.
    Logs a final success/failure summary.
    """
    log.info(f"Reading JSON: {json_path}")

    with open(json_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)

    records = payload.get("records", [])
    log.info(
        f"Found {len(records)} rows in JSON "
        f"(format: {payload.get('metadata', {}).get('format', 'unknown')})"
    )

    conn = get_connection() if not dry_run else None

    success = 0
    skipped = 0
    failed  = 0

    for rec in records:
        # Skip placeholder rows
        if _is_placeholder(rec):
            skipped += 1
            continue

        result = load_record(conn, rec, dry_run=dry_run)
        if result:
            success += 1
        else:
            failed += 1

    if conn:
        conn.close()

    log.info("=" * 50)
    log.info(f"LOAD COMPLETE")
    log.info(f"  Success : {success}")
    log.info(f"  Skipped : {skipped}  (placeholder rows)")
    log.info(f"  Failed  : {failed}")
    log.info("=" * 50)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load audit report JSON into the PostgreSQL database."
    )
    parser.add_argument(
        "--json",
        required=True,
        type=Path,
        help="Path to summary.json produced by the extractor.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate without writing to the database.",
    )
    args = parser.parse_args()

    if not args.json.exists():
        log.error(f"JSON file not found: {args.json}")
        sys.exit(1)

    load_json(args.json, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\enums\field_enums.py

"""
field_enums.py
--------------
All Enum definitions for the audit extraction system.

To add a new field:
  1. Add the field name to FieldName.
  2. Add synonyms to LabelSynonym.
  3. Wire them together in label_config.py → LABELS.

To add a new country prefix:
  - Add to StyleCountryPrefix and update STYLE_COUNTRY_MAP in label_config.py.
"""

from enum import Enum


# ---------------------------------------------------------------------------
# Field Names  (must match AuditRecord attribute names exactly)
# ---------------------------------------------------------------------------

class FieldName(str, Enum):
    """Internal names for every field extracted from Excel audit reports."""

    # Identity / header
    FACTORY           = "factory"
    DATE_OF_ISSUE     = "date_of_issue"
    INSPECTION_TYPE   = "inspection_type"
    REPORT_NO         = "report_no"
    AUDIT_REPORT      = "audit_report"
    ITEM_NAME         = "item_name"
    STYLE_NO          = "style_no"
    PO_NO             = "po_no"
    COUNTRY           = "country"

    # Time fields
    FACTORY_IN_TIME     = "factory_in_time"
    FACTORY_OUT_TIME    = "factory_out_time"
    FACTORY_TOTAL_HOURS = "factory_total_hours"
    AUDIT_START_TIME    = "audit_start_time"
    AUDIT_END_TIME      = "audit_end_time"
    AUDIT_TOTAL_HOURS   = "audit_total_hours"

    # Audit outcome
    AUDIT_RESULT = "audit_result"

    # Quantity fields
    PO_QTY    = "po_qty"
    DO_QTY    = "do_qty"
    SHIP_QTY  = "ship_qty"
    AUDIT_QTY = "audit_qty"

    # Details of shipment dates
    EXF      = "exf"
    PO_EDT   = "po_edt"
    PO_WH    = "po_wh"
    PLAN_EDT = "plan_edt"
    PLAN_WH  = "plan_wh"

    # Defect summary
    DEFECT_QTY            = "defect_qty"
    ACCEPTABLE_DEFECT_QTY = "acceptable_defect_qty"
    DEFECT_PERCENTAGE     = "defect_percentage"

    # Personnel
    PERSON    = "person"
    INSPECTOR = "inspector"

    # Additional checks
    CARTON           = "carton"
    NEEDLE_DETECTOR  = "needle_detector"
    REMARKS          = "remarks"
    DO_SET_COL_SIZE  = "do_set_col_size"
    CARTON_NUMBER    = "carton_number"

    DETAILS_OF_SHIPMENT = "details_of_shipment"

    # Client / buyer (extracted from Excel label "client")
    CLIENT = "client"


# ---------------------------------------------------------------------------
# Label Synonyms  (all text variants that appear in Excel headers)
# ---------------------------------------------------------------------------

class LabelSynonym(str, Enum):
    """
    Synonyms for column/row labels found in Excel audit sheets.
    Add new spellings here when a new sheet format is encountered.
    """

    # Factory
    FACTORY      = "factory"
    FACTORY_NAME = "factory name"

    # Date of Issue
    DATE_OF_ISSUE   = "date of issue"
    ISSUE_DATE      = "issue date"
    REPORT_DATE     = "report date"
    INSPECTION_DATE = "inspection date"

    # Inspection Type
    INSPECTION_TYPE = "inspection type"
    AUDIT_TYPE      = "audit type"

    # Factory Times
    FACTORY_IN_TIME  = "factory in time"
    FACTORY_INTIME   = "factory in-time"
    FACTORY_INTIME2  = "factory intime"
    IN_TIME          = "in time"
    FACTORY_OUT_TIME = "factory out time"
    FACTORY_OUTTIME  = "factory out-time"
    FACTORY_OUTTIME2 = "factory outtime"
    OUT_TIME         = "out time"

    # Audit Times
    AUDIT_START_TIME = "audit start time"
    START_TIME       = "start time"
    AUDIT_END_TIME   = "audit end time"
    END_TIME         = "end time"

    # Audit Result
    AUDIT_RESULT      = "audit result"
    RESULT            = "result"
    INSPECTION_RESULT = "inspection result"

    # Report / PO numbers
    REPORT_NO            = "report no"
    REPORT_NUMBER        = "report number"
    INSPECTION_REPORT_NO = "inspection report no"

    # Item Name
    ITEM_NAME   = "item name"
    DESCRIPTION = "description"

    # Style No
    STYLE_NO          = "style no"
    STYLE_NUMBER      = "style number"
    STYLE             = "style"
    LOCAL_SAMPLE_CODE = "local sample code"

    # PO No
    PO_NO             = "po no"
    PO_NO_DASH        = "po-no"
    PURCHASE_ORDER_NO = "purchase order no"

    # PO Quantity
    PO_QTY      = "po qty"
    PO_QUANTITY = "po quantity"
    PO_QTY_CAPS = "p.o qty"

    # DO Quantity
    DO_QTY      = "do qty"
    DO_QUANTITY = "do quantity"
    DO_QTY_CAPS = "d.o qty"

    # EXF date
    EXF   = "exf"
    EXF_  = "exf:"
    EXF__ = "exf :"

    # PO EDT
    PO_EDT   = "po. etd"
    _PO_EDT  = "po etd"
    PO__EDT  = "po.  etd"
    _PO__EDT = "po  etd"

    # PO Warehouse
    PO_WH       = "po wh"
    WAREHOUSE   = "warehouse"
    POWH        = "powh"
    PO_WH_SLASH = "po w/h"

    # Plan EDT
    PLAN_ETD  = "plan etd"
    PLAN__ETD = "plan  etd"

    # Plan WH
    PLAN_WH  = "plan wh"
    PLAN__WH = "plan  wh"

    # Ship Quantity
    SHIP_QTY               = "ship qty"
    SHIPMENT_QTY           = "shipment qty"
    SHIPPING_QUANTITY      = "shipping quantity"
    SHIPPING_QTY           = "shipping qty"
    AUDIT_FOR_SHIPPING_QTY = "audit for shipping qty"
    EXF_QTY                = "exf qty"

    # Audit Quantity
    AUDIT_QTY        = "audit qty"
    AUDITED_QUANTITY = "audited quantity"
    QTY_INSPECTED    = "qty.\ninspected"

    # Personnel
    INSPECTOR = "inspector"
    PERSON    = "person"

    # Defect qty (major column header in summary section)
    MAJOR_DEFECTS = "major\ndefects"

    # Carton / inspection carton
    OUR_INSPECTION_CARTON_NUMBER = "our inspection carton number"
    CARTON_INSPECTION            = "carton inspection"
    INSPECTION_CARTON            = "inspection carton"
    INSPECTION_CTN               = "inspection ctn"
    OUR_INSPECTION_CARTON        = "our inspection carton"

    # Needle detector
    NEEDLE_DETECTOR       = "needle detector"
    NEEDLE_DETECTOR_CHECK = "needle detector check"

    # Remarks
    REMARKS = "remarks"
    REMARK  = "remark"

    # DO/Set/Col/Size
    DO_SET_COL_SIZE = "do/set/col/size"

    # Client / buyer
    CLIENT       = "client"
    CLIENT_NAME  = "client name"
    BUYER        = "buyer"
    BUYER_NAME   = "buyer name"


# ---------------------------------------------------------------------------
# Direction Rules
# ---------------------------------------------------------------------------

class DirectionRule(str, Enum):
    """
    Controls where resolve_value() looks for the field value relative to the
    label cell.

    RIGHT            → scan right across the same row
    DOWN             → scan down the same column
    DOWN_IF_INT      → scan down but only accept integer values
    RIGHT_THEN_DOWN  → try right first, fall back to down
    DOWN_THEN_RIGHT  → try down first, fall back to right
    """
    RIGHT           = "right"
    DOWN            = "down"
    DOWN_IF_INT     = "down_if_int"
    RIGHT_THEN_DOWN = "right_then_down"
    DOWN_THEN_RIGHT = "down_then_right"


# ---------------------------------------------------------------------------
# Audit Type Patterns
# ---------------------------------------------------------------------------

class AuditPattern(str, Enum):
    """Keys used in AUDIT_PATTERNS regex map (label_config.py)."""
    RE_FINAL = "RE-FINAL"
    FINAL    = "FINAL"
    INLINE   = "INLINE"
    SAMPLE   = "SAMPLE"
    CMF      = "CMF"


# ---------------------------------------------------------------------------
# Style Number Country Prefixes
# ---------------------------------------------------------------------------

class StyleCountryPrefix(str, Enum):
    """
    First two characters of a style number that encode the destination country.
    Update STYLE_COUNTRY_MAP in label_config.py if new prefixes are added.
    """
    JAPAN  = "01"
    CHINA  = "03"
    USA    = "04"
    KOREA  = "05"
    EUROPE = "07"
    TAIWAN = "10"
    AU     = "14"
    CANADA = "17"
    INDIA  = "36"


# ---------------------------------------------------------------------------
# D.O. Table Column Names
# ---------------------------------------------------------------------------

class DOFieldName(str, Enum):
    """Internal names for every column in the Delivery Order plan table."""
    DATE       = "date"
    PO_QTY     = "po_qty"
    DO_NO      = "do_no"
    DO_QTY     = "do_qty"
    SHIP_QTY   = "ship_qty"
    AUDIT_QTY  = "audit_qty"
    DO_BALANCE = "do_balance"
    PO_EXTRA   = "po_extra"
    REMARKS    = "remarks"
    PO_BALANCE = "po_balance"


# ---------------------------------------------------------------------------
# D.O. Table Label Synonyms
# ---------------------------------------------------------------------------

class DOLabelSynonym(str, Enum):
    """All header text variants that can identify a D.O. table column."""

    DATE = "date"

    PO_QTY       = "po qty"
    P_O_QTY      = "p o qty"
    PO_QUANTITY  = "po quantity"
    P_O_QUANTITY = "p o quantity"

    DO_NO             = "do no"
    D_O_NO            = "d o no"
    DO_NUMBER         = "do number"
    D_O_NUMBER        = "d o number"
    DELIVERY_ORDER_NO = "delivery order no"

    DO_QTY       = "do qty"
    D_O_QTY      = "d o qty"
    DO_QUANTITY  = "do quantity"
    D_O_QUANTITY = "d o quantity"

    SHIP_QTY          = "ship qty"
    SHIP_QUANTITY     = "ship quantity"
    SHIPMENT_QTY      = "shipment qty"
    SHIPMENT_QUANTITY = "shipment quantity"

    AUDIT_QTY      = "audit qty"
    AUDIT_QUANTITY = "audit quantity"
    AUDITED_QTY    = "audited qty"

    DO_BALANCE           = "do balance"
    D_O_BALANCE          = "d o balance"
    DO_BALANCE_EXTRA     = "do balance extra"
    DO_BALANCE_AND_EXTRA = "do balance and extra"
    BALANCE_EXTRA        = "balance extra"

    PO_EXTRA  = "po extra"
    P_O_EXTRA = "p o extra"

    REMARKS                       = "remarks"
    BALANCE_QTY_PLAN              = "balance qty plan"
    BALANCE_QTY_PLAN_DATE         = "balance qty plan date"
    BALANCE_QTY_PLAN_DATE_REMARKS = "balance qty plan date remarks"
    PLAN_DATE_REMARKS             = "plan date remarks"

    PO_BALANCE = "po balance"
    PO_BAL     = "po bal"

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\enums\ui_field_enums.py

# enums/ui_field_enums.py

# Dropdown options (arrays)
ANALYSIS_TYPES = [
    "",
    "Final Summary",
    "100% Summary",
    "Metal Summary",
    "Packing List Summary",
]

REPORT_FORMATS = [
    "",
    "Uniqlo Report",
    "GU Report",
    "PUMA Report",
    "STX Report",
    "Special Audit Report",
    "General Audit Report",
    "Metal Audit Report",
    "Packing List Report",
]

# Defaults (keep them in sync with the lists above)
DEFAULT_ANALYSIS_TYPE = ANALYSIS_TYPES[0]
DEFAULT_REPORT_FORMAT = REPORT_FORMATS[0]

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\enums\__init__.py

# enums/__init__.py

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\extraction\audit_type_resolver.py

"""
audit_type_resolver.py
----------------------
Infers the audit type from the Excel *file name* when the sheet itself does
not contain an explicit "Inspection Type" / "Audit Type" label.

Decision tree (evaluated top-to-bottom):
  1. RE-FINAL  (e.g. "2nd time RE-FINAL 50%")
  2. FINAL     (e.g. "FACTORY_FINAL_AUDIT")
  3. INLINE / SAMPLE / CMF  (keyword match, returned as-is)
  4. UNKNOWN   (no keyword matched)

BUG FIXED: RE-FINAL fall-through
----------------------------------
Previously the RE-FINAL branch only returned inside the `if nth_match` block,
so filenames like "RE-FINAL_audit.xlsx" (no ordinal) fell through to the FINAL
branch and were incorrectly typed as "FINAL N%".  Now the function returns
unconditionally from the RE-FINAL branch.
"""

import logging
import re

from models.audit_record import AuditRecord
from extraction.label_config import AUDIT_PATTERNS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_pct(audit_qty: str, ship_qty: str) -> str:
    """Return 'NN.NN' percentage string, or '' if either quantity is invalid."""
    try:
        pct = round(int(audit_qty) / int(ship_qty) * 100, 2)
        return str(pct)
    except (ValueError, TypeError, ZeroDivisionError):
        logging.warning(
            f"Cannot compute audit % – audit_qty={audit_qty!r}, "
            f"ship_qty={ship_qty!r}"
        )
        return ""


# ---------------------------------------------------------------------------
# Main resolver
# ---------------------------------------------------------------------------

def resolve_audit_type(record: AuditRecord) -> str:
    """
    Derive the inspection type string from the record's file name.

    Returns one of:
      - "NN.NN% RE-FINAL"
      - "NTH TIME NN.NN% RE-FINAL"
      - "NN.NN% FINAL AUDIT"
      - "INLINE" | "SAMPLE" | "CMF"
      - "UNKNOWN"
    """
    if not record.file_name:
        return "UNKNOWN"

    name = record.file_name.lower().strip()

    # ── RE-FINAL ─────────────────────────────────────────────────────────────
    if re.search(AUDIT_PATTERNS["RE-FINAL"], name):
        pct       = _safe_pct(record.audit_qty, record.ship_qty)
        nth_match = re.search(r"\b(\d+(?:st|nd|rd|th))\s+time\b", name)

        if nth_match:
            nth_time = nth_match.group(1).upper()
            return f"{nth_time} RE-FINAL {pct}%" if pct else f"{nth_time} RE-FINAL"

        # BUG FIX: always return from the RE-FINAL branch; never fall through
        return f"RE-FINAL {pct}%" if pct else "RE-FINAL"

    # ── FINAL ─────────────────────────────────────────────────────────────────
    if re.search(AUDIT_PATTERNS["FINAL"], name):
        pct = _safe_pct(record.audit_qty, record.ship_qty)
        return f"FINAL {pct}%" if pct else "FINAL"

    # ── Other known types ─────────────────────────────────────────────────────
    for audit_type in ("INLINE", "SAMPLE", "CMF"):
        if re.search(AUDIT_PATTERNS[audit_type], name):
            return audit_type

    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Convenience wrapper used by post_processor
# ---------------------------------------------------------------------------

def extract_and_set_audit_type(record: AuditRecord) -> AuditRecord:
    """
    Set record.inspection_type from the file name if not already populated.
    Returns the (possibly mutated) record.
    """
    if not record.inspection_type:
        record.inspection_type = resolve_audit_type(record)
    return record

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\extraction\defect_extractor.py

"""
defect_extractor.py
-------------------
Auto-discovers and extracts the structured defect table from an Excel sheet.

Structure understood from samples
----------------------------------
The defect table always follows this layout:

  Row N   : "Defects" | ... | "Major Defect" | "Minor Defect" | "Comment"
  Row N+1 : "A : Fabrics" | "1.Damage" | ...
  ...
  Row M   : "F : Others" | ... | "3.Others" | ...   ← last data row

Detection strategy
------------------
1. Find the header row containing the cell "Defects" in column A.
2. The "Major Defect", "Minor Defect", and "Comment" column indices are
   discovered from that same header row — NO hardcoded columns.
3. Scan downward, carrying the current category (A:Fabrics, B:Sewing …)
   forward across merged/blank category cells.
4. Stop when the cell in column A equals "DO/Set/Col/Size" or when an
   empty row is followed by a non-defect section (robust sentinel).

Output
------
A list of dicts, one per defect item that has at least one non-zero count:

    [
        {
            "category": "B : Sewing",
            "item":     "3.Pieces not symmetrical",
            "major":    1,
            "minor":    0,
            "comment":  "CUFF POINT UP-DOWN",
        },
        ...
    ]

Also returns the totals dict:
    {"major": 9, "minor": 0}

Both are stored on AuditRecord by the caller.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from pathlib import Path


# ---------------------------------------------------------------------------
# Sentinel – the cell value that marks the end of the defect table
# ---------------------------------------------------------------------------

_END_SENTINEL_PATTERN = re.compile(r"do\s*/\s*set\s*/\s*col\s*/\s*size", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_int(value: Any) -> int:
    """Convert a cell value to int, returning 0 on failure."""
    if value is None:
        return 0
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return 0


def _is_end_sentinel(value: Any) -> bool:
    if value is None:
        return False
    return bool(_END_SENTINEL_PATTERN.search(str(value)))


def _is_category_cell(value: Any) -> bool:
    """True for section-header cells like 'A : Fabrics', 'B : Sewing' etc."""
    if not value:
        return False
    return bool(re.match(r"^[A-F]\s*:", str(value).strip()))


# ---------------------------------------------------------------------------
# Main extractor – uses openpyxl for raw cell access (preserves merged cells)
# ---------------------------------------------------------------------------

def extract_defect_table_from_file(
    path: Path,
    sheet_name: str = "Inspection Report",
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Open *path* with openpyxl and extract the defect table from *sheet_name*.

    Returns
    -------
    (defect_rows, totals)
      defect_rows : list of dicts with keys category/item/major/minor/comment
      totals      : {"major": N, "minor": N}  (summed across all rows)

    Falls back to the first sheet if *sheet_name* is not found.
    """
    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    except Exception as exc:
        logging.error(f"Cannot open '{path.name}': {exc}")
        return [], {}

    # Resolve sheet
    if sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
    else:
        # Try case-insensitive match
        match = next(
            (s for s in wb.sheetnames if s.lower() == sheet_name.lower()), None
        )
        ws = wb[match] if match else wb[wb.sheetnames[0]]

    # Load all rows into a plain list of lists for easy indexing
    rows = list(ws.iter_rows(values_only=True))

    # ── Step 1: Find the header row ─────────────────────────────────────────
    header_row_idx: Optional[int] = None
    major_col: Optional[int] = None
    minor_col: Optional[int] = None
    comment_col: Optional[int] = None

    for r_idx, row in enumerate(rows):
        if row and str(row[0] or "").strip().lower() == "defects":
            header_row_idx = r_idx
            # Discover Major / Minor / Comment column indices
            for c_idx, cell in enumerate(row):
                if cell is None:
                    continue
                normalised = str(cell).strip().lower()
                if "major" in normalised and major_col is None:
                    major_col = c_idx
                elif "minor" in normalised and minor_col is None:
                    minor_col = c_idx
                elif "comment" in normalised and comment_col is None:
                    comment_col = c_idx
            break

    if header_row_idx is None:
        logging.warning(f"[{path.name}] Defect table header ('Defects') not found")
        return [], {}

    if major_col is None:
        logging.warning(f"[{path.name}] 'Major Defect' column not found in header")
        return [], {}

    logging.info(
        f"[{path.name}] Defect table header at row {header_row_idx + 1}; "
        f"major_col={major_col}, minor_col={minor_col}, comment_col={comment_col}"
    )

    # ── Step 2: Scan data rows ───────────────────────────────────────────────
    defect_rows: List[Dict[str, Any]] = []
    current_category: str = ""

    for r_idx in range(header_row_idx + 1, len(rows)):
        row = rows[r_idx]
        col_a = row[0] if row else None

        # Stop at sentinel (DO/Set/Col/Size section)
        if _is_end_sentinel(col_a):
            break

        # Update current category if this row starts a new section
        if _is_category_cell(col_a):
            current_category = str(col_a).strip()

        # Item name is always in column B (index 1)
        item_name = str(row[1]).strip() if (row and row[1] is not None) else ""
        # if not item_name:
        #     continue  # skip blank rows

        major   = _to_int(row[major_col] if major_col < len(row) else None)
        minor   = _to_int(row[minor_col] if minor_col is not None and minor_col < len(row) else None)
        comment = ""
        if comment_col is not None and comment_col < len(row) and row[comment_col]:
            comment = str(row[comment_col]).strip()

        # Only include rows that have at least some defect data
        # if major == 0 and minor == 0 and not comment:
        #     continue

        defect_rows.append({
            "category": current_category,
            "item":     item_name,
            "major":    major,
            "minor":    minor,
            "comment":  comment,
        })

    # ── Step 3: Compute totals ────────────────────────────────────────────────
    totals = {
        "major": sum(r["major"] for r in defect_rows),
        "minor": sum(r["minor"] for r in defect_rows),
    }

    logging.info(
        f"[{path.name}] Defect table: {len(defect_rows)} item(s) with defects; "
        f"totals={totals}"
    )

    wb.close()
    return defect_rows, totals

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\extraction\defect_qty_extractor.py

"""
defect_qty_extractor.py
-----------------------
Fallback extraction strategy for the defect quantity field.

Primary extraction (via rule_extractor) matches the "Major Defects" header.
If that fails, this module's custom logic scans for the *second* occurrence of
any cell containing the word "major" and reads the integer to its right.

Why second?  Audit sheets typically have:
  Row N   – "Major" as a column *header* in the defect table
  Row M   – "Major" as a *sub-total* row  ← we want this one
"""

import logging
import re
from typing import Tuple, List
from core.cell_grid import CellGrid

# ---------------------------------------------------------------------------
# Text helper (local, keeps the module self-contained)
# ---------------------------------------------------------------------------

def _normalize(value: str) -> str:
    text = value.lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()

# ---------------------------------------------------------------------------
# Label finder
# ---------------------------------------------------------------------------

def _find_major_labels(grid: CellGrid) -> list[Tuple[int, int, str]]:
    """
    Return all (row, col, raw_value) tuples where the cell contains the
    word "major", sorted top-to-bottom.
    """
    major_labels = []
    
    for row in range(grid.nrows):
        for col in range(grid.ncols):
            cell_val = grid.get(row, col)
            if cell_val and "major" in _normalize(cell_val):
                major_labels.append((row, col, cell_val))
    
    major_labels.sort(key=lambda x: x[0])
    logging.info(f"Found {len(major_labels)} 'Major' labels: {[(r, c, v) for r, c, v in major_labels]}")
    return major_labels

# ---------------------------------------------------------------------------
# Custom (fallback) extractor
# ---------------------------------------------------------------------------

def _extract_defect_qty_custom(grid: CellGrid, known_audit_qty: str = "") -> str:
    """
    Scan for the second "major" occurrence and return the integer value
    found to its right.  Returns "" if not found.
    """
    major_labels = _find_major_labels(grid)
    
    if len(major_labels) < 2:
        logging.warning(f"Found only {len(major_labels)} 'Major' label(s), need at least 2 for fallback")
        return ""

    _, second_major_col, _ = major_labels[1]
    second_row = major_labels[1][0]
    
    # Scan up to 5 cells to the right of the second "Major" cell
    for c in range(second_major_col + 1, min(second_major_col + 6, grid.ncols)):
        raw = grid.get(second_row, c).strip()
        if not raw:
            continue
        try:
            # Accept integers only (defect count should be a whole number)
            int(float(raw))
            return raw
        except (ValueError, TypeError):
            continue
    return ""

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_defect_qty_with_fallback(grid: CellGrid, primary_value: str, audit_qty: str = "") -> str:
    """
    Return *primary_value* if it is non-empty; otherwise run the custom
    fallback search and return its result (or "").

    Parameters
    ----------
    grid          : CellGrid for the first sheet
    primary_value : value already found by the standard rule extractor
    """
    if primary_value and primary_value.strip():
        return primary_value
    
    logging.info("defect_qty primary extraction empty – running fallback")
    return _extract_defect_qty_custom(grid, audit_qty)

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\extraction\do_table_extractor.py

"""
do_table_extractor.py
---------------------
Finds and extracts the Delivery Order (D.O.) plan table from any sheet in
an Excel workbook, then stores the rows directly on AuditRecord.do_orders.

This module is fully config-driven: column headers are discovered by matching
normalised cell text against  DO_TABLE_LABELS  in label_config.py —
no column letters or positions are hardcoded.

Where to make changes
---------------------
- New header spelling       → enums/field_enums.py  (DOLabelSynonym)
                              extraction/label_config.py  (DO_TABLE_LABELS)
- New column                → enums/field_enums.py  (DOFieldName + DOLabelSynonym)
                              extraction/label_config.py  (DO_TABLE_LABELS)
                              _build_do_row() below  (read the new field)
- Fill-down (merged cells)  → extraction/label_config.py  (DO_FILL_DOWN_FIELDS)

Output stored on record
-----------------------
record.do_orders = [
    {
        "date":                 "22-Jan-26",
        "po_qty":               48000,
        "do_no":                "01",
        "do_qty":               48000,
        "ship_qty":             15132,
        "audit_qty":            378,
        "do_balance_and_extra": -32868,
        "po_balance":           -17688,
        "remarks":              "PO & DO BALANCE",
        "special_note":         null
    },
    ...
]
record.do_totals  = {"ship_qty": 30312, "audit_qty": 1636}
record.do_note    = "#OUR INSPECTION CARTON NUMBER: ..."
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from core.cell_grid import CellGrid, normalize_text
from core.sheet_reader import read_all_sheets
from extraction.label_config import DO_TABLE_LABELS, DO_FILL_DOWN_FIELDS


# ---------------------------------------------------------------------------
# Row classification helpers
# ---------------------------------------------------------------------------

_TOTAL_KEYWORDS = {"total", "totals", "grand total"}


def _is_total_row(cells: List[str]) -> bool:
    return any(normalize_text(c) in _TOTAL_KEYWORDS for c in cells if c.strip())


def _is_note_row(cells: List[str]) -> bool:
    for c in cells:
        if c.strip():
            return c.strip()[0] in {"#", "*"}
    return False


def _is_special_note(value: str) -> bool:
    """Cells like 'RANDOM FINAL (15,180) PCS' or '1st TIME RE-FINAL AUDIT…'."""
    return bool(re.search(r"(random|re.?final|re.?audit|audit)", value, re.IGNORECASE))


# ---------------------------------------------------------------------------
# Numeric helper
# ---------------------------------------------------------------------------

def _to_int_or_none(value: str) -> Optional[int]:
    if not value or not value.strip():
        return None
    # Strip everything except digits, minus, dot
    cleaned = re.sub(r"[^\d\-\.]", "", value.replace(",", ""))
    try:
        return int(float(cleaned))
    except (ValueError, TypeError):
        return None


def _format_date(value: str) -> Optional[str]:
    """Convert '2026-01-22 00:00:00' or datetime objects to '22-Jan-26'."""
    if not value:
        return None
    s = str(value).strip()
    # Already a nice string like "22-Jan-26"
    if re.match(r"\d{1,2}-[A-Za-z]{3}-\d{2,4}", s):
        return s
    # Excel datetime string "2026-01-22 00:00:00"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        from datetime import datetime
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return dt.strftime("%d-%b-%y")
        except ValueError:
            pass
    return s


# ---------------------------------------------------------------------------
# Header discovery  (driven by DO_TABLE_LABELS config)
# ---------------------------------------------------------------------------

def _find_header_row(
    grid: CellGrid,
    min_row_0: int,
    max_row_0: int,
    min_col_0: int,
    max_col_0: int,
) -> Tuple[Optional[int], Dict[str, int]]:
    """
    Scan rows looking for the header row of the D.O. table.
    Matches each cell against every synonym defined in DO_TABLE_LABELS.

    Returns (header_row_0, {field_name: col_index_0}) or (None, {}).
    """
    # Search the full sheet range - table can be anywhere (not just top 5 rows)
    for row in range(min_row_0, max_row_0 + 1):
        col_map: Dict[str, int] = {}

        for col in range(min_col_0, max_col_0 + 1):
            raw = grid.get(row, col)
            if not raw:
                continue
            normalised = normalize_text(raw)

            for field_name, synonyms in DO_TABLE_LABELS.items():
                if field_name in col_map:
                    continue
                for syn in synonyms:
                    syn_str = syn.value if hasattr(syn, "value") else str(syn)
                    if normalised == syn_str or normalised.startswith(syn_str):
                        col_map[field_name] = col
                        logging.debug(
                            f"  DO header: col {col} '{raw}' "
                            f"→ '{field_name}' via '{syn_str}'"
                        )
                        break

        # Valid header: must match at least 4 defined columns
        if len(col_map) >= 4:
            logging.info(
                f"DO table header at row {row}: {dict(col_map)}"
            )
            return row, col_map

    return None, {}


# ---------------------------------------------------------------------------
# Auto-detect which sheet and row range contains the D.O. table
# ---------------------------------------------------------------------------

def _find_do_table_in_sheets(
    all_sheets: List[CellGrid],
) -> Tuple[Optional[CellGrid], Optional[int], Dict[str, int]]:
    """
    Try every sheet until a D.O. header row is found.

    Returns (grid, header_row_0, col_map) or (None, None, {}).
    """
    for grid in all_sheets:
        header_row_0, col_map = _find_header_row(
            grid,
            min_row_0=0,
            max_row_0=grid.nrows - 1,
            min_col_0=0,
            max_col_0=grid.ncols - 1,
        )
        if header_row_0 is not None:
            return grid, header_row_0, col_map

    return None, None, {}


# ---------------------------------------------------------------------------
# Single data-row builder
# ---------------------------------------------------------------------------

def _build_do_row(
    grid: CellGrid,
    row: int,
    col_map: Dict[str, int],
    fill_down: Dict[str, str],
) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Build one D.O. row dict from grid row *row*.

    fill_down is mutated in place to carry merged-cell values forward.
    Returns (row_dict, special_note_str_or_None).
    """
    def _cell(field: str) -> str:
        col = col_map.get(field)
        return grid.get(row, col).strip() if col is not None else ""

    # ── Update fill-down for merged-cell columns ──────────────────────────────
    for field in DO_FILL_DOWN_FIELDS:
        field_str = field.value if hasattr(field, "value") else str(field)
        raw = _cell(field_str)
        if raw:
            fill_down[field_str] = raw

    # ── Detect special audit note in D.O QTY cell (merged-cell special rows) ─
    do_qty_raw   = _cell("do_qty")
    do_no_raw    = _cell("do_no")
    special_note = None

    if _is_special_note(do_qty_raw):
        special_note = do_qty_raw
        do_qty_raw   = ""
    elif _is_special_note(do_no_raw):
        special_note = do_no_raw
        do_no_raw    = ""

    row_dict: Dict[str, Any] = {
        # Carry-forward (merged) fields
        "date":    _format_date(fill_down.get("date", "")) if fill_down.get("date") else None,
        "po_qty":  _to_int_or_none(fill_down.get("po_qty", "")),

        # Per-row fields
        "do_no":                do_no_raw or None,
        "do_qty":               _to_int_or_none(do_qty_raw),
        "ship_qty":             _to_int_or_none(_cell("ship_qty")),
        "audit_qty":            _to_int_or_none(_cell("audit_qty")),
        "do_balance_and_extra": _to_int_or_none(_cell("do_balance")),
        "po_balance":           _to_int_or_none(_cell("po_balance")),
        "remarks":              _cell("remarks") or None,
        "special_note":         special_note,
    }

    return row_dict, special_note


# ---------------------------------------------------------------------------
# Public API  –  called from main.py / process_file()
# ---------------------------------------------------------------------------

def extract_do_table_to_record(record: Any, path: Any) -> None:
    """
    Find the D.O. plan table anywhere in the workbook, extract all rows,
    and store them on record.do_orders / record.do_totals / record.do_note.

    Parameters
    ----------
    record : AuditRecord  (mutated in place)
    path   : pathlib.Path to the Excel file
    """
    from core.cell_grid import CellGrid
    from core.sheet_reader import read_all_sheets

    all_dfs   = read_all_sheets(path)
    all_grids = [CellGrid(df) for df in all_dfs]

    grid, header_row_0, col_map = _find_do_table_in_sheets(all_grids)

    if grid is None or header_row_0 is None:
        logging.warning(f"[{record.file_name}] DO table not found in any sheet")
        return

    # ── Walk data rows ────────────────────────────────────────────────────────
    do_orders: List[Dict[str, Any]] = []
    totals:    Dict[str, Any]       = {}
    note:      str                  = ""
    fill_down: Dict[str, str]       = {}

    for row in range(header_row_0 + 1, grid.nrows):
        row_cells = [grid.get(row, c) for c in range(grid.ncols)]
        non_empty = [c for c in row_cells if c.strip()]

        if not non_empty:
            continue

        if _is_note_row(row_cells):
            note = " ".join(non_empty).strip()
            logging.info(f"  DO note: '{note[:80]}...'")
            continue

        if _is_total_row(row_cells):
            def _cell_t(field: str) -> str:
                col = col_map.get(field)
                return grid.get(row, col).strip() if col is not None else ""
            totals = {
                "ship_qty":  _to_int_or_none(_cell_t("ship_qty")),
                "audit_qty": _to_int_or_none(_cell_t("audit_qty")),
            }
            logging.info(f"  DO totals: {totals}")
            continue

        do_row, _ = _build_do_row(grid, row, col_map, fill_down)

        # Skip rows that have absolutely no data
        values = [v for k, v in do_row.items()
                  if k not in ("date", "po_qty") and v is not None]
        if not values:
            continue

        do_orders.append(do_row)
        logging.debug(f"  DO row: {do_row}")

    # ── Store on record ───────────────────────────────────────────────────────
    record.do_orders = do_orders
    record.do_totals = totals if totals else {}
    record.do_note   = note or ""

    logging.info(
        f"[{record.file_name}] DO table: "
        f"{len(do_orders)} row(s), totals={totals}"
    )

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\extraction\label_config.py

"""
label_config.py
---------------
Central configuration for the extraction system.

This is the PRIMARY place to make changes when:
  - A new Excel format uses different label text  →  add to a LabelSynonym list
  - A label value lives in a different direction →  change DirectionRule
  - A new country code appears                  →  add to STYLE_COUNTRY_MAP
  - A new audit type keyword appears             →  update AUDIT_PATTERNS

Structure of LABELS dict
------------------------
Simple form (default direction = right_then_down):
    FieldName.FOO: [LabelSynonym.A, LabelSynonym.B]

Extended form (custom direction):
    FieldName.FOO: {
        "synonyms":  [LabelSynonym.A, LabelSynonym.B],
        "direction": DirectionRule.RIGHT,          # or a list of rules
    }
"""

from enums.field_enums import (
    FieldName,
    LabelSynonym,
    DirectionRule,
    AuditPattern,
    StyleCountryPrefix,
)


# ---------------------------------------------------------------------------
# LABELS – field → (synonyms + optional direction rule)
# ---------------------------------------------------------------------------

LABELS: dict = {

    # ── Identity / header ──────────────────────────────────────────────────
    FieldName.FACTORY: [
        LabelSynonym.FACTORY_NAME,
        LabelSynonym.FACTORY,
    ],

    FieldName.DATE_OF_ISSUE: [
        LabelSynonym.DATE_OF_ISSUE,
        LabelSynonym.ISSUE_DATE,
        LabelSynonym.REPORT_DATE,
        LabelSynonym.INSPECTION_DATE,
    ],

    FieldName.INSPECTION_TYPE: [
        LabelSynonym.INSPECTION_TYPE,
        LabelSynonym.AUDIT_TYPE,
    ],

    FieldName.REPORT_NO: [
        LabelSynonym.REPORT_NO,
        LabelSynonym.REPORT_NUMBER,
        LabelSynonym.INSPECTION_REPORT_NO,
    ],

    FieldName.ITEM_NAME: [
        LabelSynonym.ITEM_NAME,
        LabelSynonym.DESCRIPTION,
    ],

    FieldName.STYLE_NO: [
        LabelSynonym.STYLE_NO,
        LabelSynonym.STYLE_NUMBER,
        LabelSynonym.STYLE,
        LabelSynonym.LOCAL_SAMPLE_CODE,
    ],

    FieldName.PO_NO: [
        LabelSynonym.PO_NO,
        LabelSynonym.PO_NO_DASH,
        LabelSynonym.PURCHASE_ORDER_NO,
        LabelSynonym.INSPECTION_REPORT_NO,
    ],

    FieldName.AUDIT_REPORT: [
        LabelSynonym.REPORT_NUMBER,
        LabelSynonym.REPORT_NO,
        LabelSynonym.INSPECTION_REPORT_NO,
    ],

    # ── Time fields ────────────────────────────────────────────────────────
    FieldName.FACTORY_IN_TIME: [
        LabelSynonym.FACTORY_IN_TIME,
        LabelSynonym.FACTORY_INTIME2,
        LabelSynonym.FACTORY_INTIME,
        LabelSynonym.IN_TIME,
    ],

    FieldName.FACTORY_OUT_TIME: [
        LabelSynonym.FACTORY_OUT_TIME,
        LabelSynonym.FACTORY_OUTTIME,
        LabelSynonym.FACTORY_OUTTIME2,
        LabelSynonym.OUT_TIME,
    ],

    FieldName.AUDIT_START_TIME: [
        LabelSynonym.AUDIT_START_TIME,
        LabelSynonym.START_TIME,
    ],

    FieldName.AUDIT_END_TIME: [
        LabelSynonym.AUDIT_END_TIME,
        LabelSynonym.END_TIME,
    ],

    # ── Audit outcome ──────────────────────────────────────────────────────
    FieldName.AUDIT_RESULT: [
        LabelSynonym.AUDIT_RESULT,
        LabelSynonym.RESULT,
        LabelSynonym.INSPECTION_RESULT,
    ],

    # ── Quantity fields ────────────────────────────────────────────────────

    # PO Qty: prefer integer value found below the label; fall back to right
    FieldName.PO_QTY: {
        "synonyms": [
            LabelSynonym.PO_QTY,
            LabelSynonym.PO_QUANTITY,
            LabelSynonym.PO_QTY_CAPS,
        ],
        "direction": [DirectionRule.DOWN_IF_INT, DirectionRule.RIGHT],
    },
    FieldName.DO_QTY: {
        "synonyms": [
            LabelSynonym.DO_QTY,
            LabelSynonym.DO_QUANTITY,
            LabelSynonym.DO_QTY_CAPS,
        ],
        "direction": [DirectionRule.DOWN_IF_INT, DirectionRule.RIGHT],
    },

    # --- Details OF Shipment ---
    # EXF: always to the right
    FieldName.EXF: {
        "synonyms": [
            LabelSynonym.EXF,
            LabelSynonym.EXF_,
            LabelSynonym.EXF__,
        ],
        "direction": DirectionRule.RIGHT,
    },

    # PO EDT: always to the right
    FieldName.PO_EDT: {
        "synonyms": [
            LabelSynonym.PO_EDT,
            LabelSynonym._PO_EDT,
            LabelSynonym.PO__EDT,
            LabelSynonym._PO__EDT,
        ],
        "direction": DirectionRule.RIGHT,
    },

    # PO W/H (warehouse / ship date): always to the right
    FieldName.PO_WH: {
        "synonyms": [
            LabelSynonym.PO_WH,
            LabelSynonym.WAREHOUSE,
            LabelSynonym.POWH,
            LabelSynonym.PO_WH_SLASH,
        ],
        "direction": DirectionRule.RIGHT,
    },

    # PLAN EDT: always to the right
    FieldName.PLAN_EDT: {
        "synonyms": [
            LabelSynonym.PLAN_ETD,
            LabelSynonym.PLAN__ETD,
        ],
        "direction": DirectionRule.RIGHT,
    },

    # PLAN WH: always to the right
    FieldName.PLAN_WH: {
        "synonyms": [
            LabelSynonym.PLAN_WH,
            LabelSynonym.PLAN__WH,
        ],
        "direction": DirectionRule.RIGHT,
    },

    FieldName.SHIP_QTY: [
        LabelSynonym.SHIP_QTY,
        LabelSynonym.SHIPMENT_QTY,
        LabelSynonym.SHIPPING_QUANTITY,
        LabelSynonym.SHIPPING_QTY,
        LabelSynonym.AUDIT_FOR_SHIPPING_QTY,
        LabelSynonym.EXF_QTY,
    ],

    FieldName.AUDIT_QTY: [
        LabelSynonym.AUDIT_QTY,
        LabelSynonym.AUDITED_QUANTITY,
        LabelSynonym.QTY_INSPECTED,
    ],

    # Defect qty from the "Major Defects" column header → value is to the right
    FieldName.DEFECT_QTY: {
        "synonyms": [
            LabelSynonym.MAJOR_DEFECTS,
        ],
        "direction": DirectionRule.RIGHT,
    },

    # ── Personnel ──────────────────────────────────────────────────────────
    FieldName.INSPECTOR: [
        LabelSynonym.INSPECTOR,
    ],


    FieldName.PERSON: [
        LabelSynonym.PERSON,
    ],

    FieldName.CARTON: [
        LabelSynonym.CARTON_INSPECTION,
        LabelSynonym.INSPECTION_CTN,
        LabelSynonym.INSPECTION_CARTON,
        LabelSynonym.OUR_INSPECTION_CARTON,
        LabelSynonym.OUR_INSPECTION_CARTON_NUMBER,
    ],

    FieldName.NEEDLE_DETECTOR: {
        "synonyms": [
            LabelSynonym.NEEDLE_DETECTOR,
            LabelSynonym.NEEDLE_DETECTOR_CHECK,
        ],
        "direction": DirectionRule.DOWN,
    },

    FieldName.REMARKS: {
        "synonyms": [
            LabelSynonym.REMARKS,
            LabelSynonym.REMARK,
        ],
        "direction": DirectionRule.DOWN,
    },
    FieldName.DO_SET_COL_SIZE: {
        "synonyms": [
            LabelSynonym.DO_SET_COL_SIZE,
        ],
        "direction": DirectionRule.DOWN,
    },

    FieldName.CLIENT: [
        LabelSynonym.CLIENT,
        LabelSynonym.CLIENT_NAME,
        LabelSynonym.BUYER,
        LabelSynonym.BUYER_NAME,
    ],
}

# ---------------------------------------------------------------------------
# Style number prefix → destination country
# Update here when new country codes are discovered.
# ---------------------------------------------------------------------------

STYLE_COUNTRY_MAP: dict = {
    StyleCountryPrefix.JAPAN:  "JAPAN",
    StyleCountryPrefix.CHINA:  "CHINA",
    StyleCountryPrefix.USA:    "USA",
    StyleCountryPrefix.KOREA:  "KOREA",
    StyleCountryPrefix.EUROPE: "EUROPE",
    StyleCountryPrefix.TAIWAN: "TAIWAN",
    StyleCountryPrefix.AU:     "AU",
    StyleCountryPrefix.CANADA: "CANADA",
    StyleCountryPrefix.INDIA:  "INDIA",
}


# ---------------------------------------------------------------------------
# Fields that must hold a pure integer after extraction
# (non-numeric text will be stripped by post_processor.clean_numeric_fields)
# ---------------------------------------------------------------------------

NUMERIC_FIELDS: set = {
    FieldName.PO_QTY,
    FieldName.DO_QTY,
    FieldName.SHIP_QTY,
    FieldName.AUDIT_QTY,
}


# ---------------------------------------------------------------------------
# Regex patterns used to infer the audit type from the file name
# ---------------------------------------------------------------------------

AUDIT_PATTERNS: dict = {
    AuditPattern.RE_FINAL: r"re[-\s]?final",
    AuditPattern.FINAL:    r"\bfinal\b",
    AuditPattern.INLINE:   r"inline",
    AuditPattern.SAMPLE:   r"sample",
    AuditPattern.CMF:      r"cmf",
}


# ---------------------------------------------------------------------------
# DO_TABLE_LABELS – column header → synonyms for the D.O. plan table
# ---------------------------------------------------------------------------
# This is the ONLY place you need to change when:
#   - A new Excel format spells a header differently
#     → add the new DOLabelSynonym value and list it here
#   - A new column is added to the D.O. table
#     → add DOFieldName + DOLabelSynonym entries, then add a row below
#
# The engine reads these exactly like LABELS above:
#   key   = DOFieldName  (internal name used in the output JSON)
#   value = list of DOLabelSynonym  (all known text variants for that header)
# ---------------------------------------------------------------------------

from enums.field_enums import DOFieldName, DOLabelSynonym

DO_TABLE_LABELS: dict = {

    DOFieldName.DATE: [
        DOLabelSynonym.DATE,
    ],

    DOFieldName.PO_QTY: [
        DOLabelSynonym.PO_QTY,
        DOLabelSynonym.P_O_QTY,
        DOLabelSynonym.PO_QUANTITY,
        DOLabelSynonym.P_O_QUANTITY,
    ],

    DOFieldName.DO_NO: [
        DOLabelSynonym.DO_NO,
        DOLabelSynonym.D_O_NO,
        DOLabelSynonym.DO_NUMBER,
        DOLabelSynonym.D_O_NUMBER,
        DOLabelSynonym.DELIVERY_ORDER_NO,
    ],

    DOFieldName.DO_QTY: [
        DOLabelSynonym.DO_QTY,
        DOLabelSynonym.D_O_QTY,
        DOLabelSynonym.DO_QUANTITY,
        DOLabelSynonym.D_O_QUANTITY,
    ],

    DOFieldName.SHIP_QTY: [
        DOLabelSynonym.SHIP_QTY,
        DOLabelSynonym.SHIP_QUANTITY,
        DOLabelSynonym.SHIPMENT_QTY,
        DOLabelSynonym.SHIPMENT_QUANTITY,
    ],

    DOFieldName.AUDIT_QTY: [
        DOLabelSynonym.AUDIT_QTY,
        DOLabelSynonym.AUDIT_QUANTITY,
        DOLabelSynonym.AUDITED_QTY,
    ],

    DOFieldName.DO_BALANCE: [
        DOLabelSynonym.DO_BALANCE,
        DOLabelSynonym.D_O_BALANCE,
        DOLabelSynonym.DO_BALANCE_EXTRA,
        DOLabelSynonym.DO_BALANCE_AND_EXTRA,
        DOLabelSynonym.BALANCE_EXTRA,
    ],

    DOFieldName.PO_EXTRA: [
        DOLabelSynonym.PO_EXTRA,
        DOLabelSynonym.P_O_EXTRA,
    ],

    DOFieldName.REMARKS: [
        DOLabelSynonym.REMARKS,
        DOLabelSynonym.BALANCE_QTY_PLAN,
        DOLabelSynonym.BALANCE_QTY_PLAN_DATE,
        DOLabelSynonym.BALANCE_QTY_PLAN_DATE_REMARKS,
        DOLabelSynonym.PLAN_DATE_REMARKS,
    ],

    DOFieldName.PO_BALANCE: [
        DOLabelSynonym.PO_BALANCE,
        DOLabelSynonym.PO_BAL,
    ],
}

# Columns whose values should be carried forward across merged/empty rows.
# e.g. DATE and PO_QTY span multiple D.O. rows in the same Excel table.
DO_FILL_DOWN_FIELDS: set = {
    DOFieldName.DATE,
    DOFieldName.PO_QTY,
    DOFieldName.PO_EXTRA,
}

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\extraction\post_processor.py

"""
post_processor.py
-----------------
Derives, cleans, and enriches an AuditRecord *after* raw extraction.

Processing stages (run in order by post_process_record)
--------------------------------------------------------
1.  refine_record       – normalise time strings, strip non-numeric chars
2.  calculate totals    – factory hours / audit hours from start→end times
3.  find_missing_fields – re-scan other sheets for any still-empty fields
4.  refine_record       – clean newly found values
5.  recalculate totals  – if new times were found in stage 3
6.  defect qty fallback – scan summary section for Major Defects total
7.  PO qty routing      – parse "1200 PCS" / "300 SET" into typed fields
8.  defect percentage   – defect_qty / audit_qty * 100
9.  country from style  – first 2 chars of style_no → country code
10. audit type from name– infer inspection_type from the file name
"""

import logging
import re
from dataclasses import fields
from datetime import datetime, timedelta
from pathlib import Path

from models.audit_record import AuditRecord
from core.sheet_reader import read_all_sheets
from core.cell_grid import CellGrid
from extraction.label_config import LABELS, STYLE_COUNTRY_MAP, NUMERIC_FIELDS
from extraction.rule_extractor import extract_fields
from extraction.text_number_extractor import extract_first_number_only
from extraction.defect_qty_extractor import extract_defect_qty_with_fallback
from extraction.audit_type_resolver import resolve_audit_type


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

_TIME_FIELDS = (
    "factory_in_time",
    "factory_out_time",
    "audit_start_time",
    "audit_end_time",
)


def _parse_hhmm(time_string: str) -> str:
    """
    Convert a loose time string to strict "HH:MM" (24-hour).
    Accepts: "9:30", "09:30", "9.30", "930", "9:30 AM", "09:30 PM", etc.
    Returns the original string unchanged if parsing fails.
    """
    if not isinstance(time_string, str):
        return ""

    time_string = time_string.strip()
    match = re.search(r"(\d{1,2})[:.]?(\d{2})?\s*([APap][Mm])?", time_string)
    if not match:
        return time_string

    hour_str, minute_str, am_pm = match.groups()
    hour   = int(hour_str)
    minute = int(minute_str) if minute_str else 0

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return time_string

    if am_pm:
        am_pm_lower = am_pm.lower()
        if am_pm_lower.startswith("p") and hour != 12:
            hour += 12
        elif am_pm_lower.startswith("a") and hour == 12:
            hour = 0

    try:
        return datetime.strptime(f"{hour}:{minute}", "%H:%M").strftime("%H:%M")
    except ValueError:
        return time_string


def refine_record(record: AuditRecord) -> AuditRecord:
    """
    1. Format all time fields to HH:MM.
    2. Strip non-numeric characters from numeric-only fields.
    """
    for field_name in _TIME_FIELDS:
        raw = getattr(record, field_name, "")
        if raw:
            refined = _parse_hhmm(raw)
            if refined != raw:
                logging.debug(f"  time refined [{field_name}]: '{raw}' → '{refined}'")
            setattr(record, field_name, refined)

    for field_name in NUMERIC_FIELDS:
        raw = getattr(record, field_name, None)
        if raw and isinstance(raw, str):
            cleaned = extract_first_number_only(raw)
            if cleaned and cleaned != raw:
                logging.debug(f"  numeric cleaned [{field_name}]: '{raw}' → '{cleaned}'")
                setattr(record, field_name, cleaned)

    return record


# ---------------------------------------------------------------------------
# Duration calculation
# ---------------------------------------------------------------------------

def _duration_hours(start: str, end: str) -> str | None:
    """
    Return decimal hours between two "HH:MM" strings, or None on error.
    Handles overnight spans (end < start) by adding 24 h.
    """
    try:
        t0 = datetime.strptime(start, "%H:%M")
        t1 = datetime.strptime(end, "%H:%M")
        delta = t1 - t0
        if delta.total_seconds() < 0:
            delta += timedelta(days=1)
        total_minutes = int(delta.total_seconds() // 60)
        hours   = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours:02d}:{minutes:02d}"
    except ValueError as exc:
        logging.warning(f"Duration calc failed ('{start}' → '{end}'): {exc}")
        return None


# ---------------------------------------------------------------------------
# Missing-field search  (scans all other sheets)
# ---------------------------------------------------------------------------

def find_missing_fields(record: AuditRecord, path: Path) -> None:
    """
    For every still-empty field in *record*, scan all sheets of *path* and
    fill in any values found.  Modifies *record* in place.
    """
    missing = {
        f.name for f in fields(record)
        if not getattr(record, f.name)
        and f.name in LABELS
    }

    if not missing:
        return

    logging.info(f"Searching other sheets for: {missing}")
    targeted = {f: LABELS[f] for f in missing}

    for i, sheet_df in enumerate(read_all_sheets(path)):
        if not targeted:
            break

        grid = CellGrid(sheet_df)
        found = extract_fields(grid, targeted)

        for field_name, value in found.items():
            if value:
                setattr(record, field_name, value)
                del targeted[field_name]
                logging.info(f"  [{field_name}] found in sheet {i + 1}: '{value}'")


# ---------------------------------------------------------------------------
# Defect qty fallback
# ---------------------------------------------------------------------------

def apply_defect_qty_fallback(record: AuditRecord, path: Path) -> None:
    """
    If defect_qty is still empty, run the custom "second Major label" search
    on the first sheet.  Mutates *record* in place.
    """
    if record.defect_qty:
        return

    logging.info("defect_qty empty – running fallback extraction")
    df   = read_all_sheets(path)[0]
    grid = CellGrid(df)

    value = extract_defect_qty_with_fallback(grid, primary_value="")
    if value:
        record.defect_qty = value
        logging.info(f"  defect_qty (fallback): '{value}'")


# ---------------------------------------------------------------------------
# PO quantity routing
# ---------------------------------------------------------------------------

_PO_UNIT_MAP = {
    "pcs":  "po_qty_pcs",
    "pack": "po_qty_pack",
    "set":  "po_qty_set",
}


def apply_po_qty_extraction(record: AuditRecord) -> AuditRecord:
    """
    Parse record.po_qty ("1200 PCS", "300 SET", "500 PACK", bare "1200")
    and write the integer to the correct typed field (po_qty_pcs etc.).
    """
    raw = getattr(record, "po_qty", None)
    if not raw:
        return record

    raw_lower = raw.strip().lower()
    numeric_match = re.search(r"(\d+(?:\.\d+)?)", raw_lower)
    if not numeric_match:
        logging.warning(f"po_qty: no number found in '{raw}'")
        return record

    numeric_value = int(float(numeric_match.group(1)))
    target_field  = "po_qty_pcs"  # default

    for keyword, field_name in _PO_UNIT_MAP.items():
        if keyword in raw_lower:
            target_field = field_name
            break

    setattr(record, target_field, numeric_value)
    logging.debug(f"  po_qty '{raw}' → {target_field}={numeric_value}")
    return record


# ---------------------------------------------------------------------------
# Derived calculations
# ---------------------------------------------------------------------------

def _calc_defect_percentage(record: AuditRecord) -> None:
    """Set record.defect_percentage from defect_qty / audit_qty."""
    try:
        if not record.defect_qty or not record.audit_qty:
            record.defect_percentage = ""
            return

        defect_int = int(str(record.defect_qty).strip())
        audit_int  = int(str(record.audit_qty).strip())

        if audit_int == 0:
            record.defect_percentage = ""
            logging.warning(f"audit_qty=0 → cannot calc defect % for {record.file_name}")
            return

        pct = round(defect_int / audit_int * 100, 2)
        record.defect_percentage = f"{pct}%"

    except (ValueError, TypeError) as exc:
        record.defect_percentage = ""
        logging.warning(f"defect % calc failed for {record.file_name}: {exc}")


def _set_country_from_style(record: AuditRecord) -> None:
    """Derive record.country from the first 2 characters of style_no."""
    style = str(record.style_no).strip()
    if not style or len(style) < 2:
        record.country = "UNKNOWN"
        return
    record.country = STYLE_COUNTRY_MAP.get(style[:2], "UNKNOWN")


# ---------------------------------------------------------------------------
# Master post-processor
# ---------------------------------------------------------------------------

def post_process_record(record: AuditRecord, path: Path) -> AuditRecord:
    """
    Run all enrichment stages on *record* and return the updated record.
    This is the single entry point called from main.py.
    """
    # Stage 1 – normalise times & clean numeric fields
    record = refine_record(record)

    # Stage 2 – derive totals from times found in stage 1
    record.audit_total_hours   = _duration_hours(record.audit_start_time, record.audit_end_time)
    record.factory_total_hours = _duration_hours(record.factory_in_time, record.factory_out_time)

    # Stage 3 – search other sheets for still-missing fields
    find_missing_fields(record, path)

    # Stage 4 – re-clean newly found values
    record = refine_record(record)

    # Stage 5 – recalculate totals if new times were discovered
    if not record.audit_total_hours:
        record.audit_total_hours = _duration_hours(record.audit_start_time, record.audit_end_time)
    if not record.factory_total_hours:
        record.factory_total_hours = _duration_hours(record.factory_in_time, record.factory_out_time)

    # Stage 6 – defect qty fallback
    apply_defect_qty_fallback(record, path)

    # Stage 7 – route PO qty to typed sub-field
    record = apply_po_qty_extraction(record)

    # Stage 8 – calculated metrics
    _calc_defect_percentage(record)

    # Stage 9 – country from style prefix
    _set_country_from_style(record)

    # Stage 10 – inspection type from file name (if not already set)
    if not record.inspection_type:
        record.inspection_type = resolve_audit_type(record)
        logging.info(f"[{record.file_name}] inspection_type → '{record.inspection_type}'")

    return record

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\extraction\proximity.py

"""
proximity.py
------------
Functions that locate a field's VALUE relative to its LABEL cell.

Core function : resolve_value()
  Given a label position and a direction rule, scans adjacent cells until
  a non-empty string is found.

Special handlers
  resolve_po_wh_value()       – PO W/H date may span 3 cells (MM | DD | YYYY).
  resolve_po_or_report_number() – validates PO vs Report number patterns.
"""

import logging
import re
from typing import Any, List, Tuple

from core.cell_grid import CellGrid


# ---------------------------------------------------------------------------
# Type-check helpers
# ---------------------------------------------------------------------------

def is_int(s: str) -> bool:
    """True if *s* can be parsed as an integer."""
    try:
        int(s)
        return True
    except (ValueError, TypeError):
        return False


def is_date_format(s: str) -> bool:
    """True if *s* looks like a complete date (e.g. 12/31/2024)."""
    if not s:
        return False
    return bool(re.match(r"^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$", s.strip()))


def is_valid_month_or_day(value: str) -> bool:
    """True if *value* is an integer in [1, 31] (valid MM or DD)."""
    try:
        return 1 <= int(value.strip()) <= 31
    except (ValueError, TypeError):
        return False


def is_valid_year(value: str) -> bool:
    """True if *value* is a plausible 4-digit year (1900–2100)."""
    try:
        return 1900 <= int(value.strip()) <= 2100
    except (ValueError, TypeError):
        return False


def is_valid_po_no(value: str) -> bool:
    """
    True if *value* matches the PO number pattern.
    Valid: P0726-482920-005  or  P0726-482920-005-1-2
    """
    if not value:
        return False
    return bool(re.match(r"^P\d{4}-\d{6}-\d{3}(?:-\d+)*$", value.strip()))


def is_valid_report_no(value: str) -> bool:
    """
    True if *value* matches the Report number pattern.
    Valid: EU26-02CIPL-001 or EU26-02CIPL-001.
    Strips trailing punctuation before matching.
    """
    if not value:
        return False
    # Strip trailing punctuation (period, comma, etc.)
    cleaned = value.strip().rstrip('.,;:')
    return bool(re.match(r"^[A-Z]{2}\d{2}-\d{2}[A-Z0-9]+-\d+$", cleaned))


# ---------------------------------------------------------------------------
# Inline-value extraction  (e.g. "LABEL: value" in a single cell)
# ---------------------------------------------------------------------------

def find_inline_value(label_text: str, cell_text: str) -> str:
    """
    If *cell_text* contains the label followed by a separator and a value,
    return the value part.  Returns "" otherwise.

    Example
    -------
    label_text = "factory"
    cell_text  = "Factory: ABC Garments Ltd"
    → returns "ABC Garments Ltd"
    """
    if not cell_text or not label_text:
        return ""

    lower_cell  = cell_text.lower().strip()
    lower_label = label_text.lower().strip()

    # Cell is exactly the label — no trailing value
    if lower_cell == lower_label or lower_cell == lower_label.rstrip(":- "):
        return ""

    label_core = lower_label.rstrip(":- ").strip()
    if label_core not in lower_cell:
        return ""

    # Split on the first recognised separator
    for sep in [":", "-", "\u2013", "\u2014"]:  # colon, hyphen, en-dash, em-dash
        if sep in cell_text:
            parts = cell_text.split(sep, 1)
            if len(parts) == 2:
                value = parts[1].strip()
                if value and len(value) > 2:
                    return value

    # Newline-separated inline value
    if "\n" in cell_text or "\r" in cell_text:
        lines = [ln.strip() for ln in re.split(r"[\r\n]+", cell_text) if ln.strip()]
        if len(lines) >= 2 and label_core in lines[0].lower():
            candidate = lines[1].strip()
            if candidate and len(candidate) > 2:
                return candidate

    # Simple "LABEL value" with whitespace separator
    m = re.match(rf"^{re.escape(label_core)}\s+(.+)$", lower_cell, flags=re.IGNORECASE)
    if m:
        candidate = m.group(1).strip()
        if candidate and len(candidate) > 2:
            return candidate

    return ""


# ---------------------------------------------------------------------------
# Main proximity resolver
# ---------------------------------------------------------------------------

def resolve_value(
    grid: CellGrid,
    label_pos: Tuple[int, int],
    direction_rule: Any = "right_then_down",
) -> str:
    """
    Scan cells adjacent to *label_pos* and return the first non-empty string.

    Parameters
    ----------
    grid          : CellGrid wrapping the sheet
    label_pos     : (row, col) of the label cell (0-based)
    direction_rule: DirectionRule value or list thereof.
                    Supported rules:
                      "right"           – scan right across the same row
                      "down"            – scan down the same column
                      "down_if_int"     – scan down but only accept integers
                      "right_then_down" (default)
                      "down_then_right"

    Returns
    -------
    First non-empty value found, or "" if nothing is found.
    """
    row, col = label_pos

    # Normalise to a list of rule strings
    if isinstance(direction_rule, list):
        rules: List[str] = [
            r.value if hasattr(r, "value") else str(r) for r in direction_rule
        ]
    elif direction_rule in ("right_then_down", "right then down"):
        rules = ["right", "down"]
    elif direction_rule in ("down_then_right", "down then right"):
        rules = ["down", "right"]
    else:
        rule_str = direction_rule.value if hasattr(direction_rule, "value") else str(direction_rule)
        rules = [rule_str]

    for rule in rules:

        if rule == "right":
            for c in range(col + 1, grid.ncols):
                value = grid.get(row, c)
                if value:
                    return value

        elif rule == "down":
            for r in range(row + 1, grid.nrows):
                value = grid.get(r, col)
                if value:
                    return value

        elif rule == "down_if_int":
            for r in range(row + 1, grid.nrows):
                value = grid.get(r, col)
                if value:
                    if is_int(value):
                        return value
                    break  # non-integer → stop looking

    return ""


# ---------------------------------------------------------------------------
# PO / Report number handler
# ---------------------------------------------------------------------------

def resolve_po_or_report_number(
    grid: CellGrid,
    label_pos: Tuple[int, int],
    field_name: str = "audit_report",
) -> str:
    """
    Extract and validate a PO or Report number from cells to the right of the label.

    field_name controls which pattern is accepted:
      "po_no"       → only PO pattern   (P0726-482920-005)
      "report_no"   → only Report pattern (EU26-02CIPL-001)
      "audit_report"→ accept either; fall back to raw value if no pattern matches
    """
    row, col = label_pos
    logging.debug(f"PO_OR_REPORT: resolving '{field_name}' from ({row}, {col})")

    for c in range(col + 1, min(col + 10, grid.ncols)):
        value = grid.get(row, c)
        if not value:
            continue

        value = value.strip()

        if field_name == "po_no":
            if is_valid_po_no(value):
                logging.debug(f"PO_OR_REPORT: PO match → {value}")
                return value

        elif field_name == "report_no":
            # Strip trailing punctuation for validation and return
            cleaned = value.rstrip('.,;:')
            if is_valid_report_no(value):
                logging.debug(f"PO_OR_REPORT: Report match → {cleaned}")
                return cleaned

        elif field_name == "audit_report":
            if is_valid_po_no(value) or is_valid_report_no(value):
                # For report_no matches, strip trailing punctuation
                if is_valid_report_no(value):
                    cleaned = value.rstrip('.,;:')
                    logging.debug(f"PO_OR_REPORT: pattern match → {cleaned}")
                    return cleaned
                logging.debug(f"PO_OR_REPORT: pattern match → {value}")
                return value
            # Fallback: return raw value for audit_report even without a pattern match
            logging.debug(f"PO_OR_REPORT: no pattern, returning raw → {value}")
            return value

    logging.debug(f"PO_OR_REPORT: nothing found to the right for '{field_name}'")
    return ""


# ---------------------------------------------------------------------------
# PO W/H special handler  (date may be split across 3 cells: MM | DD | YYYY)
# ---------------------------------------------------------------------------

def resolve_po_wh_value(grid: CellGrid, label_pos: Tuple[int, int]) -> str:
    """
    Extract the PO W/H (warehouse / ship date) value.

    Handles two formats:
      - Single cell:   "12/31/2024"
      - Split cells:   "12"  |  "31"  |  "2024"  → "12/31/2024"
    """
    row, col = label_pos
    logging.debug(f"PO_WH: resolving from label at ({row}, {col})")

    # Find the first non-empty cell to the right
    first_col = None
    first_val = ""

    for c in range(col + 1, min(col + 10, grid.ncols)):
        val = grid.get(row, c)
        if val:
            first_col = c
            first_val = val.strip()
            break

    if not first_val:
        logging.debug("PO_WH: no value found to the right")
        return ""

    # Format 1: full date already in one cell
    if is_date_format(first_val):
        return first_val

    # Format 2: date split across three cells (MM | DD | YYYY)
    if is_valid_month_or_day(first_val):
        mm = first_val

        second_col = None
        second_val = ""
        for c in range(first_col + 1, min(first_col + 5, grid.ncols)):
            val = grid.get(row, c)
            if val:
                second_col = c
                second_val = val.strip()
                break

        if not second_val or not is_valid_month_or_day(second_val):
            return mm

        dd = second_val

        third_val = ""
        for c in range(second_col + 1, min(second_col + 5, grid.ncols)):
            val = grid.get(row, c)
            if val:
                third_val = val.strip()
                break

        if not third_val or not is_valid_year(third_val):
            return f"{mm}/{dd}"

        result = f"{mm}/{dd}/{third_val}"
        logging.debug(f"PO_WH: reconstructed split date → {result}")
        return result

    # Format 3: non-date value — return as-is
    return first_val

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\extraction\rule_extractor.py

"""
rule_extractor.py
-----------------
Drives the label-based extraction loop over a CellGrid.

For every field defined in the LABELS config it:
  1. Searches the grid for matching label cell(s).
  2. Tries to read the value inline (same cell, e.g. "Label: Value").
  3. Falls back to proximity search (adjacent cells).
  4. Uses dedicated handlers for special fields (po_wh, po_no, report_no, etc.).

BUG FIXED: Label position reuse across fields
----------------------------------------------
Previously, if two fields shared a synonym (e.g. "report no" matching both
po_no and report_no), the same cell position could be returned for both,
causing the first extracted value to be assigned to both fields.

Fix: a global `used_positions` set tracks every (row, col) already consumed.
Each field only uses positions not yet taken.
"""

import logging
from typing import Any, Dict, Set, Tuple

from core.cell_grid import CellGrid
from extraction.proximity import (
    find_inline_value,
    resolve_value,
    resolve_po_wh_value,
    resolve_po_or_report_number,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve(
    grid: CellGrid,
    label_pos: Tuple[int, int],
    direction_rule: Any,
    field_name: str,
) -> str:
    """
    Route value resolution to the correct handler for the given field.
    Wraps exceptions so one bad cell never aborts the whole file.
    """
    try:
        if field_name in ("po_wh", "exf", "po_edt", "plan_edt", "plan_wh"):
            return resolve_po_wh_value(grid, label_pos)

        if field_name in ("po_no", "report_no", "audit_report"):
            return resolve_po_or_report_number(grid, label_pos, field_name)

        return resolve_value(grid, label_pos, direction_rule)

    except Exception as exc:
        logging.warning(
            f"resolve error – field='{field_name}' pos={label_pos}: {exc}"
        )
        return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_fields(
    grid: CellGrid,
    label_config: Dict[str, Any],
) -> Dict[str, str]:
    """
    Extract all fields specified in *label_config* from *grid*.

    Parameters
    ----------
    grid         : CellGrid for the sheet being processed
    label_config : mapping of  field_name → synonyms  OR
                              field_name → {"synonyms": [...], "direction": ...}

    Returns
    -------
    Dict mapping each field name to the extracted string value (or "").
    """
    extracted: Dict[str, str] = {}

    # Track which label positions have already been consumed by a field.
    # This prevents two fields from reading the same cell as their label.
    used_positions: Set[Tuple[int, int]] = set()

    for field_name, label_info in label_config.items():

        # ── Parse the config entry ────────────────────────────────────────────
        if isinstance(label_info, dict):
            synonyms       = label_info.get("synonyms", [])
            direction_rule = label_info.get("direction", "right_then_down")
        else:
            synonyms       = label_info
            direction_rule = "right_then_down"

        # ── Find where this label appears in the grid ─────────────────────────
        all_positions = grid.find_label_positions(synonyms)

        # Filter out positions already consumed by a previous field
        available_positions = [
            pos for pos in all_positions
            if (pos[0], pos[1]) not in used_positions
        ]

        if not available_positions:
            logging.debug(
                f"No available label for field '{field_name}' "
                f"(synonyms: {synonyms}, already-used: {len(all_positions) - len(available_positions)})"
            )
            extracted[field_name] = ""
            continue

        # ── Try each available position until a non-empty value is found ──────
        value = ""

        for label_row, label_col, label_text in available_positions:

            # Special-case fields that bypass inline extraction entirely
            if field_name == "needle_detector":
                # Use only the configured direction; do NOT check inline
                # to avoid matching patterns like "(Level-08)" in the label.
                value = _resolve(grid, (label_row, label_col), direction_rule, field_name)

            elif field_name in ("report_no", "po_no", "audit_report"):
                value = resolve_po_or_report_number(grid, (label_row, label_col), field_name)

            elif field_name == "po_wh":
                value = resolve_po_wh_value(grid, (label_row, label_col))

            elif field_name == "exf":
                value = resolve_po_wh_value(grid, (label_row, label_col))

            else:
                # 1) Inline: "LABEL: value" packed into the same cell?
                cell_text = grid.get(label_row, label_col)
                for syn in synonyms:
                    syn_text = syn.value if hasattr(syn, "value") else str(syn)
                    value = find_inline_value(syn_text, cell_text)
                    if value:
                        break

                # 2) Proximity: look in adjacent cells
                if not value:
                    value = _resolve(
                        grid, (label_row, label_col), direction_rule, field_name
                    )

            if value:
                # Mark this position as consumed so other fields won't reuse it
                used_positions.add((label_row, label_col))
                break

        extracted[field_name] = value

    return extracted

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\extraction\tabular_extractor.py

"""
tabular_extractor.py
--------------------
Extracts structured defect data from a rectangular Excel table range.

The caller supplies an Excel range string such as "B4:H38".  This module
converts that to row/column indices, identifies which column holds the
defect category names and which holds the "Major" counts, then reads every
row into a dict.

Column identification strategy (in order of priority)
------------------------------------------------------
1. Look for header cells containing the word "major" in the rows
   immediately above or at the top of the specified range.
2. If no header is found, pick the column with the most numeric values
   (heuristic – usually the major count column).
3. Fall back to the second column in the range.
"""

import logging
from typing import Dict, List, Tuple

from openpyxl.utils import range_boundaries

from core.cell_grid import CellGrid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_int(value: str) -> int:
    """Convert a string to int, returning 0 on failure."""
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0


def _is_numeric(value: str) -> bool:
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Column identification
# ---------------------------------------------------------------------------

def _find_major_column(
    grid: CellGrid,
    min_row: int,
    max_row: int,
    min_col: int,
    max_col: int,
) -> Tuple[int, int]:
    """
    Return (category_col, major_col) as 0-based column indices.

    Parameters use 1-based Excel coordinates (as returned by range_boundaries).
    """
    # Convert to 0-based for grid access
    min_col_0 = min_col - 1
    max_col_0 = max_col - 1
    min_row_0 = min_row - 1
    num_rows  = max_row - min_row + 1

    category_col = min_col_0   # first column → defect category names
    major_col: int | None = None

    # ── Strategy 1: scan header rows for a cell containing "major" ──────────
    # Check up to 3 rows above the table, plus the first row of the table.
    header_rows = list(range(max(1, min_row - 3), min_row + 1))
    header_rows_0 = [r - 1 for r in header_rows]   # convert to 0-based

    for hr in header_rows_0:
        for col in range(min_col_0, max_col_0 + 1):
            header_val = grid.get(hr, col)
            if header_val and "major" in header_val.strip().lower():
                major_col = col
                break
        if major_col is not None:
            break

    # ── Strategy 2: column with the most numeric values ──────────────────────
    if major_col is None:
        numeric_counts: Dict[int, int] = {}
        for col in range(min_col_0 + 1, max_col_0 + 1):
            count = sum(
                1 for row in range(min_row_0, min_row_0 + num_rows)
                if _is_numeric(grid.get(row, col))
            )
            numeric_counts[col] = count

        if numeric_counts:
            major_col = max(numeric_counts, key=numeric_counts.get)

    # ── Strategy 3: hard fallback ────────────────────────────────────────────
    if major_col is None:
        major_col = min_col_0 + 1

    return category_col, major_col


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_defect_table(
    grid: CellGrid,
    table_range: str,
) -> Dict[str, Dict[str, int]]:
    """
    Parse a rectangular defect table and return a nested dict.

    Return structure
    ----------------
    {
        "Incorrect Sewing": {"major": 3},
        "Wrong Label":      {"major": 1},
        ...
    }

    Parameters
    ----------
    grid        : CellGrid for the sheet containing the table
    table_range : Excel range string, e.g. "B4:H38"

    Returns an empty dict on any parse error.
    """
    if not table_range:
        logging.warning("extract_defect_table: no table_range provided")
        return {}

    # ── Parse range ──────────────────────────────────────────────────────────
    try:
        min_col, min_row, max_col, max_row = range_boundaries(table_range)
    except Exception as exc:
        logging.error(f"Invalid Excel range '{table_range}': {exc}")
        return {}

    if (max_col - min_col + 1) < 3:
        logging.error(
            f"Defect range '{table_range}' must be at least 3 columns wide "
            f"(category + major + minor)."
        )
        return {}

    # ── Identify columns ─────────────────────────────────────────────────────
    category_col, major_col = _find_major_column(
        grid, min_row, max_row, min_col, max_col
    )

    # ── Read data rows ───────────────────────────────────────────────────────
    defects: Dict[str, Dict[str, int]] = {}

    for row_1based in range(min_row, max_row + 1):
        row = row_1based - 1   # convert to 0-based

        category = grid.get(row, category_col)
        if not category or not category.strip():
            continue   # skip blank / header rows

        major_count = _to_int(grid.get(row, major_col))
        defects[category.strip()] = {"major": major_count}

    logging.info(
        f"extract_defect_table: extracted {len(defects)} defect categories "
        f"from range '{table_range}'"
    )
    return defects

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\extraction\text_number_extractor.py

"""
text_number_extractor.py
------------------------
Utility functions for pulling numeric values out of messy strings.

Common use-case: Excel cells that mix quantity and unit,
e.g. "1,200 PCS" → "1200" or  "3,500 SET" → "3500".
"""

import re
import logging


# ---------------------------------------------------------------------------
# Extraction functions
# ---------------------------------------------------------------------------

def extract_numbers_only(value: str) -> str:
    """
    Extract ALL numbers from *value* and return them space-joined.

    "1,200 PCS + 300 SET" → "1200 300"
    """
    if not value:
        return ""

    value = value.strip()
    matches = re.findall(r"[\d,]+\.?\d*", value)

    if not matches:
        logging.debug(f"No numbers found in: '{value}'")
        return ""

    cleaned = [m.replace(",", "") for m in matches]
    return " ".join(cleaned) if len(cleaned) > 1 else cleaned[0]


def extract_first_number_only(value: str) -> str:
    """
    Extract only the FIRST number from *value*.

    "1,200 PCS" → "1200"
    "PO: 3500"  → "3500"
    """
    if not value:
        return ""

    value = value.strip()
    match = re.search(r"[\d,]+\.?\d*", value)

    if not match:
        logging.debug(f"No number found in: '{value}'")
        return ""

    return match.group().replace(",", "")


def extract_integer_only(value: str) -> str:
    """
    Extract the first contiguous run of *digits* (no decimal point).

    "12.5 hours" → "12"
    "3,500 SET"  → "3"   (use extract_first_number_only if commas matter)
    """
    if not value:
        return ""

    match = re.search(r"\d+", value)
    return match.group() if match else ""


def is_mostly_numeric(value: str) -> bool:
    """Return True if *value* contains at least one digit."""
    return bool(re.search(r"\d", value))

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\extraction\__init__.py


# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\models\audit_record.py

"""
audit_record.py
---------------
Data model for a single audit report.

All fields default to sensible empty values so the object can be created
immediately after extraction without every value being present.

Notes
-----
- `po_qty` holds the *raw* extracted string (e.g. "1,200 PCS").
  Processed integers live in po_qty_pcs / po_qty_pack / po_qty_set.

- `client` is extracted from the Excel using the label "client".  It maps
  to the buyers/clients table in the DB and the factory+client combination
  determines the output Excel filename.

- `defect_rows` is the structured defect list (auto-discovered from sheet).
  Each element is:
      {"category": "B : Sewing", "item": "3.Pieces not symmetrical",
       "major": 1, "minor": 0, "comment": "CUFF POINT UP-DOWN"}

- `validation_errors` is serialised as a comma-joined string in to_dict().
"""

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List


@dataclass
class AuditRecord:
    """Represents one audit report extracted from an Excel file."""

    # Source
    file_name: str

    # Identity / header
    factory:         str = ""
    client :         str = ""
    date_of_issue:   str = ""   # normalised to MM/DD/YYYY by validator
    inspection_type: str = ""
    report_no:       str = ""
    audit_report:    str = ""
    item_name:       str = ""
    style_no:        str = ""
    po_no:           str = ""
    country:         str = ""

    # Time fields
    factory_in_time:     str = ""
    factory_out_time:    str = ""
    factory_total_hours: str = ""
    audit_start_time:    str = ""
    audit_end_time:      str = ""
    audit_total_hours:   str = ""

    # Audit outcome
    audit_result: str = "-"

    # Quantity fields
    po_qty:      str = ""  # raw extracted string e.g. "1200 PCS"
    po_qty_pcs:  int = 0   # populated by post_processor
    po_qty_pack: int = 0
    po_qty_set:  int = 0
    do_qty:      int = 0

    # Shipment date fields
    exf:      str = ""
    po_edt:   str = ""
    po_wh:    str = ""
    plan_edt: str = ""
    plan_wh:  str = ""

    shipment_dates: str = ""

    ship_qty:  str = ""
    audit_qty: str = ""

    # Defect summary
    defect_qty:            str = ""
    acceptable_defect_qty: str = "-"
    defect_percentage:     str = ""

    # Personnel
    person:    str = ""
    inspector: str = ""

    # Additional checks
    carton:          str = ""
    needle_detector: str = ""
    remarks:         str = ""
    do_set_col_size: str = ""

    # Structured defect data (auto-discovered from the defect table)
    defect_rows: List[Dict[str, Any]] = field(default_factory=list)

    # D.O. plan table
    do_orders: List[Dict[str, Any]] = field(default_factory=list)
    do_totals: Dict[str, Any]       = field(default_factory=dict)
    do_note:   str                  = ""

    # Validation
    validation_errors: List[str] = field(default_factory=list)

    # Blocking errors — records with these are NEVER inserted into the DB.
    # Populated by validate_blocking() in validator.py.
    # Examples: required field empty, defect sum ≠ header defect_qty.
    blocking_errors: List[str] = field(default_factory=list)

    # Which static defect template was matched (28 / 35 / 78 item list).
    # Set by db_manager when saving; None until then.
    defect_template_id: int = 0

    # -------------------------------------------------------------------------
    # Serialisation
    # -------------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """
        Flat dict suitable for DataFrame / Excel row creation.

        `defect_rows` is excluded from the flat dict (handled separately
        by summary_writer). `validation_errors` is joined into a single
        comma-separated string.
        """
        data = asdict(self)
        data.pop("defect_rows", None)
        data["validation_errors"] = ", ".join(self.validation_errors)
        return data

    def to_json_dict(self) -> Dict[str, Any]:
        """
        Full dict for JSON serialisation — includes defect_rows, do_orders,
        do_totals, and validation_errors as a list (not joined string).
        Used by json_writer for export and round-trip import.
        """
        return asdict(self)

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\models\__init__.py


# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\output\chart_generator.py

"""
chart_generator.py
------------------
Chart generation for audit summary Excel reports.
Creates pie charts, tables, and bar charts from defect data.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

from openpyxl.worksheet.worksheet import Worksheet
from openpyxl.chart import BarChart, PieChart, Reference, Series
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from openpyxl.chart.label import DataLabelList
from openpyxl.chart.shapes import GraphicalProperties
# ---------------------------------------------------------------------------
# Module-level style constants  (created once, reused everywhere)
# ---------------------------------------------------------------------------

_HEADER_FILL = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
_HEADER_FONT = Font(color="FFFFFF", bold=True)
_THIN_SIDE   = Side(style="thin")
_BORDER      = Border(
    left=_THIN_SIDE, right=_THIN_SIDE,
    top=_THIN_SIDE,  bottom=_THIN_SIDE,
)
_ALIGN_CENTER = Alignment(horizontal="center")
_ALIGN_LEFT   = Alignment(horizontal="left")
_ALIGN_LEFT_WRAP   = Alignment(horizontal="left",   wrap_text=True)
_ALIGN_CENTER_WRAP = Alignment(horizontal="center", wrap_text=True)
_ALIGN_LEFT_TOP    = Alignment(horizontal="left",   vertical="top")

_CHART_COLORS = ["E6B8B7", "CCC0DA", "FCD5B4", "B8CCE4", "B7DEE8"]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _styled_header(cell, value: str, wrap: bool = False) -> None:
    """Apply blue header style to a single cell."""
    cell.value     = value
    cell.font      = _HEADER_FONT
    cell.fill      = _HEADER_FILL
    cell.alignment = _ALIGN_CENTER_WRAP if wrap else _ALIGN_CENTER
    cell.border    = _BORDER


def _bordered(cell, value=None, align=None, fmt: str = "") -> None:
    """Write a value and apply border (+ optional alignment / number format)."""
    if value is not None:
        cell.value = value
    cell.border = _BORDER
    if align is not None:
        cell.alignment = align
    if fmt:
        cell.number_format = fmt


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class ChartGenerator:
    """
    Generator for audit summary charts.
    Creates pie charts, defect tables, and bar charts.
    """

    # Chart dimensions (cells)
    PIE_CHART_WIDTH  = 9  # columns
    PIE_CHART_HEIGHT = 6  # rows
    TABLE_WIDTH      = 5  # columns
    TABLE_HEIGHT     = 6  # rows

    def __init__(self, ws: Worksheet, start_row: int = 1, start_col: int = 1) -> None:
        self.ws        = ws
        self.start_row = start_row
        self.start_col = start_col

    # ------------------------------------------------------------------
    # Public chart builders
    # ------------------------------------------------------------------

    def create_pie_chart_with_table(
        self,
        defect_summary: List[Tuple[str, int, float]],
        title: str = "Top 5 Defects",
        offset_rows: int = 0,
    ) -> Tuple[int, int]:
        """
        Write a 3-column data table (Defect / Count / %) then a PieChart
        anchored to the right of it.

        Returns (last_row, last_col) so callers can stack elements.
        """
        top_n      = defect_summary[:5]
        row0       = self.start_row + offset_rows
        col0       = self.start_col

        # ── header row ────────────────────────────────────────────────
        for offset, header in enumerate(("Defect", "Count", "Percentage")):
            _styled_header(self.ws.cell(row=row0, column=col0 + offset), header)

        # ── data rows ─────────────────────────────────────────────────
        for i, (name, count, pct) in enumerate(top_n, 1):
            r = row0 + i
            _bordered(self.ws.cell(r, col0),     name,          _ALIGN_LEFT)
            _bordered(self.ws.cell(r, col0 + 1), count,         _ALIGN_CENTER, "#,##0")
            _bordered(self.ws.cell(r, col0 + 2), pct / 100,     _ALIGN_CENTER, "0.00%")

        # ── blank filler rows (keeps table height consistent) ─────────
        for i in range(len(top_n) + 1, self.TABLE_HEIGHT):
            for c in range(col0, col0 + self.TABLE_WIDTH):
                _bordered(self.ws.cell(row0 + i, c))

        # ── pie chart ─────────────────────────────────────────────────
        pie = self._build_pie_chart(title, row0, col0, len(top_n))
        chart_col = col0 + self.TABLE_WIDTH + 2
        self.ws.add_chart(pie, f"{get_column_letter(chart_col)}{row0}")

        self._adjust_column_widths(col0, self.TABLE_WIDTH)
        return (row0 + self.TABLE_HEIGHT, chart_col + self.PIE_CHART_WIDTH)
    
    # def create_category_defect_table(
    #     self,
    #     defect_summary: List[Tuple[str, str, str, int, float]],
    #     title: str = "Defect Summary by Category",
    #     start_row: Optional[int] = None,
    #     start_col: Optional[int] = None,
    # ) -> Tuple[int, int]:
    #     """
    #     Write a category-grouped summary table (Category / Items / Combined /
    #     Count / %).

    #     Returns (last_row, last_col).
    #     """
    #     row0 = start_row if start_row is not None else self.start_row
    #     col0 = start_col if start_col is not None else self.start_col

    #     # ── title ─────────────────────────────────────────────────────
    #     title_cell = self.ws.cell(row=row0, column=col0)
    #     title_cell.value = title
    #     title_cell.font  = Font(bold=True, size=12)

    #     # ── header row ────────────────────────────────────────────────
    #     header_row = row0 + 1
    #     for offset, hdr in enumerate(
    #         ("Category", "Defect Items", "Combined Name", "Count", "Percentage")
    #     ):
    #         _styled_header(
    #             self.ws.cell(row=header_row, column=col0 + offset), hdr, wrap=True
    #         )

    #     # ── group by category ─────────────────────────────────────────
    #     category_groups: Dict[str, list] = defaultdict(list)
    #     for cat, name, combined, count, pct in defect_summary:
    #         category_groups[cat].append((name, combined, count, pct))

    #     # ── data rows ─────────────────────────────────────────────────
    #     data_row = header_row + 1
    #     for category, items in category_groups.items():
    #         total_count = sum(item[2] for item in items)

    #         _bordered(self.ws.cell(data_row, col0),     category,                              _ALIGN_LEFT_TOP)
    #         _bordered(self.ws.cell(data_row, col0 + 1), ", ".join(i[0] for i in items),        _ALIGN_LEFT_WRAP)
    #         _bordered(self.ws.cell(data_row, col0 + 2), ", ".join(i[1] for i in items),        _ALIGN_LEFT_WRAP)
    #         _bordered(self.ws.cell(data_row, col0 + 3), total_count,                           _ALIGN_CENTER,  "#,##0")
    #         _bordered(self.ws.cell(data_row, col0 + 4), items[0][3] / 100 if items else 0,     _ALIGN_CENTER,  "0.00%")
    #         data_row += 1

    #     # ── blank filler rows ─────────────────────────────────────────
    #     table_height = max(len(category_groups) + 2, self.TABLE_HEIGHT + 2)
    #     for i in range(len(category_groups) + 2, table_height):
    #         for c in range(col0, col0 + self.TABLE_WIDTH + 2):
    #             _bordered(self.ws.cell(header_row + i, c))

    #     self._adjust_column_widths(col0, self.TABLE_WIDTH + 2)
    #     return (header_row + table_height, col0 + self.TABLE_WIDTH + 2)


    # def create_defect_bar_chart(
    #     self,
    #     defect_summary: List[Tuple[str, int]],
    #     title: str = "Defect Distribution",
    #     start_row: Optional[int] = None,
    #     start_col: Optional[int] = None,
    # ) -> Tuple[int, int]:
    #     """
    #     Write a (Defect / Count) data table then a BarChart below it.

    #     Returns (last_row, last_col).
    #     """
    #     row0 = start_row if start_row is not None else self.start_row
    #     col0 = start_col if start_col is not None else self.start_col

    #     # ── header row ────────────────────────────────────────────────
    #     for offset, hdr in enumerate(("Defect", "Count")):
    #         _styled_header(self.ws.cell(row=row0, column=col0 + offset), hdr)

    #     # ── data rows ─────────────────────────────────────────────────
    #     for i, (name, count) in enumerate(defect_summary, 1):
    #         r = row0 + i
    #         _bordered(self.ws.cell(r, col0),     name,  _ALIGN_LEFT)
    #         _bordered(self.ws.cell(r, col0 + 1), count, _ALIGN_CENTER, "#,##0")

    #     # ── bar chart ─────────────────────────────────────────────────
    #     n         = len(defect_summary)
    #     chart     = BarChart()
    #     chart.title      = title
    #     chart.style      = 1
    #     chart.x_axis.title = "Defect"
    #     chart.y_axis.title = "Count"
    #     chart.legend     = None
    #     chart.width      = 15
    #     chart.height     = 8
    #     chart.gapWidth   = 50

    #     data   = Reference(self.ws, min_col=col0 + 1, min_row=row0 + 1, max_row=row0 + n)
    #     labels = Reference(self.ws, min_col=col0,     min_row=row0 + 1, max_row=row0 + n)
    #     # series = Series(data, title="Defect Count")
    #     # chart.append(series)
    #     # chart.set_categories(labels)
    #     chart.add_data(data, titles_from_data=True)
    #     chart.set_categories(labels)

    #     # ── Show numbers on top of each bar ─────────────────────────────

    #     chart.add_data(data, titles_from_data=True)  # add series
    #     chart.set_categories(labels)

    #     chart.dataLabels = DataLabelList()
    #     chart.dataLabels.showVal = True
    #     chart.dataLabels.showCatName = False
    #     chart.dataLabels.showSerName = False
    #     chart.dataLabels.dLblPos = "t"  # top of bars

    #     chart_row = row0 + n + 3
    #     self.ws.add_chart(chart, f"{get_column_letter(col0)}{chart_row}")

    #     self._adjust_column_widths(col0, 2)
    #     return (chart_row + 20, col0 + 2)

    def create_defect_bar_chart(
    self,
    defect_summary: List[Tuple[str, int]],
    title: str = "Defect Distribution",
    start_row: Optional[int] = None,
    start_col: Optional[int] = None,
) -> Tuple[int, int]:
        row0 = start_row if start_row is not None else self.start_row
        col0 = start_col if start_col is not None else self.start_col

        # ── header row ────────────────────────────────────────────────
        for offset, hdr in enumerate(("Defect", "Count")):
            _styled_header(self.ws.cell(row=row0, column=col0 + offset), hdr)

        # ── data rows ─────────────────────────────────────────────────
        for i, (name, count) in enumerate(defect_summary, 1):
            r = row0 + i
            _bordered(self.ws.cell(r, col0),     name,  _ALIGN_LEFT)
            _bordered(self.ws.cell(r, col0 + 1), count, _ALIGN_CENTER, "#,##0")

        # ── bar chart ─────────────────────────────────────────────────
        n = len(defect_summary)
        chart = BarChart()
        chart.title = title
        chart.style = 1
        chart.x_axis.title = "Defect"
        chart.y_axis.title = "Count"
        chart.legend = None
        chart.width = 15
        chart.height = 8
        chart.gapWidth = 50

        data = Reference(self.ws, min_col=col0 + 1, min_row=row0 + 1, max_row=row0 + n)
        labels = Reference(self.ws, min_col=col0, min_row=row0 + 1, max_row=row0 + n)

        # Add data series and categories (only once)
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(labels)

        # Data labels configuration
        chart.dataLabels = DataLabelList()
        chart.dataLabels.showVal = True
        chart.dataLabels.showCatName = False
        chart.dataLabels.showSerName = False
        chart.dataLabels.dLblPos = "outEnd"  # try "t" or "outEnd"
        chart.dataLabels.numFmt = '#,##0'     # optional formatting

        chart_row = row0 + n + 3
        self.ws.add_chart(chart, f"{get_column_letter(col0)}{chart_row}")

        self._adjust_column_widths(col0, 2)
        return (chart_row + 20, col0 + 2)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_pie_chart(
        self, title: str, row0: int, col0: int, n_rows: int
    ) -> PieChart:
        """Construct and return a styled PieChart (does not add to sheet)."""
        pie        = PieChart()
        pie.dataLabels = DataLabelList()
        pie.dataLabels.showPercent = True
        pie.dataLabels.showCatName = False
        pie.dataLabels.showVal = False
        pie.dataLabels.showSerName = False
        pie.dataLabels.showLegendKey = False
        pie.dataLabels.dLblPos = "ctr"
        pie.title  = title
        pie.style  = 12
        pie.width  = self.PIE_CHART_WIDTH  * 1
        pie.height = self.PIE_CHART_HEIGHT * 1

        labels = Reference(self.ws, min_col=col0,     min_row=row0 + 1, max_row=row0 + n_rows)
        data   = Reference(self.ws, min_col=col0 + 1, min_row=row0 + 1, max_row=row0 + n_rows)
        series = Series(data, title="Defect Count")
        pie.append(series)
        pie.set_categories(labels)

        # Colour slices (best-effort — only works when data_points are present)
        for i, point in enumerate(series.data_points or []):
            if i < len(_CHART_COLORS):
                point.graphicalProperties = GraphicalProperties(
                    solidFill=_CHART_COLORS[i]
                )

        return pie

    def _adjust_column_widths(self, start_col: int, num_cols: int) -> None:
        """
        Set each column to the width of its longest cell value.
        Scans only down to ws.max_row; width is clamped to [10, 50].
        """
        for i in range(num_cols):
            col    = start_col + i
            letter = get_column_letter(col)
            max_w  = max(
                (
                    min(len(str(self.ws.cell(row=r, column=col).value)) * 1.2, 50)
                    for r in range(1, self.ws.max_row + 1)
                    if self.ws.cell(row=r, column=col).value is not None
                ),
                default=10,
            )
            self.ws.column_dimensions[letter].width = max(max_w, 10)

    # ------------------------------------------------------------------
    # Static data-preparation helper
    # ------------------------------------------------------------------

    @staticmethod
    def prepare_defect_summary(defect_entries: List[Dict[str, Any]]) -> Dict:
        """
        Aggregate raw defect entries into the three summaries consumed by
        the chart builders.

        Returns:
            {
                'top_5':           [(name, count, pct), ...],   # up to 5 items
                'category_summary':[(cat, name, combined, count, pct), ...],
                'full_list':       [(name, count), ...],
                'total_defects':   int,
            }
        """
        defect_counts: Dict[str, int] = defaultdict(int)
        category_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for entry in defect_entries:
            name     = entry.get("item_name") or entry.get("name") or "Unknown"
            category = entry.get("category") or "Other"
            count    = (entry.get("major") or 0) + (entry.get("minor") or 0)
            defect_counts[name]               += count
            category_counts[category][name]   += count

        total = sum(defect_counts.values())

        def _pct(n: int) -> float:
            return (n / total * 100) if total else 0.0

        top_5 = sorted(
            ((n, c, _pct(c)) for n, c in defect_counts.items()),
            key=lambda x: x[1], reverse=True,
        )[:5]

        category_summary = sorted(
            (
                (cat, name, f"{cat} : {name}", count, _pct(count))
                for cat, items in category_counts.items()
                for name, count in items.items()
            ),
            key=lambda x: x[3], reverse=True,
        )

        full_list = sorted(
            defect_counts.items(), key=lambda x: x[1], reverse=True
        )

        return {
            "top_5":            top_5,
            "category_summary": category_summary,
            "full_list":        full_list,
            "total_defects":    total,
        }

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\output\error_json_writer.py

"""
error_json_writer.py
--------------------
Writes audit records that failed BLOCKING validation to a JSON file so
the user can manually fix them and re-upload via the Extractor GUI.

File format
-----------
{
  "version": "1.0",
  "generated_at": "2026-01-05T10:30:00",
  "total_blocked": 3,
  "instructions": "Fix the fields listed in 'blocking_errors' for each record,
                   then upload this file via the Extractor's 'Upload Error JSON'
                   button.  Do NOT change the 'file_name' field.",
  "records": [
    {
      "file_name":       "DH26-01ABC-001.xlsx",
      "blocking_errors": ["REQUIRED_FIELD | factory | Factory name is missing"],
      "validation_errors": [...],
      -- all other AuditRecord fields --
      "defect_rows": [...],
      "do_orders":   [...]
    }
  ]
}

Re-import rules
---------------
- All fields in the JSON are editable EXCEPT 'file_name'.
- A record is only inserted if it passes blocking validation after the fix.
- Records that still fail after the upload remain in a new error JSON.
"""

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from models.audit_record import AuditRecord


_VERSION = "1.0"

_INSTRUCTIONS = (
    "Fix the fields listed in 'blocking_errors' for each record, "
    "then upload this file via the Extractor → 'Upload & Fix Error JSON' button. "
    "Do NOT change the 'file_name' field. "
    "Records that still fail after upload will produce a new error file."
)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def write_error_json(records: List[AuditRecord], path: Path) -> int:
    """
    Write *records* (all of which should have blocking_errors) to *path*.
    Returns the number of records written.
    """
    if not records:
        logging.info("write_error_json: no blocked records — file not written")
        return 0

    def _serialise(r: AuditRecord) -> Dict[str, Any]:
        d = asdict(r)
        # Put blocking/validation errors at the top for visibility
        return {
            "file_name":         d.pop("file_name", r.file_name),
            "blocking_errors":   d.pop("blocking_errors", []),
            "validation_errors": d.pop("validation_errors", []),
            **d,
        }

    payload = {
        "version":       _VERSION,
        "generated_at":  datetime.now().isoformat(timespec="seconds"),
        "total_blocked": len(records),
        "instructions":  _INSTRUCTIONS,
        "records":       [_serialise(r) for r in records],
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logging.info(f"Error JSON written: {path}  ({len(records)} blocked record(s))")
    return len(records)


# ---------------------------------------------------------------------------
# Read (re-import after user edits)
# ---------------------------------------------------------------------------

def read_error_json(path: Path) -> List[AuditRecord]:
    """
    Load a previously written error JSON file and return a list of
    AuditRecord objects with the user's fixes applied.

    Fields that don't map to AuditRecord attributes are silently ignored.
    """
    if not path.exists():
        raise FileNotFoundError(f"Error JSON not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))

    # Support both wrapped {records: [...]} and bare list
    if isinstance(raw, list):
        items = raw
    else:
        items = raw.get("records", [])

    records: List[AuditRecord] = []
    import dataclasses

    valid_fields = {f.name for f in dataclasses.fields(AuditRecord)}

    for item in items:
        if not isinstance(item, dict):
            continue
        # Only keep keys that are valid AuditRecord fields
        kwargs = {k: v for k, v in item.items() if k in valid_fields}
        try:
            record = AuditRecord(**kwargs)
            # Clear blocking/validation errors — they will be re-evaluated
            record.blocking_errors    = []
            record.validation_errors  = []
            records.append(record)
        except Exception as exc:
            fname = item.get("file_name", "?")
            logging.warning(f"  Could not load record '{fname}' from error JSON: {exc}")

    logging.info(f"read_error_json: loaded {len(records)} record(s) from {path}")
    return records

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\output\json_writer.py

"""
json_writer.py
--------------
Exports AuditRecord objects to JSON and imports them back.

JSON is the user-facing edit interface:
  1. Extractor runs → saves to DB → exports JSON
  2. User opens JSON, corrects wrong field values, saves
  3. Import function reads JSON → updates DB records

JSON structure
--------------
{
  "version": "1.1",
  "exported_at": "2026-03-05T10:30:00",
  "record_count": 42,
  "records": [
    {
      "file_name": "...",
      "factory": "...",
      "client": "...",
      "date_of_issue": "...",
      ...all scalar fields...,
      "defect_rows": [{"category": ..., "item": ..., "major": ..., ...}],
      "do_orders":   [...],
      "do_totals":   {...},
      "validation_errors": [...]
    },
    ...
  ]
}

No placeholder/extra rows are written — one record per audit.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from models.audit_record import AuditRecord


_JSON_VERSION = "1.1"


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def _record_to_dict(record: AuditRecord) -> Dict[str, Any]:
    """
    Serialise a single AuditRecord to a JSON-safe dict.
    All fields are included for round-trip fidelity.
    """
    return record.to_json_dict()


def write_json_output(records: List[AuditRecord], output_path: Path) -> None:
    """
    Write all records to a JSON file at *output_path*.

    Overwrites any existing file.  One record per audit — no placeholder rows.
    """
    payload = {
        "version":      _JSON_VERSION,
        "exported_at":  datetime.now().isoformat(timespec="seconds"),
        "record_count": len(records),
        "records":      [_record_to_dict(r) for r in records],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)

    logging.info(f"JSON exported: {output_path}  ({len(records)} records)")


# ---------------------------------------------------------------------------
# Import / reload
# ---------------------------------------------------------------------------

def json_to_audit_records(json_path: Path) -> List[AuditRecord]:
    """
    Load AuditRecord objects from a JSON file previously written by
    write_json_output().

    Handles both v1.1 (list under "records") and bare-list formats.
    Returns a list of AuditRecord objects ready for validation or DB save.
    """
    with open(json_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    # Support both wrapped {"records": [...]} and bare list
    if isinstance(data, list):
        raw_records = data
    elif isinstance(data, dict):
        raw_records = data.get("records", [])
    else:
        logging.error(f"Unexpected JSON structure in {json_path}")
        return []

    records: List[AuditRecord] = []

    for raw in raw_records:
        if not isinstance(raw, dict):
            continue

        # Skip any placeholder / non-record rows that may exist in older files
        if not raw.get("file_name"):
            continue

        # Extract known fields, ignore unknown ones gracefully
        known_fields = {f for f in AuditRecord.__dataclass_fields__}  # type: ignore[attr-defined]

        # Separate scalar fields from complex ones
        scalar = {k: v for k, v in raw.items() if k in known_fields
                  and k not in ("defect_rows", "do_orders", "do_totals",
                                "validation_errors")}

        # Always present: file_name
        file_name = raw.get("file_name", "")

        try:
            record = AuditRecord(file_name=file_name, **scalar)
        except TypeError as exc:
            logging.warning(f"Skipping malformed record '{file_name}': {exc}")
            continue

        # Complex fields
        record.defect_rows       = _load_list(raw.get("defect_rows"))
        record.do_orders         = _load_list(raw.get("do_orders"))
        record.do_totals         = raw.get("do_totals") or {}
        record.validation_errors = _load_validation_errors(raw.get("validation_errors"))

        records.append(record)

    logging.info(f"JSON loaded: {json_path}  ({len(records)} records)")
    return records


def _load_list(value: Any) -> List[Any]:
    """Return *value* as a list, or [] if None / wrong type."""
    if isinstance(value, list):
        return value
    return []


def _load_validation_errors(value: Any) -> List[str]:
    """
    Normalise validation_errors field:
      - list of strings  → returned as-is
      - comma-joined str → split back into list
      - None/missing     → []
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [str(e) for e in value if e]
    if isinstance(value, str) and value.strip():
        return [e.strip() for e in value.split(",") if e.strip()]
    return []

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\output\summary_writer.py

"""
summary_writer.py
-----------------
Generates the output summary Excel workbook from queried DB records.

Layout (matches the uploaded sample exactly)
--------------------------------------------
  Row 1  : Title row  +  category group headers (merged spans)
           e.g. "A : FABRICS" spanning columns 24-36
  Row 2  : Individual column headers
  Row 3  : (skipped — no averages row)
  Row 4  : 合計  totals row
  Row 5+ : One data row per audit record

  After the data rows:
    If ENABLE_PLACEHOLDER_ROWS = True (future feature):
      Each record block is followed by 5 stub rows:
        1. Carton
        2. Shipment dates
        3. Needle detector
        4. Remarks
        5. DO Set Col Size

Column order (fixed prefix, then dynamic defect columns)
---------------------------------------------------------
  factory, date_of_issue, inspection_type,
  factory_in_time, factory_out_time, factory_total_hours,
  audit_start_time, audit_end_time,  audit_total_hours,
  audit_result, report_no, item_name, style_no, po_no,
  country, po_qty_display, po_wh, ship_qty, audit_qty,
  acceptable_defect_qty, defect_qty, defect_percentage, person,
  [dynamic defect columns grouped by category ...]

Defect columns
--------------
Built dynamically from whatever defect types appear in the data.
Grouped by category (A:FABRICS, B:SEWING, …) in the row-1 merged header.

Called from writer_main.py as:
    write_summary(records, defect_map, output_path)
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from output.chart_generator import ChartGenerator

# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------

ENABLE_PLACEHOLDER_ROWS: bool = False   # set True when placeholder logic is ready


# ---------------------------------------------------------------------------
# Fixed prefix columns
# (column key → display header label)
# ---------------------------------------------------------------------------

PREFIX_COLUMNS: List[Tuple[str, str]] = [
    ("factory",            "Factory"),
    ("date_of_issue",      "Date of issue"),
    ("inspection_type",    "Inspection Type"),
    ("factory_in",         "Factory In Time"),
    ("factory_out",        "Factory Out Time"),
    ("factory_total_hours","Total Hours"),
    ("audit_start",        "Audit Start Time"),
    ("audit_end",          "Audit End Time"),
    ("audit_total_hours",  "Total Hours"),
    ("audit_result",       "Audit Result"),
    ("report_no",          "Report Number"),
    ("item_name",          "Item Name"),
    ("style_no",           "Style NO."),
    ("po_no",              "POーNO"),
    ("country",            "Country"),
    ("po_qty_pcs",         "PO Qty.(PCS)"),
    ("po_qty_pack",        "PO Qty.(PACK)"),
    ("po_qty_set",         "PO Qty.(SET)"),
    ("po_wh",              "PO  WH"),
    ("ship_qty",           "Shipping Qty"),
    ("audit_qty",          "Audit Qty."),
    ("acceptable_defect_qty", "Acceptable Defect Qty"),
    ("defect_qty",         "Defect Qty."),
    ("defect_percentage",  "Defect %"),
    ("person",             "Person"),
]

PREFIX_KEY_SET = {k for k, _ in PREFIX_COLUMNS}

# ---------------------------------------------------------------------------
# Placeholder row labels (used when ENABLE_PLACEHOLDER_ROWS = True)
# ---------------------------------------------------------------------------

_PLACEHOLDER_LABELS = [
    ("carton",          "carton"),
    ("shipment_dates",  "shipment_dates"),
    ("needle_detector", "needle_detector"),
    ("remarks",         "remarks"),
    ("do_set_col_size", "Do Set Col Size"),
]

# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

_WHITE   = "FFFFFF"
_BLACK   = "000000"
_YELLOW  = "FFFF00"
_DARK_BLUE   = "2F5496"
_ORANGE      = "C65911"
_LIGHT_GRAY  = "808080"
_TOTALS_FILL = _LIGHT_GRAY   # light gray for 合計 row

_TOP_BAR_FONT  = Font(bold=True, color=_BLACK, size=9)
_TOP_BAR_FILL  = PatternFill("solid", fgColor=_WHITE)

_HEADER_FONT   = Font(bold=True, color=_BLACK, size=9)
_DATA_FONT     = Font(size=9)
_TOTALS_FONT   = Font(bold=True, color=_WHITE, size=9)
_TITLE_FONT    = Font(bold=True, color=_WHITE, size=10)

_HEADER_FILL  = PatternFill("solid", fgColor=_YELLOW)
_TOTALS_FILL_STYLE = PatternFill("solid", fgColor=_TOTALS_FILL)
_PLACEHOLDER_FILL  = PatternFill("solid", fgColor=_LIGHT_GRAY)

_CENTRE = Alignment(horizontal="center", vertical="center", wrap_text=True)
_LEFT   = Alignment(horizontal="left",   vertical="center", wrap_text=False)
_RIGHT  = Alignment(horizontal="right",  vertical="center")

_THIN = Side(style="thin", color=_BLACK)
_CELL_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_CELL_BORDER_TOP_RIGHT_LEFT = Border(left=_THIN, right=_THIN, top=_THIN)
_CELL_BORDER_BOTTOM = Border(bottom=_THIN)
_CELL_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

_ROTATE_TEXT_UP_ALIGNMENT = Alignment(horizontal="center", vertical="center", textRotation=90, wrap_text=True)


# ---------------------------------------------------------------------------
# Category colour map (matches sample colouring)
# ---------------------------------------------------------------------------

_CATEGORY_FILLS = {
    "A": PatternFill("solid", fgColor=_WHITE),  # White
    "B": PatternFill("solid", fgColor=_WHITE),  # White
    "C": PatternFill("solid", fgColor=_WHITE),  # White
    "D": PatternFill("solid", fgColor=_WHITE),  # White
    "E": PatternFill("solid", fgColor=_WHITE),  # White
    "F": PatternFill("solid", fgColor=_WHITE),  # White
}


def _cat_fill(category: str) -> PatternFill:
    letter = category.strip()[:1].upper()
    return _CATEGORY_FILLS.get(letter, _TOP_BAR_FILL)


# ---------------------------------------------------------------------------
# Defect column plan builder
# ---------------------------------------------------------------------------

def build_defect_column_plan(
    defect_rows_by_report: Dict[int, List[Dict[str, Any]]],
) -> List[Tuple[str, str]]:
    """
    Build an ordered list of (category, item) pairs from all defect data.
    Sorted by category letter then item text.

    Returns [(category, item), ...]
    """
    seen: Dict[Tuple[str, str], None] = {}
    for rows in defect_rows_by_report.values():
        for d in rows:
            if isinstance(d, dict):
                cat  = (d.get("category") or "").strip()
                item = (d.get("item") or "").strip()
                if cat and item:
                    seen[(cat, item)] = None
    return sorted(seen.keys(), key=lambda x: (x[0], x[1]))


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------

def _get_prefix_value(row: Dict[str, Any], key: str) -> Any:
    """Extract the display value for a prefix column from a DB row dict."""
    if key == "po_qty_display":
        # Prefer pcs, then pack, then set, then raw string
        for sub in ("po_qty_pcs", "po_qty_pack", "po_qty_set"):
            v = row.get(sub)
            if v:
                return v
        return row.get("po_qty_raw", "")
    return row.get(key, "")


def _pct_float(val: Any) -> Optional[float]:
    """Convert defect_percentage stored as float or '3.71%' to float."""
    if val is None:
        return None
    try:
        return float(str(val).replace("%", "").strip())
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Sheet writer
# ---------------------------------------------------------------------------

def _write_sheet(
    ws,
    records: List[Dict[str, Any]],
    defect_items_by_report: Dict[int, List[Dict[str, Any]]],
    defect_plan: List[Tuple[str, str]],
) -> None:
    """Write all rows to worksheet *ws*."""

    total_prefix = len(PREFIX_COLUMNS)
    total_defect = len(defect_plan)
    total_cols   = total_prefix + total_defect

    # ── Row 1: title + category group headers ────────────────────────────────
    ws.row_dimensions[1].height = 22

    # Left title span (fixed prefix area)
    ws.merge_cells(start_row=1, start_column=1,
                   end_row=1, end_column=total_prefix)
    title_cell = ws.cell(row=1, column=1, value="出荷前監査報告書")
    title_cell.font      = _TOP_BAR_FONT
    title_cell.fill      = _TOP_BAR_FILL
    title_cell.alignment = _CENTRE
    title_cell.border    = _CELL_BORDER

    # Category merged spans
    if defect_plan:
        col_idx = total_prefix + 1
        i = 0
        while i < len(defect_plan):
            cat = defect_plan[i][0]
            j = i
            while j < len(defect_plan) and defect_plan[j][0] == cat:
                j += 1
            span = j - i
            if span > 1:
                ws.merge_cells(
                    start_row=1, start_column=col_idx,
                    end_row=1,   end_column=col_idx + span - 1
                )
            cell = ws.cell(row=1, column=col_idx, value=cat)
            cell.font      = _TOP_BAR_FONT
            cell.fill      = _cat_fill(cat)
            cell.alignment = _CENTRE
            cell.border    = _CELL_BORDER
            col_idx += span
            i = j

    # ── Rows 2-3: column headers (each cell merged vertically across both rows) ─
    # Row 2 holds the value; row 3 is merged into it so headers appear taller.
    ws.row_dimensions[2].height = 150
    ws.row_dimensions[3].height = 1    # collapsed — fully absorbed by merge

    def _write_header_cell(col_idx: int, label: str, fill: PatternFill) -> None:
        """Merge rows 2-3 for this column and write the header label."""
        # Clear row 3 first (BEFORE merging — MergedCell is read-only after)
        r3 = ws.cell(row=3, column=col_idx)
        r3.value = None

        # Unmerge first (safe no-op if not already merged)
        try:
            ws.unmerge_cells(
                start_row=2, start_column=col_idx,
                end_row=3,   end_column=col_idx,
            )
        except Exception:
            pass

        ws.merge_cells(
            start_row=2, start_column=col_idx,
            end_row=3,   end_column=col_idx,
        )
        cell = ws.cell(row=2, column=col_idx, value=label)
        cell.font      = _HEADER_FONT
        cell.fill      = fill
        cell.alignment = _ROTATE_TEXT_UP_ALIGNMENT
        cell.border    = _CELL_BORDER

    for col_idx, (_, label) in enumerate(PREFIX_COLUMNS, start=1):
        _write_header_cell(col_idx, label, _HEADER_FILL)

    for k, (cat, item) in enumerate(defect_plan, start=total_prefix + 1):
        _write_header_cell(k, item, _HEADER_FILL)
        # _write_header_cell(k, item, _cat_fill(cat))

    # ── Row 4: 合計 totals ────────────────────────────────────────────────────
    totals_row = 4
    ws.row_dimensions[totals_row].height = 16

    totals_label = ws.cell(row=totals_row, column=1, value="合計")
    totals_label.font      = _TOTALS_FONT
    totals_label.fill      = _TOTALS_FILL_STYLE
    totals_label.alignment = _LEFT
    totals_label.border    = _CELL_BORDER

    # We'll fill totals after writing data rows; store column sums here
    _ship_col  = next((i+1 for i, (k, _) in enumerate(PREFIX_COLUMNS) if k == "ship_qty"),  None)
    _audit_col = next((i+1 for i, (k, _) in enumerate(PREFIX_COLUMNS) if k == "audit_qty"), None)
    _defect_col = next((i+1 for i, (k, _) in enumerate(PREFIX_COLUMNS) if k == "defect_qty"), None)

    total_ship  = 0
    total_audit = 0
    total_defect_count = 0
    defect_col_totals: Dict[int, int] = {}   # col_idx → total

    # ── Rows 5+: data rows ───────────────────────────────────────────────────
    current_row = 5

    for rec in records:
        report_id = rec.get("report_id")

        # Build defect lookup for this record: (category, item) → major_count
        defect_lookup: Dict[Tuple[str, str], int] = {}
        if report_id is not None:
            for d in defect_items_by_report.get(report_id, []):
                cat  = (d.get("category") or "").strip()
                item = (d.get("item") or "").strip()
                if cat and item:
                    defect_lookup[(cat, item)] = int(d.get("major_count", 0))

        ws.row_dimensions[current_row].height = 15

        # Write prefix columns
        for col_idx, (key, _) in enumerate(PREFIX_COLUMNS, start=1):
            val  = _get_prefix_value(rec, key)
            cell = ws.cell(row=current_row, column=col_idx, value=val)
            cell.font      = _DATA_FONT
            cell.alignment = _CENTRE
            cell.border    = _CELL_BORDER

        # Write defect columns
        for k, (cat, item) in enumerate(defect_plan, start=total_prefix + 1):
            count = defect_lookup.get((cat, item), "")
            cell  = ws.cell(row=current_row, column=k, value=count if count else "")
            cell.font      = _DATA_FONT
            cell.alignment = _CENTRE
            cell.border    = _CELL_BORDER
            if isinstance(count, int) and count > 0:
                defect_col_totals[k] = defect_col_totals.get(k, 0) + count

        # Accumulate totals
        try:
            total_ship  += int(rec.get("ship_qty")  or 0)
            total_audit += int(rec.get("audit_qty") or 0)
            total_defect_count += int(rec.get("defect_qty") or 0)
        except (TypeError, ValueError):
            pass

        current_row += 1

        # Placeholder rows (controlled by flag)
        if ENABLE_PLACEHOLDER_ROWS:
            _write_placeholder_rows(ws, rec, PREFIX_COLUMNS, total_cols, current_row)
            current_row += len(_PLACEHOLDER_LABELS)

    # ── Fill totals row ───────────────────────────────────────────────────────
    if _ship_col:
        cell = ws.cell(row=totals_row, column=_ship_col, value=total_ship)
        cell.font = _TOTALS_FONT; cell.fill = _TOTALS_FILL_STYLE
    if _audit_col:
        cell = ws.cell(row=totals_row, column=_audit_col, value=total_audit)
        cell.font = _TOTALS_FONT; cell.fill = _TOTALS_FILL_STYLE
    if _defect_col:
        # defect % = total_defect / total_audit
        cell = ws.cell(row=totals_row, column=_defect_col, value=total_defect_count)
        cell.font = _TOTALS_FONT; cell.fill = _TOTALS_FILL_STYLE
        pct_col = _defect_col + 1
        if total_audit > 0:
            ws.cell(row=totals_row, column=pct_col,
                    value=round(total_defect_count / total_audit, 8)).fill = _TOTALS_FILL_STYLE

    for col_idx, total in defect_col_totals.items():
        cell = ws.cell(row=totals_row, column=col_idx, value=total)
        cell.font = _TOTALS_FONT
        cell.fill = _TOTALS_FILL_STYLE
        cell.alignment = _CENTRE

    # Fill remaining totals cells with fill colour
    for col_idx in range(2, total_cols + 1):
        cell = ws.cell(row=totals_row, column=col_idx)
        if cell.fill.fgColor.rgb in ("00000000", "FFFFFFFF", "00FFFFFF"):
            cell.fill = _TOTALS_FILL_STYLE

    # ── Column widths ─────────────────────────────────────────────────────────
    _set_column_widths(ws, total_prefix, total_defect)

    # ── Freeze panes: rows 1-4 (title + merged header + totals) ─────────────
    ws.freeze_panes = "A5"

    # ── Charts below the data rows ────────────────────────────────────────────
    # Leave 2 blank rows as a visual gap, then draw:
    #   Col 1 : Top-5 pie chart  +  category summary table  (stacked vertically)
    #   Col 2 : Full-defect bar chart  (right of pie, matching screenshot layout)
    chart_start_row = current_row + 2
    _write_inline_charts(ws, chart_start_row, defect_plan, total_prefix)


def _write_inline_charts(
    ws,
    start_row: int,
    defect_plan: List[Tuple[str, str]],
    total_prefix: int,
) -> None:
    """
    Draw charts below the data rows using data already on the sheet:
      Row 2 — defect item name headers  (cols total_prefix+1 onward)
      Row 4 — 合計 totals

    Reads those cells into (name, count) pairs, then:
      - Left side: Top‑5 pie chart (written by ChartGenerator, which writes its own small table).
      - Right side: Full bar chart created directly from row2 (categories) and row4 (values),
                    without any new table.
    """
    if not defect_plan:
        return

    n         = len(defect_plan)
    col_start = total_prefix + 1
    col_end   = col_start + n - 1

    # ── Read (name, total) from the sheet rows 2 and 4 ──────────────────────
    defect_totals: List[Tuple[str, int]] = []
    for col_idx in range(col_start, col_end + 1):
        name = ws.cell(row=2, column=col_idx).value or ""
        val  = ws.cell(row=4, column=col_idx).value
        try:
            total = int(val or 0)
        except (TypeError, ValueError):
            total = 0
        defect_totals.append((str(name), total))

    # Keep only non‑zero for the pie chart (the bar chart will show all columns,
    # zero bars are flat – you can change this if you prefer filtering).
    nonzero = [(n, c) for n, c in defect_totals if c > 0]
    if not nonzero:
        return

    top5 = nonzero[:5]

    # ── Factory name for bar chart title ─────────────────────────────────────
    try:
        factory_name = ws.cell(row=5, column=1).value or ""
    except Exception:
        factory_name = ""
    bar_title = f"{factory_name}".strip(" —")

    # ── Section heading ───────────────────────────────────────────────────────
    ws.cell(row=start_row, column=1).value = "Defect Analysis"
    ws.cell(row=start_row, column=1).font  = Font(bold=True, size=11, color=_DARK_BLUE)

    chart_row = start_row + 1

    # ── LEFT: Top‑5 pie chart (col 1) ─────────────────────────────────────────
    top5_with_pct = [
        (name, count, count / sum(c for _, c in nonzero) * 100)
        for name, count in top5
    ]
    left_gen = ChartGenerator(ws, start_row=chart_row, start_col=1)
    left_gen.create_pie_chart_with_table(top5_with_pct, title="Top 5 Defect")

    # ── RIGHT: Full bar chart (col BAR_COL) – no helper table ─────────────────
    BAR_COL = 12   # must be far enough right to clear the pie table
    from openpyxl.chart import BarChart, Reference
    from openpyxl.chart.label import DataLabelList

    # Create the bar chart
    chart = BarChart()
    chart.title = bar_title
    chart.style = 1
    chart.x_axis.title = "Defect"
    chart.y_axis.title = "Count"
    chart.legend = None
    chart.width = 15
    chart.height = 8
    chart.gapWidth = 50

    # Data series: totals from row 4, columns col_start .. col_end
    data = Reference(ws, min_col=col_start, max_col=col_end,
                     min_row=4, max_row=4)
    # Categories: defect names from row 2, same columns
    categories = Reference(ws, min_col=col_start, max_col=col_end,
                           min_row=2, max_row=2)

    chart.add_data(data, titles_from_data=False)   # no series title
    chart.set_categories(categories)

    # Data labels (show value on top of bars)
    chart.dataLabels = DataLabelList()
    chart.dataLabels.showVal = True
    chart.dataLabels.showCatName = False
    chart.dataLabels.showSerName = False
    chart.dataLabels.dLblPos = "outEnd"   # "t" or "outEnd"
    chart.dataLabels.numFmt = "#,##0"

    # Place the chart – we position it at the same row as the pie chart's anchor,
    # but far right. The exact row is chart_row; column BAR_COL.
    from openpyxl.utils import get_column_letter
    anchor_cell = f"{get_column_letter(BAR_COL)}{chart_row}"
    ws.add_chart(chart, anchor_cell)

def _write_placeholder_rows(
    ws,
    rec: Dict[str, Any],
    prefix_columns: List[Tuple[str, str]],
    total_cols: int,
    start_row: int,
) -> None:
    """Write the 5 placeholder rows below a data record."""
    file_name = rec.get("file_name", "")
    factory   = rec.get("factory", "")

    for offset, (field_key, label) in enumerate(_PLACEHOLDER_LABELS):
        row = start_row + offset
        ws.row_dimensions[row].height = 13

        for col_idx, (key, _) in enumerate(prefix_columns, start=1):
            cell = ws.cell(row=row, column=col_idx)
            cell.fill = _PLACEHOLDER_FILL
            cell.font = Font(size=8, italic=True)
            cell.alignment = _LEFT

            if key == "factory":
                cell.value = label
            elif key == "date_of_issue" and field_key in rec:
                cell.value = rec.get(field_key, "")

        # merge remaining columns
        if total_cols > len(prefix_columns):
            ws.merge_cells(
                start_row=row, start_column=len(prefix_columns) + 1,
                end_row=row,   end_column=total_cols,
            )


def _set_column_widths(ws, total_prefix: int, total_defect: int) -> None:
    """Set sensible column widths for readability."""
    narrow_cols = {
        1:  22,   # factory
        2:  12,   # date
        3:  18,   # inspection type
        4:  10,   # factory in
        5:  10,   # factory out
        6:  8,    # total hours
        7:  10,   # audit start
        8:  10,   # audit end
        9:  8,    # total hours
        10: 8,    # audit result
        11: 16,   # report no
        12: 28,   # item name
        13: 14,   # style no
        14: 22,   # po no
        15: 8,    # country
        16: 10,   # po qty
        17: 12,   # po wh
        18: 10,   # ship qty
        19: 10,   # audit qty
        20: 12,   # acceptable defect
        21: 10,   # defect qty
        22: 10,   # defect %
        23: 8,    # person
    }
    for col_idx in range(1, total_prefix + 1):
        letter = get_column_letter(col_idx)
        ws.column_dimensions[letter].width = narrow_cols.get(col_idx, 10)

    # Defect columns: narrow
    for col_idx in range(total_prefix + 1, total_prefix + total_defect + 1):
        letter = get_column_letter(col_idx)
        ws.column_dimensions[letter].width = 6


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_summary(
    records: List[Dict[str, Any]],
    defect_items_by_report: Dict[int, List[Dict[str, Any]]],
    output_path: Path,
) -> None:
    """
    Generate the summary Excel workbook and save to *output_path*.

    Parameters
    ----------
    records                : list of row dicts from v_audit_full (DB query)
    defect_items_by_report : {report_id: [defect_item_dict, ...]}
    output_path            : destination .xlsx path

    One sheet per inspection type (FINAL, RE-FINAL, INLINE, CMF, SAMPLE, UNKNOWN).
    Sheet name is the canonical inspection type.
    """
    # Build the global defect column plan (all categories/items across all records)
    defect_plan = build_defect_column_plan(defect_items_by_report)

    # Detection order: RE-FINAL / PRE-FINAL before FINAL (substring collision)
    SHEET_ORDER = ["RE-FINAL", "PRE-FINAL", "FINAL", "INLINE", "CMF", "SAMPLE", "UNKNOWN"]

    def _canonical(itype: str) -> str:
        """
        Map any inspection_type string (from Excel cell or filename) to a
        canonical sheet name. Handles every real-world variation:

          RE-FINAL  : "Re-Final", "Re Final", "RE FINAL", "2nd Re-Final",
                      "Re-Final Audit", "refinal"
          FINAL     : "Final", "FINAL AUDIT", "Final Inspection",
                      "Shipment Audit", "Pre-Shipment"
          INLINE    : "Inline", "In-Line", "In Line", "Inline Inspection"
          CMF       : "CMF", "Counter Master Fitting"
          SAMPLE    : "Sample", "Pre-Production", "PP", "Pre Production"
          PRE-FINAL : "Pre-Final", "Pre Final", "PRE FINAL"
        """
        import re as _re
        u = (itype or "").upper().strip()

        # PRE-FINAL must be checked BEFORE RE-FINAL
        # ("PRE-FINAL" contains "RE-FINAL" as a substring)
        if _re.search(r"PRE[\s\-]?FINAL", u):
            return "PRE-FINAL"

        # RE-FINAL — use negative lookbehind to exclude "PRE-FINAL"
        if _re.search(r"(?<!PRE[\-\s])RE[\s\-]?FINAL|REFINAL", u):
            return "RE-FINAL"

        if _re.search(r"\bFINAL\b|SHIPMENT\s*AUDIT|PRE[\s\-]?SHIPMENT", u):
            return "FINAL"

        if _re.search(r"IN[\s\-]?LINE", u):
            return "INLINE"

        if _re.search(r"\bCMF\b|COUNTER\s*MASTER", u):
            return "CMF"

        if _re.search(r"\bSAMPLE\b|PRE[\s\-]?PROD|PP\s*SAMPLE|\bPP\b", u):
            return "SAMPLE"

        return "UNKNOWN"

    by_type: Dict[str, List[Dict[str, Any]]] = {}
    for rec in records:
        key = _canonical(rec.get("inspection_type") or "")
        by_type.setdefault(key, []).append(rec)

    wb = openpyxl.Workbook()
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    # Tab display order in the workbook
    DISPLAY_ORDER = ["FINAL", "RE-FINAL", "PRE-FINAL", "INLINE", "CMF", "SAMPLE", "UNKNOWN"]

    sheets_written = 0
    for sheet_name in DISPLAY_ORDER:
        type_records = by_type.get(sheet_name)
        if not type_records:
            continue

        # Per-sheet defect plan — only defect types in this sheet's records
        sheet_defect_plan = build_defect_column_plan(
            {r["report_id"]: defect_items_by_report.get(r["report_id"], [])
             for r in type_records}
        )

        ws = wb.create_sheet(title=sheet_name[:31])
        _write_sheet(ws, type_records, defect_items_by_report, sheet_defect_plan)
        sheets_written += 1

        logging.info(
            f"  Sheet '{sheet_name}': {len(type_records)} record(s), "
            f"{len(sheet_defect_plan)} defect column(s)"
        )

    if not wb.sheetnames:
        wb.create_sheet("No Data")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    logging.info(f"Summary saved: {output_path}  ({sheets_written} sheet(s))")

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\output\__init__.py


# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\validation\validator.py

"""
validator.py
------------
Multi-layer validation and refinement of AuditRecord objects.

Layers (applied in order)
--------------------------
Layer 1 – DATE STRIPPING
    Date fields must contain a date only.  If the raw value carries a time
    component (e.g. "2026-01-01 10:00:00") the time part is silently stripped
    and only the date is kept.

Layer 2 – DATE FORMATTING
    Accepted dates are normalised to MM/DD/YYYY.

Layer 3 – TIME VALIDATION
    Time fields (factory in/out, audit start/end) must be parseable as
    HH:MM.  Unparseable values → set to "" (null) rather than storing garbage.

Layer 4 – PATTERN VALIDATION
    Report numbers and PO numbers share the same Excel label in some sheets.
    Each field is validated against its expected regex:
      Report No : e.g.  JP26-02BABL-001   ->  [A-Z]{2}\d{2}-\d{2}[A-Z0-9]+-\d+
      PO No     : e.g.  P0426-482649-004  →  P\d{4}-\d{6}-\d{3}(-\d+)*

Layer 5 – BUSINESS RULES
    Mandatory field checks, numeric range validation, etc.

Adding a new validation rule
-----------------------------
1. Write a bool function  f(value) -> bool  (True = valid).
2. Add a tuple  (f, "human-readable error message")  to VALIDATION_RULES[FieldName.XXX].
"""

import logging
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Tuple

from models.audit_record import AuditRecord
from enums.field_enums import FieldName


# ---------------------------------------------------------------------------
# Layer 1 + 2 : Date stripping and formatting
# ---------------------------------------------------------------------------

_DATE_FORMATS = [
    "%m/%d/%Y",  # target format – skip re-formatting if already correct
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%Y-%m-%d",
    "%m-%d-%Y",
    "%d-%m-%Y",
    "%m.%d.%Y",
    "%d.%m.%Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%Y/%d/%m",
    "%Y-%d-%m",
    "%d-%Y-%m",
    "%m/%Y/%d",
    "%d/%Y/%m",
]

# Regex that detects a datetime string with both a date and a time component.
# E.g. "2026-01-01 10:00:00" or "2026-01-01T10:00"
_DATETIME_RE = re.compile(
    r"^(\d{4}[-/]\d{1,2}[-/]\d{1,2}|"   # YYYY-MM-DD …
    r"\d{1,2}[-/]\d{1,2}[-/]\d{4})"       # DD/MM/YYYY …
    r"[\sT]"                               # separator
    r"\d{1,2}[:.]\d{2}"                   # time component
)


def _strip_time_from_date(value: str) -> str:
    """
    If *value* contains both a date and a time component, strip the time.

    "2026-01-01 10:00:00" → "2026-01-01"
    "01/15/2026 09:30"    → "01/15/2026"
    "2026-01-15"          → "2026-01-15"   (unchanged)
    """
    if not value:
        return value
    s = value.strip()
    if _DATETIME_RE.match(s):
        # Keep everything before the first space or T
        stripped = re.split(r"[\sT]", s, maxsplit=1)[0]
        logging.info(f"  date stripped of time component: '{s}' → '{stripped}'")
        return stripped
    return s


def _format_date(date_string: str) -> str:
    """
    Strip any time component, then normalise to MM/DD/YYYY.
    Returns the original string unchanged if no format matches.
    """
    if not isinstance(date_string, str) or not date_string.strip():
        return date_string or ""

    # Layer 1: strip time component
    date_string = _strip_time_from_date(date_string.strip())

    # Layer 2: normalise to MM/DD/YYYY
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(date_string, fmt).strftime("%m/%d/%Y")
        except ValueError:
            continue

    logging.warning(f"Date format not recognised: '{date_string}'")
    return date_string


# ---------------------------------------------------------------------------
# Layer 3 : Time validation
# ---------------------------------------------------------------------------

def _format_time(time_string: str) -> str:
    """
    Convert a loose time string to "HH:MM AM/PM" (12-hour with suffix).
    Returns "" (empty / null) if the value is not a valid time — this
    prevents storing garbage in the time fields.

    Examples
    --------
    "9:30"          → "09:30 AM"
    "14:00"         → "02:00 PM"
    "9.30AM"        → "09:30 AM"
    "2026-01-01..." → ""   (datetime strings are invalid as times)
    """
    if not isinstance(time_string, str) or not time_string.strip():
        return ""

    s = time_string.strip()

    # Reject strings that look like full dates / datetimes
    if re.match(r"\d{4}[-/]\d{2}[-/]\d{2}", s):
        logging.info(
            f"  time field contains datetime '{s}' → set to null"
        )
        return ""

    match = re.search(r"(\d{1,2})[:.]?(\d{2})?\s*([APap][Mm])?", s)
    if not match:
        logging.info(f"  time field '{s}' not parseable → set to null")
        return ""

    hour_str, minute_str, am_pm = match.groups()
    hour   = int(hour_str)
    minute = int(minute_str) if minute_str else 0

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        logging.info(
            f"  time field '{s}' out of range → set to null"
        )
        return ""

    if am_pm:
        am_pm_lower = am_pm.lower()
        if am_pm_lower.startswith("p") and hour != 12:
            hour += 12
        elif am_pm_lower.startswith("a") and hour == 12:
            hour = 0

    try:
        return datetime.strptime(f"{hour}:{minute}", "%H:%M").strftime("%I:%M %p")
    except ValueError:
        logging.info(f"  time field '{s}' failed strptime → set to null")
        return ""


# ---------------------------------------------------------------------------
# Layer 4 : Pattern validation helpers
# ---------------------------------------------------------------------------

_REPORT_NO_RE = re.compile(r"^[A-Z]{2}\d{2}-\d{2}[A-Z0-9]+-\d+$")
_PO_NO_RE     = re.compile(r"^P\d{4}-\d{6}-\d{3}(-\d+)*$")


def is_valid_report_no(value: str) -> bool:
    """True if value matches the Report Number pattern (e.g. JP26-02BABL-001)."""
    if not value:
        return False
    return bool(_REPORT_NO_RE.match(value.strip().rstrip(".,;:")))


def is_valid_po_no(value: str) -> bool:
    """True if value matches the PO Number pattern (e.g. P0426-482649-004)."""
    if not value:
        return False
    return bool(_PO_NO_RE.match(value.strip()))


# ---------------------------------------------------------------------------
# Layer 5 : Business rule validators
# ---------------------------------------------------------------------------

def is_not_empty(value: Any) -> bool:
    return bool(str(value).strip())


def is_numeric(value: Any) -> bool:
    if isinstance(value, (int, float)):
        return True
    return str(value).strip().replace(".", "", 1).isdigit()


def is_date_mmddyyyy(value: str) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.strptime(value.strip(), "%m/%d/%Y")
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Validation rules per field
# ---------------------------------------------------------------------------

ValidationRule = Callable[[Any], bool]
RuleList       = List[Tuple[ValidationRule, str]]

VALIDATION_RULES: Dict[str, RuleList] = {
    FieldName.FACTORY: [
        (is_not_empty, "Factory name should not be empty."),
    ],
    FieldName.DATE_OF_ISSUE: [
        (is_not_empty,    "Date of Issue should not be empty."),
        (is_date_mmddyyyy, "Date of Issue must be in MM/DD/YYYY format."),
    ],
    FieldName.EXF: [
        (is_date_mmddyyyy, "EXF date must be in MM/DD/YYYY format."),
    ],
    FieldName.PO_EDT: [
        (is_date_mmddyyyy, "PO EDT must be in MM/DD/YYYY format."),
    ],
    FieldName.PO_WH: [
        (is_date_mmddyyyy, "PO WH date must be in MM/DD/YYYY format."),
    ],
    FieldName.PLAN_EDT: [
        (is_date_mmddyyyy, "Plan EDT must be in MM/DD/YYYY format."),
    ],
    FieldName.PLAN_WH: [
        (is_date_mmddyyyy, "Plan WH must be in MM/DD/YYYY format."),
    ],
    FieldName.SHIP_QTY: [
        (is_numeric, "Ship Quantity should be a number."),
    ],
    FieldName.AUDIT_QTY: [
        (is_numeric, "Audit Quantity should be a number."),
    ],
    FieldName.REPORT_NO: [
        (
            lambda v: not v or is_valid_report_no(v),
            "Report No does not match expected pattern (e.g. JP26-02BABL-001).",
        ),
    ],
    FieldName.PO_NO: [
        (
            lambda v: not v or is_valid_po_no(v),
            "PO No does not match expected pattern (e.g. P0426-482649-004).",
        ),
    ],
}


# ---------------------------------------------------------------------------
# Refinement map  (field → formatter)
# ---------------------------------------------------------------------------

_REFINEMENT_RULES: Dict[str, Callable[[str], str]] = {
    # Time fields → "HH:MM AM/PM" or "" on failure
    "factory_in_time":  _format_time,
    "factory_out_time": _format_time,
    "audit_start_time": _format_time,
    "audit_end_time":   _format_time,
    # Date fields → "MM/DD/YYYY" (time component stripped first)
    "date_of_issue":    _format_date,
    "exf":              _format_date,
    "po_wh":            _format_date,
    "po_edt":           _format_date,
    "plan_edt":         _format_date,
    "plan_wh":          _format_date,
}


def apply_refinement_rules(record: AuditRecord) -> AuditRecord:
    """Apply date/time formatting to all relevant fields in *record*."""
    for field_name, formatter in _REFINEMENT_RULES.items():
        raw = getattr(record, field_name, None)
        if not raw:
            continue
        refined = formatter(raw)
        if refined != raw:
            logging.info(f"  refined [{field_name}]: '{raw}' → '{refined}'")
        setattr(record, field_name, refined)
    return record


# ---------------------------------------------------------------------------
# Blocking validation  (records that FAIL these are never inserted into DB)
# ---------------------------------------------------------------------------

# Fields that MUST be present for a record to be usable.
# If any of these are missing the record goes to the error JSON instead.
_BLOCKING_REQUIRED_FIELDS: List[Tuple[str, str]] = [
    ("factory",         "Factory name is missing"),
    ("date_of_issue",   "Date of Issue is missing"),
    ("inspection_type", "Inspection Type is missing"),
    ("report_no",       "Report Number is missing"),
    ("ship_qty",        "Shipping Quantity is missing"),
    ("audit_qty",       "Audit Quantity is missing"),
]


def validate_blocking(record: AuditRecord) -> AuditRecord:
    """
    Run blocking validations.  Any failure appends to record.blocking_errors
    and the record will be written to the error JSON and skipped by the DB.

    Checks:
      1. Required fields must not be empty.
      2. Sum of extracted defect major counts must equal record.defect_qty.
         A mismatch means the defect table was not read correctly.
    """
    errors: List[str] = []

    # Check 1: required fields
    for field_key, msg in _BLOCKING_REQUIRED_FIELDS:
        val = getattr(record, field_key, None)
        if not val or not str(val).strip():
            errors.append(f"REQUIRED_FIELD | {field_key} | {msg}")
            logging.warning(f"[{record.file_name}] BLOCKING: {msg}")

    # Check 2: defect count integrity
    if record.defect_qty and record.defect_rows:
        try:
            header_qty = int(str(record.defect_qty).strip())
            extracted_sum = sum(
                int(d.get("major", 0) or 0) + int(d.get("minor", 0) or 0)
                for d in record.defect_rows
                if isinstance(d, dict)
            )
            if header_qty != extracted_sum:
                msg = (
                    f"DEFECT_MISMATCH | "
                    f"header says {header_qty} total defects but "
                    f"extracted defect rows sum to {extracted_sum}"
                )
                errors.append(msg)
                logging.warning(f"[{record.file_name}] BLOCKING: {msg}")
        except (ValueError, TypeError):
            pass   # can't compare — don't block on this

    record.blocking_errors.extend(errors)
    return record


def validate_blocking_all(records: List[AuditRecord]) -> List[AuditRecord]:
    """Apply validate_blocking to every record and return the list."""
    for r in records:
        validate_blocking(r)
    blocked = sum(1 for r in records if r.blocking_errors)
    logging.info(f"Blocking validation: {blocked}/{len(records)} records blocked")
    return records


# ---------------------------------------------------------------------------
# Per-record validation
# ---------------------------------------------------------------------------

def validate_record(record: AuditRecord) -> AuditRecord:
    """
    1. Apply refinement rules (date stripping, date/time formatting).
    2. Run all VALIDATION_RULES and collect error messages.
    Returns the mutated record.
    """
    record = apply_refinement_rules(record)

    errors: List[str] = []

    for field_name, rules in VALIDATION_RULES.items():
        value = getattr(record, field_name, None)
        if not value:
            continue  # only validate fields that were actually extracted
        for rule_fn, error_msg in rules:
            if not rule_fn(value):
                full_msg = f"'{field_name}': {error_msg}"
                errors.append(full_msg)
                logging.warning(
                    f"Validation [{record.file_name}] – {full_msg}"
                )

    record.validation_errors.extend(errors)

    if errors:
        logging.warning(
            f"[{record.file_name}] {len(errors)} validation error(s)"
        )
    else:
        logging.info(f"[{record.file_name}] passed all validations")

    return record


# ---------------------------------------------------------------------------
# Batch validation
# ---------------------------------------------------------------------------

def validate_all_records(records: List[AuditRecord]) -> List[AuditRecord]:
    """
    Validate every record and log a summary.
    Returns the same list with validation_errors populated.
    """
    logging.info("=" * 60)
    logging.info("VALIDATION PHASE")
    logging.info("=" * 60)

    validated = [validate_record(r) for r in records]

    files_with_errors = sum(1 for r in validated if r.validation_errors)
    total_errors      = sum(len(r.validation_errors) for r in validated)

    logging.info(f"Total validated  : {len(records)}")
    logging.info(f"Files with errors: {files_with_errors}")
    logging.info(f"Total errors     : {total_errors}")
    logging.info("=" * 60)

    return validated

# FILE: D:\Project\UQ_GU_Summary-test\UQ_GU_Summary-test\analysis\validation\__init__.py

