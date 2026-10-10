from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path


def load_prompt(prompt_path: Path, override: str | None = None) -> str:
    if override and override.strip():
        return override.strip()
    return prompt_path.read_text(encoding="utf-8").strip()


@dataclass(frozen=True)
class FewShotImage:
    name: str
    mime_type: str
    content: bytes
    role: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class FewShotExample:
    id: str
    title: str
    images: list[FewShotImage] = field(default_factory=list)
    input_json: str | None = None
    expected_json: str = "[]"


def load_few_shot_examples(examples_dir: Path | None) -> list[FewShotExample]:
    """Load multimodal few-shot cases: example drawings + expected wire-table JSON.

    Layout: <examples_dir>/manifest.json lists cases; each case folder holds the
    drawing images and an expected.json with the standard answer.
    """
    return _load_few_shot_examples(examples_dir, section="cases")


def _load_few_shot_examples(
    examples_dir: Path | None,
    *,
    section: str,
) -> list[FewShotExample]:
    if examples_dir is None:
        return []
    manifest_path = examples_dir / "manifest.json"
    if not manifest_path.is_file():
        return []

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    examples: list[FewShotExample] = []
    cases = manifest.get(section)
    if cases is None and section != "cases":
        cases = manifest.get("cases", [])
    for case in cases or []:
        case_id = str(case.get("id") or "").strip()
        if not case_id:
            continue
        expected_path = examples_dir / case.get("expected", f"{case_id}/expected.json")
        if not expected_path.is_file():
            continue
        # Re-serialize compactly so the assistant turn is valid, tight JSON.
        expected_json = json.dumps(
            json.loads(expected_path.read_text(encoding="utf-8")),
            ensure_ascii=False,
        )
        input_json: str | None = None
        input_path_value = case.get("input")
        if input_path_value:
            input_path = examples_dir / input_path_value
            if input_path.is_file():
                input_json = json.dumps(
                    json.loads(input_path.read_text(encoding="utf-8")),
                    ensure_ascii=False,
                )

        images: list[FewShotImage] = []
        for item in case.get("images", []):
            image_path = examples_dir / item["path"]
            if not image_path.is_file():
                continue
            mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
            images.append(
                FewShotImage(
                    name=image_path.name,
                    mime_type=mime_type,
                    content=image_path.read_bytes(),
                    role=item.get("role"),
                    note=item.get("note"),
                )
            )
        if not images:
            continue
        examples.append(
            FewShotExample(
                id=case_id,
                title=str(case.get("title") or case_id),
                images=images,
                input_json=input_json,
                expected_json=expected_json,
            )
        )
    return examples


def load_segment_few_shot_examples(examples_dir: Path | None) -> list[FewShotExample]:
    """Load segmentation image pairs and their merge-decision JSON answers."""
    return load_few_shot_examples(examples_dir)


def load_page_scan_few_shot_examples(examples_dir: Path | None) -> list[FewShotExample]:
    """Load image-backed examples for the single-page scanner."""
    return _load_few_shot_examples(examples_dir, section="stage2_cases")


def load_page_classification_few_shot_examples(examples_dir: Path | None) -> list[FewShotExample]:
    """Load image-backed examples for Plant Function/Page Number classification."""
    return load_few_shot_examples(examples_dir)


def load_cross_page_few_shot_examples(examples_dir: Path | None) -> list[FewShotExample]:
    """Load image-backed examples for single-row cross-page completion."""
    return _load_few_shot_examples(examples_dir, section="stage3_cases")
