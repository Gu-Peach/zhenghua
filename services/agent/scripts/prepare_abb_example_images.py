"""Reproduce the minimal ABB examples from the user-supplied full drawings."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src/agent/extraction_agent/prompts/abb"
REFERENCE = Path(__file__).resolve().parents[1] / "tests/fixtures/abb_reference/images"


def main() -> None:
    """Copy only current runtime images from preserved reference drawings."""
    images = ROOT / "examples_wiring" / "lv11" / "images"
    classification = ROOT / "examples_page_classification" / "lv11_205"
    images.mkdir(parents=True, exist_ok=True)
    classification.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REFERENCE / "lv11_205.png", classification / "page.png")
    for identity in ("lv11_205", "lv12_241"):
        shutil.copyfile(REFERENCE / f"{identity}.png", images / f"{identity}.png")
    print("Prepared classification205, scan205 and internal completion205/241 images.")


if __name__ == "__main__":
    main()
