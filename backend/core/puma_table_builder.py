import pandas as pd

def build_tables(all_reports):
    detail_rows = []
    summary_rows = []

    for report in all_reports:
        po_list = report.get("POs", [])
        style = report.get("Style", "")

        # ------------------
        # DETAIL TABLE
        # ------------------
        detail_data = {
            "Sample Size": report.get("Sample Size", ""),
            "Description": report.get("Description", ""),
            "Inspection Date": report.get("Inspection Date", ""),
            "Style": style,
        }

        # dynamic PO columns
        for i, po in enumerate(po_list):
            detail_data[f"PO_{i+1}"] = po

        detail_rows.append(detail_data)

        # ------------------
        # SUMMARY TABLE
        # ------------------
        summary_rows.append({
            "Style No with PO": f"{style}({','.join(po_list)})" if po_list else style,
            "PO Qty": report.get("PO Qty", ""),
            "Actual Qty": report.get("Actual Qty", ""),
            "Inspected Qty": report.get("Inspected Qty", ""),
            "Major Defect": report.get("Major Defect", ""),
            "Minor Defect": report.get("Minor Defect", ""),
        })

    return pd.DataFrame(detail_rows), pd.DataFrame(summary_rows)