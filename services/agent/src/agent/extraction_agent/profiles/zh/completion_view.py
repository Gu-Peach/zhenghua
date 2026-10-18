"""Compatibility imports for the shared, profile-configured completion mechanism."""

from src.agent.extraction_agent.infrastructure.document.completion_view import (
    CompletionImageViewport,
    CompletionInputView,
    CompletionViewRules,
    PreparedCompletionView,
    prepare_completion_example_view,
    prepare_completion_view,
    transform_completion_points,
)

__all__ = [
    "CompletionViewRules",
    "CompletionInputView",
    "CompletionImageViewport",
    "PreparedCompletionView",
    "prepare_completion_view",
    "transform_completion_points",
    "prepare_completion_example_view",
]
