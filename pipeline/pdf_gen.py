"""PDF generation — two strategies:

1. Primary:  LibreOffice headless converts a tailored .docx → PDF
             (preserves exact formatting from the Word template)
2. Fallback: ReportLab builds a simple PDF from plain text
             (used when LibreOffice is not installed or conversion fails)
"""

import asyncio
import logging
import platform
import shutil
from functools import partial
from pathlib import Path

import config

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"

# Known LibreOffice paths per platform
_SOFFICE_PATHS = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/usr/bin/soffice",
    "/usr/bin/libreoffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
]


def _find_soffice() -> str | None:
    """Return the soffice binary path, or None if not installed."""
    # Check if it's on PATH first
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    for candidate in _SOFFICE_PATHS:
        if Path(candidate).exists():
            return candidate
    return None


async def convert_docx_to_pdf(docx_path: Path) -> Path | None:
    """Convert a .docx to PDF via LibreOffice headless.

    Returns the PDF path on success, or None on failure.
    """
    soffice = _find_soffice()
    if soffice is None:
        logger.error(
            "LibreOffice not found. Install it from https://www.libreoffice.org/ "
            "for high-fidelity PDF conversion. Falling back to ReportLab."
        )
        return None

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        soffice,
        "--headless",
        "--convert-to", "pdf",
        "--outdir", str(OUTPUT_DIR),
        str(docx_path),
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=config.LIBREOFFICE_TIMEOUT)

        if proc.returncode != 0:
            logger.error(
                "LibreOffice conversion failed (exit %d): %s",
                proc.returncode,
                stderr.decode().strip(),
            )
            return None

        # LibreOffice outputs PDF with same stem into --outdir
        raw_pdf = OUTPUT_DIR / f"{docx_path.stem}.pdf"
        # Rename to drop the "_tailored" suffix → {company}_{job_id}.pdf
        clean_name = docx_path.stem.replace("_tailored", "") + ".pdf"
        pdf_path = OUTPUT_DIR / clean_name
        if raw_pdf.exists():
            raw_pdf.replace(pdf_path)  # .replace() overwrites on Windows
            logger.info("LibreOffice PDF saved: %s", pdf_path.name)
            return pdf_path

        logger.error("LibreOffice ran but PDF not found at %s", pdf_path)
        return None

    except asyncio.TimeoutError:
        logger.error("LibreOffice conversion timed out after 60s")
        return None
    except Exception:
        logger.exception("LibreOffice conversion error")
        return None


# ---------------------------------------------------------------------------
# ReportLab fallback
# ---------------------------------------------------------------------------

def _generate_pdf_reportlab(tailored_resume: str, filepath: Path) -> None:
    """CPU-bound fallback PDF generation via ReportLab."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("ResumeBody", parent=styles["Normal"], fontSize=11, leading=14, spaceAfter=4))
    styles.add(ParagraphStyle("ResumeHeading", parent=styles["Heading2"], fontSize=12, leading=15, spaceAfter=4, spaceBefore=10))

    def escape(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    doc = SimpleDocTemplate(
        str(filepath), pagesize=LETTER,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
    )

    story = []
    for line in tailored_resume.split("\n"):
        stripped = line.strip()
        if not stripped:
            story.append(Spacer(1, 6))
            continue
        upper = stripped.upper()
        if (stripped == upper and len(stripped) > 2 and stripped.replace(" ", "").isalpha()) or \
           (stripped.endswith(":") and len(stripped.split()) <= 4):
            story.append(Paragraph(escape(stripped), styles["ResumeHeading"]))
        else:
            story.append(Paragraph(escape(stripped), styles["ResumeBody"]))

    doc.build(story)


async def generate_pdf_fallback(tailored_resume: str, company_slug: str, job_id: str) -> Path:
    """Fallback: generate PDF from plain text via ReportLab."""
    filename = f"{company_slug}_{job_id}.pdf"
    filepath = OUTPUT_DIR / filename

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, partial(_generate_pdf_reportlab, tailored_resume, filepath))

    logger.info("Fallback PDF (ReportLab) saved to %s", filepath)
    return filepath
