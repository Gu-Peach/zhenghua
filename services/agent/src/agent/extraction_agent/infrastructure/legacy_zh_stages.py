"""Compatibility import for callers migrating to the native ZH stage adapter."""

from src.agent.extraction_agent.infrastructure.zh_vlm_stages import ZhVlmExtractionStageAdapter

LegacyZhStageAdapter = ZhVlmExtractionStageAdapter

__all__ = ["LegacyZhStageAdapter"]
