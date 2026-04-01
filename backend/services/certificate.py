# """
# DOCX certificate generation service.
# Mirrors replace_text_in_document() + certificate loop from original script.
# """
# import logging
# from datetime import datetime
# from pathlib import Path

# from docx import Document

# from shared.exceptions import CertificateGenerationError

# logger = logging.getLogger(__name__)


# def _replace_in_paragraph(para, replacements: dict, pos_list: list, po_state: dict):
#     """Replace template placeholders in a single paragraph, preserving formatting."""
#     full_text = "".join(run.text for run in para.runs)

#     needs_repl = any(k in full_text for k in replacements)
#     needs_po = pos_list and "{{Po}}" in full_text

#     if not (needs_repl or needs_po):
#         return

#     for key, value in replacements.items():
#         if key != "{{Po}}":
#             full_text = full_text.replace(key, str(value))

#     if pos_list:
#         for _ in range(full_text.count("{{Po}}")):
#             if po_state["index"] < len(pos_list):
#                 full_text = full_text.replace("{{Po}}", str(pos_list[po_state["index"]]), 1)
#                 po_state["index"] += 1
#             else:
#                 full_text = full_text.replace("{{Po}}", "")

#     if para.runs:
#         first = para.runs[0]
#         # Snapshot formatting
#         fmt = {
#             "bold": first.bold,
#             "italic": first.italic,
#             "underline": first.underline,
#             "font_name": first.font.name,
#             "font_size": first.font.size,
#         }
#         try:
#             color = first.font.color.rgb
#         except Exception:
#             color = None

#         # Clear all but first run
#         for run in para.runs[1:]:
#             run._element.getparent().remove(run._element)

#         para.runs[0].text = full_text
#         para.runs[0].bold = fmt["bold"]
#         para.runs[0].italic = fmt["italic"]
#         para.runs[0].underline = fmt["underline"]
#         if fmt["font_name"]:
#             para.runs[0].font.name = fmt["font_name"]
#         if fmt["font_size"]:
#             para.runs[0].font.size = fmt["font_size"]
#         if color:
#             para.runs[0].font.color.rgb = color
#     else:
#         para.add_run(full_text)


# def _replace_in_document(doc: Document, replacements: dict, pos_list: list):
#     """Apply replacements across paragraphs, tables, headers, footers."""
#     po_state = {"index": 0}

#     for para in doc.paragraphs:
#         _replace_in_paragraph(para, replacements, pos_list, po_state)

#     for table in doc.tables:
#         for row in table.rows:
#             for cell in row.cells:
#                 for para in cell.paragraphs:
#                     _replace_in_paragraph(para, replacements, pos_list, po_state)

#     for section in doc.sections:
#         for para in section.header.paragraphs:
#             _replace_in_paragraph(para, replacements, pos_list, po_state)
#         for para in section.footer.paragraphs:
#             _replace_in_paragraph(para, replacements, pos_list, po_state)


# def generate_certificate(record: dict, template_path: Path, output_dir: Path) -> Path:
#     """
#     Generate one DOCX certificate for a single inspection record.
#     Returns the path of the generated file.
#     Raises CertificateGenerationError on failure.
#     """
#     if not template_path.exists():
#         raise CertificateGenerationError(f"Template not found: {template_path}")

#     output_dir.mkdir(parents=True, exist_ok=True)

#     try:
#         doc = Document(template_path)

#         replacements = {
#             "{{Style}}": record["style"],
#             "{{Date}}": record["inspection_date"],
#             "{{Date_Current}}": datetime.now().strftime("%Y-%m-%d"),
#             "{{Po_Qty}}": str(record["po_qty"]),
#             "{{Factory}}": record["factory_name"],
#             "{{Actual_Qty}}": str(record["actual_qty"]),
#             "{{Sample_size}}": str(record["inspected_qty"]),
#         }

#         _replace_in_document(doc, replacements, record["po_numbers"])

#         po_str = ",".join(record["po_numbers"])
#         # Use inspection_date if available, otherwise fall back to current date
#         date_str = record.get("inspection_date") or datetime.now().strftime("%Y-%m-%d")
#         filename = (
#             f"{date_str} "
#             f"{record['style']}({po_str}) {record['factory_code']}.docx"
#         )
#         output_path = output_dir / filename

#         # Handle duplicate filenames
#         counter = 1
#         base = output_path
#         while output_path.exists():
#             output_path = output_dir / f"{base.stem}_{counter}{base.suffix}"
#             counter += 1

#         doc.save(output_path)
#         logger.info("Certificate saved → %s", output_path.name)
#         return output_path

#     except Exception as exc:
#         raise CertificateGenerationError(
#             f"Failed to generate cert for style {record.get('style')}: {exc}"
#         ) from exc


# def generate_all_certificates(
#     records: list[dict], template_path: Path, output_dir: Path
# ) -> list[Path]:
#     """Generate certificates for all records. Returns list of generated paths."""
#     results = []
#     for record in records:
#         try:
#             path = generate_certificate(record, template_path, output_dir)
#             results.append(path)
#         except CertificateGenerationError as exc:
#             logger.error(exc)
#     return results
"""
DOCX certificate generation service.
Mirrors replace_text_in_document() + certificate loop from original script.
"""
import logging
from datetime import date, datetime
from pathlib import Path

