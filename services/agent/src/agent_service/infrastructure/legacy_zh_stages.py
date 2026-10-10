"""Compatibility import for callers migrating to the native ZH stage adapter."""

from .zh_vlm_stages import ZhVlmExtractionStageAdapter

LegacyZhStageAdapter = ZhVlmExtractionStageAdapter

__all__ = ["LegacyZhStageAdapter"]
