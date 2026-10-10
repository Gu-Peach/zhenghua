from __future__ import annotations

from dataclasses import dataclass

from agent_service.config import (
    AgentSettings,
)


@dataclass(frozen=True, slots=True)
class Settings:
    max_pdf_pages: int
    concurrency: int
    reference_target_limit: int
    pdf_render_scale: float
    pdf_render_dpi: int
    keep_temp_images: bool
    output_mode: str
    terminal_strip_mapping: dict[str, str]

    @classmethod
    def from_agent(cls, settings: AgentSettings, *, max_pdf_pages: int | None = None) -> Settings:
        dpi = max(300, settings.extraction_render_dpi)
        return cls(
            max_pdf_pages=(settings.extraction_max_pdf_pages if max_pdf_pages is None else max_pdf_pages),
            concurrency=settings.extraction_concurrency,
            reference_target_limit=settings.extraction_reference_target_limit,
            pdf_render_scale=dpi / 72,
            pdf_render_dpi=dpi,
            keep_temp_images=settings.extraction_keep_temp_images,
            output_mode=settings.extraction_output_mode,
            terminal_strip_mapping=dict(settings.terminal_strip_mapping or {}),
        )
