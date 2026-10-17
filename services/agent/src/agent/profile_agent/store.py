"""Local development draft repository. Production rule files and business tables are read-only."""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pymupdf

from src.domain.models.profiles import ProfileSnapshot
from src.profiles.package import build_package, checksum, safe_path
from src.profiles.registry import ProfileRegistry

from .models import (
    Attachment,
    DraftCreate,
    DraftView,
    FileDiff,
    FileEdit,
    PdfSampleInfo,
    ProfileActor,
    ProfileError,
    Proposal,
    ProposalRequest,
    TemplateFields,
)
from .template import COMMON_POLICY, canonical_expected, json_write, render_template


class DraftStore:
    """Immutable filesystem revisions plus transactional SQLite heads/audit/confirmation receipts."""

    def __init__(self, root: Path, registry: ProfileRegistry) -> None:
        self.root, self.registry = root.resolve(), registry
        self.root.mkdir(parents=True, exist_ok=True)
        if root.is_symlink():
            raise ValueError("Draft root cannot be a symlink")
        with self._db() as db:
            db.executescript("""
              create table if not exists drafts(id text primary key,owner text not null,revision int not null,
                path text not null,checksum text not null,metadata text not null);
              create table if not exists revisions(draft text,revision int,path text,checksum text,
                metadata text,
                operation text,audit text,created_at text default CURRENT_TIMESTAMP,
                primary key(draft,revision),unique(draft,operation));
              create table if not exists proposals(id text primary key,draft text,owner text,payload text);
              create table if not exists turns(draft text,turn_id text,request_hash text,payload text,
                primary key(draft,turn_id));
            """)

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.root / "drafts.sqlite3", timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _owned(db: sqlite3.Connection, draft: UUID, actor: ProfileActor) -> sqlite3.Row:
        row = db.execute("select * from drafts where id=?", (str(draft),)).fetchone()
        if row is None:
            raise ProfileError("DRAFT_NOT_FOUND", "规则草稿不存在", 404)
        if row["owner"] != str(actor.user_id):
            raise ProfileError("ACCESS_DENIED", "无权访问该规则草稿", 403)
        return cast(sqlite3.Row, row)

    def _path(self, value: str) -> Path:
        result = self.root / safe_path(value)
        if not result.resolve().is_relative_to(self.root) or any(
            p.is_symlink() for p in [result, *result.parents]
        ):
            raise ProfileError("UNSAFE_PATH", "草稿目录路径无效", 422)
        return result

    @staticmethod
    def file(root: Path, value: str) -> Path:
        try:
            path = root / safe_path(value)
        except ValueError as exc:
            raise ProfileError("UNSAFE_PATH", "仅允许草稿内的相对资源路径", 422) from exc
        if not path.resolve().is_relative_to(root.resolve()) or any(
            p.is_symlink() for p in [path, *path.parents]
        ):
            raise ProfileError("UNSAFE_PATH", "资源不能越界或经过符号链接", 422)
        return path

    @staticmethod
    def inventory(root: Path) -> list[str]:
        paths = []
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ProfileError("UNSAFE_PATH", "草稿不能含符号链接", 422)
            if path.is_file():
                paths.append(path.relative_to(root).as_posix())
        return paths

    @classmethod
    def digest(cls, root: Path, metadata: dict[str, Any]) -> str:
        digest = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode())
        for value in cls.inventory(root):
            digest.update(value.encode())
            digest.update(b"\0")
            digest.update(cls.file(root, value).read_bytes())
        return "sha256:" + digest.hexdigest()

    def _verified(self, row: sqlite3.Row) -> tuple[Path, dict[str, Any]]:
        root, meta = self._path(row["path"]), json.loads(row["metadata"])
        if self.digest(root, meta) != row["checksum"]:
            raise ProfileError("DRAFT_CHANGED_EXTERNALLY", "草稿文件已在工具外修改，请重新建立草稿核对", 409)
        return root, meta

    def _view(self, row: sqlite3.Row) -> DraftView:
        root, meta = self._verified(row)
        manifest = json.loads((root / "profile.json").read_text(encoding="utf-8"))
        return DraftView(
            draft_id=row["id"],
            revision=row["revision"],
            checksum=row["checksum"],
            key=manifest["key"],
            version=manifest["version"],
            source=meta.get("source"),
            files=self.inventory(root),
            attachments=meta.get("attachments", []),
            template=TemplateFields.model_validate_json((root / "template.json").read_text(encoding="utf-8"))
            if meta.get("generated")
            else None,
            warnings=["草稿及导出包未正式发布，也未改变任何项目的规则版本。"],
        )

    def get(self, draft: UUID, actor: ProfileActor) -> DraftView:
        with self._db() as db:
            return self._view(self._owned(db, draft, actor))

    def list_drafts(self, actor: ProfileActor) -> list[DraftView]:
        with self._db() as db:
            return [
                self._view(row)
                for row in db.execute(
                    "select * from drafts where owner=? order by rowid desc limit 100", (str(actor.user_id),)
                )
            ]

    def root_for(self, draft: UUID, actor: ProfileActor) -> tuple[Path, dict[str, Any]]:
        with self._db() as db:
            return self._verified(self._owned(db, draft, actor))

    def _fresh_source(self, key: str, version: str | None) -> ProfileSnapshot:
        current = ProfileRegistry(
            profile_root=self.registry.profile_root,
            workspace_root=self.registry.workspace_root,
            allow_legacy_references=self.registry.allow_legacy_references,
        )
        current.load_all(strict=False)
        return current.resolve(key, version, allow_experimental=True)

    def snapshot(
        self, draft: UUID, actor: ProfileActor, revision: int
    ) -> tuple[DraftView, Path, dict[str, Any]]:
        with self._db() as db:
            row = self._owned(db, draft, actor)
            if row["revision"] != revision:
                raise ProfileError("VERSION_CONFLICT", "草稿修订已变化，请重新读取", 409)
            root, meta = self._verified(row)
            return self._view(row), root, meta

    def create(self, request: DraftCreate, actor: ProfileActor) -> DraftView:
        with self._db() as db:
            db.execute("begin immediate")
            existing = db.execute("select * from drafts where id=?", (str(request.draft_id),)).fetchone()
            if existing:
                row = self._owned(db, request.draft_id, actor)
                if json.loads(row["metadata"])["create"] != request.model_dump(mode="json"):
                    raise ProfileError("CREATE_CONFLICT", "相同草稿ID的创建参数已变化", 409)
                return self._view(row)
            relative = f"{actor.user_id}/{request.draft_id}/revisions/{uuid4()}"
            root = self._path(relative)
            meta: dict[str, Any] = {
                "create": request.model_dump(mode="json"),
                "attachments": [],
                "confirmed_expected": {},
                "generated": request.source_profile is None,
            }
            if request.source_profile:
                snapshot = self._fresh_source(request.source_profile, request.source_version)
                if request.key != snapshot.manifest.key:
                    raise ProfileError("KEY_MISMATCH", "编辑现有规则需保持key；新标准请使用通用模板新建", 422)
                build_package(snapshot, root)
                latest = self._fresh_source(snapshot.manifest.key, snapshot.manifest.version)
                if latest.checksum != snapshot.checksum:
                    raise ProfileError("SOURCE_CHANGED", "复制期间源规则发生变化，请待修改完成后重试", 409)
                (root / "manifest.json").unlink()
                manifest = json.loads((root / "profile.json").read_text(encoding="utf-8"))
                major, minor, patch, _ = snapshot.manifest.semantic_version
                manifest["version"] = f"{major}.{minor}.{patch + 1}"
                manifest["status"] = "experimental"
                json_write(root / "profile.json", manifest)
                meta["source"] = {
                    "key": snapshot.manifest.key,
                    "version": snapshot.manifest.version,
                    "checksum": snapshot.checksum,
                }
                # Only the unchanged existing case answers inherit their baseline acceptance.
                from .validation import case_files

                for item in case_files(root):
                    file = self.file(root, item["expected_path"])
                    payload = json.loads(file.read_text(encoding="utf-8"))
                    canonical = canonical_expected(item["stage"], payload)
                    if canonical != payload:
                        json_write(file, canonical)
                    meta["confirmed_expected"][item["expected_path"]] = checksum(
                        self.file(root, item["expected_path"]).read_bytes()
                    )
            else:
                root.mkdir(parents=True)
                render_template(root, TemplateFields(key=request.key, display_name=request.display_name))
            fingerprint = self.digest(root, meta)
            values = (str(request.draft_id), str(actor.user_id), 1, relative, fingerprint, json.dumps(meta))
            db.execute("insert into drafts values(?,?,?,?,?,?)", values)
            db.execute(
                "insert into revisions(draft,revision,path,checksum,metadata,operation,audit) "
                "values(?,?,?,?,?,?,?)",
                (str(request.draft_id), 1, relative, fingerprint, json.dumps(meta), "create", "{}"),
            )
            return self._view(self._owned(db, request.draft_id, actor))

    def mutate(
        self,
        draft: UUID,
        actor: ProfileActor,
        revision: int,
        operation: str,
        action: Callable[[Path, dict[str, Any]], dict[str, Any]],
        fingerprint: str | None = None,
    ) -> DraftView:
        with self._db() as db:
            db.execute("begin immediate")
            row = self._owned(db, draft, actor)
            return self._mutate_locked(db, row, draft, actor, revision, operation, action, fingerprint)

    def _mutate_locked(
        self,
        db: sqlite3.Connection,
        row: sqlite3.Row,
        draft: UUID,
        actor: ProfileActor,
        revision: int,
        operation: str,
        action: Callable[[Path, dict[str, Any]], dict[str, Any]],
        fingerprint: str | None = None,
    ) -> DraftView:
        receipt = db.execute(
            "select * from revisions where draft=? and operation=?", (str(draft), operation)
        ).fetchone()
        if receipt:
            if json.loads(receipt["audit"]).get("request_fingerprint") != fingerprint:
                raise ProfileError("OPERATION_CONFLICT", "相同操作标识的内容已变化", 409)
            if receipt["revision"] != row["revision"]:
                raise ProfileError("RECEIPT_STALE", "该操作已执行，草稿随后又有更新，请读取最新修订", 409)
            return self._view(row)
        if row["revision"] != revision:
            raise ProfileError("VERSION_CONFLICT", "草稿已更新，请重新读取后修改", 409)
        source, meta = self._verified(row)
        relative = f"{actor.user_id}/{draft}/revisions/{uuid4()}"
        target = self._path(relative)
        shutil.copytree(source, target)
        audit = action(target, meta)
        audit["request_fingerprint"] = fingerprint
        self.basic_check(target)
        fingerprint = self.digest(target, meta)
        db.execute(
            "insert into revisions(draft,revision,path,checksum,metadata,operation,audit) "
            "values(?,?,?,?,?,?,?)",
            (str(draft), revision + 1, relative, fingerprint, json.dumps(meta), operation, json.dumps(audit)),
        )
        db.execute(
            "update drafts set revision=?,path=?,checksum=?,metadata=? where id=?",
            (revision + 1, relative, fingerprint, json.dumps(meta), str(draft)),
        )
        return self._view(self._owned(db, draft, actor))

    @staticmethod
    def basic_check(root: Path) -> None:
        from .validation import check_structure

        errors = check_structure(root)
        if errors:
            raise ProfileError("PROFILE_INVALID", "；".join(item.message for item in errors)[:2000], 422)

    def read(
        self, draft: UUID, actor: ProfileActor, path: str, offset: int = 0, limit: int = 16000
    ) -> dict[str, Any]:
        root, _ = self.root_for(draft, actor)
        file = self.file(root, path)
        if not file.is_file() or file.suffix not in {".md", ".json", ".txt"}:
            raise ProfileError("FILE_NOT_READABLE", "仅可读取当前草稿的文本规则/案例", 404)
        content = file.read_text(encoding="utf-8")
        return {
            "path": path,
            "checksum": checksum(file.read_bytes()),
            "text": content[offset : offset + limit],
            "offset": offset,
            "next_offset": offset + limit if offset + limit < len(content) else None,
            "total_characters": len(content),
        }

    def images(self, draft: UUID, actor: ProfileActor, paths: list[str]) -> list[dict[str, str]]:
        root, _ = self.root_for(draft, actor)
        result = []
        for path in paths:
            file = self.file(root, path)
            if not file.is_file() or file.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                raise ProfileError("IMAGE_NOT_FOUND", "图片不属于该草稿", 404)
            mime = (
                "image/jpeg"
                if file.suffix.lower() in {".jpg", ".jpeg"}
                else "image/webp"
                if file.suffix.lower() == ".webp"
                else "image/png"
            )
            result.append(
                {
                    "path": path,
                    "data_url": f"data:{mime};base64,{base64.b64encode(file.read_bytes()).decode()}",
                }
            )
        return result

    def attach(
        self, draft: UUID, actor: ProfileActor, revision: int, image_id: UUID, filename: str, content: bytes
    ) -> DraftView:
        if not content or len(content) > 10 * 1024 * 1024:
            raise ProfileError("IMAGE_SIZE", "图片必须非空且不超过10MiB", 422)
        try:
            pixmap = pymupdf.Pixmap(content)
            if pixmap.width * pixmap.height > 40_000_000:
                raise ValueError("Image dimensions too large")
            normalized = pixmap.tobytes("png")
        except Exception as exc:
            raise ProfileError("INVALID_IMAGE", "不能读取此图片或图片尺寸过大", 422) from exc

        def write(root: Path, meta: dict[str, Any]) -> dict[str, Any]:
            if any(a["id"] == str(image_id) for a in meta["attachments"]):
                raise ProfileError("ATTACHMENT_CONFLICT", "图片ID已使用", 409)
            path = f"attachments/{image_id}.png"
            self.file(root, path).parent.mkdir(parents=True, exist_ok=True)
            self.file(root, path).write_bytes(normalized)
            meta["attachments"].append(
                Attachment(
                    id=image_id,
                    filename=Path(filename).name[:200],
                    path=path,
                    checksum=checksum(normalized),
                    mime_type="image/png",
                ).model_dump(mode="json")
            )
            return {"action": "attach", "path": path, "checksum": checksum(normalized)}

        return self.mutate(draft, actor, revision, f"attach:{image_id}:{checksum(content)}", write)

    def attach_pdf_sample(
        self, draft: UUID, actor: ProfileActor, revision: int, sample: PdfSampleInfo, images: list[bytes]
    ) -> DraftView:
        """Commit only selected page PNGs and their provenance in one immutable revision."""
        if len(images) != len(sample.pages):
            raise ProfileError("PDF_SAMPLE_INVALID", "抽样图片数量与页码不一致", 422)

        def write(root: Path, meta: dict[str, Any]) -> dict[str, Any]:
            for page, content in zip(sample.pages, images, strict=True):
                path = f"attachments/{page.attachment_id}.png"
                self.file(root, path).parent.mkdir(parents=True, exist_ok=True)
                self.file(root, path).write_bytes(content)
                meta["attachments"].append(
                    Attachment(
                        id=page.attachment_id,
                        filename=f"{Path(sample.filename).stem[:160]}_pdf_{page.pdf_page_number:04d}.png",
                        path=path,
                        checksum=checksum(content),
                        mime_type="image/png",
                        origin="pdf_sample",
                    ).model_dump(mode="json")
                )
            info = sample.model_dump(mode="json")
            meta.setdefault("pdf_samples", {})[str(sample.request_id)] = info
            meta["classification_pdf_sample"] = info
            meta["wizard"] = {"candidates": {}, "confirmed": {}, "requests": {}, "seals": {}}
            meta["confirmed_expected"] = {}
            meta.setdefault("conversation", {})["active_stage"] = "classification"
            return {"action": "pdf_sample", "sample": info}

        return self.mutate(
            draft,
            actor,
            revision,
            f"pdf-sample:{sample.request_id}",
            write,
            checksum(sample.model_dump_json().encode()),
        )

    @classmethod
    def apply_files(cls, root: Path, edits: list[FileEdit]) -> list[FileDiff]:
        manifest = json.loads((root / "profile.json").read_text(encoding="utf-8"))
        protected = {
            "profile.json",
            "schema.json",
            "manifest.json",
            "template.json",
            manifest["resources"].get("template_common"),
        }
        changes = []
        seen = set()
        for edit in edits:
            if edit.path in protected or edit.path in seen:
                raise ProfileError(
                    "PROTECTED_FILE",
                    "模板身份、Schema和公共约束不能由编辑工具改写，且每批文件只能出现一次",
                    422,
                )
            seen.add(edit.path)
            path = cls.file(root, edit.path)
            if path.suffix not in {".md", ".json"} or edit.path.startswith("attachments/"):
                raise ProfileError("EDIT_NOT_ALLOWED", "工具只能编辑草稿中的Markdown/JSON规则及案例", 422)
            allowed = any(
                edit.path == value or edit.path.startswith(value + "/")
                for value in manifest["resources"].values()
            )
            if not allowed:
                raise ProfileError("EDIT_NOT_ALLOWED", "文件不属于该Profile声明的资源", 422)
            before = path.read_text(encoding="utf-8") if path.is_file() else None
            if (checksum(path.read_bytes()) if path.is_file() else None) != edit.before_checksum:
                raise ProfileError("FILE_CONFLICT", "文件摘要已变化，请先读取最新文件", 409)
            if edit.operation == "delete":
                if before is None:
                    raise ProfileError("FILE_NOT_FOUND", "要删除的资源不存在", 404)
                path.unlink()
            else:
                if edit.content is None or "\x00" in edit.content:
                    raise ProfileError("INVALID_CONTENT", "写入操作必须提供有效文本", 422)
                if path.suffix == ".json":
                    after_json = json.loads(edit.content)
                    if edit.path == manifest["resources"]["routing_rules"] and before:
                        prior = json.loads(before)
                        for key in ("profile_key", "schema_version"):
                            if after_json.get(key) != prior.get(key):
                                raise ProfileError("PROTECTED_CONTRACT", "不能改变规则身份或输出协议", 422)
                        for key in ("output_contract", "workflow", "dynamic_resources"):
                            if after_json.get("extraction", {}).get(key) != prior["extraction"].get(key):
                                raise ProfileError("PROTECTED_CONTRACT", "不能改变提取工作流或输出协议", 422)
                if before and before.startswith(COMMON_POLICY) and not edit.content.startswith(COMMON_POLICY):
                    raise ProfileError("PROTECTED_CONTRACT", "不能删除或改写共享提取约束", 422)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(edit.content, encoding="utf-8")
            changes.append(
                FileDiff(
                    path=edit.path, before=before, after=edit.content if edit.operation == "write" else None
                )
            )
        return changes

    def edit(
        self,
        draft: UUID,
        actor: ProfileActor,
        revision: int,
        operation: str,
        edits: list[FileEdit],
        authorization: str,
    ) -> DraftView:
        if authorization not in {"explicit_instruction", "confirmed_proposal"}:
            raise ProfileError("CONFIRMATION_REQUIRED", "建议尚未获用户确认", 409)
        return self.mutate(
            draft,
            actor,
            revision,
            operation,
            lambda root, meta: {
                "action": "edit",
                "authorization": authorization,
                "diffs": [change.model_dump() for change in self.apply_files(root, edits)],
            },
            checksum(json.dumps([authorization, [e.model_dump() for e in edits]], sort_keys=True).encode()),
        )

    def propose(
        self, draft: UUID, actor: ProfileActor, revision: int, identifier: UUID, request: ProposalRequest
    ) -> Proposal:
        with self._db() as db:
            db.execute("begin immediate")
            row = self._owned(db, draft, actor)
            root, _ = self._verified(row)
            if row["revision"] != revision:
                raise ProfileError("VERSION_CONFLICT", "建议基于的草稿版本已变化", 409)
            for finding in request.findings:
                for anchor in finding.evidence:
                    if anchor.quote not in self.read(draft, actor, anchor.path, 0, 300000)["text"]:
                        raise ProfileError("INVALID_EVIDENCE", "建议引用的原文与当前资源不一致", 422)
            target = self._path(f"{actor.user_id}/{draft}/previews/{uuid4()}")
            shutil.copytree(root, target)
            diffs = self.apply_files(target, request.edits)
            self.basic_check(target)
            proposal = Proposal(
                **request.model_dump(),
                id=identifier,
                draft_id=draft,
                base_revision=revision,
                base_checksum=row["checksum"],
                diffs=diffs,
            )
            old = db.execute("select payload from proposals where id=?", (str(identifier),)).fetchone()
            if old:
                previous = Proposal.model_validate_json(old["payload"])
                if previous.model_dump(exclude={"status", "applied_revision"}) != proposal.model_dump(
                    exclude={"status", "applied_revision"}
                ):
                    raise ProfileError("PROPOSAL_CONFLICT", "相同建议ID内容已变化", 409)
                return previous
            db.execute(
                "insert into proposals values(?,?,?,?)",
                (str(identifier), str(draft), str(actor.user_id), proposal.model_dump_json()),
            )
            return proposal

    def proposal(self, draft: UUID, actor: ProfileActor, identifier: UUID) -> Proposal:
        with self._db() as db:
            self._owned(db, draft, actor)
            row = db.execute(
                "select payload from proposals where id=? and draft=? and owner=?",
                (str(identifier), str(draft), str(actor.user_id)),
            ).fetchone()
            if not row:
                raise ProfileError("PROPOSAL_NOT_FOUND", "建议不存在", 404)
            return Proposal.model_validate_json(row["payload"])

    def confirm(
        self, draft: UUID, actor: ProfileActor, identifier: UUID, revision: int, accepted: bool
    ) -> DraftView:
        with self._db() as db:
            db.execute("begin immediate")
            row = self._owned(db, draft, actor)
            record = db.execute(
                "select payload from proposals where id=? and draft=? and owner=?",
                (str(identifier), str(draft), str(actor.user_id)),
            ).fetchone()
            if record is None:
                raise ProfileError("PROPOSAL_NOT_FOUND", "建议不存在", 404)
            proposal = Proposal.model_validate_json(record["payload"])
            if proposal.status == "rejected" and accepted:
                raise ProfileError("PROPOSAL_REJECTED", "建议已被拒绝，不能再应用", 409)
            if proposal.status == "accepted":
                if not accepted:
                    raise ProfileError("PROPOSAL_ACCEPTED", "建议已应用，不能通过拒绝撤销", 409)
                return self._view(row)
            if not accepted:
                proposal.status = "rejected"
                db.execute(
                    "update proposals set payload=? where id=?", (proposal.model_dump_json(), str(identifier))
                )
                return self._view(row)
            if revision != proposal.base_revision or row["checksum"] != proposal.base_checksum:
                raise ProfileError("VERSION_CONFLICT", "确认版本与建议不一致，请重新核对", 409)
            result = self._mutate_locked(
                db,
                row,
                draft,
                actor,
                revision,
                f"proposal:{identifier}",
                lambda root, meta: {
                    "action": "edit",
                    "authorization": "confirmed_proposal",
                    "proposal_id": str(identifier),
                    "diffs": [change.model_dump() for change in self.apply_files(root, proposal.edits)],
                },
            )
            proposal.status, proposal.applied_revision = "accepted", result.revision
            db.execute(
                "update proposals set payload=? where id=?", (proposal.model_dump_json(), str(identifier))
            )
            return result

    def confirm_expected(
        self, draft: UUID, actor: ProfileActor, revision: int, expected: dict[str, str]
    ) -> DraftView:
        from .validation import case_files

        if not expected:
            raise ProfileError("EMPTY_CONFIRMATION", "请选择要确认的Expected及其摘要", 422)
        operation = (
            "expected:"
            + hashlib.sha256(json.dumps([revision, expected], sort_keys=True).encode()).hexdigest()
        )

        def confirm(root: Path, meta: dict[str, Any]) -> dict[str, Any]:
            allowed = {case["expected_path"] for case in case_files(root)}
            for path, value in expected.items():
                if path not in allowed or checksum(self.file(root, path).read_bytes()) != value:
                    raise ProfileError("EXPECTED_CONFLICT", "Expected已变化或不属于当前案例，请重新查看", 409)
                meta["confirmed_expected"][path] = value
            return {"action": "confirm_expected", "confirmed_by": str(actor.user_id), "files": expected}

        return self.mutate(draft, actor, revision, operation, confirm)

    def audit(self, draft: UUID, actor: ProfileActor) -> list[dict[str, Any]]:
        with self._db() as db:
            self._owned(db, draft, actor)
            return [
                {
                    "revision": row["revision"],
                    "operation": row["operation"],
                    "created_at": row["created_at"],
                    "audit": json.loads(row["audit"]),
                }
                for row in db.execute(
                    "select * from revisions where draft=? order by revision", (str(draft),)
                )
            ]

    def history(self, draft: UUID, actor: ProfileActor) -> list[dict[str, str]]:
        with self._db() as db:
            self._owned(db, draft, actor)
            rows = db.execute(
                "select payload from turns where draft=? order by rowid desc limit 8", (str(draft),)
            ).fetchall()
            return [message for row in reversed(rows) for message in json.loads(row["payload"])["messages"]]

    def cached_turn(
        self, draft: UUID, actor: ProfileActor, turn_id: UUID, request_hash: str
    ) -> dict[str, Any] | None:
        with self._db() as db:
            self._owned(db, draft, actor)
            row = db.execute(
                "select * from turns where draft=? and turn_id=?", (str(draft), str(turn_id))
            ).fetchone()
            if not row:
                return None
            if row["request_hash"] != request_hash:
                raise ProfileError("TURN_CONFLICT", "相同回合ID的输入已变化", 409)
            return cast(dict[str, Any], json.loads(row["payload"])["reply"])

    def save_turn(
        self,
        draft: UUID,
        actor: ProfileActor,
        turn_id: UUID,
        request_hash: str,
        message: str,
        reply: dict[str, Any],
    ) -> None:
        with self._db() as db:
            row = self._owned(db, draft, actor)
            if row["revision"] != reply["revision"]:
                raise ProfileError("VERSION_CONFLICT", "回复保存前草稿已更新，请核对最新修订", 409)
            payload = {
                "reply": reply,
                "messages": [
                    {"role": "user", "content": message[:12000]},
                    {"role": "assistant", "content": reply["answer"][:16000]},
                ],
            }
            db.execute(
                "insert into turns values(?,?,?,?)",
                (str(draft), str(turn_id), request_hash, json.dumps(payload)),
            )
