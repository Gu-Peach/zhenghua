"""Exact scoped searches, with bounded numeric ranges only after literal lookup misses."""

from __future__ import annotations

import json
import re
from typing import Any

from .repository import Repository


def expand_number_range(value: str) -> list[str] | None:
    parts = re.split(r"\s*(?:[-~～—–]|至)\s*", value.strip())
    if len(parts) != 2:
        return None
    start = re.fullmatch(r"(.*?)([0-9]{1,12})", parts[0])
    if not start:
        return None
    prefix, digits = start.groups()
    if re.fullmatch(r"[0-9]{1,12}", parts[1]):
        end_digits = (
            digits[: -len(parts[1])] + parts[1]
            if len(parts[1]) < len(digits)
            else parts[1]
        )
    else:
        end = re.fullmatch(r"(.*?)([0-9]{1,12})", parts[1])
        if not end or end[1] != prefix:
            return None
        end_digits = end[2]
    first, last = int(digits), int(end_digits)
    if last < first or last - first >= 200:
        return None
    return [f"{prefix}{number:0{len(digits)}d}" for number in range(first, last + 1)]


def exact_set(values: list[str]) -> str:
    return (
        "in.("
        + ",".join(
            json.dumps(value, ensure_ascii=False) for value in dict.fromkeys(values)
        )
        + ")"
    )


async def search_number_rows(
    db: Repository, params: dict[str, str], number: str | None, numbers: list[str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if numbers:
        rows = await db.rows(
            "extraction_connection_rows",
            {**params, "principle_number": exact_set(numbers)},
        )
        return rows, {"kind": "exact_set", "requested": list(dict.fromkeys(numbers))}
    if number is None:
        return await db.rows("extraction_connection_rows", params), {
            "kind": "scoped_page"
        }
    literal = {**params, "principle_number": f"eq.{number}"}
    rows = await db.rows("extraction_connection_rows", literal)
    expanded = expand_number_range(number)
    if rows or not expanded:
        return rows, {"kind": "exact", "input": number}
    if int(params.get("offset", "0")) and await db.rows(
        "extraction_connection_rows",
        {
            **literal,
            "offset": "0",
            "limit": "1",
            "select": "id",
        },
    ):
        return rows, {"kind": "exact", "input": number}
    rows = await db.rows(
        "extraction_connection_rows",
        {**params, "principle_number": exact_set(expanded)},
    )
    return rows, {
        "kind": "number_range",
        "input": number,
        "expanded": expanded,
        "note": "仅返回该项目/批次/页面范围内实际存在的编号，未命中编号不会补造为记录",
    }
