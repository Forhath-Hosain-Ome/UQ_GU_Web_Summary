def replace_text(text, replacements, po_state=None):
    for key, value in replacements.items():
        if key != "{{Po}}":
            text = text.replace(key, str(value))

    if po_state:
        while "{{Po}}" in text:
            text = text.replace("{{Po}}", po_state.next(), 1)

    return text