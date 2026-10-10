from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from ...domain.models.profile_detection import ProfileDetectionResult
from ...tools.pdf_first_page import FirstPageImage


class ProfileDetectionState(TypedDict, total=False):
    run_id: str
    project_id: str
    pdf_path: Path
    first_page: FirstPageImage
    result: ProfileDetectionResult
