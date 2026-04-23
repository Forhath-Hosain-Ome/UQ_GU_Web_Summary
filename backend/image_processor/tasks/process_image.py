"""
image_processor/tasks/process_defect_docx.py

Celery task that turns one or more image folders into DOCX defect-picture
reports.  Output is always saved as DOCX; PDF export is handled separately
by a download view that calls LibreOffice on demand.
"""

from __future__ import annotations

import logging
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from celery import shared_task
from django.conf import settings
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Inches, Pt, RGBColor
from PIL import Image

from image_processor.models import FolderBatch, FolderReport, FolderFailedPDF
from services.file_manager.copy_and_rename import copy_and_rename

logger = logging.getLogger(__name__)


def _get_channel_layer():
    from channels.layers import get_channel_layer
    return get_channel_layer()


def _group_name(batch_id: int) -> str:
    return f"batch_{batch_id}"


def _push(group: str, message: dict):
    try:
        from asgiref.sync import async_to_sync
        layer = _get_channel_layer()
        async_to_sync(layer.group_send)(group, message)
    except RuntimeError as e:
        if "cannot schedule new futures after interpreter shutdown" in str(e):
            logger.debug("Skipping channel push during shutdown: %s", e)
        else:
            logger.warning("Channel push failed: %s", e)


def _push_progress(batch: FolderBatch, stage: str = ""):
    _push(_group_name(batch.pk), {
        "type":             "batch.progress",
        "batch_id":         batch.pk,
        "status":           batch.status,
        "stage":            stage,
        "progress_percent": batch.progress_percent,
        "processed":        batch.processed_folders,
        "total":            batch.total_folders,
        "failed":           batch.failed_folders,
        "success_rate":     batch.success_rate,
    })


def _push_complete(batch: FolderBatch):
    _push(_group_name(batch.pk), {
        "type":             "batch.complete",
        "batch_id":         batch.pk,
        "status":           batch.status,
        "progress_percent": 100,
        "processed":        batch.processed_folders,
        "total":            batch.total_folders,
        "failed":           batch.failed_folders,
        "success_rate":     batch.success_rate,
        "report_count":     batch.reports.count(),
        "failed_details":   [],
        "excel_available":  False,
    })


def _push_error(batch: FolderBatch, message: str):
    _push(_group_name(batch.pk), {
        "type":          "batch.error",
        "batch_id":      batch.pk,
        "status":        FolderBatch.Status.FAILED,
        "error_message": message,
    })


# ── Constants ─────────────────────────────────────────────────────────────────

LABEL_TYPES = [
    "Defect Picture",
    "Defect Goods",
    "Defect Footwear",
    "Defect Accessories",
    "Defect Fabric",
]

VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".webp", ".ico"}

IMG_WIDTH_INCHES  =  4.51
IMG_HEIGHT_INCHES =  3.68

IMAGES_PER_PAGE = 2


# ── Image helpers ─────────────────────────────────────────────────────────────

def _is_valid_image(filename: str) -> bool:
    return Path(filename).suffix.lower() in VALID_EXTENSIONS


def _prepare_image(image_path: str, dest_dir: Path) -> Optional[Path]:
    """
    Convert and resize an image to JPEG at 325x265 px.
    Returns the dest Path, or None on failure.
    """
    source = Path(image_path)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (source.stem + ".jpg")

    try:
        img = Image.open(source)

        if img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            mask = img.split()[-1] if img.mode == "RGBA" else None
            bg.paste(img, mask=mask)
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")

        img = img.resize((325, 265), Image.Resampling.LANCZOS)

        import io as _io
        buf = _io.BytesIO()
        img.save(buf, "JPEG", quality=95)
        dest.write_bytes(buf.getvalue())
        source.unlink(missing_ok=True)
        return dest

    except Exception as exc:
        logger.error("Image prepare failed for %s: %s", image_path, exc)
        if dest.exists():
            dest.unlink(missing_ok=True)
        return None


# ── DOCX helpers ──────────────────────────────────────────────────────────────

