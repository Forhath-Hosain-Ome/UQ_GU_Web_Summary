import os
import subprocess


def convert_docx_to_pdf(docx_path, pdf_path):
    subprocess.run(['libreoffice', '--headless', '--convert-to', 'pdf', '--outdir', os.path.dirname(pdf_path), docx_path])
    # The output PDF will be in the same directory with same basename
    generated_pdf = os.path.splitext(docx_path)[0] + '.pdf'
    if os.path.exists(generated_pdf):
        shutil.move(generated_pdf, pdf_path)