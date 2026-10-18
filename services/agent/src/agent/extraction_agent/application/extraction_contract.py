"""Shared request and result policy for local scripts and incremental uploads."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.agent.extraction_agent.domain.models.extraction_stages import (
    DrawingPageInput,
    PageScanData,
    PageScanDiagnostics,
    PageScanResult,
)

EXTRACTION_CONTRACT_VERSION = "stage2-script-aligned-v1"
SCAN_CONTEXT_PREFIX = (
    "本次测试不提取色标：每条 connection.color 必须为 null。其他字段按图中证据读取。\n"
)


def scan_context(value: str) -> str:
    """Keep the verified script text identical, including when an old caller prepends it."""
    return value if value.startswith(SCAN_CONTEXT_PREFIX) else SCAN_CONTEXT_PREFIX + value


def without_color(result: PageScanResult) -> PageScanResult:
    for unit in result.units:
        for connection in unit.connections:
            connection.color = None
    return result


def scan_diagnostics(result: PageScanData, page: DrawingPageInput) -> PageScanDiagnostics:
    """Describe the model's parsed facts before the shared agent filters receiving ends."""
    connections = [connection for unit in result.units for connection in unit.connections]
    receivers = sum(connection.endpoint_role == "receiver" for connection in connections)
    skipped = page.blank or page.non_wiring or result.blank
    retained = 0 if skipped else len(connections) - receivers
    return PageScanDiagnostics(
        raw_units=len(result.units), raw_connections=len(connections),
        source_connections=sum(connection.endpoint_role == "source" for connection in connections),
        receiver_connections=receivers,
        unknown_connections=sum(connection.endpoint_role == "unknown" for connection in connections),
        retained_connections=retained,
        outcome=(
            "skipped" if skipped else "no_connections" if not connections else
            "receivers_only" if not retained else "sources_retained"
        ),
    )


def drawing_page_input(
    path: Path, number: int, metadata: Mapping[str, Any], *, blank: bool = False,
) -> DrawingPageInput:
    """Use indexed business identity; the image's number remains its physical PDF page."""
    return DrawingPageInput(
        pdf_page_number=number,
        image_path=path,
        plant_function=metadata.get("function"),
        drawing_page_number=metadata.get("internal_page"),
        object_location=metadata.get("object_loc"),
        blank=blank or bool(metadata.get("blank")),
        non_wiring=bool(metadata.get("is_non_wiring")),
    )
