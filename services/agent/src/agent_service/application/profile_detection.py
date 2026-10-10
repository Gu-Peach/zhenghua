from __future__ import annotations

from pathlib import Path

from ..agents.profile_router import ProfileRouterAgent
from ..config import AgentSettings
from ..graphs.profile_detection import ProfileDetectionRuntime
from ..harness.model_gateway import ModelGateway
from ..profiles import ProfileRegistry
from ..tools.pdf_first_page import PdfFirstPageRenderer


def create_profile_detection_runtime(
    *,
    settings: AgentSettings,
    registry: ProfileRegistry,
    gateway: ModelGateway,
) -> ProfileDetectionRuntime:
    prompt_path = settings.workspace_root / "services" / "agent" / "prompts" / "profile_router.md"
    return ProfileDetectionRuntime(
        renderer=PdfFirstPageRenderer(
            dpi=settings.profile_detection_dpi,
            max_pdf_bytes=settings.profile_max_pdf_bytes,
        ),
        router=ProfileRouterAgent(
            gateway=gateway,
            registry=registry,
            prompt_path=Path(prompt_path),
            auto_select_threshold=settings.profile_auto_select_threshold,
        ),
    )
