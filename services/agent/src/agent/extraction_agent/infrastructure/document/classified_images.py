from __future__ import annotations

import shutil
from pathlib import Path


def relocate_classified_image(
    source: Path, destination: Path, *, restored: bool, page_label: str, pdf_page: int
) -> tuple[Path, str, bool]:
    """Relocate a rendered page, reusing saved paths on resume and keeping collisions distinct."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_key = str(source.resolve())
    collision = False
    if destination.exists() and source.resolve() != destination.resolve():
        if restored:
            source.unlink(missing_ok=True)
        else:
            destination = destination.with_name(f"{page_label}__pdf_{pdf_page:04d}.png")
            collision = True
    if source.is_file() and source.resolve() != destination.resolve():
        shutil.move(str(source), str(destination))
    return destination.resolve(), source_key, collision
