"""Render the full bank (no tailoring) to a sample PDF for manual review.

Same input as scripts/render_sample.py; additionally converts through
jobengine.resume.pdf.render_pdf (real LibreOffice headless, not mocked) so
there is something real to open and eyeball. Requires soffice on PATH.
"""

from pathlib import Path

from jobengine.resume.bank import load_bank
from jobengine.resume.pdf import render_pdf
from jobengine.resume.render import RenderProfile, load_identity, render

OUTPUT_DIR = Path("resume/rendered/preview")
DOCX_PATH = OUTPUT_DIR / "sample.docx"


def main() -> None:
    bank = load_bank()
    identity = load_identity()
    profile = RenderProfile(
        section_order=["education", "work_history", "projects", "publications"],
        include_summary=False,
    )
    doc = render(bank, identity, profile)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    doc.save(DOCX_PATH)
    print(f"Wrote {DOCX_PATH}")

    pdf_path = render_pdf(DOCX_PATH, OUTPUT_DIR)
    print(f"Wrote {pdf_path}")


if __name__ == "__main__":
    main()
