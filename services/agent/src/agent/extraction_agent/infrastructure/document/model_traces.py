"""Private local response diagnostics; never persist request messages or credentials."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class LocalModelTraceStore:
    """Write transport responses before Stage 2 parses their inner JSON."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    async def append(self, run_id: str, trace: Mapping[str, Any]) -> None:
        keys = (
            "kind",
            "agent",
            "model",
            "attempts",
            "duration_seconds",
            "usage",
            "finish_reason",
            "metadata",
            "response_content",
            "error_type",
            "schema_error",
        )
        payload = {key: trace[key] for key in keys if key in trace}
        payload["run_id"] = run_id
        payload["validation_stage"] = "transport_response_before_extraction_json_validation"
        content = payload.get("response_content")
        payload["response_char_count"] = len(content) if isinstance(content, str) else None
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        destination = self.directory / f"{stamp}-{uuid4().hex}.json"
        try:
            await asyncio.to_thread(self._write, destination, payload)
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("Could not save local model response diagnostics (%s)", type(exc).__name__)

    @staticmethod
    def _write(path: Path, payload: Mapping[str, Any]) -> None:
        # Import lazily to avoid loading the Graph while constructing adapters.
        from src.agent.extraction_agent.infrastructure.document.checkpoint import _write_json_atomic

        _write_json_atomic(path, dict(payload))

    async def list(self, run_id: str) -> list[Mapping[str, Any]]:
        return await asyncio.to_thread(self._list, run_id)

    def _list(self, run_id: str) -> list[Mapping[str, Any]]:
        rows: list[Mapping[str, Any]] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(value, dict) and value.get("run_id") == run_id:
                    rows.append(value)
            except (OSError, ValueError):
                continue
        return rows
