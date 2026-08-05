"""Tests for jobengine.resume.pdf. See specs/03-renderer.md's PDF section."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from jobengine.resume.pdf import PdfConversionError, render_pdf


def _fake_run_factory(*, returncode: int = 0, create_pdf: bool = True):
    def _fake_run(cmd, *args, **kwargs):
        if create_pdf:
            outdir_index = cmd.index("--outdir") + 1
            outdir = Path(cmd[outdir_index])
            docx_path = Path(cmd[-1])
            (outdir / f"{docx_path.stem}.pdf").write_bytes(b"%PDF-1.4 fake")
        return subprocess.CompletedProcess(cmd, returncode)

    return _fake_run


def test_render_pdf_calls_soffice_headless_convert_to_pdf(tmp_path):
    docx_path = tmp_path / "resume.docx"
    docx_path.write_bytes(b"fake docx")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch("subprocess.run", side_effect=_fake_run_factory()) as mock_run:
        render_pdf(docx_path, out_dir)

    cmd = mock_run.call_args.args[0]
    assert cmd[0] == "soffice"
    assert "--headless" in cmd
    assert "--convert-to" in cmd
    assert cmd[cmd.index("--convert-to") + 1] == "pdf"
    assert "--outdir" in cmd
    assert cmd[cmd.index("--outdir") + 1] == str(out_dir)
    assert cmd[-1] == str(docx_path)


def test_render_pdf_returns_path_to_converted_pdf(tmp_path):
    docx_path = tmp_path / "resume.docx"
    docx_path.write_bytes(b"fake docx")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch("subprocess.run", side_effect=_fake_run_factory()):
        result = render_pdf(docx_path, out_dir)

    assert result == out_dir / "resume.pdf"


def test_render_pdf_uses_unique_userinstallation_profile_per_call(tmp_path):
    docx_path = tmp_path / "resume.docx"
    docx_path.write_bytes(b"fake docx")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    seen_profiles = []
    real_fake_run = _fake_run_factory()

    def _capture(cmd, *args, **kwargs):
        env_args = [a for a in cmd if a.startswith("-env:UserInstallation=")]
        assert len(env_args) == 1
        seen_profiles.append(env_args[0])
        return real_fake_run(cmd, *args, **kwargs)

    with patch("subprocess.run", side_effect=_capture):
        render_pdf(docx_path, out_dir)
    with patch("subprocess.run", side_effect=_capture):
        render_pdf(docx_path, out_dir)

    assert seen_profiles[0] != seen_profiles[1]


def test_render_pdf_passes_a_timeout_to_subprocess_run(tmp_path):
    docx_path = tmp_path / "resume.docx"
    docx_path.write_bytes(b"fake docx")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch("subprocess.run", side_effect=_fake_run_factory()) as mock_run:
        render_pdf(docx_path, out_dir)

    assert mock_run.call_args.kwargs.get("timeout") is not None
    assert mock_run.call_args.kwargs["timeout"] > 0


def test_render_pdf_raises_on_nonzero_exit(tmp_path):
    docx_path = tmp_path / "resume.docx"
    docx_path.write_bytes(b"fake docx")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with (
        patch(
            "subprocess.run",
            side_effect=_fake_run_factory(returncode=1, create_pdf=False),
        ),
        pytest.raises(PdfConversionError),
    ):
        render_pdf(docx_path, out_dir)


def test_render_pdf_raises_on_timeout(tmp_path):
    docx_path = tmp_path / "resume.docx"
    docx_path.write_bytes(b"fake docx")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    def _timeout(cmd, *args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 60))

    with (
        patch("subprocess.run", side_effect=_timeout),
        pytest.raises(PdfConversionError),
    ):
        render_pdf(docx_path, out_dir)


def test_render_pdf_raises_if_soffice_reports_success_but_no_pdf_appears(tmp_path):
    docx_path = tmp_path / "resume.docx"
    docx_path.write_bytes(b"fake docx")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with (
        patch(
            "subprocess.run",
            side_effect=_fake_run_factory(returncode=0, create_pdf=False),
        ),
        pytest.raises(PdfConversionError),
    ):
        render_pdf(docx_path, out_dir)


def test_render_pdf_raises_if_soffice_binary_is_missing(tmp_path):
    docx_path = tmp_path / "resume.docx"
    docx_path.write_bytes(b"fake docx")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with (
        patch("subprocess.run", side_effect=FileNotFoundError()),
        pytest.raises(PdfConversionError),
    ):
        render_pdf(docx_path, out_dir)


def test_render_pdf_creates_out_dir_if_missing(tmp_path):
    docx_path = tmp_path / "resume.docx"
    docx_path.write_bytes(b"fake docx")
    out_dir = tmp_path / "does_not_exist_yet"

    with patch("subprocess.run", side_effect=_fake_run_factory()):
        render_pdf(docx_path, out_dir)

    assert out_dir.is_dir()
