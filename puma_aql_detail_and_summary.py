import os
import sys
import re
import gc
import shutil
import logging
from pathlib import Path
from collections import defaultdict
from datetime import datetime
import pdfplumber
import pandas as pd
from docx import Document
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from tkinter import Tk, Button, Label, filedialog, messagebox

enum = {
    "TBDYF" : "VIYELLATEX LTD",
    "TBDEK" : "EKL",
    "ABDPA" : "ABDPA",
    "TBDSH" : "DEWHIRST GROUP",
    "TBDSJ" : "SQUARE FASHION LTD",
    "TBDSG" : "SQUARE FASHION LTD",
    "TBDJK" : "DBL GROUP",
    "TBDJJ" : "DBL GROUP",
    "TBDAG" : "ABL",
    "TBDFT" : "FAKHRUDDIN TEXTILE MILLS LTD",
}

# ---------------- PROJECT ROOT ----------------
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent

OUTPUT_ROOT = PROJECT_ROOT / "output"
OUTPUT_ROOT.mkdir(exist_ok=True)

# ---------------- EXE SAFETY ----------------
if getattr(sys, "frozen", False):
    os.chdir(sys._MEIPASS)

# ---------------- LOGGING ----------------
logging.basicConfig(
    filename="pdf_process.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# ---------------- CORE EXTRACTION ----------------
def extract_reports(pdf_folder):
    # Changed from defaultdict to regular list
    # Each PDF gets its own entry, no grouping by style
    all_reports = []
    processed_files = []
    for pdf_file in Path(pdf_folder).glob("*.pdf"):
        try:
            text_all = ""

            with pdfplumber.open(pdf_file) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        text_all += t + "\n"

            if not text_all.strip():
                raise ValueError("Empty PDF")

            # Inspection Date (parse and format to YYYY-MM-DD)
            m = re.search(r"Inspection Date\s+(\d{2}\s\w{3}\s\d{4})", text_all)
            if m:
                try:
                    inspection_date = datetime.strptime(m.group(1), '%d %b %Y').strftime('%Y-%m-%d')
                except Exception:
                    # If parsing fails, keep the original captured string
                    inspection_date = m.group(1)
            else:
                inspection_date = ""

            # ---- Extract TOTAL row ----
            total_line = re.search(r"Total\s+.*", text_all, re.IGNORECASE)
            if not total_line:
                raise ValueError("TOTAL row not found")

            nums = list(map(int, re.findall(r"\d+", total_line.group(0))))
            po_qty, actual_qty, inspected_qty = nums[0], nums[1], nums[-1]

            # ---- Major / Minor Defects (FROM RESULTS SECTION) ----
            major_defect = ""
            minor_defect = ""
            
            m = re.search(r"Workmanship\s+Pass\s+(\d+\s*/\s*\d+)\s+(\d+\s*/\s*\d+)", text_all)
            if m:
                major_defect = m.group(1).replace(" ", "")
                minor_defect = m.group(2).replace(" ", "")

            # ---- Style + Description ----
            m = re.search(r"1\.\s+(.+?)\s+(\d{6})\s+\d+", text_all)
            if not m:
                raise ValueError("Style not found")

            desc_and_nums = m.group(1)
            style = m.group(2)
            
            description = desc_and_nums.strip()
            
            # Check if next line continues the description
            lines = text_all.split('\n')
            for i, line in enumerate(lines):
                if "1. " in line:
                    if i+1 < len(lines):
                        next_line = lines[i+1].strip()
                        if next_line and all(c.isalpha() or c.isspace() for c in next_line):
                            description += " " + next_line
                    break

            # ---- PO numbers ----
            pos = re.findall(r"\b460\d{7,}\b", text_all)
            if not pos:
                raise ValueError("POs not found")

            # ---- Factory ----
            factory = ""
            m = re.search(
                r"^Factory\s+([A-Z0-9&._()\- ]+?)(?:\s{2,}|Sample Size|QC Stage|Inspection Date|$)",
                text_all,
                re.IGNORECASE | re.MULTILINE
            )
            if m:
                factory_code = m.group(1).strip().upper()
                # Map code to full factory name using enum dict, fallback to code
                factory = enum.get(factory_code, factory_code)

            # ---- Final Customer ----
            m = re.search(r"Inspected\s+\d+\.\s+\d+\s+\d{2}\s\w{3}\s\d{4}\s+(\w+)", text_all)
            final_customer = m.group(1) if m else ""

            
            # Create a separate entry for THIS PDF (no grouping)
            report_entry = {
                "Inspection Date": inspection_date,
                "Style": style,
                "Description": description,
                "Sample Size": inspected_qty,
                "PO Qty": po_qty,
                "Actual Qty": actual_qty,
                "Inspected Qty": inspected_qty,
                "Major Defect": major_defect,
                "Minor Defect": minor_defect,
                "FactoryCode": factory_code,
                "Factory": factory,
                "Final Customer": final_customer,
                "POs": sorted(pos)  # Keep as list, not set
            }
            
            all_reports.append(report_entry)

            processed_files.append({
                'file': pdf_file,
                'style': style,
                'description': description,
                'inspection_date': inspection_date,
                'po_qty': po_qty,
                'actual_qty': actual_qty,
                'inspected_qty': inspected_qty,
                'factory_code': factory_code,
                'factory': factory,
                'final_customer': final_customer,
                'pos': sorted(pos)
            })

            logging.info(f"{pdf_file.name} | OK | Style={style} | POs={','.join(pos)}")

        except Exception as e:
            logging.error(f"{pdf_file.name} | FAILED | {str(e)}")
    return all_reports, processed_files

# ---------------- BUILD DATAFRAMES ----------------
def build_tables(all_reports):
    detail_rows = []
    summary_rows = []

    for report in all_reports:
        po_list = report["POs"]
        style_po = f"{report['Style']}({','.join(po_list)})"

        # Detailed
        detail_data = {
            "Sample Size": report["Sample Size"],
            " ": "",
            "Description": report["Description"],
            "Inspection Date": report["Inspection Date"],
            "Style": report["Style"],
            "  ": "",
            "   ": "",
            "    ": "",
            "     ": "",
        }
        # Add each PO to its own column
        for i, po in enumerate(po_list):
            detail_data[f"PO_{i+1}"] = po
        detail_rows.append(detail_data)

        # Summary
        summary_rows.append({
            "Style No with PO": style_po,
            "PO Qty": report["PO Qty"],
            "Actual Qty": report["Actual Qty"],
            "Inspected Qty": report["Inspected Qty"],
            "Major Defect": report["Major Defect"],
            "Minor Defect": report["Minor Defect"]
        })

    return (
        pd.DataFrame(detail_rows),
        pd.DataFrame(summary_rows)
    )

# -------- REPLACE TEXT IN DOCUMENT (INCLUDING TABLES & HEADERS/FOOTERS) --------
def replace_text_in_document(doc, replacements, pos_list=None):
    """Replace placeholders in document while preserving formatting"""
    
    # CRITICAL: Use a mutable object to track PO index across ALL paragraphs
    po_state = {'index': 0}  # This persists across all function calls
    
    def replace_in_paragraph(para, replacements, pos_list=None, po_state=None):
        """Replace text in a single paragraph, handling split runs and preserving formatting"""
        # Get full paragraph text
        full_text = ''.join([run.text for run in para.runs])
        
        # Check if any replacement is needed
        needs_replacement = any(key in full_text for key in replacements.keys())
        needs_po_replacement = pos_list and '{{Po}}' in full_text
        
        if not (needs_replacement or needs_po_replacement):
            return
        
        # Do replacements on full text (except {{Po}})
        for key, value in replacements.items():
            if key != '{{Po}}':
                full_text = full_text.replace(key, str(value))
        
        # Handle multiple {{Po}} replacements using GLOBAL counter
        if pos_list and po_state is not None:
            # Count how many {{Po}} are in THIS paragraph
            po_count = full_text.count('{{Po}}')
            
            # Replace each {{Po}} with next available PO from global list
            for _ in range(po_count):
                if po_state['index'] < len(pos_list):
                    current_po = str(pos_list[po_state['index']])
                    full_text = full_text.replace('{{Po}}', current_po, 1)
                    logging.info(f"Replaced {{{{Po}}}} with {current_po} (PO #{po_state['index'] + 1})")
                    po_state['index'] += 1
                else:
                    # No more POs available, remove remaining placeholders
                    full_text = full_text.replace('{{Po}}', '')
                    logging.warning("Ran out of POs, removing remaining {{Po}} placeholders")
        
        # Preserve formatting by keeping the first run's properties
        if para.runs:
            first_run = para.runs[0]
            # Store original formatting
            original_bold = first_run.bold
            original_italic = first_run.italic
            original_underline = first_run.underline
            original_font_name = first_run.font.name
            original_font_size = first_run.font.size
            original_font_color = first_run.font.color.rgb if first_run.font.color.rgb else None
            
            # Clear all runs except the first one
            for run in para.runs[1:]:
                r = run._element
                r.getparent().remove(r)
            
            # Update the first run with replaced text
            para.runs[0].text = full_text
            
            # Restore original formatting
            para.runs[0].bold = original_bold
            para.runs[0].italic = original_italic
            para.runs[0].underline = original_underline
            if original_font_name:
                para.runs[0].font.name = original_font_name
            if original_font_size:
                para.runs[0].font.size = original_font_size
            if original_font_color:
                para.runs[0].font.color.rgb = original_font_color
        else:
            para.add_run(full_text)
    
    # Log start of replacement
    if pos_list:
        logging.info(f"Starting document replacement with {len(pos_list)} POs: {pos_list}")
    
    # Replace in paragraphs
    try:
        for para in doc.paragraphs:
            replace_in_paragraph(para, replacements, pos_list, po_state)
    except Exception as e:
        logging.error(f"Error replacing in paragraphs: {str(e)}")
    
    # Replace in tables
    try:
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        replace_in_paragraph(para, replacements, pos_list, po_state)
    except Exception as e:
        logging.error(f"Error replacing in tables: {str(e)}")
    
    # Replace in headers and footers
    try:
        for section in doc.sections:
            for para in section.header.paragraphs:
                replace_in_paragraph(para, replacements, pos_list, po_state)
            
            for para in section.footer.paragraphs:
                replace_in_paragraph(para, replacements, pos_list, po_state)
    except Exception as e:
        logging.error(f"Error replacing in headers/footers: {str(e)}")
    
    # Log final summary
    if pos_list:
        logging.info(f"Replacement complete: Used {po_state['index']} out of {len(pos_list)} POs")
        if po_state['index'] < len(pos_list):
            unused = pos_list[po_state['index']:]
            logging.warning(f"Unused POs: {unused}")

# ---------------- GUI ACTION ----------------
def run_process():
    folder = filedialog.askdirectory(title="Select PDF Folder")
    if not folder:
        return

    grouped, processed_files = extract_reports(folder)
    report_count = len(grouped)

    factory_code = next(
        (r["FactoryCode"] for r in grouped if r.get("FactoryCode")),
        "Unknown_Factory"
    )

    # Make filename safe
    factory_code = re.sub(r'[\\/:*?"<>|]', '_', factory_code)

    if not grouped:
        messagebox.showerror("Error", "No data extracted. Check logs.")
        return

    detail_df, summary_df = build_tables(grouped)

    output_excel_path = OUTPUT_ROOT / f"AQL_Inspection_Report_{factory_code}_{report_count}_report.xlsx"

    with pd.ExcelWriter(output_excel_path, engine="openpyxl") as writer:
        detail_df.to_excel(writer, sheet_name="Detail", index=False)
        summary_df.to_excel(writer, sheet_name="AQL Summary", index=False)

    # Rename PDFs
    for item in processed_files:
        old_path = item['file']

        # Build CLEAN base filename (no inherited _1)
        new_name = (
            f"Apparel Report_{item['style']} {item['factory_code']}, "
            f"Puma Warehouse WH AQL, PO {item['pos'][0]}, "
            f"Customer {item['final_customer']}.pdf"
        )

        # Safety: strip any trailing _<number> just in case
        new_name = re.sub(r'_\d+(?=\.pdf$)', '', new_name)

        new_path = OUTPUT_ROOT / new_name

        # Handle duplicates ONLY in output folder
        if new_path.exists():
            counter = 1
            while True:
                candidate = OUTPUT_ROOT / f"{new_path.stem}_{counter}{new_path.suffix}"
                if not candidate.exists():
                    new_path = candidate
                    break
                counter += 1

        try:
            shutil.copy2(old_path, new_path)
            logging.info(f"Copied {old_path.name} → {new_path.name}")
        except Exception as e:
            logging.error(f"Failed to copy {old_path.name}: {str(e)}")

    # Create CERTIFICATES folder if it doesn't exist
    cert_folder = OUTPUT_ROOT / "CERTIFICATES_OUTPUT"
    cert_folder.mkdir(exist_ok=True)

    # Generate DOCX certificates - Check multiple locations for template
    template_path = os.path.join(folder, "CERTIFICATE", "CERTIFICATE.docx")
    
    # If not found in folder, check in script directory
    if not os.path.exists(template_path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(script_dir, "CERTIFICATE", "CERTIFICATE.docx")
    
    # If still not found, check parent directory
    if not os.path.exists(template_path):
        template_path = os.path.join(os.path.dirname(folder), "CERTIFICATE", "CERTIFICATE.docx")
    
    logging.info(f"Looking for template at: {template_path}")
    logging.info(f"Template exists: {os.path.exists(template_path)}")
    logging.info(f"Processed files count: {len(processed_files)}")
    
    if os.path.exists(template_path):
        logging.info(f"Template found: {template_path}")
        logging.info(f"Certificate output folder: {cert_folder}")
        
        for item in processed_files:
            try:
                # Load fresh template for each item
                doc = Document(template_path)
                logging.info(f"Processing certificate for style: {item['style']}")
                
                # Create replacement dictionary
                #replacements = {
                #    '{{Style}}': underline_fill(item['style'], 25),
                #    '{{Date}}': underline_fill(item['inspection_date'], 15),
                #    '{{Sample_size}}': underline_fill(item['inspected_qty'], 10),
                #    '{{Po_Qty}}': underline_fill(item['po_qty'], 10),
                #    '{{Actual_Qty}}': underline_fill(item['actual_qty'], 10),
                #}
                replacements = {
                    '{{Style}}': item['style'],
                    '{{Date}}': item['inspection_date'],
                    '{{Date_Current}}': datetime.now().strftime('%Y-%m-%d'),
                    '{{Po_Qty}}': str(item['po_qty']),
                    '{{Factory}}': item['factory'],
                    '{{Actual_Qty}}': str(item['actual_qty']),
                    '{{Sample_size}}': str(item.get('inspected_qty')),
                    # '{{Description}}': item['description'],
                    # '{{Final_Customer}}': item['final_customer']
                }
                
                logging.info(f"Replacements: {replacements}")
                logging.info(f"POs to replace: {item['pos']}")
                
                # Replace text in all document parts (pass pos_list for multiple POs)
                replace_text_in_document(doc, replacements, item['pos'])
                
                # Save to the output folder with unique name
                cert_filename = f"{datetime.now().strftime('%Y-%m-%d')} {item['style']}({','.join(item['pos'])}) {item['factory']}.docx"
                output_docx = os.path.join(cert_folder, cert_filename)
                
                # Handle duplicates
                counter = 1
                base_output_docx = output_docx
                while os.path.exists(output_docx):
                    stem = Path(base_output_docx).stem
                    output_docx = os.path.join(cert_folder, f"{stem}_{counter}.docx")
                    counter += 1
                
                logging.info(f"Saving certificate to: {output_docx}")
                doc.save(output_docx)
                logging.info(f"✓ Generated certificate: {output_docx}")
                
            except Exception as e:
                logging.error(f"✗ Failed to generate certificate for {item['style']}: {str(e)}", exc_info=True)
    else:
        logging.warning(f"Template not found: {template_path}")

    messagebox.showinfo(
        "Success",
        f"Report generated successfully.\n\n"
        f"📁 Output folder:\n{OUTPUT_ROOT}\n\n"
        "• AQL_Inspection_Report.xlsx\n"
        "• AQL_Inspection_Summary.csv\n"
        "• DOCX certificates (CERTIFICATES_OUTPUT)\n"
        "• PDFs renamed/copied"
    )

def underline_fill(value, width=30):
    value = str(value)
    return value + "_" * max(0, width - len(value))

def remove_trailing_counter(filename: str) -> str:
    """
    Removes trailing _<number> before .pdf
    Example: file_1.pdf -> file.pdf
    """
    return re.sub(r'_\d+(?=\.pdf$)', '', filename, flags=re.IGNORECASE)

# ---------------- CLEAR CACHE & MEMORY ----------------
def clear_cache():
    try:
        if not messagebox.askyesno(
            "Confirm Reset",
            "This will DELETE all files in the output folder.\n\nContinue?"
        ):
            return

        # 1️⃣ Clear runtime memory
        for var in [
            'grouped',
            'processed_files',
            'detail_df',
            'summary_df'
        ]:
            if var in globals():
                globals()[var] = None

        gc.collect()

        # 2️⃣ Clear OUTPUT folder (THIS resets file counters)
        if OUTPUT_ROOT.exists():
            for item in OUTPUT_ROOT.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)

        # 3️⃣ Clear log file
        log_file = PROJECT_ROOT / "pdf_process.log"
        if log_file.exists():
            log_file.write_text("")

        messagebox.showinfo(
            "Cache Cleared",
            "✔ Memory cleared\n"
            "✔ Output folder cleaned\n"
            "✔ File counter reset\n"
            "✔ Logs cleared"
        )

    except Exception as e:
        messagebox.showerror(
            "Error",
            f"Failed to clear cache:\n{str(e)}"
        )

# ---------------- GUI ----------------
root = Tk()
root.title("Puma AQL Inspection Report Tool")
root.geometry("450x290")
root.resizable(False, False)

Label(root, text="Puma AQL Inspection Report Tool", font=("Arial", 12, "bold")).pack(pady=15)

Button(
    root,
    text="Select PDF Folder & Generate Report",
    width=42,
    height=2,
    command=run_process
).pack(pady=20)

Button(
    root,
    text="Clear Cache / Memory",
    width=42,
    height=2,
    bg="#d9534f",
    fg="white",
    command=clear_cache
).pack(pady=10)

Label(
    root,
    text="• Summary matches official AQL format\n• Sample Size from TOTAL row\n• Logs: pdf_process.log\n• PDFs renamed after processing\n• Certificates in CERTIFICATES_OUTPUT folder",
    font=("Arial", 9),
    justify="center"
).pack()

root.mainloop()
