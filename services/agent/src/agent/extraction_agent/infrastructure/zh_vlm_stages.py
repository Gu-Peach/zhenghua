from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, TypeVar, get_args, get_origin

from pydantic import BaseModel, ValidationError

from src.config import AgentSettings
from src.domain.enums import ErrorCode
from src.agent.extraction_agent.domain.models.extraction_stages import (
    CrossPageCompletionData,
    CrossPageCompletionRequest,
    DrawingPageInput,
    PageClassificationData,
    PageClassificationRequest,
    PageScanData,
    PageScanRequest,
)
from src.domain.models.profiles import ProfileBinding
from src.domain.ports import ExtractionStageAdapter
from src.harness.model_gateway import ModelGateway, ModelGatewayError, ModelRequest
from src.agent.extraction_agent.infrastructure.document.json_response import _extract_json_candidate

T = TypeVar("T", bound=BaseModel)


class ZhVlmExtractionStageAdapter(ExtractionStageAdapter):
    """Native multimodal adapter for ZH page extraction operations."""

    enforce_evidence_contract = True

    def __init__(self, settings: AgentSettings, gateway: ModelGateway) -> None:
        self._settings = settings
        self._gateway = gateway
        self._examples: dict[tuple[str, str], list[dict[str, Any]]] = {}

    async def classify_page(self, request: PageClassificationRequest) -> PageClassificationData:
        if request.page.blank:
            return PageClassificationData(blank=True, confidence=1.0, reason="blank page from PDF renderer")
        user_text = self.classification_instruction(request)
        return await self._invoke_stage(
            stage="page_classification",
            request_id=request.run_id,
            profile=request.profile,
            prompt_resource="classification_prompt",
            example_resource="classification_examples",
            example_section="cases",
            images=[request.page],
            user_text=user_text,
            output_model=PageClassificationData,
            normalize=_normalize_classification,
            item_id=f"pdf-page:{request.page.pdf_page_number}",
        )

    def classification_instruction(self, request: PageClassificationRequest) -> str:
        return (
            "只读取当前图纸的 Plant Function 和 Page Number，并判断是否为空白页或非接线图。"
            "不要提取线路、端子、线号或端点。"
            f"\nPDF物理页码：{request.page.pdf_page_number}"
            f"\n已知上下文：{request.known_context or '无'}"
            "\n严格输出 PageClassification JSON。"
        )

    async def scan_page(self, request: PageScanRequest) -> PageScanData:
        if request.page.blank or request.page.non_wiring:
            return PageScanData(
                pdf_page_number=request.page.pdf_page_number,
                drawing_function=request.page.plant_function,
                drawing_page_number=request.page.drawing_page_number,
                blank=request.page.blank,
            )
        user_text = self.scan_instruction(request)
        return await self._invoke_stage(
            stage="page_scan",
            request_id=request.run_id,
            profile=request.profile,
            prompt_resource="page_scan_prompt",
            example_resource="wiring_examples",
            example_section="stage2_cases",
            images=[request.page],
            user_text=user_text,
            output_model=PageScanData,
            normalize=lambda value: _normalize_page_scan(
                value, request.page.pdf_page_number, require_direction=self.enforce_evidence_contract
            ),
            item_id=f"pdf-page:{request.page.pdf_page_number}",
        )

    def scan_instruction(self, request: PageScanRequest) -> str:
        return (
            "扫描当前页放线标记，读取每个放线段两侧直接连接的端子；遇到端子停止，"
            "不要穿过端子继续追到PLC。附近同排的X/XD标识与端子数字组合成完整terminal。\n"
            "按箭头或实际接线判断起终点；跨页接收段不重复输出，本页独立放线段仍提取。"
            "endpoint_role与direction_basis保留判断；同页端点直接填写，"
            "需要目标图时绑定引用并留空终点。\n"
            "读取原理号、元件、描述和实际接口；terminal_strip由程序映射，模型留null。"
            "电流遵守系统Prompt约束，其他未知信息留null。\n"
            f"当前页上下文：{request.page_context or '无'}\n"
            f"PDF物理页码：{request.page.pdf_page_number}\n"
            "严格输出 PageScanData JSON。"
        )

    async def resolve_cross_page(
        self,
        request: CrossPageCompletionRequest,
    ) -> CrossPageCompletionData:
        user_text = self.cross_page_instruction(request)
        return await self._invoke_stage(
            stage="page_scan",
            request_id=request.run_id,
            profile=request.profile,
            prompt_resource="cross_page_prompt",
            example_resource="wiring_examples",
            example_section="stage3_cases",
            input_json=request.task_context,
            images=self.completion_images(request),
            user_text=user_text,
            output_model=CrossPageCompletionData,
            normalize=lambda value: _normalize_cross_page(
                value, request.task_id, require_evidence=self.enforce_evidence_contract
            ),
            item_id=request.task_id,
        )

    def cross_page_instruction(self, request: CrossPageCompletionRequest) -> str:
        return (
            "这是Stage2内部双图补全，只处理任务指定的放线段。"
            "按原始引用、原理号和实线定位目标图，读取直接相连的端子，遇到端子停止。\n"
            "同排附近X/XD标识与数字组合成完整端子；保留来源起点，"
            "terminal_strip由程序映射、模型留null。无法确认的字段留null并复核。\n"
            "如果 task_context 已有 current，输出 current=null 表示不修改 Stage 2 的已有电流；"
            "只有目标页明确给出本连接电流且 task_context 中为空时才输出电流。\n"
            f"任务上下文：{request.task_context}\n"
            f"目标 PDF 物理页：{request.target_page.pdf_page_number}\n"
            "严格输出 CrossPageCompletionData JSON。"
        )

    def completion_images(self, request: CrossPageCompletionRequest) -> list[DrawingPageInput]:
        return ([request.source_page] if request.source_page else []) + [request.target_page]

    async def _invoke_stage(
        self,
        *,
        stage: str,
        request_id: str,
        profile: ProfileBinding,
        prompt_resource: str,
        example_resource: str,
        example_section: str,
        images: Sequence[DrawingPageInput],
        user_text: str,
        output_model: type[T],
        normalize: Any,
        input_json: str | None = None,
        item_id: str | None = None,
    ) -> T:
        prompt = profile.resource(prompt_resource).read_text(encoding="utf-8")
        prefix = self._few_shot_messages(
            profile=profile,
            resource=example_resource,
            section=example_section,
            input_json=input_json,
        )
        contract = output_model.model_json_schema()
        if self.enforce_evidence_contract and "DrawingEndpoint" in contract.get("$defs", {}):
            endpoint_schema = contract["$defs"]["DrawingEndpoint"]["properties"]
            endpoint_schema["terminal_strip"] = {
                "type": "null", "default": None,
                "description": "由程序映射的放线表业务分类，模型留null",
            }
            endpoint_schema["terminal"]["description"] = "实际完整端子；同排X/XD标识与数字组成XD3:109等"
            endpoint_schema["terminal_board"]["description"] = "图中实际端子排或设备接口标识，如XD3、X1"
            endpoint_schema["terminal_code"]["description"] = "实际接口标识，不是针脚数字或业务分类"
        if self.enforce_evidence_contract and output_model is PageScanData:
            connection_schema = contract["$defs"]["ScannedConnection"]
            connection_schema["required"] = list(
                dict.fromkeys([*connection_schema.get("required", []), "endpoint_role", "direction_basis"])
            )
        system_prompt = (
            prompt + "\n输出 JSON Schema：\n" + json.dumps(contract)
            if self.enforce_evidence_contract else prompt
        )
        messages = [
            {"role": "system", "content": system_prompt},
            *prefix,
            {"role": "user", "content": _multimodal_content(user_text, images)},
        ]
        last_error: Exception | None = None
        for schema_attempt in range(2):
            attempt_messages = list(messages)
            if schema_attempt:
                attempt_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "上次输出未通过 JSON schema 校验，请重新检查图片和上下文，只输出完整合法 JSON。"
                        ),
                    }
                )
            try:
                response = await self._gateway.invoke(
                    ModelRequest(
                        agent_name=stage,
                        run_id=request_id,
                        messages=attempt_messages,
                        temperature=0.0,
                        max_tokens=self._settings.model_max_tokens,
                        json_mode=self._settings.model_json_mode,
                        enable_thinking=self._settings.model_enable_thinking,
                        metadata={
                            "profile": profile.profile.key,
                            "profile_version": profile.profile.version,
                            "profile_checksum": profile.profile.checksum,
                            "prompt_checksum": (
                                f"sha256:{hashlib.sha256(system_prompt.encode('utf-8')).hexdigest()}"
                            ),
                            "input_pdf_pages": [image.pdf_page_number for image in images],
                            "item_id": item_id,
                            "stage": stage,
                        },
                    )
                )
            except ModelGatewayError as exc:
                if exc.code != ErrorCode.MODEL_SCHEMA_INVALID:
                    raise
                last_error = exc
                continue

            try:
                parsed = _json_payload(response.content)
                return output_model.model_validate(_filter_schema(output_model, normalize(parsed)))
            except (ValueError, ValidationError) as exc:
                last_error = exc
        detail = str(last_error)[:500] if last_error is not None else "unknown schema error"
        raise ValueError(
            f"{stage} returned invalid structured data after two attempts: {detail}"
        ) from last_error

    def _few_shot_messages(
        self,
        *,
        profile: ProfileBinding,
        resource: str,
        section: str,
        input_json: str | None,
    ) -> list[dict[str, Any]]:
        key = (str(profile.resource(resource)), section)
        if key not in self._examples:
            self._examples[key] = _load_examples(
                profile.resource(resource),
                section,
                max_image_side=self._settings.model_fewshot_max_image_side,
            )
        examples = self._examples[key]
        if section == "stage3_cases":
            examples = _select_stage3_examples(examples, input_json=input_json, limit=1)
        messages: list[dict[str, Any]] = []
        for example in examples:
            images = [
                {
                    "type": "image_url",
                    "image_url": {"url": item["data_url"], "detail": "auto"},
                }
                for item in example["images"]
            ]
            extra_input = example.get("input_json") or input_json
            text = f"【示例：{example['title']}】按系统要求从示例图中读取并输出结构化 JSON。"
            if extra_input:
                text += f"\n结构化任务输入：{extra_input}"
            messages.extend(
                [
                    {"role": "user", "content": [{"type": "text", "text": text}, *images]},
                    {"role": "assistant", "content": example["expected_json"]},
                ]
            )
        return messages