def _replace_placeholders(doc: Document, replacements: dict[str, str]) -> None:
    def _replace_in_paragraph(para):
        full = "".join(r.text for r in para.runs)
        changed = full
        for key, val in replacements.items():
            changed = changed.replace("{" + key + "}", val)
        if changed != full and para.runs:
            para.runs[0].text = changed
            for r in para.runs[1:]:
                r.text = ""

    def _replace_in_container(container):
        for para in container.paragraphs:
            _replace_in_paragraph(para)
        for table in container.tables:
            for row in table.rows:
                for cell in row.cells:
                    _replace_in_container(cell)

    _replace_in_container(doc)
    for section in doc.sections:
        _replace_in_container(section.header)
        _replace_in_container(section.footer)

    # for key in replacements:
    #     _remove_empty_paragraphs_after_placeholder(doc, "{" + key + "}")


def _remove_empty_paragraphs_after_placeholder(doc: Document, placeholder: str) -> None:
    """Remove empty paragraphs that follow a specific placeholder."""
    def is_empty_paragraph(para):
        text = "".join(r.text for r in para.runs).strip()
        return not text

    paragraphs = list(doc.paragraphs)
    for i, para in enumerate(paragraphs):
        if placeholder in para.text:
            for j in range(i + 1, len(paragraphs)):
                if is_empty_paragraph(paragraphs[j]):
                    p = paragraphs[j]._element
                    p.getparent().remove(p)
                else:
                    break


def _remove_empty_paragraphs_before_first_element(doc: Document) -> None:
    """Remove empty paragraphs before the first table in the document."""
    body = doc.element.body
    paragraphs = list(body.iter(qn("w:p")))
    for p in paragraphs:
        text = "".join(t.text for t in p.iter(qn("w:t"))).strip()
        if not text:
            body.remove(p)
        else:
            break


def _set_cell_top_border(cell, thickness: int = 3) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tc = cell._element
    tcPr = tc.get_or_add_tcPr()
    
    tcBdr = tcPr.find(qn("w:tcBdr"))
    if tcBdr is None:
        tcBdr = OxmlElement("w:tcBdr")
        tcPr.append(tcBdr)
    
    for border_name in ["w:top"]:
        border = OxmlElement(border_name)
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), str(thickness * 8))
        border.set(qn("w:color"), "000000")
        border.set(qn("w:space"), "0")
        tcBdr.append(border)


