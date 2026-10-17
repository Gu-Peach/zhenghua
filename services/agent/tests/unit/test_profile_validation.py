from __future__ import annotations

import json
from uuid import uuid4

import pymupdf
import pytest

from src.agent.profile_agent.models import Attachment, ExampleCase, TemplateFields
from src.agent.profile_agent.template import RESOURCES, install_cases, render_template
from src.agent.profile_agent.validation import case_files, validate_draft
from src.profiles.package import checksum


def confirm_answers(root, metadata):
    metadata["confirmed_expected"] = {
        case["expected_path"]: checksum((root / case["expected_path"]).read_bytes())
        for case in case_files(root)
    }


@pytest.fixture
def package(tmp_path):
    render_template(
        tmp_path,
        TemplateFields(
            key="optional_negative",
            display_name="负例可选规则",
            company_signals=["SAMPLE"],
            wire_marker="斜线",
            grouping_rule="工作区",
            page_number_rule="业务页号",
            page_naming_rule="工作区与业务页号",
            cross_page_rule="工作区和业务页号匹配",
        ),
    )
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20))
    pix.clear_with(255)
    pixels = pix.tobytes("png")
    (tmp_path / "sample.png").write_bytes(pixels)
    image = Attachment(
        id=uuid4(), filename="sample.png", path="sample.png", checksum=checksum(pixels), mime_type="image/png"
    )
    source = {"attachment_id": image.id, "role": "source_page"}
    target = {"attachment_id": image.id, "role": "target_page"}
    cases = [
        ExampleCase(
            id="classify",
            title="分类",
            stage="classification",
            images=[source],
            expected={"plant_function": "002.C", "drawing_page_number": 1},
        ),
        ExampleCase(
            id="scan",
            title="初扫",
            stage="scan",
            images=[source],
            expected={
                "units": [{"unit_id": "u1", "connections": [{"start": {"terminal": "X3:1"}}]}],
            },
        ),
        ExampleCase(
            id="complete",
            title="补全",
            stage="completion",
            images=[source, target],
            input={"task_id": "task-1"},
            expected={"task_id": "task-1", "end": {"terminal": "XD3:3"}},
        ),
    ]
    install_cases(tmp_path, cases, [image])
    metadata = {
        "generated": True,
        "wizard": {
            "confirmed": {stage: "confirmed" for stage in ("classification", "scan", "completion")},
            "seals": {
                stage: checksum((tmp_path / RESOURCES[resource]).read_bytes())
                for stage, resource in (
                    ("classification", "classification_prompt"),
                    ("scan", "page_scan_prompt"),
                    ("completion", "cross_page_prompt"),
                )
            },
        },
    }
    confirm_answers(tmp_path, metadata)
    return tmp_path, metadata, image, cases


def test_three_confirmed_positive_cases_are_ready_without_negative(package):
    root, metadata, *_ = package
    report = validate_draft(root, metadata)
    assert report.ready and report.issues == [] and report.case_count == 3
    assert all(case["kind"] == "positive" for case in case_files(root))


def test_provided_negative_remains_in_manifest_and_is_validated(package):
    root, metadata, image, _ = package
    negative = ExampleCase(
        id="blank_scan",
        title="不应提取的页面",
        stage="scan",
        kind="negative",
        images=[{"attachment_id": image.id, "role": "source_page"}],
        expected={"units": []},
    )
    install_cases(root, [negative], [image])
    confirm_answers(root, metadata)
    assert validate_draft(root, metadata).ready
    saved = next(case for case in case_files(root) if case["id"] == "blank_scan")
    assert saved["kind"] == "negative" and saved["images"]
    assert json.loads((root / saved["expected_path"]).read_text(encoding="utf-8"))["units"] == []


@pytest.mark.parametrize("confirmed", [False, True])
def test_optional_negative_cannot_bypass_answer_checks(package, confirmed):
    root, metadata, image, cases = package
    # A claimed negative containing a real source terminal remains invalid.
    invalid = cases[1].model_copy(update={"id": "invalid_negative", "kind": "negative"})
    install_cases(root, [invalid], [image])
    if confirmed:
        confirm_answers(root, metadata)
    report = validate_draft(root, metadata)
    codes = {issue.code for issue in report.issues}
    assert not report.ready and "NEGATIVE_EXPECTED_MISMATCH" in codes
    assert ("EXPECTED_UNCONFIRMED" in codes) is not confirmed


def test_optional_negative_does_not_remove_stage_confirmation_requirement(package):
    root, metadata, *_ = package
    metadata["wizard"]["confirmed"].pop("completion")
    report = validate_draft(root, metadata)
    assert not report.ready and "STAGES_UNCONFIRMED" in {issue.code for issue in report.issues}
