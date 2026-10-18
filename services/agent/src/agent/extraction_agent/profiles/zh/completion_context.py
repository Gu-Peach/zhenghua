"""Compatibility imports for the shared, profile-configured completion mechanism."""

from src.agent.extraction_agent.infrastructure.document.completion_context import (
    CompletionPageContext,
    CompletionSourceComponent,
    TargetOnlyCompletionContext,
    target_only_context,
)

__all__ = [
    "CompletionPageContext",
    "CompletionSourceComponent",
    "TargetOnlyCompletionContext",
    "target_only_context",
]
