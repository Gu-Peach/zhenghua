"""Reproduce the minimal ABB examples from the user-supplied full drawings."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src/agent/extraction_agent/prompts/abb"


def main() -> None:
    """Copy classification, completion pair and circle examples; preserve originals."""
    images = ROOT / "examples_wiring" / "annotated" / "images"
    classification = ROOT / "examples_page_classification" / "lv11_205"
    images.mkdir(parents=True, exist_ok=True)
    classification.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "1.png", classification / "page.png")
    for source, identity in (("1", "lv11_205"), ("2", "lv12_241"), ("3", "lv21_281")):
        shutil.copyfile(ROOT / f"{source}.png", images / f"{identity}.png")
    print("Prepared classification205, scan205/281 and internal completion205/241 images.")


if __name__ == "__main__":
    main()
