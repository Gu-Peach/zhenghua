"""Atomic manual add/remove on existing schema; never rebuild result generations."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID, uuid4

import asyncpg  # type: ignore[import-untyped]  # Driver currently ships no typing marker.

from .models import ConnectionCreate, ConnectionDelete
from .repository import ServiceError


class ConnectionMutations:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def add(
        self, project: str, user: str, body: ConnectionCreate, key: str
    ) -> dict[str, Any]:
        return await self._mutate(project, user, "add", None, body, key)

    async def remove(
        self, project: str, user: str, connection: str, body: ConnectionDelete, key: str
    ) -> dict[str, Any]:
        return await self._mutate(project, user, "remove", connection, body, key)

    async def _mutate(
        self,
        project: str,
        user: str,
        action: str,
        target: str | None,
        body: ConnectionCreate | ConnectionDelete,
        key: str,
    ) -> dict[str, Any]:
        if not self.database_url:
            raise ServiceError(
                503,
                "TRANSACTION_CONNECTION_REQUIRED",
                "端子增删需要配置 Server 数据库事务连接",
            )
        pid, actor = UUID(project), UUID(user)
        fingerprint = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
        proposal = (
            "manual-crud:"
            + hashlib.sha256(
                f"{user}:{project}:{action}:{target}:{key}".encode()
            ).hexdigest()
        )
        connection = None
        try:
            connection = await asyncpg.connect(
                self.database_url, timeout=15, command_timeout=30
            )
            await connection.set_type_codec(
                "jsonb",
                schema="pg_catalog",
                encoder=lambda value: json.dumps(
                    value, ensure_ascii=False, default=str
                ),
                decoder=json.loads,
            )
            async with connection.transaction():
                owner = await connection.fetchrow(
                    "SELECT owner_id,status FROM public.projects WHERE id=$1 FOR UPDATE",
                    pid,
                )
                if not owner:
                    raise ServiceError(404, "PROJECT_NOT_FOUND", "项目不存在")
                member = await connection.fetchval(
                    "SELECT role FROM public.project_members WHERE project_id=$1 AND user_id=$2",
                    pid,
                    actor,
                )
                if owner["owner_id"] != actor and member not in {"owner", "editor"}:
                    raise ServiceError(403, "ACCESS_DENIED", "没有修改项目的权限")
                if owner["status"] == "archived":
                    raise ServiceError(
                        409, "PROJECT_ARCHIVED", "项目已归档，不能增删端子"
                    )
                saved = await connection.fetchrow(
                    "SELECT payload,commit_receipt,confirmed_by FROM public.result_proposals WHERE id=$1 AND project_id=$2",
                    proposal,
                    pid,
                )
                if saved:
                    if (
                        saved["confirmed_by"] != actor
                        or saved["payload"].get("request_fingerprint") != fingerprint
                    ):
                        raise ServiceError(
                            409, "IDEMPOTENCY_CONFLICT", "提交标识已用于其他内容"
                        )
                    if saved["commit_receipt"]:
                        return {**saved["commit_receipt"], "idempotent": True}
                result = await connection.fetchrow(
                    "SELECT * FROM public.result_versions WHERE project_id=$1 ORDER BY version DESC LIMIT 1 FOR UPDATE",
                    pid,
                )
                if (
                    not result
                    or result["id"] != body.result_version_id
                    or result["revision"] != body.result_revision
                    or result["status"] not in {"draft", "needs_review", "accepted"}
                ):
                    raise ServiceError(
                        409, "VERSION_CONFLICT", "结果已改变，请刷新后重试"
                    )
                source_file = await connection.fetchval(
                    "SELECT id FROM public.document_files WHERE project_id=$1 AND kind='source_pdf' LIMIT 1",
                    pid,
                )
                if not source_file or not result["profile"]:
                    raise ServiceError(
                        409, "SOURCE_REQUIRED", "结果缺少来源 PDF 或冻结 Profile"
                    )
                cid = UUID(target) if target else uuid4()
                before: dict[str, Any] = {}
                after: dict[str, Any] = {}
                if action == "add" and isinstance(body, ConnectionCreate):
                    unit = await connection.fetchrow(
                        "SELECT * FROM public.wiring_units WHERE id=$1 AND project_id=$2 AND result_version_id=$3 FOR UPDATE",
                        body.wiring_unit_id,
                        pid,
                        result["id"],
                    )
                    if not unit:
                        raise ServiceError(
                            409, "UNIT_SCOPE_MISMATCH", "线号单元不属于当前结果"
                        )
                    drawing = await connection.fetchrow(
                        "SELECT * FROM public.drawings WHERE id=$1 AND project_id=$2 AND workspace_id=$3",
                        body.source_drawing_id,
                        pid,
                        unit["workspace_id"],
                    )
                    if not drawing:
                        raise ServiceError(
                            409,
                            "DRAWING_SCOPE_MISMATCH",
                            "来源图纸不属于该线号的工作区",
                        )
                    fields = body.fields.model_dump()
                    for field in ("voltage_level", "terminal_strip"):
                        if (
                            field in body.fields.model_fields_set
                            and fields[field] != unit[field]
                        ):
                            raise ServiceError(
                                422,
                                "SHARED_FIELD_MISMATCH",
                                "新增端子不能同时改变既有线号的共享字段，请使用编辑",
                            )
                        fields.pop(field)
                    target_page = None
                    if body.target_drawing_id:
                        target_page = await connection.fetchrow(
                            "SELECT d.*,w.code AS function FROM public.drawings d JOIN public.workspaces w ON w.id=d.workspace_id WHERE d.id=$1 AND d.project_id=$2",
                            body.target_drawing_id,
                            pid,
                        )
                        if (
                            not target_page
                            or target_page["id"] == drawing["id"]
                            or target_page["classification_snapshot_id"]
                            != drawing["classification_snapshot_id"]
                        ):
                            raise ServiceError(
                                409,
                                "TARGET_SCOPE_MISMATCH",
                                "目标图纸须属于同一项目/图纸快照，并与来源页不同",
                            )
                    state = fields.get("is_cross_page") or (
                        "cross_page"
                        if target_page
                        else "same_page"
                        if fields.get("end_terminal")
                        else "unknown"
                    )
                    if (state == "cross_page") != bool(target_page):
                        raise ServiceError(
                            422,
                            "TARGET_REQUIRED",
                            "跨页连接必须明确提供目标页；不能猜测引用",
                        )
                    fields["is_cross_page"] = state
                    review = state == "unknown" or not fields.get("end_terminal")
                    order = await connection.fetchval(
                        "SELECT coalesce(max(core_order),0)+1 FROM public.wiring_connections WHERE wiring_unit_id=$1",
                        unit["id"],
                    )
                    raw = {
                        **fields,
                        "connection_id": str(cid),
                        "origin": "manual",
                        "source_pages": [drawing["pdf_page_number"]],
                        "voltage_level": unit["voltage_level"],
                        "terminal_strip": unit["terminal_strip"],
                        "start": {
                            "device": fields.get("start_code"),
                            "name": fields.get("start_description"),
                            "terminal": fields["start_terminal"],
                        },
                        "end": {
                            "device": fields.get("end_code"),
                            "name": fields.get("end_description"),
                            "terminal": fields.get("end_terminal"),
                        },
                    }
                    if target_page:
                        raw["references"] = [
                            {
                                "target_function": target_page["function"],
                                "target_drawing_page": target_page["workspace_page"],
                                "target_pdf_page": target_page["pdf_page_number"],
                            }
                        ]
                        raw["source_pages"].append(target_page["pdf_page_number"])
                    await connection.execute(
                        """INSERT INTO public.wiring_connections(id,wiring_unit_id,source_drawing_id,core_order,principle_number,start_code,start_description,start_terminal,end_code,end_description,end_terminal,current_value,remark,color_mark,is_cross_page,status,needs_review,confidence,raw_payload)
                        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)""",
                        cid,
                        unit["id"],
                        drawing["id"],
                        order,
                        *(
                            fields.get(k)
                            for k in (
                                "principle_number",
                                "start_code",
                                "start_description",
                                "start_terminal",
                                "end_code",
                                "end_description",
                                "end_terminal",
                                "current_value",
                                "remark",
                                "color_mark",
                            )
                        ),
                        state,
                        "needs_review" if review else "confirmed",
                        review,
                        0.0 if review else 1.0,
                        raw,
                    )
                    await connection.execute(
                        "INSERT INTO public.connection_evidence(connection_id,drawing_id,kind,raw_text) VALUES($1,$2,'manual','用户人工新增端子，来源页已指定')",
                        cid,
                        drawing["id"],
                    )
                    if target_page:
                        await connection.execute(
                            "INSERT INTO public.connection_evidence(connection_id,drawing_id,kind,raw_text) VALUES($1,$2,'target','用户明确指定跨页目标')",
                            cid,
                            target_page["id"],
                        )
                    after = {
                        **raw,
                        "core_order": order,
                        "wiring_unit_id": str(unit["id"]),
                        "source_drawing_id": str(drawing["id"]),
                    }
                elif action == "remove" and isinstance(body, ConnectionDelete):
                    record = await connection.fetchrow(
                        "SELECT c.*,u.wire_number,u.project_id,u.result_version_id FROM public.wiring_connections c JOIN public.wiring_units u ON u.id=c.wiring_unit_id WHERE c.id=$1 AND u.project_id=$2 AND u.result_version_id=$3 FOR UPDATE OF c,u",
                        cid,
                        pid,
                        result["id"],
                    )
                    if not record or record["record_version"] != body.record_version:
                        raise ServiceError(
                            409,
                            "VERSION_CONFLICT",
                            "端子不存在、已改变或不属于当前结果",
                        )
                    evidence = await connection.fetch(
                        "SELECT to_jsonb(e) AS value FROM public.connection_evidence e WHERE connection_id=$1",
                        cid,
                    )
                    before = {
                        **dict(record),
                        "evidence": [e["value"] for e in evidence],
                    }
                    unit = record
                    await connection.execute(
                        "DELETE FROM public.wiring_connections WHERE id=$1", cid
                    )
                else:
                    raise ServiceError(422, "INVALID_ACTION", "无效的端子操作")
                pending = await connection.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM public.wiring_connections c JOIN public.wiring_units u ON u.id=c.wiring_unit_id WHERE u.result_version_id=$1 AND c.needs_review)",
                    result["id"],
                )
                if not pending:
                    await connection.execute(
                        "UPDATE public.result_versions SET status='superseded' WHERE project_id=$1 AND id<>$2 AND status='accepted'",
                        pid,
                        result["id"],
                    )
                revision = await connection.fetchval(
                    "UPDATE public.result_versions SET revision=revision+1,confirmed_by=$2,status=$3 WHERE id=$1 RETURNING revision",
                    result["id"],
                    actor,
                    "needs_review" if pending else "accepted",
                )
                receipt = {
                    "result_version_id": str(result["id"]),
                    "result_version": result["version"],
                    "result_revision": revision,
                    "connection_id": str(cid),
                    "action": action,
                    "wire_number": unit["wire_number"],
                    "proposal_id": proposal,
                    "idempotent": False,
                }
                await self._audit(
                    connection,
                    pid,
                    actor,
                    source_file,
                    result,
                    cid,
                    action,
                    proposal,
                    fingerprint,
                    before,
                    after,
                    receipt,
                )
                return receipt
        except ServiceError:
            raise
        except (
            asyncpg.PostgresError,
            asyncpg.InterfaceError,
            OSError,
            TimeoutError,
        ) as exc:
            raise ServiceError(
                503,
                "TRANSACTION_FAILED",
                "端子事务未完成，请按同一提交标识重试；不要重复创建任务",
            ) from exc
        finally:
            if connection is not None:
                await connection.close()

    async def _audit(
        self,
        db: Any,
        project: UUID,
        actor: UUID,
        source: UUID,
        result: Any,
        cid: UUID,
        action: str,
        proposal: str,
        fingerprint: str,
        before: dict[str, Any],
        after: dict[str, Any],
        receipt: dict[str, Any],
    ) -> None:
        run, fid, artifact = uuid4(), proposal + ":feedback", proposal + ":audit"
        operation = {
            "op": action,
            "target_type": "CONNECTION",
            "target_id": str(cid),
            "before": before,
            "after": after,
            "reason": "用户人工新增端子" if action == "add" else "用户明确确认删除端子",
            "evidence_ids": [artifact],
            "confidence": 1.0,
        }
        payload = {
            "request_fingerprint": fingerprint,
            "feedback_id": fid,
            "feedback_ids": [fid],
            "base_result_version": result["version"],
            "base_result_revision": result["revision"],
            "profile": result["profile"],
            "operations": [operation],
            "validation": {"schema_valid": True, "business_rules_valid": True},
        }
        await db.execute(
            "INSERT INTO public.agent_runs(id,idempotency_key,request_fingerprint,run_type,status,project_id,source_document_id,requested_by,scope,profile,options) VALUES($1,$2,$3,'SCOPED_CORRECTION','SUCCEEDED',$4,$5,$6,$7,$8,$9)",
            run,
            proposal,
            fingerprint,
            project,
            source,
            actor,
            {"type": "CONNECTION", "id": str(cid)},
            result["profile"],
            {"manual_action": action},
        )
        await db.execute(
            "INSERT INTO public.result_proposals(id,agent_run_id,project_id,status,payload,committed_result_version_id,committed_at,confirmed_by,commit_receipt) VALUES($1,$2,$3,'READY_FOR_REVIEW',$4,$5,now(),$6,$7)",
            proposal,
            run,
            project,
            payload,
            result["id"],
            actor,
            receipt,
        )
        accepted = {
            "feedback_id": fid,
            "project_id": str(project),
            "accepted": True,
            "result_version_id": str(result["id"]),
            "profile": result["profile"],
            "model_name": "manual",
            "target": {"type": "CONNECTION", "ids": [str(cid)]},
            "before": {str(cid): before} if before else {},
            "after": {str(cid): after} if after else {},
            "evidence_ids": [artifact],
            "stage_artifact_ids": [artifact],
            "trace_ids": [],
            "prompt_checksum": result["profile"].get("checksum") or "unversioned",
            "feedback_origin": "manual",
            "correction_run_id": str(run),
            "context": {"action": action, "source": "table_editor"},
        }
        await db.execute(
            "INSERT INTO public.feedback_items(id,project_id,target_type,target_id,issue_kind,status,requested_by,base_result_version,base_result_version_id,proposal_id,committed_result_version_id,correction_bundle,before_value,after_value,accepted_payload,accepted_at) VALUES($1,$2,'CONNECTION',$3,$4,'accepted',$5,$6,$7,$8,$7,$9,$10,$11,$12,now())",
            fid,
            project,
            str(cid),
            "MANUAL_ADD" if action == "add" else "MANUAL_REMOVE",
            actor,
            result["version"],
            result["id"],
            proposal,
            {"action": action, "source": "table_editor"},
            before,
            after,
            accepted,
        )
        await db.execute(
            "INSERT INTO public.agent_artifacts(artifact_id,agent_run_id,kind,payload) VALUES($1,$2,'manual_connection_mutation',$3)",
            artifact,
            run,
            {
                "artifact_id": artifact,
                "agent_run_id": str(run),
                "kind": "manual_connection_mutation",
                "before": before,
                "after": after,
                "action": action,
            },
        )
