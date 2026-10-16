from __future__ import annotations

import asyncio
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
from src.agent.extraction_agent.infrastructure.document.model_images import prepare_vision_messages
from src.agent.extraction_agent.profiles.zh.completion_context import target_only_context

T = TypeVar("T", bound=BaseModel)


class ZhVlmExtractionStageAdapter(ExtractionStageAdapter):
    """Native multimodal adapter for ZH page extraction operations."""

    enforce_evidence_contract = True
    zh_endpoint_semantics = True

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
            "先定位当前页导线上的放线斜杠标记，以标记为搜索起点，沿导线两侧延伸，"
            "分别找到最近的实际端子或跨页箭头；遇到端子停止，不穿过端子继续追到设备。"
            "原理号和端子文字只用于读取、匹配信息，不能代替标记成为搜索起点；"
            "两端间没有标记的相邻连接不作为这个放线段输出。"
            "附近同排的X/XD标识与端子数字组合成完整terminal。\n"
            "找到端点后，检查同一放线段上的箭头，按箭头指向及相对端子位置判断起终点；"
            "不借用隔着端子或设备的其他段箭头。出页段的本页端子是起点，入页段是接收端。"
            "无箭头时按本页实际接线判断，无法确认保留unknown/needs_review。"
            "跨页接收段不重复输出，本页独立放线段仍提取。"
            "endpoint_role与direction_basis保留判断；同页端点直接填写，"
            "需要目标图时绑定引用并留空终点。\n"
            "读取原理号、元件、描述和实际接口；terminal_strip由程序映射，模型留null。"
            "device是元件标识，不填X/XD排号或原理号。"
            "同页元件先读端子附近/所属框体，优先+对象位置，没有则用该端所在页Object Loc；"
            "跨页先读对应导线引用中的+对象标识，再看附近，最后用该端所在页Object Loc。"
            "来源出页引用中的+对象属于终点，目标回指中的+对象属于起点，不反填。"
            "初扫对端对象标识放references.target_object，end仍留null。"
            "每个可见实际端子的terminal_coordinates填写该端子符号中心的归一化x/y(0到1)"
            "及所属图片PDF物理页号，左上角为原点；不是端子文字、斜杠或箭头的位置。"
            "跨页初扫只填本页端子坐标；无法定位时留null。"
            "端点确定后再沿同一相线查对应断路器电流，经过端子只为读电流，不改变端点或坐标。"
            "Ie:(0.7-1)*160A直接读160A并保留Ie原文，不计算系数或改取Set；明确Ir仍优先。"
            "不取相邻回路电流，N/PE/控制/通信/光纤为空，其他未知信息留null。\n"
            f"当前页上下文：{request.page_context or '无'}\n"
            f"PDF物理页码：{request.page.pdf_page_number}\n"
            "严格输出 PageScanData JSON。"
        )

    async def resolve_cross_page(
        self,
        request: CrossPageCompletionRequest,
    ) -> CrossPageCompletionData:
        preserve_current = False
        if request.profile.rules.extraction.cross_page_input_mode == "target_only":
            context = target_only_context(request)
            preserve_current = context.current not in (None, "")
            request = request.model_copy(update={"task_context": context.model_dump_json(exclude_none=True)})

        def normalize(value: Any) -> dict[str, Any]:
            result = _normalize_cross_page(
                value, request.task_id, require_evidence=self.enforce_evidence_contract,
                target_pdf_page=request.target_page.pdf_page_number,
            )
            if preserve_current:
                for field in ("current", "current_basis", "current_source_text"):
                    result[field] = None
            return result

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
            normalize=normalize,
            item_id=request.task_id,
        )

    def cross_page_instruction(self, request: CrossPageCompletionRequest) -> str:
        if request.profile.rules.extraction.cross_page_input_mode == "target_only":
            return (
                "这是Stage2内部定向补全，只提供目标图和初扫保存的来源事实。"
                "source_page是来源业务工作区/页号/Object Loc，target_page是当前目标图；"
                "PDF物理页用于图片坐标，不代替业务页回指。"
                "先从目标图找到对应来源页的回指标识，再结合line_number、signal_name和references"
                "核对同一条线，从对应箭头沿实际导线向页内到第一个端子。"
                "回指可在页底且箭头朝外，按任务归属补终点，不重新定向。PE/N或重复原理号不能单独确定匹配；"
                "同页多路信号还要核对线路名、对象或列号，不按左右顺序配对。"
                "无法唯一确认的字段留null并needs_review。"
                "来源端子和坐标由工作流保存，当前上下文只含来源元件元数据，终点必须独立读目标图。"
                "沿匹配线路到实际接点，先分别读接口标识和针脚，再组合完整端子；"
                "X21旁的5为X21:5，N_230/HTR_L等文字是线路功能，N-BAR/PE-BAR按原文读取。"
                "references有source_index_raw时按其核对后的地址字段定位，raw保留原始识别文本。"
                "终点元件按任务对应出页引用→目标端附近→目标页Object Loc读取，"
                "来源元件补充按目标回指→已存起点元件→来源页Object Loc读取。"
                "end.terminal填写完整实际端子，terminal_strip留null；"
                "end.terminal_coordinates是目标整图归一化坐标及目标PDF物理页。"
                "电流沿用系统硬约束，有已存current时返回null表示保留。\n"
                f"任务上下文：{request.task_context}\n"
                "严格输出CrossPageCompletionData JSON，只处理这条任务。"
            )
        return (
            "这是Stage2内部双图补全，只处理任务指定的放线段。"
            "按原始引用、原理号和实线定位目标图，读取直接相连的端子，遇到端子停止。\n"
            "同排附近X/XD标识与数字组合成完整端子；保留来源起点，"
            "terminal_strip由程序映射、模型留null。无法确认的字段留null并复核。\n"
            "两端元件先读对应线路引用中的+对象标识，再看该端附近/所属框体，"
            "最后用该端所在页Object Loc；出页引用给终点，目标回指给起点。"
            "附近+对象位置优先于器件代号，X/XD排号和原理号不是元件。"
            "end.device填终点元件，location填所属对象位置；"
            "有依据的起点元件补充只通过source_component(device/location/basis)返回，"
            "起点端子、原理号和方向不变。\n"
            "end.terminal_coordinates填写终点端子在目标整张图上的归一化x/y与目标PDF物理页号，"
            "不是来源图坐标或引用地址的位置；无法定位留null，来源坐标不修改。\n"
            "如果 task_context 已有 current，输出 current=null 表示不修改 Stage 2 的已有电流；"
            "只有目标页明确给出本连接电流且 task_context 中为空时才输出电流。\n"
            "读电流可独立沿同一相线查对应断路器，不能改变已找到的端点和坐标；"
            "Ie:(0.7-1)*160A直接读160A、basis=Ie并保留原文，明确Ir仍优先，不取Set或相邻回路值。\n"
            f"任务上下文：{request.task_context}\n"
            f"目标 PDF 物理页：{request.target_page.pdf_page_number}\n"
            "严格输出 CrossPageCompletionData JSON。"
        )

    def completion_images(self, request: CrossPageCompletionRequest) -> list[DrawingPageInput]:
        if request.profile.rules.extraction.cross_page_input_mode == "target_only":
            return [request.target_page]
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
        if not self.zh_endpoint_semantics and "ScannedConnection" in contract.get("$defs", {}):
            # The optional matching hint is requested only by the ZH scan Prompt.
            contract["$defs"]["ScannedConnection"]["properties"].pop("signal_name", None)
        if not self.zh_endpoint_semantics and "DrawingReference" in contract.get("$defs", {}):
            contract["$defs"]["DrawingReference"]["properties"].pop("source_index_raw", None)
        if "DrawingEndpoint" in contract.get("$defs", {}):
            endpoint_schema = contract["$defs"]["DrawingEndpoint"]
            endpoint_schema["properties"]["terminal_coordinates"]["description"] = (
                "实际端子符号/接点中心在整张输入图片中的归一化x/y（0到1），"
                "左上为原点，pdf_page_number使用本端图片的物理页号；无法定位时null"
            )
            endpoint_schema["required"] = list(dict.fromkeys([
                *endpoint_schema.get("required", []), "terminal_coordinates",
            ]))
            prompt += (
                "\n通用端子坐标要求：每个可见start/end填写terminal_coordinates={x,y,pdf_page_number}。"
                "读取实际端子符号或连接点中心，按整张图片宽高归一化到0到1，左上为原点；"
                "不要标放线标记、文字、箭头或裁剪区域坐标，不按端子编号推算。"
                "初扫同页两端使用当前PDF物理页，跨页补全end使用目标PDF物理页，"
                "来源起点坐标保持不变。等比例缩放前后的归一化坐标相同；未知端子/无法定位时null。"
            )
        if self.enforce_evidence_contract and "DrawingEndpoint" in contract.get("$defs", {}):
            endpoint_schema = contract["$defs"]["DrawingEndpoint"]["properties"]
            endpoint_schema["terminal_strip"] = {
                "type": "null", "default": None,
                "description": "由程序映射的放线表业务分类，模型留null",
            }
            endpoint_schema["terminal"]["description"] = "实际完整端子；同排X/XD标识与数字组成XD3:109等"
            endpoint_schema["terminal_board"]["description"] = "图中实际端子排或设备接口标识，如XD3、X1"
            endpoint_schema["terminal_code"]["description"] = "实际接口标识，不是针脚数字或业务分类"
            if self.zh_endpoint_semantics:
                endpoint_schema["device"]["description"] = (
                    "ZH起/终点元件标识，常见+01F...；同页附近→本端所在页Object Loc，"
                    "跨页对应线路引用的对象标识→附近→本端所在页Object Loc；X/XD排号和原理号不是元件"
                )
            endpoint_schema["location"]["description"] = "该端所属对象位置，与元件标识可以相同"
        if self.enforce_evidence_contract and output_model is PageScanData:
            connection_schema = contract["$defs"]["ScannedConnection"]
            connection_schema["required"] = list(
                dict.fromkeys([*connection_schema.get("required", []), "endpoint_role", "direction_basis"])
            )
        # The output protocol is shared. The switch above only changes the
        # ZH-specific semantics, never whether ABB receives a JSON contract.
        system_prompt = prompt + "\n输出 JSON Schema：\n" + json.dumps(contract)
        input_content = await asyncio.to_thread(_multimodal_content, user_text, images)
        messages = [
            {"role": "system", "content": system_prompt},
            *prefix,
            {"role": "user", "content": input_content},
        ]
        messages, image_metadata = await asyncio.to_thread(
            prepare_vision_messages,
            messages,
            input_max_side=self._settings.model_input_max_image_side,
            max_total_pixels=self._settings.model_max_total_image_pixels,
            few_shot_min_side=self._settings.model_fewshot_min_image_side,
        )
        if example_section == "stage3_cases":
            image_metadata["completion_input_mode"] = profile.rules.extraction.cross_page_input_mode
        last_error: Exception | None = None
        for schema_attempt in range(2):
            attempt_messages = list(messages)
            if schema_attempt:
                attempt_messages.append(
                    {
                        "role": "user",
                        "content": _schema_retry_instruction(last_error),
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
                            **image_metadata,
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
                if response.finish_reason == "length":
                    raise ValueError(
                        f"{stage} model output stopped at its length limit; "
                        "finish_reason=length; inspect model_calls before retrying."
                    ) from exc
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


def _schema_retry_instruction(error: Exception | None) -> str:
    """Report bounded parse diagnostics without replaying a huge invalid answer."""
    detail = "输出不符合字段Schema"
    if isinstance(error, json.JSONDecodeError):
        detail = f"JSON语法错误：{error.msg}；行{error.lineno}、列{error.colno}、位置{error.pos}"
    return (
        f"上次输出未通过校验（{detail}）。请按提供的JSON Schema重新输出单个完整合法JSON对象；"
        "不要输出解释、Markdown、重复连接或多份答案，使用紧凑JSON并省略无值的可选字段。"
    )


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
    if current.get("context_version") == 2:
        if (
            current_features["signal_name"]
            and current_features["signal_name"] == candidate_features["signal_name"]
        ):
            score += 12
        for side in ("source", "target"):
            if (
                current_features[f"{side}_function"]
                and current_features[f"{side}_function"] == candidate_features[f"{side}_function"]
                and current_features[f"{side}_page"] is not None
                and current_features[f"{side}_page"] == candidate_features[f"{side}_page"]
            ):
                score += 4
    return score


def _stage3_task_features(task: Mapping[str, Any]) -> dict[str, Any]:
    source_record = task.get("source_record")
    source_record = source_record if isinstance(source_record, Mapping) else {}
    references = task.get("references")
    references = references if isinstance(references, list) else []
    first_reference = next((item for item in references if isinstance(item, Mapping)), {})
    start = task.get("start")
    start = start if isinstance(start, Mapping) else {}
    source_page = task.get("source_page")
    source_page = source_page if isinstance(source_page, Mapping) else {}
    target_page = task.get("target_page")
    target_page = target_page if isinstance(target_page, Mapping) else {}
    start_terminal = str(source_record.get("start_terminal") or start.get("terminal") or "").strip().upper()
    start_code = start_terminal.split(":", 1)[0] if start_terminal else ""
    source_function = str(
        source_record.get("drawing_function") or source_page.get("drawing_function") or ""
    ).strip().upper()
    target_function = str(
        target_page.get("drawing_function") or first_reference.get("target_function") or ""
    ).strip().upper()
    return {
        "line_number": str(task.get("line_number") or source_record.get("line_number") or "").strip().upper(),
        "start_terminal": start_terminal,
        "start_code": start_code,
        "source_function": source_function,
        "target_function": target_function,
        "signal_name": str(task.get("signal_name") or source_record.get("signal_name") or "").strip().upper(),
        "source_page": source_page.get("drawing_page_number") or source_record.get("drawing_page_number"),
        "target_page": target_page.get("drawing_page_number") or first_reference.get("target_drawing_page"),
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
                            "terminal_coordinates",
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
    for unit in normalized["units"]:
        if not isinstance(unit, dict):
            continue
        for connection in unit.get("connections", []):
            if not isinstance(connection, dict):
                continue
            for side in ("start", "end"):
                _bind_terminal_coordinates(connection.get(side), page_number)
    return normalized


def _normalize_cross_page(
    payload: Any, task_id: str, *, require_evidence: bool = False, target_pdf_page: int | None = None
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
    if target_pdf_page is not None:
        _bind_terminal_coordinates(normalized.get("end"), target_pdf_page)
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


def _bind_terminal_coordinates(endpoint: Any, pdf_page_number: int) -> None:
    """Bind model coordinates to the actual image rather than a guessed reference page."""
    if not isinstance(endpoint, dict):
        return
    if endpoint.get("terminal") in (None, ""):
        endpoint["terminal_coordinates"] = None
    elif isinstance(endpoint.get("terminal_coordinates"), dict):
        endpoint["terminal_coordinates"]["pdf_page_number"] = pdf_page_number


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
