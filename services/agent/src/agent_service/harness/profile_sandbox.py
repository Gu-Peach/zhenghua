from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path, PurePosixPath

from ..domain.models.improvement import CandidatePatchOperation

_TEXT_EXTENSIONS = {".md", ".json", ".yaml", ".yml", ".txt"}


class ProfileSandbox:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def create(self, *, candidate_id: str, source_profile: Path) -> Path:
        target = (self.root / candidate_id).resolve()
        if self.root not in target.parents:
            raise ValueError("Candidate path escapes the sandbox root.")
        if target.exists():
            raise FileExistsError(target)
        source = source_profile.resolve()
        if not source.is_dir() or any(path.is_symlink() for path in source.rglob("*")):
            raise ValueError("Profile sandbox source must be a directory without symlinks.")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)
        return target

    def apply(self, sandbox: Path, operations: list[CandidatePatchOperation]) -> str:
        root = sandbox.resolve()
        if self.root != root and self.root not in root.parents:
            raise ValueError("Sandbox is outside the configured root.")
        suggestions = root / ".suggestions"
        for index, operation in enumerate(operations, start=1):
            relative = self._safe_relative(operation.relative_path)
            target = (root / Path(*relative.parts)).resolve()
            if root not in target.parents and target != root:
                raise ValueError("Patch path escapes the candidate sandbox.")
            if operation.op == "suggest_code_change":
                suggestions.mkdir(parents=True, exist_ok=True)
                (suggestions / f"{index:03d}.json").write_text(
                    json.dumps(operation.model_dump(mode="json"), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                continue
            if target.suffix.lower() not in _TEXT_EXTENSIONS:
                raise ValueError(f"Automated candidate patch cannot edit {target.suffix!r} files.")
            if operation.op == "remove":
                if target.is_file():
                    target.unlink()
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(operation.content or "", encoding="utf-8")
        return self.checksum(root)

    @staticmethod
    def _safe_relative(value: str) -> PurePosixPath:
        path = PurePosixPath(value.replace("\\", "/"))
        if (
            path.is_absolute()
            or not path.parts
            or ":" in path.parts[0]
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError(f"Unsafe profile patch path: {value!r}.")
        return path

    @staticmethod
    def checksum(root: Path) -> str:
        digest = hashlib.sha256()
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            digest.update(path.relative_to(root).as_posix().encode("utf-8"))
            digest.update(path.read_bytes())
        return f"sha256:{digest.hexdigest()}"
