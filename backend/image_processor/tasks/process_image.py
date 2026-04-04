"""
image_processor/tasks/process_defect_docx.py

Celery task that turns one or more image folders into DOCX defect-picture
reports.  Output is always saved as DOCX; PDF export is handled separately
by a download view that calls LibreOffice on demand.

Three generation modes (controlled by the `mode` parameter):
  "basic"      — 2 images per page, no labels, pure template layout
  "named"      — image filename printed above each image with configurable
                 text style (font, size, color)
  "translated" — filename AND its translation printed above each image
                 (defect_name / translated_defect_name), also styled

Label-type dropdown (controls the header line in the document):
  LABEL_TYPES = [
      "Defect Picture",
      "Defect Goods",
      "Defect Footwear",
      "Defect Accessories",
      "Defect Fabric",
  ]
The full header text becomes:  "{label_type} Dated {date}"
Style line becomes:            "STYLE NO : {style}"   (style = folder name)

Image sizing matches the VBA macro:
  width  = 325 px → Inches(3.385)   (325 / 96 dpi)
  height = 265 px → Inches(2.760)   (265 / 96 dpi)
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
from docx.shared import Inches, Pt, RGBColor
from PIL import Image

from image_processor.models import FolderBatch, FolderReport, FolderFailedPDF

# Reuse puma_summary's file-move utility — consistent cross-service behaviour.
# Internally: dest.write_bytes(source.read_bytes()) then source.unlink(). No shutil.
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

# From VBA macro: xShape.Width = 325, xShape.Height = 265  (Word units = px at 96dpi)
IMG_WIDTH_INCHES  = 325 / 96   # ≈ 3.385"
IMG_HEIGHT_INCHES = 265 / 96   # ≈ 2.760"

IMAGES_PER_PAGE = 2


# ── Image helpers ─────────────────────────────────────────────────────────────

def _is_valid_image(filename: str) -> bool:
    return Path(filename).suffix.lower() in VALID_EXTENSIONS


def _prepare_image(image_path: str, dest_dir: Path) -> Optional[Path]:
    """
    Convert and resize an image to JPEG at the macro dimensions (325x265 px).
    Writes the output into dest_dir using Path.write_bytes (no shutil).
    Deletes the source file from temp using Path.unlink after a successful write,
    mirroring the read_bytes / write_bytes / unlink pattern in copy_and_rename.
    Returns the dest Path, or None on failure.
    """
    source = Path(image_path)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (source.stem + ".jpg")

    try:
        img = Image.open(source)

        # Flatten transparency onto a white background
        if img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            mask = img.split()[-1] if img.mode == "RGBA" else None
            bg.paste(img, mask=mask)
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Resize to macro dimensions
        img = img.resize((325, 265), Image.Resampling.LANCZOS)

        # Encode to JPEG bytes in memory, then write with Path.write_bytes
        import io as _io
        buf = _io.BytesIO()
        img.save(buf, "JPEG", quality=95)
        dest.write_bytes(buf.getvalue())

        # Remove the original temp file (matches copy_and_rename's unlink step)
        source.unlink(missing_ok=True)

        return dest

    except Exception as exc:
        logger.error("Image prepare failed for %s: %s", image_path, exc)
        # Clean up partial write if dest was partially created
        if dest.exists():
            dest.unlink(missing_ok=True)
        return None


# ── DOCX helpers ──────────────────────────────────────────────────────────────

def _replace_placeholders(doc: Document, replacements: dict[str, str]) -> None:
    """
    Replace {key} placeholders everywhere in the document:
    headers, footers, body paragraphs, and table cells.
    Preserves existing run formatting by operating run-by-run.
    """
    def _replace_in_paragraph(para):
        # Reconstruct full text, find/replace, then rewrite into runs
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


def _get_separator_table_xml(doc: Document):
    """
    Return a deep copy of the first table in the template (the horizontal rule).
    Raises if template has no table.
    """
    if not doc.tables:
        raise ValueError("Template has no table — cannot use as page separator.")
    import copy
    return copy.deepcopy(doc.tables[0]._element)


def _add_label_paragraph(
    doc: Document,
    text: str,
    font_name: str = "Verdana",
    font_size_pt: int = 11,
    color_hex: str = "000000",
    bold: bool = False,
    alignment=WD_ALIGN_PARAGRAPH.LEFT,
) -> None:
    """Add a styled text paragraph (used for image-name labels)."""
    para = doc.add_paragraph()
    para.alignment = alignment
    run = para.add_run(text)
    run.font.name      = font_name
    run.font.size      = Pt(font_size_pt)
    run.font.bold      = bold
    run.font.color.rgb = RGBColor.from_string(color_hex)


def _add_image_paragraph(doc: Document, image_path: str) -> None:
    """Add a centred paragraph containing a resized inline picture."""
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
    """
    Build a single DOCX for one folder.

    mode="basic":
        2 images per page, no labels above images. Pure template layout.

    mode="named":
        Filename (without extension) printed above each image using label_style.
        label_style keys: font_name, font_size_pt, color_hex, bold

    mode="translated":
        Two lines above each image:
            line 1 → original filename (stem)
            line 2 → translated text from `translations` dict
                     key = filename stem, value = translated string
        Both lines use label_style.

    All modes:
        - template placeholders {date} and {style} are replaced
        - images are paired 2-per-page with the separator table between pages
        - output saved as DOCX (no PDF conversion here)
    """
    if label_style is None:
        label_style = {}
    if translations is None:
        translations = {}

    label_type = label_type if label_type in LABEL_TYPES else LABEL_TYPES[0]

    doc = Document(template_path)

    # 1. Replace header/style placeholders
    _replace_placeholders(doc, {
        "date":  f"{label_type} Dated {date_str}",
        "style": f"STYLE NO : {style_name}",
    })

    # 2. Grab the separator table XML and remove the original from the doc
    sep_table_xml = _get_separator_table_xml(doc)
    doc.tables[0]._element.getparent().remove(doc.tables[0]._element)

    body = doc.element.body

    # 3. Group images into pages of IMAGES_PER_PAGE
    pages = [image_paths[i:i + IMAGES_PER_PAGE]
             for i in range(0, len(image_paths), IMAGES_PER_PAGE)]

    import copy

    for page_idx, page_images in enumerate(pages):
        # Add page break before every page after the first
        if page_idx > 0:
            doc.add_page_break()

        # Add separator table clone
        body.append(copy.deepcopy(sep_table_xml))

        for img_path in page_images:
            stem = Path(img_path).stem

            if mode == "named":
                _add_label_paragraph(
                    doc, stem,
                    font_name    = label_style.get("font_name",    "Verdana"),
                    font_size_pt = label_style.get("font_size_pt", 11),
                    color_hex    = label_style.get("color_hex",    "000000"),
                    bold         = label_style.get("bold",         False),
                )

            elif mode == "translated":
                translated = translations.get(stem, "")
                label_text = f"{stem} / {translated}" if translated else stem
                _add_label_paragraph(
                    doc, label_text,
                    font_name    = label_style.get("font_name",    "Verdana"),
                    font_size_pt = label_style.get("font_size_pt", 11),
                    color_hex    = label_style.get("color_hex",    "000000"),
                    bold         = label_style.get("bold",         False),
                )

            _add_image_paragraph(doc, img_path)

    # 4. Save
    os.makedirs(os.path.dirname(output_docx_path), exist_ok=True)
    doc.save(output_docx_path)
    logger.info("DOCX saved: %s", output_docx_path)


# ── Translation helper ────────────────────────────────────────────────────────

def _translate_names(names: list[str], target_language: str) -> dict[str, str]:
    """
    Translate a list of image stem names using deep-translator.
    Returns dict mapping original → translated.
    Falls back to original name on any error.

    Requires:  pip install deep-translator
    """
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


# ── Temp-dir cleanup (no shutil) ────────────────────────────────────────────

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
    label_type: str = "Defect Picture",
    mode: str = "basic",
    label_style: Optional[dict] = None,
    use_translation: bool = False,
    translation_language: str = "en",
    template_path: Optional[str] = None,
) -> dict:
    """
    Process folders in source_folder into DOCX defect-picture reports.

    Parameters
    ----------
    batch_id : int
        FK to FolderBatch.
    source_folder : str
        Absolute path to directory containing image folders.
    date : str
        Date string from the frontend calendar (e.g. "2026-04-01").
    label_type : str
        One of LABEL_TYPES.  Becomes the header label e.g. "Defect Goods".
    mode : str
        "basic" | "named" | "translated"
    label_style : dict | None
        For named/translated modes.  Keys: font_name, font_size_pt,
        color_hex (hex without #), bold (bool).
    use_translation : bool
        When True and mode=="translated", calls the translation API.
    translation_language : str
        BCP-47 language code for the translation target (e.g. "fr", "de").
    template_path : str | None
        Override the default template location.
    """
    if label_style is None:
        label_style = {}

    # ── Resolve template ──────────────────────────────────────────────────
    if not template_path:
        template_path = str(
            Path(settings.BASE_DIR) / "media" / "templates" / "defect_image.docx"
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

    # Find folders in source_folder
    source_path = Path(source_folder)
    folders = [f for f in source_path.iterdir() if f.is_dir()]

    try:
        for folder_path in folders:
            folder_name = folder_path.name
            folder_extract_dir = folder_path

            # One output dir per folder, namespaced by batch to avoid collisions
            folder_output_dir = output_base / str(batch_id) / folder_name
            folder_output_dir.mkdir(parents=True, exist_ok=True)

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
                # Each image is written to prepared_dir via write_bytes/unlink —
                # the same pattern used by copy_and_rename in puma_summary.
                prepared_dir = Path(temp_dir) / folder_name / "_prepared"
                prepared_dir.mkdir(parents=True, exist_ok=True)
                prepared = []
                for img_path in raw_images:
                    out = _prepare_image(img_path, prepared_dir)
                    if out:
                        prepared.append(out)
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
                if mode == "translated" and use_translation:
                    stems = [
                        Path(p).stem
                        for p in prepared
                    ]
                    translations = _translate_names(stems, translation_language)

                # ── Generate DOCX ─────────────────────────────────────────
                safe_folder = folder_name.replace(" ", "_")
                docx_filename = (
                    f"{label_type}_Dated_{date}_Style_{safe_folder}.docx"
                )
                docx_output_path = str(folder_output_dir / docx_filename)

                _generate_docx(
                    template_path  = template_path,
                    style_name     = folder_name,
                    date_str       = date,
                    label_type     = label_type,
                    image_paths    = prepared,
                    output_docx_path = docx_output_path,
                    mode           = mode,
                    label_style    = label_style,
                    translations   = translations,
                )

                # ── Update report record ──────────────────────────────────
                # pdf_output_path stores the DOCX path (field name is legacy)
                rel_path = os.path.relpath(
                    docx_output_path,
                    str(Path(settings.BASE_DIR) / "media"),
                )
                report.status          = FolderReport.Status.COMPLETED
                report.image_count     = len(prepared)
                report.pdf_output_path = rel_path          # stores DOCX rel path
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
        raise self.retry(exc=exc, countdown=60)

    finally:
        # Clean up source dir using Path.unlink/rmdir — no shutil
        _rmtree(Path(source_folder))