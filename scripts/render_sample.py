"""Render the full bank (no tailoring) to a sample docx for manual review.

Same input as tests/test_render.py's golden test: the real bank, the real
identity.toml, and the default profile (education first, no summary).
Writes to resume/rendered/preview/, never to an outbound directory, since
this is a manual dry-run artifact, not something meant to go out.
"""

from pathlib import Path

from jobengine.resume.bank import load_bank
from jobengine.resume.render import RenderProfile, load_identity, render

OUTPUT_PATH = Path("resume/rendered/preview/sample.docx")


def main() -> None:
    bank = load_bank()
    identity = load_identity()
    profile = RenderProfile(
        section_order=["education", "work_history", "projects", "publications"],
        include_summary=False,
    )
    doc = render(bank, identity, profile)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUTPUT_PATH)
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
