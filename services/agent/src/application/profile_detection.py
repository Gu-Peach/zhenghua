from __future__ import annotations

from pathlib import Path

from src.agents.profile_router import ProfileRouterAgent
from src.config import AgentSettings
from src.graphs.profile_detection import ProfileDetectionRuntime
from src.harness.model_gateway import ModelGateway
from src.profiles import ProfileRegistry
from src.tools.pdf_first_page import PdfFirstPageRenderer


def create_profile_detection_runtime(
    *,
    settings: AgentSettings,
    registry: ProfileRegistry,
    gateway: ModelGateway,
) -> ProfileDetectionRuntime:
    prompt_path = settings.workspace_root / "services" / "agent" / "src/agent/extraction_agent/prompts" / "profile_router.md"
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
