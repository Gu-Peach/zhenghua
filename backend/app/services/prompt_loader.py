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
    expected_json: str = "[]"


def load_few_shot_examples(examples_dir: Path | None) -> list[FewShotExample]:
    """Load multimodal few-shot cases: example drawings + expected wire-table JSON.

    Layout: <examples_dir>/manifest.json lists cases; each case folder holds the
    drawing images and an expected.json with the standard answer.
    """
    if examples_dir is None:
        return []
    manifest_path = examples_dir / "manifest.json"
    if not manifest_path.is_file():
        return []

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    examples: list[FewShotExample] = []
    for case in manifest.get("cases", []):
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
                expected_json=expected_json,
            )
        )
    return examples


def load_segment_few_shot_examples(examples_dir: Path | None) -> list[FewShotExample]:
    """Load segmentation image pairs and their merge-decision JSON answers."""
    return load_few_shot_examples(examples_dir)