from docx import Document

from shared.exceptions import CertificateGenerationError

logger = logging.getLogger(__name__)


def _replace_in_paragraph(para, replacements: dict, pos_list: list, po_state: dict):
    """Replace template placeholders in a single paragraph, preserving formatting."""
    full_text = "".join(run.text for run in para.runs)

    needs_repl = any(k in full_text for k in replacements)
    needs_po   = pos_list and "{{Po}}" in full_text

    if not (needs_repl or needs_po):
        return

    for key, value in replacements.items():
        if key != "{{Po}}":
            full_text = full_text.replace(key, str(value))

    if pos_list:
        for _ in range(full_text.count("{{Po}}")):
            if po_state["index"] < len(pos_list):
                full_text = full_text.replace("{{Po}}", str(pos_list[po_state["index"]]), 1)
                po_state["index"] += 1
            else:
                full_text = full_text.replace("{{Po}}", "")

    if para.runs:
        first = para.runs[0]
        fmt = {
            "bold":      first.bold,
            "italic":    first.italic,
            "underline": first.underline,
            "font_name": first.font.name,
            "font_size": first.font.size,
        }
        try:
            color = first.font.color.rgb
        except Exception:
            color = None

        for run in para.runs[1:]:
            run._element.getparent().remove(run._element)

        para.runs[0].text      = full_text
        para.runs[0].bold      = fmt["bold"]
        para.runs[0].italic    = fmt["italic"]
        para.runs[0].underline = fmt["underline"]
        if fmt["font_name"]:
            para.runs[0].font.name = fmt["font_name"]
        if fmt["font_size"]:
            para.runs[0].font.size = fmt["font_size"]
        if color:
            para.runs[0].font.color.rgb = color
    else:
        para.add_run(full_text)


def _replace_in_document(doc: Document, replacements: dict, pos_list: list):
    """Apply replacements across paragraphs, tables, headers, footers."""
    po_state = {"index": 0}

    for para in doc.paragraphs:
        _replace_in_paragraph(para, replacements, pos_list, po_state)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    _replace_in_paragraph(para, replacements, pos_list, po_state)

    for section in doc.sections:
        for para in section.header.paragraphs:
            _replace_in_paragraph(para, replacements, pos_list, po_state)
        for para in section.footer.paragraphs:
            _replace_in_paragraph(para, replacements, pos_list, po_state)


def generate_certificate(record: dict, template_path: Path, output_dir: Path) -> Path:
    """
    Generate one DOCX certificate for a single inspection record.

    record must include:
        style, inspection_date, po_qty, actual_qty, inspected_qty,
        factory_name, factory_code, final_customer, po_numbers (list),
        report_date (date | str)  ← used for the filename prefix

    report_date is the fixed date set when the InspectionReport row was
    first created (model default=timezone.localdate). Using it here means
    the certificate filename always reflects when the report was generated,
    not when the DOCX file happens to be produced.

    Returns the path of the generated file.
    Raises CertificateGenerationError on failure.
    """
    if not template_path.exists():
        raise CertificateGenerationError(f"Template not found: {template_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        doc = Document(template_path)

        replacements = {
            "{{Style}}":        record["style"],
            "{{Date}}":         str(record["inspection_date"] or ""),
            "{{Date_Current}}": str(record.get("report_date") or date.today()),
            "{{Po_Qty}}":       str(record["po_qty"]),
            "{{Factory}}":      record["factory_name"],
            "{{Actual_Qty}}":   str(record["actual_qty"]),
            "{{Sample_size}}":  str(record["inspected_qty"]),
        }

        _replace_in_document(doc, replacements, record["po_numbers"])

        # ── Certificate filename ──────────────────────────────────────────
        # Format: "YYYY-MM-DD {style}({po1,po2,...}) {factory_name}.docx"
        # The date prefix comes from report_date (fixed at report creation),
        # NOT from datetime.now() which would change on every download.
        report_date_str = str(record.get("report_date") or date.today())
        po_str          = ",".join(record["po_numbers"])
        filename        = (
            f"{report_date_str} "
            f"{record['style']}({po_str}) "
            f"{record['factory_name']}.docx"
        )
        output_path = output_dir / filename

        # Handle duplicate filenames
        counter = 1
        base    = output_path
        while output_path.exists():
            output_path = output_dir / f"{base.stem}_{counter}{base.suffix}"
            counter += 1

        doc.save(output_path)
        logger.info("Certificate saved → %s", output_path.name)
        return output_path

    except Exception as exc:
        raise CertificateGenerationError(
            f"Failed to generate cert for style {record.get('style')}: {exc}"
        ) from exc


def generate_all_certificates(
    records: list[dict], template_path: Path, output_dir: Path
) -> list[Path]:
    """Generate certificates for all records. Returns list of generated paths."""
    results = []
    for record in records:
        try:
            path = generate_certificate(record, template_path, output_dir)
            results.append(path)
        except CertificateGenerationError as exc:
            logger.error(exc)
    return results