def _load_examples(
    directory: Path,
    section: str,
    *,
    max_image_side: int,
) -> list[dict[str, Any]]:
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        return []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    examples: list[dict[str, Any]] = []
    for item in manifest.get(section, []):
        image_payloads = []
        for image in item.get("images", []):
            path = (directory / image["path"]).resolve()
            if not path.is_file():
                continue
            image_bytes, mime = _prepare_few_shot_image(path, max_side=max_image_side)
            encoded = base64.b64encode(image_bytes).decode("ascii")
            image_payloads.append(
                {
                    "name": path.name,
                    "data_url": f"data:{mime};base64,{encoded}",
                }
            )
        expected = item.get("expected")
        expected_path = (
            (directory / expected).resolve() if expected else (directory / item["id"] / "expected.json")
        )
        if not image_payloads or not expected_path.is_file():
            continue
        expected_json = json.dumps(
            json.loads(expected_path.read_text(encoding="utf-8")),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        input_path = (directory / item["input"]).resolve() if item.get("input") else None
        examples.append(
            {
                "title": str(item.get("title") or item.get("id")),
                "images": image_payloads,
                "expected_json": expected_json,
                "input_json": (
                    json.dumps(json.loads(input_path.read_text(encoding="utf-8")), ensure_ascii=False)
                    if input_path is not None and input_path.is_file()
                    else None
                ),
            }
        )
    return examples


def _select_stage3_examples(
    examples: list[dict[str, Any]],
    *,
    input_json: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    if limit <= 0 or not examples:
        return []
    current = _parse_json_object(input_json)
    ranked = sorted(
        enumerate(examples),
        key=lambda item: (-_stage3_example_score(current, item[1]), item[0]),
    )
    return [example for _, example in ranked[:limit]]


def _stage3_example_score(current: Mapping[str, Any], example: Mapping[str, Any]) -> int:
    candidate = _parse_json_object(example.get("input_json"))
    current_features = _stage3_task_features(current)
    candidate_features = _stage3_task_features(candidate)
    score = 0
    if current_features["line_number"] and (
        current_features["line_number"] == candidate_features["line_number"]
    ):
        score += 20
    if current_features["start_terminal"] and (
        current_features["start_terminal"] == candidate_features["start_terminal"]
    ):
        score += 8
    if current_features["start_code"] and (
        current_features["start_code"] == candidate_features["start_code"]
    ):
        score += 4
    if current_features["source_function"] and (
        current_features["source_function"] == candidate_features["source_function"]
    ):
        score += 3
    if current_features["target_function"] and (
        current_features["target_function"] == candidate_features["target_function"]
    ):
        score += 3
    if current_features["cross_function"] == candidate_features["cross_function"]:
        score += 1
    return score


def _stage3_task_features(task: Mapping[str, Any]) -> dict[str, Any]:
    source_record = task.get("source_record")
    source_record = source_record if isinstance(source_record, Mapping) else {}
    references = task.get("references")
    references = references if isinstance(references, list) else []
    first_reference = next((item for item in references if isinstance(item, Mapping)), {})
    start_terminal = str(source_record.get("start_terminal") or "").strip().upper()
    start_code = start_terminal.split(":", 1)[0] if start_terminal else ""
    source_function = str(source_record.get("drawing_function") or "").strip().upper()
    target_function = str(first_reference.get("target_function") or "").strip().upper()
    return {
        "line_number": str(task.get("line_number") or source_record.get("line_number") or "").strip().upper(),
        "start_terminal": start_terminal,
        "start_code": start_code,
        "source_function": source_function,
        "target_function": target_function,
        "cross_function": bool(source_function and target_function and source_function != target_function),
    }


def _parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _prepare_few_shot_image(path: Path, *, max_side: int) -> tuple[bytes, str]:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    image_bytes = path.read_bytes()

    import pymupdf

    pixmap = pymupdf.Pixmap(str(path))
    if max(pixmap.width, pixmap.height) <= max_side:
        return image_bytes, mime

    while max(pixmap.width, pixmap.height) > max_side:
        pixmap.shrink(1)
    return pixmap.tobytes("png"), "image/png"


def _multimodal_content(text: str, pages: Sequence[DrawingPageInput]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for page in pages:
        mime = mimetypes.guess_type(page.image_path.name)[0] or "image/png"
        encoded = base64.b64encode(page.image_path.read_bytes()).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{encoded}", "detail": "auto"},
            }
        )
    return content


def _json_payload(content: str) -> Any:
    raw = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.IGNORECASE | re.DOTALL)
    raw = fenced.group(1) if fenced else raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return json.loads(_extract_json_candidate(raw))


