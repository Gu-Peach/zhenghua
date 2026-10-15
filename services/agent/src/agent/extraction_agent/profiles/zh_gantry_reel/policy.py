from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.agent.extraction_agent.domain.models.drawing_index import DrawingIndex, DrawingPage
from src.agent.extraction_agent.domain.models.wiring import WireRecord
from src.agent.extraction_agent.profiles.zh.policy import ZhExtractionPolicy

POLICY_VERSION = "0.1.2"

SHEET_RE = re.compile(r"^(\d{1,2})([A-Z])$")
ADDRESS_RE = re.compile(
    r"(?<![A-Z0-9])(?P<sheet>\d{1,2}[A-Z])(?P<column>\d{2})(?P<row>[A-HJ-NP-V])(?![A-Z0-9])"
)


def encode_sheet(raw: str, *, terminal_report: bool = False) -> tuple[str, int]:
    """Reversible business identity; never use the PDF physical index as SH.NO."""
    text = raw.strip().upper()
    if terminal_report:
        match = re.fullmatch(r"(\d+)(?:\.([A-Z]))?", text)
        if not match:
            raise ValueError("Invalid TD sheet identity")
        number = int(match[1])
        if not 1 <= number <= 99:
            raise ValueError("TD base sheet must be between 1 and 99")
        return "GCR.TD", number * 100 + ord(match[2]) - 64 if match[2] else number
    match = SHEET_RE.fullmatch(text)
    if not match:
        raise ValueError("Invalid elementary SH.NO.")
    return f"GCR.{int(match[1])}", ord(match[2]) - 64


def decode_sheet(function: str, number: int) -> str:
    if function == "GCR.TD":
        return f"TD:{number // 100}.{chr(96 + number % 100)}" if number >= 100 else f"TD:{number}"
    match = re.fullmatch(r"GCR\.(\d+)", function)
    if not match or not 1 <= number <= 26:
        raise ValueError("Invalid normalized gantry sheet identity")
    return f"{int(match[1])}{chr(64 + number)}"


def parse_title_block(text: str) -> tuple[str | None, int | None, str | None, bool]:
    """Read the title-block stream between CONT.ON.SH and Approved by."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if "CONT.ON.SH" not in lines:
        return None, None, None, False
    start = lines.index("CONT.ON.SH") + 1
    block = lines[start : start + 12]
    if "Approved by:" in block:
        block = block[: block.index("Approved by:")]
    report = "F13_001" in text or any("端子图表" in line for line in block)
    for index, line in enumerate(block):
        if (report and re.fullmatch(r"\d+(?:\.[a-zA-Z])?", line)) or (
            not report and SHEET_RE.fullmatch(line)
        ):
            function, page = encode_sheet(line, terminal_report=report)
            title = " ".join(block[:index]) or None
            return function, page, title, report or line == "0A"
    return None, None, None, report


class ZhGantryReelPolicy(ZhExtractionPolicy):
    """Own only grid identity/reference and actual terminal fields; reuse transport rules."""

    enforce_evidence_contract = False

    def project_identity(self, text: str) -> tuple[str | None, str | None]:
        match = re.search(r"(?:Project\s+No\.?\s*:\s*|\b)(\d{10})\b", text)
        return (match[1] if match else None), None

    def build_drawing_index(self, path: Path) -> DrawingIndex:
        from src.agent.extraction_agent.infrastructure.document.pdf_runtime import read_pdf_text_pages

        texts = read_pdf_text_pages(path)
        cabinet = next(
            (m[1] for _, text in texts if (m := re.search(r"Cabinets\s+Name\s*:\s*(\+\w+)", text))), None
        )
        index = DrawingIndex(pdf_path=str(path))
        for physical, text in texts:
            function, number, title, non_wiring = parse_title_block(text)
            index.pages.append(
                DrawingPage(
                    pdf_page=physical,
                    function=function,
                    internal_page=number,
                    object_loc=cabinet,
                    title=title,
                    text=text,
                    is_non_wiring=non_wiring,
                )
            )
            if function and number is not None:
                key = f"{function}:{number}"
                if key in index.page_lookup:
                    raise ValueError("Duplicate gantry SH.NO. in input PDF")
                index.page_lookup[key] = physical
        return index

    def parse_references(self, page: Any) -> list[Any]:
        # Printed wire numbers and arrow references share the coordinate syntax.
        # Consume only the scanner's connection-bound references, not all PDF text.
        return []

    def prepare_reference(
        self, raw: Mapping[str, Any], *, source_page: Mapping[str, Any], drawing_index: Mapping[str, Any]
    ) -> dict[str, Any]:
        reference = dict(raw)
        match = ADDRESS_RE.search(str(reference.get("raw") or "").upper())
        if not match or not 1 <= int(match["column"]) <= 48:
            reference.update(
                target_pdf_page=None,
                external=True,
                reason="missing or invalid explicit grid address; no inferred target",
            )
            return reference
        if match and 1 <= int(match["column"]) <= 48:
            parsed_function, parsed_number = encode_sheet(match["sheet"])
            reference.update(
                target_function=parsed_function,
                target_drawing_page=parsed_number,
                target_internal_page=parsed_number,
                target_column=int(match["column"]),
            )
            reference["reason"] = f"SH.NO.={match['sheet']}; column={match['column']}; row={match['row']}"
        function = reference.get("target_function")
        number = reference.get("target_drawing_page")
        target = (
            drawing_index.get("page_lookup", {}).get(f"{function}:{number}") if function and number else None
        )
        reference["target_pdf_page"] = int(target) if target is not None else None
        reference["external"] = target is None
        if target is None:
            reference["reason"] = (
                reference.get("reason") or ""
            ) + "; target absent/ambiguous in supplied atlas"
        return reference

    def normalize_record(self, record: WireRecord, mapping: Mapping[str, str]) -> WireRecord:
        # No XA/XD-to-business-class inference in this family: actual X strips win.
        record.terminal_strip = next(
            (
                board.lstrip("-")
                for board in (record.start_terminal_board, record.end_terminal_board)
                if board and re.fullmatch(r"-?X\d+", board)
            ),
            None,
        )
        record.color = None
        if record.drawing_function and record.drawing_page_number:
            record.drawing_page = decode_sheet(record.drawing_function, record.drawing_page_number)
            record.drawing_source_pages = list(
                dict.fromkeys([record.drawing_page, *record.drawing_source_pages])
            )
        return record
