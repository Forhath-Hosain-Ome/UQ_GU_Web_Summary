def update_paragraph(para, replacements, po_state=None):
    full_text = ''.join(run.text for run in para.runs)

    if not any(k in full_text for k in replacements.keys()) and "{{Po}}" not in full_text:
        return

    new_text = replace_text(full_text, replacements, po_state)

    if para.runs:
        para.runs[0].text = new_text

        for run in para.runs[1:]:
            r = run._element
            r.getparent().remove(r)
    else:
        para.add_run(new_text)