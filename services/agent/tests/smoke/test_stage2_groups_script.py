from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from zipfile import ZipFile

import httpx
import pytest

from src.config import AgentSettings
from src.agent.extraction_agent.domain.models.extraction_stages import (
    CrossPageCompletionData,
    DrawingEndpoint,
    PageScanData,
    ScannedConnection,
    ScannedWireUnit,
)
from src.infrastructure.supabase_client import SupabaseClient

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location(
    "local_stage2_groups", ROOT / "services/agent/scripts/run_stage2_groups.py"
)
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)


def inputs(tmp_path: Path) -> argparse.Namespace:
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    template = tmp_path / "template.xlsx"
    with ZipFile(template, "w") as archive:
        strings = "".join(f"<si><t>{header}</t></si>" for header in runner.HEADERS)
        cells = "".join(f'<c r="{chr(65 + i)}1" t="s"><v>{i}</v></c>' for i in range(12))
        archive.writestr("xl/sharedStrings.xml", f'<sst xmlns="{ns}">{strings}</sst>')
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            f'<worksheet xmlns="{ns}"><sheetFormatPr defaultColWidth="12"/>'
            f"<sheetData><row>{cells}</row></sheetData></worksheet>",
        )
        archive.writestr(
            "xl/styles.xml",
            f'<styleSheet xmlns="{ns}"><fonts><font><name val="宋体"/><sz val="9"/></font></fonts>'
            '<cellXfs><xf fontId="0"/></cellXfs></styleSheet>',
        )
    pages_dir = tmp_path / "pages"
    index = {"pages": [], "page_lookup": {}, "references": []}
    for number, function in enumerate(["002.C", "002.M", "003.C"], 1):
        folder = pages_dir / function
        folder.mkdir(parents=True)
        (folder / "1.png").write_bytes(f"unique-source-{number}".encode())
        index["pages"].append({"pdf_page": number, "function": function, "internal_page": 1})
        index["page_lookup"][f"{function}:1"] = number
    index_path = tmp_path / "index.json"
    index_path.write_text(json.dumps(index), encoding="utf-8")
    return argparse.Namespace(
        output_dir=tmp_path / "output",
        pages_dir=pages_dir,
        index=index_path,
        groups=["002.C", "002.M"],
        template=template,
        max_source_pages=0,
        allow_real_model=False,
        export_only=False,
        skip_xlsx=True,
        completion_max_side=0,
        run_id="offline-groups-test",
    )


def test_only_requested_groups_are_scanned_and_database_construction_is_forbidden(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("Database/network construction forbidden in a local test")

    monkeypatch.setattr(SupabaseClient, "__init__", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden)
    monkeypatch.setattr(
        AgentSettings,
        "from_env",
        classmethod(
            lambda cls: AgentSettings(
                persistence_backend="supabase",
                checkpoint_backend="supabase",
                profile_packages_enabled=True,
                supabase_url="https://database.invalid",
                supabase_service_role_key="must-be-dropped",
            )
        ),
    )

    class Stages:
        def __init__(self):
            self.scans = []

        async def scan_page(self, request):
            number = request.page.pdf_page_number
            self.scans.append(number)
            assert request.page.image_path.read_bytes() == f"unique-source-{number}".encode()
            assert "connection.color" in request.page_context
            return PageScanData(
                units=[
                    ScannedWireUnit(
                        unit_id="wire",
                        connections=[
                            ScannedConnection(
                                start=DrawingEndpoint(device="-XD1", terminal="L1"),
                                color="should-be-blank",
                                references=[{"target_function": "003.C", "target_drawing_page": 1}],
                                is_cross_page="cross_page",
                                status="needs_reference",
                            )
                        ],
                    )
                ]
            )

        async def resolve_cross_page(self, request):
            assert request.target_page.image_path.read_bytes() == b"unique-source-3"
            assert request.source_page.image_path.read_bytes() != b"unique-source-3"
            return CrossPageCompletionData(
                end=DrawingEndpoint(device="-Q1", terminal="L1"), status="resolved"
            )

    args = inputs(tmp_path)
    stages = Stages()
    summary = asyncio.run(runner.execute(args, stages=stages))
    assert stages.scans == [1, 2]
    assert summary["source_pages"] == 2
    assert summary["database_upload"] is False
    assert summary["storage_upload"] is False
    table = json.loads((args.output_dir / "table.json").read_text(encoding="utf-8"))
    assert table["headers"] == runner.HEADERS
    assert [row[0] for row in table["rows"]] == ["002C01", "002M01"]
    assert all(len(row) == 12 and row[10] is None for row in table["rows"])


def test_missing_requested_image_fails_preflight(tmp_path: Path) -> None:
    args = inputs(tmp_path)
    (args.pages_dir / "002.M/1.png").unlink()
    with pytest.raises(ValueError, match="Missing requested source images"):
        runner.load_pages(args.pages_dir, args.index, args.groups)


def test_empty_values_and_actual_zero_are_distinct_in_standard_rows() -> None:
    rows = runner.table_rows(
        [
            {"drawing_function": "002.C", "drawing_page_number": 1, "current": 0},
            {"drawing_function": "002.M", "drawing_page_number": 3},
        ]
    )
    assert rows[0][9] == 0
    assert rows[1][9] is None
    assert rows[0][10] is None


def test_unknown_reference_page_zero_becomes_null_without_inventing_a_target() -> None:
    from src.agent.extraction_agent.infrastructure.zh_vlm_stages import _normalize_page_scan

    data = {
        "units": [
            {
                "unit_id": "u",
                "connections": [
                    {
                        "start": {"device": "-XD21", "terminal": "1"},
                        "references": [
                            {"target_drawing_page": 0, "target_pdf_page": "0", "target_function": "002.M"}
                        ],
                    }
                ],
            }
        ]
    }
    scanned = PageScanData.model_validate(_normalize_page_scan(data, 56))
    reference = scanned.units[0].connections[0].references[0]
    assert reference.target_drawing_page is None
    assert reference.target_pdf_page is None
    assert reference.target_function == "002.M"
    data["units"][0]["connections"][0]["references"][0]["target_drawing_page"] = -1
    with pytest.raises(ValueError):
        PageScanData.model_validate(_normalize_page_scan(data, 56))
