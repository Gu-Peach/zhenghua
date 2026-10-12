from __future__ import annotations

import hashlib
import json
from typing import Any, cast
from uuid import uuid4

from .models import ConnectionEdit, ConnectionFields, ConnectionPage, ConnectionRow
from .repository import Repository, ServiceError


class WorkbenchService:
    def __init__(self, repository: Repository) -> None:
        self.db = repository

    async def projects(self, token: str) -> list[dict[str, Any]]:
        projects = await self.db.all_rows(
            "projects", {"order": "created_at.asc,id.asc"}, token=token
        )
        if not projects:
            return []
        allowed = "in.(" + ",".join(str(row["id"]) for row in projects) + ")"
        # Batched read models keep folder counts real without per-project HTTP requests.
        workspaces = await self.db.all_rows(
            "workspaces", {"project_id": allowed, "order": "sort_order.asc,id.asc"}
        )
        drawings = await self.db.all_rows(
            "drawings", {"project_id": allowed, "order": "pdf_page_number.asc,id.asc"}
        )
        results = await self.db.all_rows(
            "result_versions", {"project_id": allowed, "order": "version.desc"}
        )
        runs = await self.db.all_rows(
            "agent_runs",
            {
                "project_id": allowed,
                "order": "created_at.desc",
                "select": "id,project_id,status,current_stage,run_type",
            },
        )
        for project in projects:
            snapshot = project.get("published_classification_snapshot_id")
            visible = [
                w
                for w in workspaces
                if w["project_id"] == project["id"]
                and snapshot
                and w.get("classification_snapshot_id") == snapshot
            ]
            for workspace in visible:
                workspace["drawings"] = [
                    d
                    for d in drawings
                    if d["workspace_id"] == workspace["id"]
                    and d.get("classification_snapshot_id") == snapshot
                ]
            project["workspaces"] = visible
            project["result"] = next(
                (r for r in results if r["project_id"] == project["id"]), None
            )
            project["latest_run"] = next(
                (r for r in runs if r["project_id"] == project["id"]), None
            )
        return projects

    async def latest(self, project: str) -> dict[str, Any] | None:
        rows = await self.db.rows(
            "result_versions",
            {"project_id": f"eq.{project}", "order": "version.desc", "limit": "1"},
        )
        return rows[0] if rows else None

    async def units(self, project: str, user: str) -> list[dict[str, Any]]:
        await self.db.require_project(project, user)
        result = await self.latest(project)
        if not result:
            return []
        return await self.db.all_rows(
            "wiring_units",
            {
                "project_id": f"eq.{project}",
                "result_version_id": f"eq.{result['id']}",
                "order": "wire_number.asc,id.asc",
            },
        )

    async def delete_project(self, project: str, user: str, updated_at: str) -> None:
        """Two-system delete: archive before asset cleanup; failures remain resumable/archived."""
        row = await self.db.require_project(project, user, owner=True)
        if row["updated_at"] != updated_at:
            raise ServiceError(409, "VERSION_CONFLICT", "项目已改变，请刷新再删除")

        async def active_runs() -> bool:
            return bool(
                await self.db.rows(
                    "agent_runs",
                    {
                        "project_id": f"eq.{project}",
                        "status": "in.(QUEUED,RUNNING,WAITING_INPUT)",
                        "limit": "1",
                    },
                )
            )

        if await active_runs():
            raise ServiceError(409, "ACTIVE_RUN", "先结束或取消处理任务，再删除项目")
        archived = await self.db.update(
            "projects",
            {"id": f"eq.{project}", "updated_at": f"eq.{updated_at}"},
            {"status": "archived"},
        )
        if not archived:
            raise ServiceError(409, "VERSION_CONFLICT", "项目已改变")
        if await active_runs():
            raise ServiceError(
                409, "ACTIVE_RUN", "任务刚刚启动；项目已归档，等待任务结束后重试删除"
            )
        sources = await self.db.rows("document_files", {"project_id": f"eq.{project}"})
        drawings = await self.db.all_rows(
            "drawings", {"project_id": f"eq.{project}", "order": "id.asc"}
        )
        buckets = {s["storage_bucket"] for s in sources} | {
            d["image_bucket"] for d in drawings
        }
        prefix = f"projects/{project}/"
        for bucket in buckets:
            paths: list[str] = []

            async def collect(
                folder: str, bucket: str = bucket, paths: list[str] = paths
            ) -> None:
                if not folder.startswith(prefix):
                    raise ServiceError(409, "UNSAFE_PATH", "删除路径不属于项目")
                offset = 0
                while True:
                    objects = await self.db.call(
                        "POST",
                        f"/storage/v1/object/list/{bucket}",
                        json={
                            "prefix": folder.rstrip("/"),
                            "offset": offset,
                            "limit": 100,
                            "sortBy": {"column": "name", "order": "asc"},
                        },
                    )
                    for obj in objects:
                        name = obj["name"]
                        if "/" in name or name in {".", ".."}:
                            raise ServiceError(409, "UNSAFE_PATH", "非法对象名称")
                        path = folder + name
                        if obj.get("id"):
                            paths.append(path)
                        else:
                            await collect(path + "/")
                    if len(objects) < 100:
                        break
                    offset += 100

            await collect(prefix)
            for offset in range(0, len(paths), 100):
                await self.db.call(
                    "DELETE",
                    f"/storage/v1/object/{bucket}",
                    json={"prefixes": paths[offset : offset + 100]},
                )
        # Existing aggregate cascade migration handles result/run/evidence ordering.
        await self.db.call(
            "DELETE",
            "/rest/v1/projects",
            params={"id": f"eq.{project}", "status": "eq.archived"},
        )

    async def detail(self, project: str, user: str) -> dict[str, Any]:
        row = await self.db.require_project(project, user)
        snapshot = row.get("published_classification_snapshot_id")
        params = {"project_id": f"eq.{project}", "order": "sort_order.asc,id.asc"}
        if snapshot:
            params["classification_snapshot_id"] = f"eq.{snapshot}"
        # Unpublished projections must not appear in the tree.
        workspaces = await self.db.all_rows("workspaces", params) if snapshot else []
        drawings = (
            await self.db.all_rows(
                "drawings",
                {
                    **{k: v for k, v in params.items() if k != "order"},
                    "order": "pdf_page_number.asc,id.asc",
                },
            )
            if snapshot
            else []
        )
        sources = await self.db.rows(
            "document_files", {"project_id": f"eq.{project}", "kind": "eq.source_pdf"}
        )
        latest = await self.latest(project)
        for workspace in workspaces:
            workspace["drawings"] = [
                d for d in drawings if d["workspace_id"] == workspace["id"]
            ]
        runs = await self.db.rows(
            "agent_runs",
            {
                "project_id": f"eq.{project}",
                "order": "created_at.desc",
                "limit": "1",
                "select": "id,status,current_stage,run_type",
            },
        )
        return {
            **row,
            "workspaces": workspaces,
            "sources": sources,
            "result": latest,
            "latest_run": runs[0] if runs else None,
        }

    async def results(
        self,
        project: str,
        user: str,
        *,
        offset: int,
        limit: int,
        workspace: str | None = None,
        drawing: str | None = None,
        search: str = "",
        version: str | None = None,
    ) -> ConnectionPage:
        await self.db.require_project(project, user)
        versions = await self.db.rows(
            "result_versions",
            {
                "project_id": f"eq.{project}",
                **({"id": f"eq.{version}"} if version else {}),
                "order": "version.desc",
                "limit": "1",
            },
        )
        if not versions:
            if version:
                raise ServiceError(404, "RESULT_NOT_FOUND", "结果版本不存在")
            return ConnectionPage(items=[], offset=offset, limit=limit, has_more=False)
        latest = versions[0]
        params = {
            "project_id": f"eq.{project}",
            "result_version_id": f"eq.{latest['id']}",
            "offset": str(offset),
            "limit": str(limit + 1),
            "order": "pdf_page_number.asc,wire_number.asc,core_order.asc,connection_id.asc",
        }
        if workspace:
            params["workspace_id"] = f"eq.{workspace}"
        if drawing:
            params["drawing_id"] = f"eq.{drawing}"
        if search:
            # Restrict PostgREST expression characters; do not interpolate arbitrary filters.
            safe = "".join(c for c in search if c.isalnum() or c in " :_-+")[:100]
            if safe:
                params["or"] = (
                    "("
                    + ",".join(
                        f"{key}.ilike.*{safe}*"
                        for key in (
                            "start_terminal",
                            "end_terminal",
                            "principle_number",
                            "start_description",
                            "end_description",
                        )
                    )
                    + ")"
                )
        rows = await self.db.rows("wiring_connection_rows", params)
        return ConnectionPage(
            items=[ConnectionRow.model_validate(row) for row in rows[:limit]],
            result_version_id=latest["id"],
            result_version=latest["version"],
            result_revision=latest["revision"],
            offset=offset,
            limit=limit,
            has_more=len(rows) > limit,
        )

    async def connection(
        self, connection: str, user: str, *, write: bool = False
    ) -> dict[str, Any]:
        rows = await self.db.rows(
            "wiring_connection_rows",
            {"connection_id": f"eq.{connection}", "limit": "1"},
        )
        if not rows:
            raise ServiceError(404, "CONNECTION_NOT_FOUND", "连接不存在")
        await self.db.require_project(rows[0]["project_id"], user, write=write)
        return rows[0]

    async def drawing(self, drawing: str, user: str) -> dict[str, Any]:
        rows = await self.db.rows("drawings", {"id": f"eq.{drawing}", "limit": "1"})
        if not rows:
            raise ServiceError(404, "DRAWING_NOT_FOUND", "图纸不存在")
        row = rows[0]
        await self.db.require_project(row["project_id"], user)
        return {
            **row,
            "image_url": await self.db.signed_url(
                row["image_bucket"], row["image_path"]
            )
            if row.get("image_path")
            else None,
        }

    async def target(self, connection: str, user: str) -> dict[str, Any]:
        row = await self.connection(connection, user)
        if row["is_cross_page"] != "cross_page":
            raise ServiceError(409, "NOT_CROSS_PAGE", "当前连接不是跨页连接")
        evidence = await self.db.rows(
            "connection_evidence", {"connection_id": f"eq.{connection}"}
        )
        ids = {
            e["drawing_id"]
            for e in evidence
            if e["kind"] == "target" and e["drawing_id"] != row.get("drawing_id")
        }
        raw = (await self.db.rows("wiring_connections", {"id": f"eq.{connection}"}))[
            0
        ].get("raw_payload") or {}
        drawings = await self.db.all_rows(
            "drawings",
            {"project_id": f"eq.{row['project_id']}", "order": "pdf_page_number.asc"},
        )
        source = next((d for d in drawings if d["id"] == row.get("drawing_id")), None)
        # Keep historical classification identity, including when a newer run exists.
        if source:
            drawings = [
                d
                for d in drawings
                if d.get("classification_snapshot_id")
                == source.get("classification_snapshot_id")
            ]
        for ref in raw.get("references") or []:
            if not isinstance(ref, dict):
                continue
            function = ref.get("target_function")
            page = ref.get("target_drawing_page")
            if function and page is not None:
                workspaces = await self.db.rows(
                    "workspaces",
                    {"project_id": f"eq.{row['project_id']}", "code": f"eq.{function}"},
                )
                wsids = {w["id"] for w in workspaces}
                ids.update(
                    d["id"]
                    for d in drawings
                    if d["workspace_id"] in wsids
                    and str(d["workspace_page"]) == str(page)
                )
        history_version: int | None = None
        identity_fields = (
            "drawing_id",
            "principle_number",
            "start_code",
            "start_terminal",
            "end_code",
        )
        if (
            not ids
            and not raw.get("references")
            and all(row.get(key) for key in identity_fields)
        ):
            matches = await self.db.all_rows(
                "wiring_connection_rows",
                {
                    "project_id": f"eq.{row['project_id']}",
                    "result_version": f"lt.{row['result_version']}",
                    **{key: f"eq.{row[key]}" for key in identity_fields},
                    "order": "result_version.desc,connection_id.asc",
                },
            )
            for historical in matches:
                # Match complete source identity, not merely a repeated terminal label.
                if historical.get("source_document_id") != row.get(
                    "source_document_id"
                ) or historical.get("core_order") != row.get("core_order"):
                    continue
                targets = await self.db.rows(
                    "connection_evidence",
                    {
                        "connection_id": f"eq.{historical['connection_id']}",
                        "kind": "eq.target",
                    },
                )
                ids.update(
                    e["drawing_id"]
                    for e in targets
                    if e["drawing_id"] != row["drawing_id"]
                )
                if targets and history_version is None:
                    history_version = historical["result_version"]
        candidates = [d for d in drawings if d["id"] in ids]
        if len(candidates) != 1:
            raise ServiceError(
                409, "TARGET_UNRESOLVED", "缺少唯一跨页引用证据，不能猜测目标页"
            )
        drawing = await self.drawing(candidates[0]["id"], user)
        if history_version is not None:
            drawing["reference_note"] = (
                f"当前快照缺少引用；依据相同来源连接的历史 V{history_version} 唯一目标证据定位"
            )
        return drawing

    async def edit(
        self, connection: str, user: str, edit: ConnectionEdit, key: str
    ) -> dict[str, Any]:
        row = await self.connection(connection, user, write=True)
        project = row["project_id"]
        proposal_id = (
            "manual:"
            + hashlib.sha256(f"{user}:{connection}:{key}".encode()).hexdigest()
        )
        fingerprint = hashlib.sha256(edit.model_dump_json().encode()).hexdigest()
        existing = await self.db.rows("result_proposals", {"id": f"eq.{proposal_id}"})
        if existing:
            if existing[0]["payload"].get("request_fingerprint") != fingerprint:
                raise ServiceError(
                    409, "IDEMPOTENCY_CONFLICT", "该提交标识已用于其他修改"
                )
            if existing[0].get("commit_receipt"):
                return cast(dict[str, Any], existing[0]["commit_receipt"])
        result = await self.latest(project)
        if (
            not result
            or str(edit.result_version_id) != result["id"]
            or edit.result_revision != result["revision"]
            or edit.record_version != row["record_version"]
        ):
            raise ServiceError(409, "VERSION_CONFLICT", "结果已变更，请刷新后重新编辑")
        values = edit.changes.model_dump(exclude_unset=True)
        if values.get("is_cross_page", "unknown") is None:
            raise ServiceError(422, "INVALID_FIELDS", "跨页状态不能清空")
        values = {k: v for k, v in values.items() if row.get(k) != v}
        if not values:
            return {"changed": False, "result_revision": result["revision"]}
        current = (
            await self.db.rows("wiring_connections", {"id": f"eq.{connection}"})
        )[0]
        # The read view contains both connection fields and shared wiring-unit metadata.
        before = {k: row.get(k) for k in ConnectionFields.model_fields}
        after = {**before, **values}
        # Preserve nested endpoint values for downstream Agent evidence, including null edits.
        raw = dict(current.get("raw_payload") or {})
        raw.update(after)
        for endpoint in ("start", "end"):
            nested = dict(raw.get(endpoint) or {})
            nested.update(
                device=after[f"{endpoint}_code"],
                name=after[f"{endpoint}_description"],
                terminal=after[f"{endpoint}_terminal"],
            )
            raw[endpoint] = nested
        run_id = existing[0]["agent_run_id"] if existing else str(uuid4())
        fid = proposal_id + ":feedback"
        operation = {
            "op": "replace",
            "target_type": "CONNECTION",
            "target_id": connection,
            "expected_version": edit.record_version,
            "before": before,
            "after": raw,
            "evidence_ids": [f"connection:{connection}"],
            "reason": "用户通过表格确认修改",
            "confidence": 1.0,
        }
        if not existing:
            await self.db.insert(
                "agent_runs",
                {
                    "id": run_id,
                    "idempotency_key": proposal_id,
                    "request_fingerprint": fingerprint,
                    "run_type": "SCOPED_CORRECTION",
                    "status": "SUCCEEDED",
                    "project_id": project,
                    "source_document_id": row["source_document_id"],
                    "requested_by": user,
                    "scope": {"type": "CONNECTION", "id": connection},
                    "feedback_id": fid,
                    "profile": result["profile"],
                },
            )
            await self.db.insert(
                "result_proposals",
                {
                    "id": proposal_id,
                    "agent_run_id": run_id,
                    "project_id": project,
                    "status": "READY_FOR_REVIEW",
                    "payload": {
                        "request_fingerprint": fingerprint,
                        "feedback_id": fid,
                        "feedback_ids": [fid],
                        "profile": result["profile"],
                        "base_result_version": result["version"],
                        "base_result_revision": edit.result_revision,
                        "operations": [operation],
                        "validation": {
                            "schema_valid": True,
                            "business_rules_valid": True,
                        },
                    },
                },
            )
        if not await self.db.rows("feedback_items", {"id": f"eq.{fid}"}):
            await self.db.insert(
                "feedback_items",
                {
                    "id": fid,
                    "project_id": project,
                    "target_type": "CONNECTION",
                    "target_id": connection,
                    "issue_kind": "DIRECT_VALUE_CHANGE",
                    "status": "prepared",
                    "requested_by": user,
                    "base_result_version": result["version"],
                    "base_result_version_id": result["id"],
                    "correction_bundle": {"source": "manual_table_edit"},
                },
            )
        accepted = {
            "feedback_id": fid,
            "project_id": project,
            "accepted": True,
            "result_version_id": result["id"],
            "profile": result["profile"],
            "model_name": "manual",
            "target": {"type": "CONNECTION", "ids": [connection]},
            "before": {connection: before},
            "after": {connection: raw},
            "evidence_ids": [f"connection:{connection}"],
            "stage_artifact_ids": [proposal_id],
            "trace_ids": [],
            "prompt_checksum": result["profile"].get("checksum") or "unversioned",
            "correction_run_id": run_id,
            "feedback_origin": "manual",
            "context": {"source": "table_editor"},
        }
        return cast(
            dict[str, Any],
            await self.db.rpc(
                "apply_confirmed_result_patch",
                {
                    "value": {
                        "proposal_id": proposal_id,
                        "project_id": project,
                        "confirmed_by": user,
                        "changes": [
                            {
                                "target_id": connection,
                                "expected_version": edit.record_version,
                                "before": before,
                                "after": raw,
                                "record": {**current, **after},
                            }
                        ],
                        "feedback_updates": [
                            {
                                "feedback_id": fid,
                                "before": before,
                                "after": raw,
                                "accepted_payload": accepted,
                            }
                        ],
                    }
                },
            ),
        )

    async def rules(self, token: str, user: str) -> list[dict[str, Any]]:
        rows = await self.db.all_rows(
            "profile_resource_packages",
            {
                "order": "profile_key.asc,created_at.desc",
                "status": "neq.retired",
                "candidate_id": "is.null",
                "select": "id,profile_key,profile_version,source_profile_checksum,package_checksum,status,created_at,published_at,created_by",
            },
            token=token,
        )
        latest: dict[str, dict[str, Any]] = {}
        for row in sorted(
            rows,
            key=lambda item: (
                str(item.get("profile_key") or ""),
                str(item.get("created_at") or ""),
                str(item.get("profile_version") or ""),
            ),
            reverse=True,
        ):
            if row["status"] != "retired":
                latest.setdefault(str(row["profile_key"]), row)
        return [
            {**row, "can_delete": row.get("created_by") == user}
            for row in sorted(latest.values(), key=lambda item: str(item["profile_key"]))
        ]

    async def package(self, package_id: str, token: str) -> dict[str, Any]:
        rows = await self.db.rows(
            "profile_resource_packages", {"id": f"eq.{package_id}"}, token=token
        )
        if not rows:
            raise ServiceError(404, "PACKAGE_NOT_FOUND", "资源包不存在")
        row = rows[0]
        manifest_text = await self.db.text_object(
            row["storage_bucket"], row["manifest_path"]
        )
        if (
            "sha256:" + hashlib.sha256(manifest_text.encode()).hexdigest()
            != row["manifest_checksum"]
        ):
            raise ServiceError(409, "CHECKSUM_MISMATCH", "资源清单校验失败")
        manifest = json.loads(manifest_text)
        files, images = [], []
        for entry in manifest["files"]:
            path = entry["path"]
            if path.startswith("/") or ".." in path.split("/") or "\\" in path:
                raise ServiceError(409, "UNSAFE_RESOURCE", "非法资源路径")
            object_path = row["storage_prefix"] + "/" + path
            if path.endswith((".md", ".json", ".txt")):
                text = await self.db.text_object(row["storage_bucket"], object_path)
                if (
                    "sha256:" + hashlib.sha256(text.encode()).hexdigest()
                    != entry["checksum"]
                ):
                    raise ServiceError(409, "CHECKSUM_MISMATCH", "规则文件校验失败")
                files.append({"path": path, "content": text})
            elif path.endswith((".png", ".jpg", ".jpeg")):
                images.append(
                    {
                        "path": path,
                        "url": await self.db.signed_url(
                            row["storage_bucket"], object_path
                        ),
                    }
                )
        return {"manifest": manifest, "files": files, "images": images}
