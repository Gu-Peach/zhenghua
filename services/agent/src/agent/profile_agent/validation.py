"""Deterministic structural checks. These do not claim that generated answers are visually correct."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pymupdf

from src.domain.models.profiles import ProfileManifest, ProfileRuleSet
from src.profiles.package import checksum, safe_path

from .models import TemplateFields, ValidationIssue, ValidationReport
from .template import MODELS, fixed_schemas


def relative_file(root: Path, value: str) -> Path:
    path = root / safe_path(value)
    if not path.resolve().is_relative_to(root.resolve()) or any(
        p.is_symlink() for p in [path, *path.parents]
    ):
        raise ValueError("资源引用越界或经过符号链接")
    if not path.is_file():
        raise ValueError(f"资源文件不存在：{value}")
    return path


def case_files(root: Path) -> list[dict[str, Any]]:
    manifest = ProfileManifest.model_validate_json((root / "profile.json").read_text(encoding="utf-8"))
    result = []
    for resource, sections in (
        ("classification_examples", ["cases"]),
        ("wiring_examples", ["stage2_cases", "stage3_cases"]),
    ):
        directory = root / safe_path(manifest.resources[resource])
        value = json.loads(
            relative_file(root, f"{manifest.resources[resource]}/manifest.json").read_text(encoding="utf-8")
        )
        for section in sections:
            entries = value.get(section, [])
            if not isinstance(entries, list):
                raise ValueError("案例列表必须为数组")
            seen = set()
            for case in entries:
                identifier = case["id"]
                if identifier in seen:
                    raise ValueError("同阶段案例ID重复")
                seen.add(identifier)
                expected = directory / safe_path(case.get("expected") or f"{identifier}/expected.json")
                expected_path = expected.relative_to(root).as_posix()
                images = []
                for image in case.get("images", []):
                    images.append(
                        {**image, "path": (directory / safe_path(image["path"])).relative_to(root).as_posix()}
                    )
                result.append(
                    {
                        "id": identifier,
                        "stage": {
                            "cases": "classification",
                            "stage2_cases": "scan",
                            "stage3_cases": "completion",
                        }[section],
                        "kind": case.get("kind"),
                        "expected_path": expected_path,
                        "images": images,
                        "input_path": (directory / safe_path(case["input"])).relative_to(root).as_posix()
                        if case.get("input")
                        else None,
                    }
                )
    return result


def check_structure(root: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    def error(code: str, path: str | None, message: str) -> None:
        issues.append(ValidationIssue(code=code, path=path, message=message))

    try:
        manifest = ProfileManifest.model_validate_json(
            relative_file(root, "profile.json").read_text(encoding="utf-8")
        )
        if manifest.resource_mode != "packaged":
            raise ValueError("草稿必须为自包含资源包")
        required = {
            "classification_prompt",
            "page_scan_prompt",
            "cross_page_prompt",
            "classification_examples",
            "wiring_examples",
            "routing_rules",
        }
        if not required.issubset(manifest.resources):
            raise ValueError("缺少提取阶段必需资源")
        for value in manifest.resources.values():
            path = root / safe_path(value)
            if not path.resolve().is_relative_to(root.resolve()) or not path.exists():
                raise ValueError("资源缺失或越界")
        if any(path.is_symlink() for path in root.rglob("*")):
            raise ValueError("资源包不能包含符号链接")
        rules = ProfileRuleSet.model_validate_json(
            relative_file(root, manifest.resources["routing_rules"]).read_text(encoding="utf-8")
        )
        if rules.profile_key != manifest.key or rules.extraction.output_contract != "wiring_connection_v1":
            raise ValueError("规则身份或输出契约不一致")
        resources = {name for values in rules.extraction.dynamic_resources.values() for name in values}
        if not resources.issubset(manifest.resources):
            raise ValueError("动态资源引用不存在")
        if json.loads(relative_file(root, "schema.json").read_text(encoding="utf-8")) != fixed_schemas():
            raise ValueError("提取阶段Schema不能修改")
        cases = case_files(root)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        error("PACKAGE_STRUCTURE", None, f"规则结构无效：{str(exc)[:1000]}")
        return issues
    for case in cases:
        path = case["expected_path"]
        try:
            payload = json.loads(relative_file(root, path).read_text(encoding="utf-8"))
            MODELS[case["stage"]].model_validate(payload)
            if not case["images"]:
                raise ValueError("案例必须有实际图片，不能只有文字")
            for image in case["images"]:
                file = relative_file(root, image["path"])
                if file.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                    raise ValueError("案例引用必须是图片")
                pixmap = pymupdf.Pixmap(file.read_bytes())
                if not pixmap.width or not pixmap.height:
                    raise ValueError("案例图片无法解码")
            if case["stage"] == "completion":
                if not case["input_path"]:
                    raise ValueError("补全案例必须提供指定连接的任务输入")
                task = json.loads(relative_file(root, case["input_path"]).read_text(encoding="utf-8"))
                if not isinstance(task, dict) or not task.get("task_id"):
                    raise ValueError("补全任务输入缺少task_id")
                roles = {image.get("role") for image in case["images"]}
                needed = (
                    {"target_page"}
                    if rules.extraction.cross_page_input_mode == "target_only"
                    else {"source_page", "target_page"}
                )
                if not needed.issubset(roles):
                    raise ValueError("补全案例图片不满足所选跨页输入模式")
        except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
            error("CASE_INVALID", path, f"案例{case['id']}：{str(exc)[:1000]}")
    return issues


def validate_draft(root: Path, metadata: dict[str, Any]) -> ValidationReport:
    issues = check_structure(root)
    if issues:
        return ValidationReport(ready=False, issues=issues)
    if metadata.get("generated"):
        fields = TemplateFields.model_validate_json((root / "template.json").read_text(encoding="utf-8"))
        for name in (
            "company_signals",
            "wire_marker",
            "grouping_rule",
            "page_number_rule",
            "page_naming_rule",
            "cross_page_rule",
        ):
            value = getattr(fields, name)
            if not value or isinstance(value, str) and not value.strip():
                issues.append(
                    ValidationIssue(
                        code="TEMPLATE_INCOMPLETE", path="template.json", message=f"待补充图纸依据：{name}"
                    )
                )
        if fields.open_questions:
            issues.append(
                ValidationIssue(
                    code="OPEN_QUESTIONS", path="template.json", message="尚有待用户补充/确认的问题"
                )
            )
        if "adapter_change_required" in {fields.reference_mode, fields.page_number_mode}:
            issues.append(
                ValidationIssue(
                    code="ADAPTER_REQUIRED",
                    path="template.json",
                    message="当前适配器不能表达该引用/页码格式，需要额外代码适配，不能仅靠Prompt宣称支持",
                )
            )
    cases = case_files(root)
    stages = set()
    negative = False
    positive_scan = False
    for case in cases:
        stages.add(case["stage"])
        path = case["expected_path"]
        payload = json.loads(relative_file(root, path).read_text(encoding="utf-8"))
        inferred_negative = (
            case["stage"] == "scan"
            and not payload.get("units")
            or case["stage"] == "completion"
            and not (payload.get("end") or {}).get("terminal")
            or case["stage"] == "classification"
            and (payload.get("blank") or payload.get("non_wiring"))
        )
        negative = negative or case["kind"] == "negative" or bool(inferred_negative)
        if case["stage"] == "scan" and case["kind"] != "negative":
            positive_scan = positive_scan or any(
                (connection.get("start") or {}).get("terminal")
                for unit in payload.get("units", [])
                for connection in unit.get("connections", [])
            )
        if metadata.get("confirmed_expected", {}).get(path) != checksum(
            relative_file(root, path).read_bytes()
        ):
            issues.append(
                ValidationIssue(
                    code="EXPECTED_UNCONFIRMED", path=path, message="新增或修改的Expected尚未由用户确认"
                )
            )
    for stage in ("classification", "scan", "completion"):
        if stage not in stages:
            issues.append(ValidationIssue(code="CASE_MISSING", message=f"缺少{stage}实际图片案例"))
    if not negative:
        issues.append(
            ValidationIssue(
                code="NEGATIVE_CASE_MISSING", message="需提供至少一个不应提取或无法唯一补全的负例"
            )
        )
    if not positive_scan:
        issues.append(
            ValidationIssue(code="POSITIVE_CASE_MISSING", message="需提供至少一个包含实际来源端子的初扫正例")
        )
    return ValidationReport(ready=not issues, issues=issues, case_count=len(cases))