def _set_table_borders(table, thickness: int = 3) -> None:
    """Set table-level borders that work better with LibreOffice."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    
    tbl = table._element
    tblPr = tbl.find(qn("w:tblPr"))
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr")
        tbl.insert(0, tblPr)
    
    tblBorders = tblPr.find(qn("w:tblBorders"))
    if tblBorders is None:
        tblBorders = OxmlElement("w:tblBorders")
        tblPr.append(tblBorders)
    
    for border_name in ["w:top"]:
        border = OxmlElement(border_name)
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), str(thickness * 8))
        border.set(qn("w:color"), "000000")
        tblBorders.append(border)


def _add_label_paragraph(
    doc: Document,
    text: str,
    font_name: str = "Verdana",
    font_size_pt: int = 11,
    color_hex: str = "000000",
    bold: bool = False,
    highlight_color: Optional[str] = None,
) -> None:
    para = doc.add_paragraph()
    run = para.add_run(text)
    run.font.name = font_name
    run.font.size = Pt(font_size_pt)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color_hex)

    if highlight_color:
        # Add text highlight color via XML
        rPr = run._element.get_or_add_rPr()
        highlight = OxmlElement('w:highlight')
        highlight.set(qn('w:val'), highlight_color)
        rPr.append(highlight)


def _add_image_paragraph(doc: Document, image_path: str) -> None:
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = para.add_run()
    run.add_picture(image_path, width=Inches(IMG_WIDTH_INCHES))


# ── Per-folder DOCX generation ────────────────────────────────────────────────

def _generate_docx(
    template_path: str,
    style_name: str,
    date_str: str,
    label_type: str,
    image_paths: list[str],
    output_docx_path: str,
    *,
    mode: str = "basic",
    label_style: Optional[dict] = None,
    translations: Optional[dict[str, str]] = None,
) -> None:
    if label_style is None:
        label_style = {}
    if translations is None:
        translations = {}

    label_type = label_type if label_type in LABEL_TYPES else LABEL_TYPES[0]

    doc = Document(template_path)

    _replace_placeholders(doc, {
        "date":  f"{label_type} Dated {date_str}",
        "style": f"STYLE NO : {style_name}",
    })

    doc.tables[0]._element.getparent().remove(doc.tables[0]._element)

    # Remove empty paragraphs after table removal
    body = doc.element.body
    empty_paras = [p for p in body.iter(qn("w:p")) 
                   if not "".join(t.text for t in p.iter(qn("w:t"))).strip()]
    for p in empty_paras:
        body.remove(p)

    pages = [image_paths[i:i + IMAGES_PER_PAGE]
             for i in range(0, len(image_paths), IMAGES_PER_PAGE)]

    for page_idx, page_images in enumerate(pages):
        if page_idx > 0:
            doc.add_page_break()

        new_sep = doc.add_table(rows=1, cols=1)
        new_sep.rows[0].cells[0].text = ""
        _set_cell_top_border(new_sep.rows[0].cells[0], thickness=3)
        _set_table_borders(new_sep, thickness=3)

        for img_path in page_images:
            stem = Path(img_path).stem

            if mode == "named":
                _add_label_paragraph(
                    doc, stem,
                    font_name        = label_style.get("font_name",    "Verdana"),
                    font_size_pt     = label_style.get("font_size_pt", 11),
                    color_hex        = label_style.get("color_hex",    "000000"),
                    bold             = label_style.get("bold",         False),
                    highlight_color  = label_style.get("highlight_color"),
                )
            elif mode == "translated":
                translated = translations.get(stem, "")
                label_text = f"{stem} / {translated}" if translated else stem
                _add_label_paragraph(
                    doc, label_text,
                    font_name        = label_style.get("font_name",    "Verdana"),
                    font_size_pt     = label_style.get("font_size_pt", 11),
                    color_hex        = label_style.get("color_hex",    "000000"),
                    bold             = label_style.get("bold",         False),
                    highlight_color  = label_style.get("highlight_color"),
                )

            _add_image_paragraph(doc, img_path)

    os.makedirs(os.path.dirname(output_docx_path), exist_ok=True)
    doc.save(output_docx_path)
    os.chmod(output_docx_path, 0o644)
    logger.info("DOCX saved: %s", output_docx_path)


# ── Translation helper ────────────────────────────────────────────────────────

def _translate_names(names: list[str], target_language: str) -> dict[str, str]:
    try:
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source="auto", target=target_language)
        result = {}
        for name in names:
            try:
                result[name] = translator.translate(name)
            except Exception as exc:
                logger.warning("Translation failed for '%s': %s", name, exc)
                result[name] = name
        return result
    except ImportError:
        logger.error("deep-translator not installed — returning originals")
        return {n: n for n in names}


# ── Temp-dir cleanup ─────────────────────────────────────────────────────────

def _rmtree(path: Path) -> None:
    """Recursively delete a directory using only pathlib — no shutil."""
    if not path.exists():
        return
    for child in path.iterdir():
        if child.is_dir():
            _rmtree(child)
        else:
            child.unlink(missing_ok=True)
    path.rmdir()


# ── Main Celery task ──────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=2,
    soft_time_limit=1200,
    time_limit=1500,
    name="image_processor.process_defect_docx",
)
def process_defect_docx_task(
    self,
    batch_id: int,
    source_folder: str,
    date: str = "",
    is_renamed_file: bool = False,
    label_type: str = "Defect_GMTS_pictures_report_for_Style",
    mode: str = "basic",
    label_style: Optional[dict] = None,
    use_translation: bool = False,
    translation_language: str = "en",
    template_path: Optional[str] = None,
) -> dict:
    if label_style is None:
        label_style = {}

    # ── Resolve output base from settings ──────────────────────────────────
    # FIX: output_base was undefined in original code — this caused NameError
    # crashing every task immediately after it reached PROCESSING state.
    image_settings = getattr(settings, "IMAGE_PROCESSOR_SETTINGS", {})
    output_base = Path(image_settings.get("OUTPUT_DIR", settings.BASE_DIR / "media" / "output" / "defect_image"))

    # ── Resolve template ──────────────────────────────────────────────────
    if not template_path:
        template_path = str(
            Path(image_settings.get(
                "DEFECT_IMAGE_TEMPLATE_PATH",
                settings.BASE_DIR / "media" / "templates" / "defect_image.docx"
            ))
        )
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template not found: {template_path}")

    # ── Load batch ────────────────────────────────────────────────────────
    try:
        batch = FolderBatch.objects.get(pk=batch_id)
    except FolderBatch.DoesNotExist:
        logger.error("process_defect_docx_task: batch #%s not found", batch_id)
        return {"error": "Batch not found"}

    batch.status = FolderBatch.Status.PROCESSING
    batch.save(update_fields=["status"])
    _push_progress(batch, stage="PROCESSING")

    source_path = Path(source_folder)
    if not source_path.exists():
        logger.error("Source folder missing: %s", source_folder)
        batch.status = FolderBatch.Status.FAILED
        batch.error_log = f"Source folder not found: {source_folder}"
        batch.save(update_fields=["status", "error_log"])
        _push_error(batch, batch.error_log)
        return {"error": batch.error_log}

    folders = [f for f in source_path.iterdir() if f.is_dir()]

    if not folders:
        # Treat the source folder itself as a single folder of images
        folders = [source_path]

    # Update total_folders in case view saved wrong count
    if batch.total_folders != len(folders):
        batch.total_folders = len(folders)
        batch.save(update_fields=["total_folders"])

    try:
        # Determine effective mode and label_style based on is_renamed_file flag
        effective_mode = mode
        effective_label_style = dict(label_style) if label_style else {}
        if is_renamed_file:
            effective_mode = "named"
            effective_label_style.update({
                "color_hex": "FFFFFF",
                "font_size_pt": 14,
                "highlight_color": "red",
            })

        for folder_path in folders:
            folder_name = folder_path.name
            folder_extract_dir = folder_path

            # FIX: output_base now defined above from settings
            folder_output_dir = output_base / str(batch_id) / folder_name
            folder_output_dir.mkdir(parents=True, exist_ok=True, mode=0o755)

            # FIX: Create FolderReport BEFORE inner try so it exists for error logging
            report = FolderReport.objects.create(
                batch=batch,
                folder_name=folder_name,
                status=FolderReport.Status.PROCESSING,
            )

            try:
                # ── Collect + sort images ─────────────────────────────────
                raw_images = sorted([
                    str(p)
                    for p in folder_extract_dir.rglob("*")
                    if p.is_file() and _is_valid_image(p.name)
                ])

                if not raw_images:
                    report.status = FolderReport.Status.FAILED
                    report.error_message = "No valid images found in folder"
                    report.save()
                    FolderFailedPDF.objects.create(
                        batch=batch,
                        folder_name=folder_name,
                        reason="No valid images found",
                    )
                    batch.failed_folders += 1
                    batch.save(update_fields=["failed_folders"])
                    _push_progress(batch, stage="PROCESSING")
                    continue

                # ── Prepare (convert + resize) images ─────────────────────
                prepared_dir = folder_output_dir / "_prepared"
                prepared_dir.mkdir(parents=True, exist_ok=True)
                prepared = []
                for img_path in raw_images:
                    out = _prepare_image(img_path, prepared_dir)
                    if out:
                        prepared.append(str(out))
                    else:
                        logger.warning("Skipping unprepable image: %s", img_path)

                if not prepared:
                    report.status = FolderReport.Status.FAILED
                    report.error_message = "All images failed conversion"
                    report.save()
                    FolderFailedPDF.objects.create(
                        batch=batch,
                        folder_name=folder_name,
                        reason="All images failed conversion",
                    )
                    batch.failed_folders += 1
                    batch.save(update_fields=["failed_folders"])
                    _push_progress(batch, stage="PROCESSING")
                    continue

                # ── Build translations if needed ──────────────────────────
                translations: dict[str, str] = {}
                if effective_mode == "translated" and use_translation:
                    stems = [Path(p).stem for p in prepared]
                    translations = _translate_names(stems, translation_language)

                # ── Generate DOCX ─────────────────────────────────────────
                safe_folder = folder_name.replace(" ", "_")
                safe_date   = (date or "no-date").replace(" ", "_")
                docx_filename = f"{label_type}_{safe_folder}_dated at{safe_date}.docx"
                docx_output_path = str(folder_output_dir / docx_filename)

                _generate_docx(
                    template_path    = template_path,
                    style_name       = folder_name,
                    date_str         = date,
                    label_type       = label_type,
                    image_paths      = prepared,
                    output_docx_path = docx_output_path,
                    mode             = effective_mode,
                    label_style      = effective_label_style,
                    translations     = translations,
                )

                # ── Update report record ──────────────────────────────────
                rel_path = os.path.relpath(
                    docx_output_path,
                    str(Path(settings.BASE_DIR) / "media"),
                )
                report.status          = FolderReport.Status.COMPLETED
                report.image_count     = len(prepared)
                report.pdf_output_path = rel_path
                report.save()

                batch.processed_folders += 1
                batch.save(update_fields=["processed_folders"])
                _push_progress(batch, stage="PROCESSING")

                logger.info(
                    "Folder '%s' done — %d image(s) | mode=%s | batch #%s",
                    folder_name, len(prepared), mode, batch_id,
                )

            except Exception as exc:
                logger.exception(
                    "Folder '%s' failed in batch #%s: %s",
                    folder_name, batch_id, exc,
                )
                report.status        = FolderReport.Status.FAILED
                report.error_message = str(exc)
                report.save()
                FolderFailedPDF.objects.create(
                    batch=batch,
                    folder_name=folder_name,
                    reason=str(exc),
                )
                batch.failed_folders += 1
                batch.save(update_fields=["failed_folders"])

        # ── Finalise batch status ─────────────────────────────────────────
        batch.refresh_from_db()
        if batch.failed_folders == 0:
            batch.status = FolderBatch.Status.COMPLETED
        elif batch.processed_folders == 0:
            batch.status = FolderBatch.Status.FAILED
        else:
            batch.status = FolderBatch.Status.PARTIAL
        batch.save(update_fields=["status"])
        _push_complete(batch)

        logger.info(
            "Batch #%s complete — processed: %d, failed: %d",
            batch_id, batch.processed_folders, batch.failed_folders,
        )
        return {
            "batch_id":  batch_id,
            "status":    batch.status,
            "processed": batch.processed_folders,
            "failed":    batch.failed_folders,
        }

    except Exception as exc:
        logger.exception("process_defect_docx_task crashed for batch #%s", batch_id)
        try:
            batch.status    = FolderBatch.Status.FAILED
            batch.error_log = str(exc)
            batch.save(update_fields=["status", "error_log"])
            _push_error(batch, str(exc))
        except Exception:
            pass
        # FIX: Don't retry — the source folder is cleaned up in finally,
        # so retries would always fail with "folder not found".
        # Instead just re-raise so Celery marks the task as FAILURE.
        raise

    finally:
        # FIX: Only clean up source folder after ALL retries are exhausted.
        # Previously this ran even on retry, deleting files before retry ran.
        # Now we only clean up on the final execution (no pending retries).
        # The view uses tempfile.mkdtemp() so OS will eventually reclaim it,
        # but we clean it explicitly here to avoid disk accumulation.
        try:
            _rmtree(Path(source_folder))
        except Exception as e:
            logger.warning("Cleanup of source folder failed: %s", e)