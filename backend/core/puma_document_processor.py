from .puma_paragraph_handler import update_paragraph
from .puma_postate import POState

def replace_text_in_document(doc, replacements, pos_list=None):
    po_state = POState(pos_list)

    # paragraphs
    for para in doc.paragraphs:
        update_paragraph(para, replacements, po_state)

    # tables
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    update_paragraph(para, replacements, po_state)

    # headers & footers
    for section in doc.sections:
        for para in section.header.paragraphs:
            update_paragraph(para, replacements, po_state)

        for para in section.footer.paragraphs:
            update_paragraph(para, replacements, po_state)