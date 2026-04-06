import os
import subprocess
import shutil


def convert_docx_to_pdf(docx_path, pdf_path):
    env = os.environ.copy()
    env['SAL_USE_VCLPLUGIN'] = 'svp'
    
    subprocess.run([
        'libreoffice', '--headless', '--convert-to', 'pdf',
        '--outdir', os.path.dirname(pdf_path),
        docx_path
    ], env=env)
    
    generated_pdf = os.path.splitext(docx_path)[0] + '.pdf'
    if os.path.exists(generated_pdf) and generated_pdf != pdf_path:
        shutil.move(generated_pdf, pdf_path)