"""Formal ZH package preserves the user-verified crop resources and installed policy."""

from __future__ import annotations

import json
from pathlib import Path

from src.agent.extraction_agent.profiles.extraction_policy import default_extraction_policies
from src.agent.extraction_agent.profiles.zh.policy import ZhExtractionPolicy
from src.agent.profile_agent.validation import check_structure
from src.profiles import ProfileRegistry
from src.profiles.package import build_package, verify_package

ROOT = Path(__file__).resolve().parents[4]
PROFILES = ROOT / "services/agent/src/agent/extraction_agent/profiles"
PROMPTS = ROOT / "services/agent/src/agent/extraction_agent/prompts/zh"


def _registry(root: Path = PROFILES) -> ProfileRegistry:
    registry = ProfileRegistry(profile_root=root, workspace_root=ROOT, allow_legacy_references=True)
    registry.load_all()
    return registry


def test_formal_zh_uses_single_prompt_source_and_installed_policy() -> None:
    registry = _registry()
    formal = registry.bind("zh")
    assert formal.profile.version == "2.3.0"
    assert formal.adapter == "zh_native"
    assert isinstance(default_extraction_policies().resolve(formal.adapter), ZhExtractionPolicy)
    expected = {
        "classification_prompt": PROMPTS / "page_classification.md",
        "page_scan_prompt": PROMPTS / "page_scan_index.md",
        "cross_page_prompt": PROMPTS / "page_connection_completion.md",
        "classification_examples": PROMPTS / "examples_page_classification",
        "wiring_examples": PROMPTS / "examples_wiring/002c",
    }
    for resource, path in expected.items():
        assert formal.resource(resource) == path
    assert not (PROFILES / "zh/resources").exists()
    assert formal.rules.extraction.cross_page_input_mode == "target_only"
    cases = json.loads((formal.resource("wiring_examples") / "manifest.json").read_text(encoding="utf-8"))
    assert len(cases["stage2_cases"]) == 1
    assert len(cases["stage3_cases"]) == 7


def test_formal_zh_can_be_packaged_without_executable_python(tmp_path: Path) -> None:
    destination = tmp_path / "profiles/selected"
    manifest = build_package(_registry().resolve("zh"), destination)
    verify_package(destination, manifest)
    assert check_structure(destination) == []
    assert not any(Path(entry.path).suffix in {".py", ".pyc"} for entry in manifest.files)
    frozen = _registry(destination.parent).bind("zh")
    assert frozen.profile.version == "2.3.0"
    assert frozen.adapter == "zh_native"
    assert frozen.rules.extraction.cross_page_input_mode == "target_only"
    assert json.loads(frozen.resource("completion_view_rules").read_text(encoding="utf-8"))["enabled"]


def test_packaged_classification_rejects_conflicting_legacy_alias(tmp_path: Path) -> None:
    destination = tmp_path / "profiles/selected"
    build_package(_registry().resolve("zh"), destination)
    frozen = _registry(destination.parent).bind("zh")
    expected = frozen.resource("classification_examples") / "006m01_identity/expected.json"
    payload = json.loads(expected.read_text(encoding="utf-8"))
    payload["drawing_page_number"] = payload["page_number"] + 1
    expected.write_text(json.dumps(payload), encoding="utf-8")
    assert any(issue.code == "CASE_INVALID" for issue in check_structure(destination))
