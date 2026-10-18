"""Read evidence and persist edit proposals; confirmed business-row writes belong to Server."""

from __future__ import annotations

import asyncio
import base64
import math
from typing import Any, Literal, Protocol
from urllib.parse import unquote

import pymupdf
from pydantic import ValidationError

from src.infrastructure.supabase_client import SupabaseClient

from .models import (
    ConnectionEditProposal,
    ConnectionEditRequest,
    ConnectionFacts,
    ConnectionQuery,
    DrawingEvidence,
    DrawingReadResult,
    ExplainActor,
    ExplainContext,
    ExplainError,
    ExplainTurn,
    ModelImage,
    ProfileEvidence,
    SearchResult,
    TerminalPosition,
)


class ExplanationRepository(Protocol):
    async def load(self, turn: ExplainTurn, actor: ExplainActor) -> ExplainContext: ...

    async def search(
        self, turn: ExplainTurn, actor: ExplainActor, query: ConnectionQuery
    ) -> SearchResult: ...

    async def read_drawings(
        self, turn: ExplainTurn, actor: ExplainActor, numbers: list[int]
    ) -> DrawingReadResult: ...

    async def propose_edit(
        self, turn: ExplainTurn, actor: ExplainActor, proposal_id: str, request: ConnectionEditRequest
    ) -> ConnectionEditProposal: ...

    async def edit_proposals(
        self, turn: ExplainTurn, actor: ExplainActor, identifiers: list[str]
    ) -> list[ConnectionEditProposal]: ...


def _text(value: Any, limit: int = 4000) -> str | None:
    return str(value)[:limit] if value is not None else None


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