def _normalize_classification(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
        payload = payload["result"]
    if not isinstance(payload, dict):
        raise ValueError("Page classification must be a JSON object.")
    normalized = dict(payload)
    normalized["plant_function"] = (
        normalized.get("plant_function") or normalized.get("drawing_function") or normalized.get("function")
    )
    normalized["drawing_page_number"] = normalized.get("drawing_page_number") or normalized.get("page_number")
    for alias in ("drawing_function", "function", "page_number"):
        normalized.pop(alias, None)
    return normalized


def _normalize_page_scan(
    payload: Any, page_number: int, *, require_direction: bool = False
) -> dict[str, Any]:
    if isinstance(payload, list):
        payload = {"units": [{"unit_id": "page-unit-1", "connections": payload}]}
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
        payload = payload["result"]
    if not isinstance(payload, dict):
        raise ValueError("Page scan must be a JSON object or array.")
    normalized = dict(payload)
    # A legacy model occasionally used drawing_function for a numeric page.
    # Preserve real function codes such as 002.C or LV11.
    function_value = normalized.get("drawing_function")
    legacy_numeric_page = isinstance(function_value, int) or (
        isinstance(function_value, str) and function_value.strip().isdigit()
    )
    if legacy_numeric_page and "drawing_page_number" not in normalized:
        normalized["drawing_page_number"] = function_value
        normalized.pop("drawing_function", None)
    if "references" in normalized and "page_references" not in normalized:
        normalized["page_references"] = normalized["references"]
    normalized.pop("records", None)
    normalized.pop("connections", None)
    normalized.pop("items", None)
    normalized.pop("references", None)
    if not isinstance(normalized.get("units"), list):
        rows = normalized.get("connections") or normalized.get("records") or normalized.get("items")
        normalized["units"] = (
            [{"unit_id": "page-unit-1", "connections": rows}] if isinstance(rows, list) else []
        )
    for unit_index, unit in enumerate(normalized["units"], start=1):
        if not isinstance(unit, dict):
            continue
        unit.setdefault("unit_id", f"page-unit-{unit_index}")
        unit["connections"] = unit.get("connections") or unit.get("records") or []
        unit.pop("records", None)
        # Models sometimes emit numeric drawing page labels (for example 432)
        # even though the domain contract keeps labels as strings. Normalize
        # both unit- and connection-level page lists before Pydantic validation.
        for field in ("source_drawing_pages",):
            values = unit.get(field)
            if isinstance(values, list):
                unit[field] = [str(value) for value in values if value not in (None, "")]
        for connection in unit["connections"]:
            if not isinstance(connection, dict):
                continue
            if require_direction and connection.get("endpoint_role") != "receiver":
                if (
                    not connection.get("endpoint_role")
                    or not str(connection.get("direction_basis") or "").strip()
                ):
                    connection["endpoint_role"] = "unknown"
                    connection["status"] = "needs_review"
                    normalized["needs_review"] = True
                    note = "missing endpoint role or direction evidence; source is unconfirmed"
                    connection["source_note"] = "; ".join(filter(None, [connection.get("source_note"), note]))
            values = connection.get("source_drawing_pages")
            if isinstance(values, list):
                connection["source_drawing_pages"] = [
                    str(value) for value in values if value not in (None, "")
                ]
            for side in ("start", "end"):
                if not isinstance(connection.get(side), dict):
                    endpoint = {
                        name: connection.get(f"{side}_{name}")
                        for name in (
                            "part",
                            "location",
                            "device",
                            "name",
                            "terminal_board",
                            "terminal_code",
                            "terminal_strip",
                            "terminal",
                        )
                        if connection.get(f"{side}_{name}") not in (None, "")
                    }
                    if endpoint:
                        connection[side] = endpoint
                for name in (
                    "part",
                    "location",
                    "device",
                    "name",
                    "terminal_board",
                    "terminal_code",
                    "terminal_strip",
                    "terminal",
                ):
                    connection.pop(f"{side}_{name}", None)
            refs = connection.get("references") or []
            connection["references"] = [{"raw": ref} if isinstance(ref, str) else ref for ref in refs]
            for reference in connection["references"]:
                if not isinstance(reference, dict):
                    continue
                # Drawing/physical page 0 is not a page; VLMs use it as an unknown sentinel.
                # Columns are deliberately excluded because EPLAN can use column zero.
                for field in ("target_drawing_page", "target_internal_page", "target_pdf_page"):
                    value = reference.get(field)
                    if type(value) is int and value == 0 or isinstance(value, str) and value == "0":
                        reference[field] = None
            if refs:
                connection["is_cross_page"] = "cross_page"
            elif isinstance(connection.get("end"), dict) and connection["end"]:
                connection["is_cross_page"] = "same_page"
            elif connection.get("is_cross_page") not in {"same_page", "cross_page", "unknown"}:
                connection["is_cross_page"] = "unknown"
    normalized.setdefault("pdf_page_number", page_number)
    normalized.setdefault("page_references", [])
    return normalized


def _normalize_cross_page(
    payload: Any, task_id: str, *, require_evidence: bool = False
) -> dict[str, Any]:
    if isinstance(payload, dict):
        payload = payload.get("completion") or payload.get("result") or payload
    if not isinstance(payload, dict):
        raise ValueError("Cross-page completion must be a JSON object.")
    normalized = dict(payload)
    normalized.setdefault("task_id", task_id)
    if normalized.get("end") is None and any(key.startswith("end_") for key in normalized):
        normalized["end"] = {
            key.removeprefix("end_"): value
            for key, value in normalized.items()
            if key.startswith("end_") and value not in (None, "")
        }
    for key in tuple(normalized):
        if key.startswith("end_"):
            normalized.pop(key, None)
    normalized.setdefault("intermediate_points", [])
    if require_evidence:
        end = normalized.get("end")
        if (
            not isinstance(end, dict)
            or end.get("terminal") in (None, "")
            or not str(normalized.get("source_note") or "").strip()
        ):
            normalized["status"] = "needs_review"
            normalized["needs_review"] = True
            normalized.setdefault("warnings", []).append("missing endpoint or target path evidence")
    return normalized


def _filter_schema(model: type[BaseModel], value: Any) -> Any:
    if not isinstance(value, Mapping):
        return value
    filtered: dict[str, Any] = {}
    for name, field in model.model_fields.items():
        if name not in value:
            continue
        filtered[name] = _filter_nested(field.annotation, value[name])
    return filtered


def _filter_nested(annotation: Any, value: Any) -> Any:
    if value is None:
        return None
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (list, Sequence) and args and isinstance(value, list):
        return [_filter_nested(args[0], item) for item in value]
    nested_model = annotation if isinstance(annotation, type) and issubclass(annotation, BaseModel) else None
    if nested_model is None:
        nested_model = next(
            (item for item in args if isinstance(item, type) and issubclass(item, BaseModel)),
            None,
        )
    if nested_model is not None:
        return _filter_schema(nested_model, value)
    return value
