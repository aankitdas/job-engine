"""Docx-to-PDF conversion via LibreOffice headless. See specs/03-renderer.md's
PDF section.

`soffice --headless` is known to hang or fail under concurrent invocations
that share a lock file in the default user profile directory. Every call
gets its own throwaway `-env:UserInstallation` profile dir and a hard
subprocess timeout so a stuck conversion can never wedge the pipeline.
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

_TIMEOUT_SECONDS = 60


class PdfConversionError(Exception):
    """Raised when soffice fails, times out, is missing, or produces no PDF."""


def render_pdf(docx_path: Path, out_dir: Path) -> Path:
    """Convert docx_path to PDF via LibreOffice headless, writing into out_dir.

    Returns the path to the converted PDF (out_dir / f"{docx_path.stem}.pdf").
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    profile_dir = Path(f"/tmp/jobengine-soffice-{uuid.uuid4().hex}")

    cmd = [
        "soffice",
        "--headless",
        "--norestore",
        f"-env:UserInstallation=file://{profile_dir}",
        "--convert-to",
        "pdf",
        "--outdir",
        str(out_dir),
        str(docx_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise PdfConversionError(
            "soffice not found on PATH. Install LibreOffice "
            "(e.g. `sudo apt-get install -y libreoffice-writer`)."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise PdfConversionError(
            f"soffice conversion of {docx_path} timed out after {_TIMEOUT_SECONDS}s"
        ) from exc

    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace") if result.stderr else ""
        raise PdfConversionError(
            f"soffice exited {result.returncode} converting {docx_path}: {stderr}"
        )

    pdf_path = out_dir / f"{docx_path.stem}.pdf"
    if not pdf_path.exists():
        raise PdfConversionError(
            f"soffice reported success but {pdf_path} does not exist"
        )
    return pdf_path
