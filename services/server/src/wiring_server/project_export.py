"""Read authorized, version-checked project rows and compile a text-only XLSX download."""

from __future__ import annotations

import asyncio
import math
import re
import unicodedata
from dataclasses import dataclass
from io import BytesIO
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

from .repository import Repository, ServiceError
from .simple_management import ManagementService

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
COLUMNS = (
    ("页码", "workspace_page", 14),
    ("原理号", "principle_number", 20),
    ("电压等级", "voltage_level", 16),
    ("端子排", "terminal_strip", 14),
    ("起点代号", "start_code", 22),
    ("起点描述", "start_description", 32),
    ("起点端子", "start_terminal", 24),
    ("终点代号", "end_code", 22),
    ("终点描述", "end_description", 32),
    ("终点端子", "end_terminal", 24),
    ("电流", "current_value", 16),
    ("备注", "remark", 40),
    ("色标", "color_mark", 12),
)
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


@dataclass(frozen=True)
class ExportFile:
    filename: str
    content: bytes


def xml_bytes(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def text_value(value: Any) -> str:
    text = "" if value is None else str(value)
    if len(text) > 32767 or any(
        ord(char) not in {9, 10, 13}
        and not (
            32 <= ord(char) <= 0xD7FF
            or 0xE000 <= ord(char) <= 0xFFFD
            or 0x10000 <= ord(char) <= 0x10FFFF
        )
        for char in text
    ):
        raise ServiceError(
            422,
            "EXPORT_CELL_INVALID",
            "线表含Excel无法保存的超长文本或字符，请核对数据后重试",
        )
    return text


def build_xlsx(rows: list[dict[str, Any]]) -> bytes:
    """Compile the small OOXML subset needed for data export, with no executable formulas."""
    if len(rows) > 1_048_575:
        raise ServiceError(422, "EXPORT_TOO_LARGE", "项目记录超过Excel单表上限")
    sheet = ET.Element("worksheet", xmlns=NS)
    ET.SubElement(sheet, "dimension", ref=f"A1:M{len(rows) + 1}")
    views = ET.SubElement(sheet, "sheetViews")
    view = ET.SubElement(views, "sheetView", workbookViewId="0")
    ET.SubElement(
        view,
        "pane",
        ySplit="1",
        topLeftCell="A2",
        activePane="bottomLeft",
        state="frozen",
    )
    ET.SubElement(view, "selection", pane="bottomLeft", activeCell="A2", sqref="A2")
    ET.SubElement(sheet, "sheetFormatPr", defaultRowHeight="24")
    cols = ET.SubElement(sheet, "cols")
    for index, (_, _, width) in enumerate(COLUMNS, 1):
        ET.SubElement(
            cols,
            "col",
            min=str(index),
            max=str(index),
            width=str(width),
            customWidth="1",
        )
    data = ET.SubElement(sheet, "sheetData")
    values = [[title for title, _, _ in COLUMNS]]
    values.extend([[text_value(row.get(key)) for _, key, _ in COLUMNS] for row in rows])
    for index, cells in enumerate(values, 1):
        lines = max(
            sum(
                max(
                    1,
                    math.ceil(
                        sum(
                            2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
                            for char in line
                        )
                        / width
                    ),
                )
                for line in value.split("\n")
            )
            for value, (_, _, width) in zip(cells, COLUMNS, strict=True)
        )
        node = ET.SubElement(
            data,
            "row",
            r=str(index),
            ht="30" if index == 1 else str(min(409, max(28, lines * 15 + 8))),
            customHeight="1",
        )
        for column, value in enumerate(cells):
            cell = ET.SubElement(
                node,
                "c",
                r=f"{chr(65 + column)}{index}",
                s="1" if index == 1 else "2",
                t="inlineStr",
            )
            text = ET.SubElement(
                ET.SubElement(cell, "is"),
                "t",
                {"{http://www.w3.org/XML/1998/namespace}space": "preserve"},
            )
            text.text = value
    ET.SubElement(sheet, "autoFilter", ref=f"A1:M{len(rows) + 1}")
    styles = ET.Element("styleSheet", xmlns=NS)
    fonts = ET.SubElement(styles, "fonts", count="2")
    for bold in (False, True):
        font = ET.SubElement(fonts, "font")
        ET.SubElement(font, "sz", val="11")
        ET.SubElement(font, "name", val="宋体")
        if bold:
            ET.SubElement(font, "b")
    fills = ET.SubElement(styles, "fills", count="3")
    for pattern in ("none", "gray125", "solid"):
        fill = ET.SubElement(
            ET.SubElement(fills, "fill"), "patternFill", patternType=pattern
        )
        if pattern == "solid":
            ET.SubElement(fill, "fgColor", rgb="FFFFFF00")
    borders = ET.SubElement(styles, "borders", count="2")
    ET.SubElement(borders, "border")
    border = ET.SubElement(borders, "border")
    for side in ("left", "right", "top", "bottom"):
        ET.SubElement(
            ET.SubElement(border, side, style="thin"), "color", rgb="FFB7B7B7"
        )
    xf = ET.SubElement(styles, "cellStyleXfs", count="1")
    ET.SubElement(xf, "xf", numFmtId="0", fontId="0", fillId="0", borderId="0")
    xfs = ET.SubElement(styles, "cellXfs", count="3")
    for style in range(3):
        item = ET.SubElement(
            xfs,
            "xf",
            numFmtId="49",
            fontId="1" if style == 1 else "0",
            fillId="2" if style == 1 else "0",
            borderId="1" if style else "0",
            xfId="0",
            applyNumberFormat="1",
            applyAlignment="1",
        )
        ET.SubElement(
            item,
            "alignment",
            vertical="center",
            horizontal="center" if style == 1 else "left",
            wrapText="1",
        )
    cell_styles = ET.SubElement(styles, "cellStyles", count="1")
    ET.SubElement(cell_styles, "cellStyle", name="Normal", xfId="0", builtinId="0")
    workbook = ET.Element("workbook", xmlns=NS, attrib={"xmlns:r": DOC_REL})
    ET.SubElement(
        ET.SubElement(workbook, "sheets"),
        "sheet",
        name="放线表",
        sheetId="1",
        attrib={"r:id": "rId1"},
    )
    relationships = ET.Element("Relationships", xmlns=REL)
    for identifier, target, kind in (
        ("rId1", "worksheets/sheet1.xml", "worksheet"),
        ("rId2", "styles.xml", "styles"),
    ):
        ET.SubElement(
            relationships,
            "Relationship",
            Id=identifier,
            Target=target,
            Type=f"{DOC_REL}/{kind}",
        )
    root_rel = ET.Element("Relationships", xmlns=REL)
    ET.SubElement(
        root_rel,
        "Relationship",
        Id="rId1",
        Target="xl/workbook.xml",
        Type=f"{DOC_REL}/officeDocument",
    )
    content_types = ET.Element(
        "Types", xmlns="http://schemas.openxmlformats.org/package/2006/content-types"
    )
    ET.SubElement(
        content_types,
        "Default",
        Extension="rels",
        ContentType="application/vnd.openxmlformats-package.relationships+xml",
    )
    ET.SubElement(
        content_types, "Default", Extension="xml", ContentType="application/xml"
    )
    for path, kind in (
        ("workbook.xml", "sheet.main"),
        ("styles.xml", "styles"),
        ("worksheets/sheet1.xml", "worksheet"),
    ):
        ET.SubElement(
            content_types,
            "Override",
            PartName=f"/xl/{path}",
            ContentType=f"application/vnd.openxmlformats-officedocument.spreadsheetml.{kind}+xml",
        )
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as package:
        for path, root in (
            ("[Content_Types].xml", content_types),
            ("_rels/.rels", root_rel),
            ("xl/workbook.xml", workbook),
            ("xl/_rels/workbook.xml.rels", relationships),
            ("xl/styles.xml", styles),
            ("xl/worksheets/sheet1.xml", sheet),
        ):
            package.writestr(path, xml_bytes(root))
    return buffer.getvalue()


class ProjectExport:
    def __init__(self, db: Repository) -> None:
        self.db = db

    async def download(self, project: str, user: str) -> ExportFile:
        original = await self.db.require_project(project, user)
        if original["status"] == "processing":
            raise ServiceError(
                409, "EXTRACTION_IN_PROGRESS", "项目正在提取，请处理完成后导出"
            )
        management = ManagementService(self.db)
        batch = await management.batch(original)
        filters = {
            "project_id": f"eq.{project}",
            "batch_id": f"eq.{batch}",
            "order": "source_pdf_page_number.asc,row_order.asc,id.asc",
        }
        fields = [
            key
            for _, key, _ in COLUMNS
            if key not in {"workspace_page", "voltage_level"}
        ]
        projection = ",".join(
            [
                "id",
                "record_version",
                "source_drawing_page",
                *fields,
                "voltage_level:evidence->>voltage_level",
            ]
        )
        rows = (
            await self.db.all_rows(
                "extraction_connection_rows", {**filters, "select": projection}
            )
            if batch
            else []
        )
        content = await asyncio.to_thread(
            build_xlsx,
            [
                {
                    **row,
                    "workspace_page": row.get("source_drawing_page"),
                    "voltage_level": row["voltage_level"]
                    if "voltage_level" in row
                    else (row.get("evidence") or {}).get("voltage_level"),
                }
                for row in rows
            ],
        )
        versions = (
            await self.db.all_rows(
                "extraction_connection_rows", {**filters, "select": "id,record_version"}
            )
            if batch
            else []
        )
        current = await self.db.require_project(project, user)
        expected = [(row["id"], row["record_version"]) for row in rows]
        actual = [(row["id"], row["record_version"]) for row in versions]
        if (
            expected != actual
            or len({identifier for identifier, _ in expected}) != len(expected)
            or any(
                current.get(key) != original.get(key)
                for key in ("updated_at", "status", "drawing_index")
            )
            or await management.batch(current) != batch
        ):
            raise ServiceError(
                409, "EXPORT_CHANGED", "导出期间线表或项目发生变更，请重新导出"
            )
        name = (
            re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(original["name"]))[:120].strip(
                " ."
            )
            or "项目"
        )
        return ExportFile(f"{name}_放线表.xlsx", content)
