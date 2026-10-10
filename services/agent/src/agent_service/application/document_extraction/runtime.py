from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from agent_service.application.document_extraction.ports import (
    DocumentStageClient as VLMClient,
)
from agent_service.application.document_extraction.settings import (
    Settings,
)
from agent_service.domain.models.image_payload import (
    ImagePayload,
)
from agent_service.graphs.document_extraction.state import (
    GraphState,
)
from agent_service.profiles.extraction_policy import ExtractionPolicy

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str], None]


@dataclass
class AgentRunResult:
    state: GraphState
    extraction_errors: dict[str, str]
    validation_warnings: list[str]


@dataclass
class GraphRuntime:
    settings: Settings
    extraction_client: VLMClient
    output_mode: str
    policy: ExtractionPolicy
    preloaded_images: list[ImagePayload] | None = None
    progress: ProgressCallback | None = None
    payload_by_path: dict[str, ImagePayload] = field(default_factory=dict)
    temp_page_dir: Path | None = None
    extraction_errors: dict[str, str] = field(default_factory=dict)
    validation_warnings: list[str] = field(default_factory=list)
    scan_page_numbers: set[int] | None = None

    def __post_init__(self) -> None:
        self.payload_by_path = {}
        self.extraction_errors = {}
        self.validation_warnings = []

    def log(self, message: str) -> None:
        logger.info(message)
        if self.progress:
            self.progress(message)

    def payload_for(self, image_path: str) -> ImagePayload:
        assert self.payload_by_path is not None
        key = str(Path(image_path).resolve())
        payload = self.payload_by_path.get(key) or self.payload_by_path.get(image_path)
        if payload is None:
            raise FileNotFoundError(f"Rendered page is not registered: {image_path}")
        if not payload.content:
            path = Path(image_path)
            if path.is_file():
                payload = replace(payload, content=path.read_bytes())
                self.payload_by_path[key] = payload
                self.payload_by_path[image_path] = payload
        return payload