class SupabaseExplanationRepository:
    def __init__(self, client: SupabaseClient, *, bucket: str = "project-assets") -> None:
        self.client, self.bucket = client, bucket

    async def propose_edit(
        self, turn: ExplainTurn, actor: ExplainActor, proposal_id: str, request: ConnectionEditRequest
    ) -> ConnectionEditProposal:
        """Only persist a deterministic preview. This adapter never commits edits to business rows."""
        project = await self._authorized_project(turn, actor)
        if project.get("status") == "processing":
            raise ExplainError("EXTRACTION_IN_PROGRESS", "提取期间线表只读，请完成后再提出修改。", 409)
        try:
            value = await self.client.rpc(
                "prepare_explain_connection_edit",
                {
                    "value": {
                        "actor": str(actor.user_id),
                        "project_id": str(turn.project_id),
                        "batch_id": turn.batch_id,
                        "proposal_id": proposal_id,
                        "request": request.model_dump(mode="json", exclude_unset=True),
                        "user_request": turn.message,
                    }
                },
            )
        except Exception as exc:
            from src.domain.errors import AgentServiceError

            if not isinstance(exc, AgentServiceError):
                raise
            message = str(exc.details.get("provider_message", ""))
            if "SWAP_TARGET_UNCONFIRMED" in message or "SWAP_SOURCE_NOT_INDEXED" in message:
                raise ExplainError(
                    "EDIT_POSITION_UNCONFIRMED",
                    "端点位置或目标页尚未确认，不能猜测整组调换后的图纸位置；可先核对页码。",
                    422,
                ) from exc
            if "EDIT_SCOPE_TOO_LARGE" in message:
                raise ExplainError(
                    "EDIT_SCOPE_TOO_LARGE", "范围超过1000行，请按工作区内的页码或原理号进一步缩小。", 422
                ) from exc
            if exc.details.get("provider_code") == "PT409":
                raise ExplainError(
                    "EDIT_VERSION_CONFLICT", "批次或修改请求已变化，请刷新线表后重新生成方案。", 409
                ) from exc
            raise ExplainError(
                "EDIT_PREVIEW_UNAVAILABLE", "修改预览暂不可用，请检查新增迁移与数据服务。", 503
            ) from exc
        proposal = ConnectionEditProposal.model_validate(value)
        if proposal.project_id != turn.project_id or proposal.batch_id != turn.batch_id:
            raise ExplainError("EDIT_SCOPE_MISMATCH", "修改预览不属于当前项目或批次。", 403)
        return proposal

    async def edit_proposals(
        self, turn: ExplainTurn, actor: ExplainActor, identifiers: list[str]
    ) -> list[ConnectionEditProposal]:
        await self._authorized_project(turn, actor)
        from uuid import UUID

        rows = await self.client.select(
            "connection_edit_proposals",
            params={
                "project_id": f"eq.{turn.project_id}",
                "created_by": f"eq.{actor.user_id}",
                "proposal_id": "in.(" + ",".join(str(UUID(value)) for value in identifiers) + ")",
                "select": ",".join(ConnectionEditProposal.model_fields),
                "limit": "8",
            },
        )
        proposals = [
            ConnectionEditProposal.model_validate(
                {name: row[name] for name in ConnectionEditProposal.model_fields}
            )
            for row in rows
        ]
        if any(
            p.project_id != turn.project_id
            or p.batch_id != turn.batch_id
            or str(p.proposal_id) not in identifiers
            for p in proposals
        ):
            raise ExplainError("EDIT_SCOPE_MISMATCH", "修改方案不属于当前项目、批次或请求范围。", 403)
        return proposals

    def _safe_image_path(self, project_id: Any, bucket: Any, path: Any) -> bool:
        decoded = unquote(path) if isinstance(path, str) else ""
        return (
            bucket == self.bucket
            and decoded.startswith(f"projects/{project_id}/")
            and "\\" not in decoded
            and not any(part in {"", ".", ".."} for part in decoded.split("/"))
        )

    async def read_drawings(
        self, turn: ExplainTurn, actor: ExplainActor, numbers: list[int]
    ) -> DrawingReadResult:
        """Read only indexed project images; caller limits pages to retrieved evidence."""
        project = await self._authorized_project(turn, actor)
        pages = _object(project.get("drawing_index")).get("pages") or []
        result = DrawingReadResult()
        for number in list(dict.fromkeys(numbers))[:4]:
            matches = [p for p in pages if isinstance(p, dict) and p.get("pdf_page_number") == number]
            if len(matches) != 1:
                result.gaps.append(f"物理页{number}未唯一登记，无法读取图像。")
                continue
            page = matches[0]
            bucket, path = page.get("image_bucket", self.bucket), page.get("image_path")
            if not self._safe_image_path(turn.project_id, bucket, path):
                result.gaps.append(f"物理页{number}的图片路径不属于当前项目。")
                continue
            assert isinstance(path, str)
            try:
                data = await self.client.download(bucket=bucket, object_path=path)
                image = await asyncio.to_thread(_model_image, data)
                result.images.append(ModelImage(pdf_page_number=number, data_url=image))
            except Exception:
                result.gaps.append(f"物理页{number}图片不可用，本轮未完成看图。")
        return result

    async def _authorized_project(self, turn: ExplainTurn, actor: ExplainActor) -> dict[str, Any]:
        projects = await self.client.select(
            "extraction_projects",
            params={
                "id": f"eq.{turn.project_id}",
                "owner_id": f"eq.{actor.user_id}",
                "limit": "1",
            },
        )
        if not projects:
            raise ExplainError("PROJECT_NOT_FOUND", "项目不存在或无权访问。", 404)
        project = projects[0]
        # Verify responses too: service-role credentials do not provide row-level isolation.
        if str(project.get("id")) != str(turn.project_id) or str(project.get("owner_id")) != str(
            actor.user_id
        ):
            raise ExplainError("PROJECT_NOT_FOUND", "项目不存在或无权访问。", 404)
        if project.get("status") == "archived":
            raise ExplainError("PROJECT_ARCHIVED", "项目已归档，不能继续读取解释。", 409)
        return project

    async def load(self, turn: ExplainTurn, actor: ExplainActor) -> ExplainContext:
        project = await self._authorized_project(turn, actor)
        rows = await self.client.select(
            "extraction_connection_rows",
            params={
                "id": f"eq.{turn.connection_id}",
                "project_id": f"eq.{turn.project_id}",
                "limit": "1",
            },
        )
        if (
            not rows
            or str(rows[0].get("id")) != str(turn.connection_id)
            or str(rows[0].get("project_id")) != str(turn.project_id)
        ):
            raise ExplainError("CONNECTION_NOT_FOUND", "连接不存在或不属于当前项目。", 404)
        raw = rows[0]
        if turn.batch_id is not None and turn.batch_id != raw.get("batch_id"):
            raise ExplainError("BATCH_CONFLICT", "提取批次已变化，请刷新线表后重新打开解释。", 409)
        if turn.record_version is not None and turn.record_version != raw.get("record_version"):
            raise ExplainError("ROW_VERSION_CONFLICT", "这一行已经更新，请刷新后重新打开解释。", 409)
        return await self._context(project, raw)

    async def search(self, turn: ExplainTurn, actor: ExplainActor, query: ConnectionQuery) -> SearchResult:
        """Read one stable page; all filters are exact and never interpreted as raw SQL."""
        project = await self._authorized_project(turn, actor)
        active = _text(_object(project.get("drawing_index")).get("active_batch_id"))
        batch = turn.batch_id or active
        if turn.query is not None and turn.batch_id and active and turn.batch_id != active:
            raise ExplainError("BATCH_CONFLICT", "提取批次已变化，请刷新后重新打开解释。", 409)
        result = SearchResult(project_name=_text(project.get("name"), 200) or "", batch_id=batch, query=query)
        if not batch:
            result.gaps.append("项目尚无当前提取批次，未查询其他批次的线表。")
            return result
        names = {
            "connection_id": "id",
            "drawing_page": "source_drawing_page",
            "pdf_page_number": "source_pdf_page_number",
        }
        filters = {names.get(key, key): value for key, value in query.exact_filters().items()}
        rows = await self.client.select(
            "extraction_connection_rows",
            params={
                "project_id": f"eq.{turn.project_id}",
                "batch_id": f"eq.{batch}",
                **{key: f"eq.{value}" for key, value in filters.items()},
                "order": "source_pdf_page_number.asc,row_order.asc,id.asc",
                "offset": str(query.offset),
                "limit": str(query.limit + 1),
            },
        )
        # Fail closed even if an adapter/backend returns a row outside the filters.
        for raw in rows:
            if str(raw.get("project_id")) != str(turn.project_id) or raw.get("batch_id") != batch:
                raise ExplainError("INVALID_SEARCH_RESULT", "检索返回了不属于当前项目或批次的记录。", 502)
            if any(str(raw.get(key)) != str(value) for key, value in filters.items()):
                raise ExplainError("INVALID_SEARCH_RESULT", "检索结果不符合精确匹配条件。", 502)
        result.has_more = len(rows) > query.limit
        result.next_offset = query.offset + query.limit if result.has_more else None
        image_cache: dict[str, str | None] = {}
        for raw in rows[: query.limit]:
            result.rows.append(await self._context(project, raw, image_cache))
        if not result.rows:
            result.gaps.append("当前精确条件下没有匹配记录，不能据此推断图中没有端子。")
        if result.has_more:
            result.gaps.append("当前仅返回一部分记录，请使用相同条件和next_offset继续检索。")
        from .tools.retrieval import merge_drawings

        result.drawings = merge_drawings(result.rows)
        return result

    async def _context(
        self, project: dict[str, Any], raw: dict[str, Any], image_cache: dict[str, str | None] | None = None
    ) -> ExplainContext:
        gaps: list[str] = []
        evidence = _object(raw.get("evidence"))
        facts = {name: raw[name] for name in ConnectionFacts.model_fields if name in raw}
        facts["voltage_level"] = _text(evidence.get("voltage_level"))
        for field in ("start_terminal_coordinates", "end_terminal_coordinates"):
            try:
                if facts.get(field) is not None:
                    facts[field] = TerminalPosition.model_validate(facts[field])
            except ValidationError:
                facts[field] = None
                gaps.append(f"{field}未保存有效坐标，不能定位高亮。")
        try:
            row = ConnectionFacts.model_validate(facts)
        except ValidationError as exc:
            raise ExplainError("INVALID_ROW", "数据库行字段不完整或类型不符合解释契约。", 409) from exc
        record = _object(evidence.get("record"))
        recorded: dict[str, Any] = {}
        for field in (
            "source_note",
            "direction_basis",
            "current_basis",
            "current_source_text",
            "signal_name",
            "unit_identity_confidence",
        ):
            value = record.get(field)
            if value is not None:
                recorded[field] = _text(value)
        if record.get("confidence") is not None:
            try:
                confidence = float(record["confidence"])
                if 0 <= confidence <= 1:
                    recorded["confidence"] = confidence
            except (TypeError, ValueError):
                gaps.append("原提取记录的置信度格式无效，未用于解释。")
        for field in ("processing_status", "extraction_method"):
            if evidence.get(field) is not None:
                recorded[field] = _text(evidence[field])
        references = record.get("references")
        if isinstance(references, list):
            allowed = {"raw", "target_function", "target_drawing_page", "target_pdf_page", "source_index_raw"}
            recorded["references"] = [
                {k: _text(v, 1000) for k, v in ref.items() if k in allowed}
                for ref in references[:30]
                if isinstance(ref, dict)
            ]
        differences = []
        for old_field, current_field in (
            ("start_terminal", "start_terminal"),
            ("end_terminal", "end_terminal"),
            ("line_number", "principle_number"),
            ("current", "current_value"),
        ):
            if old_field in record and _text(record[old_field]) != _text(getattr(row, current_field)):
                differences.append(
                    {
                        "field": current_field,
                        "recorded_value": _text(record[old_field]),
                        "current_value": _text(getattr(row, current_field)),
                    }
                )
        if differences:
            recorded["field_differences"] = differences
            gaps.append("当前字段与已保存提取值不同；原始来源说明不能直接证明修改后的值，变更原因需查审计。")
        manual = _object(evidence.get("manual_change"))
        if manual.get("proposal_id"):
            recorded["manual_change"] = {
                key: manual.get(key) for key in ("proposal_id", "operation", "time", "fields")
            }
            if manual.get("operation") == "swap_endpoints":
                gaps.append(
                    "该行起终点已人工调换，记录所属页与工作区保持；坐标自身PDF页号才是端点位置。历史方向说明和引用不能当成新方向的证明。"
                )
        reasons = evidence.get("review_reasons")
        if isinstance(reasons, list):
            recorded["review_reasons"] = [
                {k: _text(v, 1000) for k, v in item.items() if k in {"code", "field", "message"}}
                for item in reasons[:30]
                if isinstance(item, dict)
            ]
        profile = await self._profile(project, evidence, gaps)
        context = ExplainContext(
            project_name=_text(project.get("name"), 200) or "",
            row=row,
            profile=profile,
            recorded=recorded,
            gaps=gaps,
        )
        index = _object(project.get("drawing_index"))
        raw_pages = index.get("pages")
        pages: list[Any] = raw_pages if isinstance(raw_pages, list) else []
        indexed_pair = {row.source_pdf_page_number, row.target_pdf_page_number}
        if any(
            point is not None and point.pdf_page_number not in indexed_pair
            for point in (row.start_terminal_coordinates, row.end_terminal_coordinates)
        ):
            context.gaps.append("端子坐标所属页不在记录关联页中，未用于定位。")
        await self._drawing(
            context, pages, "source", row.source_pdf_page_number, row.source_drawing_page, image_cache
        )
        if (
            row.target_pdf_page_number is not None
            and row.target_pdf_page_number != row.source_pdf_page_number
        ):
            await self._drawing(
                context, pages, "target", row.target_pdf_page_number, row.target_drawing_page, image_cache
            )
            if not row.is_cross_page and row.target_pdf_page_number != row.source_pdf_page_number:
                context.gaps.append("跨页标志与目标物理页不一致，需要核对数据库记录。")
        elif row.is_cross_page:
            context.gaps.append(
                "跨页目标物理页尚未确认，无法提供目标图纸。"
                if row.target_pdf_page_number is None
                else "跨页标志与同页目标不一致，未重复展示目标图片。"
            )
        # References may preserve a candidate page even when endpoint completion failed.
        for reference in recorded.get("references", []):
            number = reference.get("target_pdf_page")
            label = reference.get("target_drawing_page")
            matches = [
                p
                for p in pages
                if isinstance(p, dict)
                and (
                    str(p.get("pdf_page_number")) == str(number)
                    if number
                    else bool(label) and p.get("drawing_page") == label
                )
            ]
            if len(matches) == 1:
                candidate = matches[0].get("pdf_page_number")
                if isinstance(candidate, int) and not any(
                    d.pdf_page_number == candidate for d in context.drawings
                ):
                    await self._drawing(context, pages, "reference", candidate, label, image_cache)
            elif number or label:
                context.gaps.append("跨页引用在图纸索引中缺失或不唯一，未猜测目标图纸。")
        return context

    async def _profile(
        self, project: dict[str, Any], evidence: dict[str, Any], gaps: list[str]
    ) -> ProfileEvidence | None:
        frozen = evidence.get("profile")
        if isinstance(frozen, dict) and frozen.get("key"):
            if not frozen.get("version") or not frozen.get("checksum"):
                gaps.append("该行规则快照不完整，部分版本或资源摘要尚未记录。")
            return ProfileEvidence(
                key=str(frozen["key"]),
                version=_text(frozen.get("version"), 100),
                checksum=_text(frozen.get("checksum"), 100),
                source="record_evidence",
            )
        gaps.append("该行未保存提取时的规则快照；项目规则引用不能证明当时使用的版本。")
        if project.get("profile_id"):
            profiles = await self.client.select(
                "extraction_profiles",
                params={
                    "id": f"eq.{project['profile_id']}",
                    "limit": "1",
                },
            )
            if profiles and str(profiles[0].get("id")) == str(project["profile_id"]):
                value = profiles[0]
                return ProfileEvidence(
                    key=str(value["profile_key"]),
                    version=_text(value.get("profile_version"), 100),
                    checksum=_text(value.get("checksum"), 100),
                    source="project_reference",
                )
        return None

    async def _drawing(
        self,
        context: ExplainContext,
        pages: list[Any],
        role: Literal["source", "target", "reference"],
        number: int,
        label: str | None,
        image_cache: dict[str, str | None] | None = None,
    ) -> None:
        matches = [p for p in pages if isinstance(p, dict) and p.get("pdf_page_number") == number]
        # Source/target index the extraction page pair, not endpoint direction.
        position = (
            next(
                (
                    point
                    for point in (
                        context.row.start_terminal_coordinates,
                        context.row.end_terminal_coordinates,
                    )
                    if point is not None and point.pdf_page_number == number
                ),
                None,
            )
            if role != "reference"
            else None
        )
        drawing = DrawingEvidence(
            role=role, pdf_page_number=number, drawing_page=label, terminal_coordinates=position
        )
        context.drawings.append(drawing)
        if len(matches) != 1:
            context.gaps.append(f"{role}物理页{number}在项目索引中缺失或不唯一。")
            return
        page = matches[0]
        drawing.drawing_page = _text(page.get("drawing_page"), 200) or label
        drawing.workspace_code = _text(page.get("workspace_code"), 200)
        path, bucket = page.get("image_path"), page.get("image_bucket", self.bucket)
        if not path:
            context.gaps.append(f"{role}物理页{number}尚未保存页面图片。")
            return
        if not self._safe_image_path(context.row.project_id, bucket, path):
            context.gaps.append(f"{role}图片路径不属于当前项目，未生成地址。")
            return
        try:
            if image_cache is not None and path in image_cache:
                drawing.image_url = image_cache[path]
            else:
                drawing.image_url = await self.client.create_signed_url(
                    bucket=bucket, object_path=path, expires_in=300
                )
                if image_cache is not None:
                    image_cache[path] = drawing.image_url
            if drawing.image_url:
                drawing.url_expires_in = 300
            else:
                context.gaps.append(f"{role}页面图片暂不可用，可重新请求解释刷新地址。")
        except Exception:
            if image_cache is not None:
                image_cache[path] = None
            # A missing image must not erase the available row/evidence explanation.
            context.gaps.append(f"{role}页面图片暂不可用，可重新请求解释刷新地址。")


def _model_image(data: bytes) -> str:
    """Bound image size for visual explanation; preserve full-page identity, not re-extraction."""
    if len(data) > 20_000_000:
        raise ValueError("Image too large")
    pixmap = pymupdf.Pixmap(data)
    if pixmap.width * pixmap.height > 100_000_000:
        raise ValueError("Image dimensions too large")
    ratio = min(
        1.0, 1536 / max(pixmap.width, pixmap.height), math.sqrt(1_000_000 / (pixmap.width * pixmap.height))
    )
    if ratio < 1:
        pixmap = pymupdf.Pixmap(pixmap, max(1, int(pixmap.width * ratio)), max(1, int(pixmap.height * ratio)))
    encoded = base64.b64encode(pixmap.tobytes("png")).decode("ascii")
    return "data:image/png;base64," + encoded
