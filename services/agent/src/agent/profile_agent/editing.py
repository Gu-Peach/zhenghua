"""Published-package drafts share the existing Profile Agent tools and mutation store."""

from __future__ import annotations

import base64
import io
import json
import mimetypes
import stat
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from uuid import UUID

from src.profiles.package import PackageManifest, checksum, safe_path, verify_package

from .models import DraftCreate, EditPackage, ProfileActor, ProfileEditState, ProfileError, ProfileImport
from .store import DraftStore
from .template import fixed_schemas
from .validation import case_files, edit_content_checksum, validate_draft


class ProfileEditor:
    def __init__(self, store: DraftStore) -> None:
        self.store = store

    def import_profile(self, body: ProfileImport, actor: ProfileActor) -> ProfileEditState:
        files = None
        if body.content_base64 is not None:
            try:
                content = base64.b64decode(body.content_base64, validate=True)
                if len(content) > 30 * 1024 * 1024 or checksum(content) != body.source_checksum:
                    raise ValueError("Archive size or checksum mismatch")
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    entries = archive.infolist()
                    if len(entries) > 500 or sum(e.file_size for e in entries) > 30 * 1024 * 1024:
                        raise ValueError("Archive expansion limit")
                    if len({e.filename for e in entries}) != len(entries):
                        raise ValueError("Duplicate entries")
                    for entry in entries:
                        safe_path(entry.filename)
                        if stat.S_ISLNK(entry.external_attr >> 16):
                            raise ValueError("Symlink entry")
                    files = {e.filename: archive.read(e) for e in entries}
                manifest = PackageManifest.model_validate_json(files["manifest.json"])
                if set(files) != {"manifest.json", *(entry.path for entry in manifest.files)}:
                    raise ValueError("Unlisted archive entries")
                if (manifest.profile_key, manifest.profile_version) != (
                    body.profile_key,
                    body.profile_version,
                ):
                    raise ValueError("Source identity mismatch")
                with tempfile.TemporaryDirectory(prefix="profile-edit-import-") as temporary:
                    root = Path(temporary)
                    for name, data in files.items():
                        target = root / safe_path(name)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(data)
                    verify_package(root, manifest)
            except (ValueError, KeyError, OSError, RuntimeError, zipfile.BadZipFile) as exc:
                raise ProfileError("PROFILE_IMPORT_INVALID", "规则包校验失败，无法建立编辑草稿", 422) from exc
        source = {
            "profile_id": str(body.profile_id),
            "key": body.profile_key,
            "version": body.profile_version,
            "checksum": body.source_checksum,
            "schema_checksum": checksum(json.dumps(fixed_schemas(), sort_keys=True).encode()),
        }
        if files is not None and json.loads(files.get("schema.json", b"{}")) != fixed_schemas():
            # The immutable source is verified first. Only the new draft receives the code-owned protocol.
            files["schema.json"] = json.dumps(fixed_schemas(), ensure_ascii=False, indent=2).encode()
            source["schema_upgraded"] = "true"
        view = self.store.create(
            DraftCreate(
                draft_id=body.draft_id,
                key=body.profile_key,
                display_name=body.display_name,
                source_profile=body.profile_key,
                source_version=body.profile_version,
            ),
            actor,
            package_files=files,
            source=source,
        )
        _, root, _ = self.store.snapshot(body.draft_id, actor, view.revision)
        if json.loads((root / "schema.json").read_text(encoding="utf-8")) != fixed_schemas():

            def upgrade(target: Path, meta: dict[str, Any]) -> dict[str, Any]:
                (target / "schema.json").write_text(
                    json.dumps(fixed_schemas(), ensure_ascii=False, indent=2), encoding="utf-8"
                )
                meta["source"]["schema_upgraded"] = "true"
                meta["source"]["schema_checksum"] = source["schema_checksum"]
                return {"action": "upgrade_editor_schema", "requires_review": True}

            self.store.mutate(
                body.draft_id, actor, view.revision, f"editor-schema:{source['schema_checksum']}", upgrade
            )
        return self.state(body.draft_id, actor)

    def state(self, draft: UUID, actor: ProfileActor) -> ProfileEditState:
        view = self.store.get(draft, actor)
        _, root, meta = self.store.snapshot(draft, actor, view.revision)
        if not meta.get("editor"):
            raise ProfileError("EDITOR_DRAFT_REQUIRED", "请先从已有规则创建编辑草稿", 422)
        texts, images = [], []
        for name in self.store.inventory(root):
            if name.startswith("attachments/"):
                continue
            file = self.store.file(root, name)
            if file.suffix in {".md", ".json", ".txt"}:
                texts.append(
                    {
                        "path": name,
                        "content": file.read_text(encoding="utf-8"),
                        "checksum": checksum(file.read_bytes()),
                    }
                )
            elif file.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                mime = mimetypes.guess_type(name)[0] or "image/png"
                images.append(
                    {
                        "path": name,
                        "url": f"data:{mime};base64,{base64.b64encode(file.read_bytes()).decode()}",
                    }
                )
        return ProfileEditState(
            draft=view,
            package=EditPackage.model_validate(
                {
                    "manifest": json.loads((root / "profile.json").read_text(encoding="utf-8")),
                    "files": texts,
                    "images": images,
                }
            ),
            validation=validate_draft(root, meta),
            proposals=self.store.proposals(draft, actor),
            history=self.store.history(draft, actor),
            changed=edit_content_checksum(root) != meta["editor"].get("baseline_content"),
        )

    def accept(self, draft: UUID, actor: ProfileActor, revision: int) -> ProfileEditState:
        """The user reviews the exact current rules/Expected; no model may perform this action."""
        self.state(draft, actor)

        def apply(root: Path, meta: dict[str, Any]) -> dict[str, Any]:
            meta["confirmed_expected"] = {
                c["expected_path"]: checksum(self.store.file(root, c["expected_path"]).read_bytes())
                for c in case_files(root)
            }
            meta["editor"]["accepted_content"] = edit_content_checksum(root)
            return {"action": "accept_editor_revision", "reviewed_revision": revision}

        self.store.mutate(draft, actor, revision, f"editor-review:{revision}", apply)
        return self.state(draft, actor)
