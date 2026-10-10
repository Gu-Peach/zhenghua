from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

import httpx

from ..core.config import Settings
from ..core.terminal_strips import (
    ALLOWED_TERMINAL_CODES,
    normalize_terminal_strip,
    terminal_strip_for_device as configured_terminal_strip_for_device,
)
from ..schemas.wire import (
    CrossPageCompletion,
    Endpoint,
    PageClassification,
    PageScanResult,
    ReferenceEvidence,
    WireConnection,
    WireRecord,
    WireUnit,
)
from .prompt_loader import (
    FewShotExample,
    load_cross_page_few_shot_examples,
    load_few_shot_examples,
    load_page_classification_few_shot_examples,
    load_page_scan_few_shot_examples,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImagePayload:
    name: str
    mime_type: str
    content: bytes
    # Set by the PDF splitter when a page has (almost) no ink; such pages are skipped.
    blank: bool = False
    # Optional embedded PDF text used only for deterministic cross-page grouping hints.
    page_text: str | None = None
    page_number: int | None = None


class VLMError(RuntimeError):
    """Raised when the VLM call succeeds poorly or returns invalid JSON."""


class VLMClient:
    def __init__(
        self,
        settings: Settings,
        prompt: str,
        *,
        few_shot_examples: Sequence[FewShotExample] | None = None,
    ):
        self.settings = settings
        self.prompt = prompt
        self._few_shot_examples = list(few_shot_examples) if few_shot_examples is not None else None
        self._classification_examples: list[FewShotExample] | None = None
        self._page_scan_examples: list[FewShotExample] | None = None
        self._cross_page_examples: list[FewShotExample] | None = None

    @property
    def few_shot_examples(self) -> list[FewShotExample]:
        if self._few_shot_examples is None:
            if self.settings.few_shot_images:
                self._few_shot_examples = load_few_shot_examples(self.settings.few_shot_examples_dir)
            else:
                self._few_shot_examples = []
        return self._few_shot_examples

    @property
    def page_scan_examples(self) -> list[FewShotExample]:
        if self._page_scan_examples is None:
            enabled = getattr(self.settings, "page_scan_few_shot_images", True)
            directory = getattr(self.settings, "page_scan_few_shot_examples_dir", None)
            if directory is None:
                from ..core.config import default_page_scan_few_shot_examples_dir

                directory = default_page_scan_few_shot_examples_dir()
            self._page_scan_examples = load_page_scan_few_shot_examples(directory) if enabled else []
            logger.info(
                "page scan few-shot: enabled=%s loaded=%d directory=%s",
                enabled,
                len(self._page_scan_examples),
                directory,
            )
        return self._page_scan_examples

    @property
    def classification_examples(self) -> list[FewShotExample]:
        if self._classification_examples is None:
            enabled = getattr(self.settings, "classification_few_shot_images", True)
            directory = getattr(self.settings, "classification_few_shot_examples_dir", None)
            if directory is None:
                from ..core.config import default_page_classification_few_shot_examples_dir

                directory = default_page_classification_few_shot_examples_dir()
            self._classification_examples = (
                load_page_classification_few_shot_examples(directory) if enabled else []
            )
        return self._classification_examples

    @property
    def cross_page_examples(self) -> list[FewShotExample]:
        if self._cross_page_examples is None:
            enabled = getattr(self.settings, "cross_page_few_shot_images", True)
            directory = getattr(self.settings, "cross_page_few_shot_examples_dir", None)
            if directory is None:
                from ..core.config import default_cross_page_few_shot_examples_dir

                directory = default_cross_page_few_shot_examples_dir()
            self._cross_page_examples = load_cross_page_few_shot_examples(directory) if enabled else []
            logger.info(
                "cross-page few-shot: enabled=%s loaded=%d directory=%s",
                enabled,
                len(self._cross_page_examples),
                directory,
            )
        return self._cross_page_examples

    async def classify_page(
        self,
        image: ImagePayload,
        *,
        context_text: str = "",
    ) -> PageClassification:
        """Read only Plant Function/Page Number for stage-one classification."""
        if image.blank:
            return PageClassification(blank=True, confidence=1.0, reason="blank image")
        user_text = (
            "只读取图框身份，不要提取线路、端子或线号。\n"
            f"PDF物理页码：{image.page_number}\n"
            f"当前上下文：{context_text or '无'}\n"
            "严格输出 PageClassification JSON。"
        )
        return await self._complete_json_with_schema(
            images=[image],
            user_text=user_text,
            system_prompt=self._configured_prompt("classification_prompt_path", self.prompt),
            prefix_messages=build_classification_few_shot_messages(self.classification_examples),
            parser=parse_page_classification,
            label="page classification",
        )

    async def extract_image(self, image: ImagePayload) -> list[WireRecord]:
        return await self.extract_images([image])

    async def extract_images(self, images: Sequence[ImagePayload], *, context_text: str | None = None) -> list[WireRecord]:
        records: list[WireRecord] = []
        for image in images:
            if image.blank:
                continue
            result = await self.scan_page(image, page_context=context_text or "")
            records.extend(
                page_scan_result_to_records(
                    result,
                    image,
                    terminal_strip_mapping=self.settings.terminal_strip_mapping,
                )
            )
        return records

    async def scan_page(
        self,
        image: ImagePayload,
        *,
        related_images: Sequence[ImagePayload] = (),
        page_context: str = "",
    ) -> PageScanResult:
        """Read one source page and optional referenced target pages in one call."""
        if image.blank:
            return PageScanResult(pdf_page_number=image.page_number, blank=True, units=[])

        target_names = ", ".join(target.name for target in related_images) or "none"
        user_text = (
            "当前调用是第二阶段页扫描，只把第一张图片当作当前来源页；如果没有明确传入目标图片，不要补全跨页终点。\n"
            "只提取当前来源页发出的线连接，并直接输出当前页能确认的 units/connections。\n"
            "同页能确认的终点直接填写 end；跨页引用必须绑定到对应 connection，end=null，status=needs_reference。\n"
            "必须沿当前端子实际连接的导线追踪，并读取该导线旁、断线处或箭头处的放线标记，原样填写 line_number；\n"
            "不能只按端子、设备名称或空间邻近关系配对，也不能用同一网络或相邻导线的其他放线标记替代当前导线的标记。\n"
            "同一 wire_number 下不同芯号、起点、终点或实际路径必须拆成不同 connection；相同 line_number 也不能据此自动合并。\n"
            "图片中的红框、箭头和人工批注只用于指示检查位置，不是图纸字段，不要把批注文字写入结果。\n"
            f"当前页上下文：{page_context or '无'}\n"
            f"当前来源图片：{image.name}\n"
            f"随附目标图片（第二阶段应为 none）：{target_names}\n"
            "电流 current 只能填写图中明确可见的电流/额定电流值；不能根据电压、线号、端子号推算。看不到时填 null。\n"
            "严格只输出 PageScanResult JSON。"
        )
        result = await self._complete_json_with_schema(
            images=[image, *related_images],
            user_text=user_text,
            system_prompt=self._configured_prompt("page_scan_prompt_path", self.prompt),
            prefix_messages=build_page_scan_few_shot_messages(self.page_scan_examples),
            parser=lambda content: parse_page_scan_result(
                content,
                default_pdf_page=image.page_number,
            ),
            label="page scan",
        )
        if result.pdf_page_number is None:
            result.pdf_page_number = image.page_number
        return result

    async def resolve_cross_page(
        self,
        source_image: ImagePayload,
        target_images: Sequence[ImagePayload],
        *,
        task_context: str = "",
    ) -> CrossPageCompletion:
        """Complete one source-row's missing endpoint using indexed target pages."""
        if source_image.blank:
            return CrossPageCompletion(status="needs_review", needs_review=True, warnings=["source page is blank"])
        target_names = ", ".join(image.name for image in target_images) or "none"
        user_text = (
            "第一张图片是当前放线表行的来源页，后续图片是脚本根据该行跨页引用定位到的目标页。\n"
            "只处理下面 task_context 指定的这一条 connection，不要提取或合并目标页的其他线路。\n"
            "根据当前行的起点端子、line_number/放线标记、Plant Function + Page Number + Column 引用，"
            "在目标页对应位置沿实际导线确认终点或中间端点。\n"
            "只在图中明确确认后填写 end；找不到时 end 必须为 null，status=needs_review，不能猜测。\n"
            f"任务上下文：{task_context or '无'}\n"
            f"来源图片：{source_image.name}\n"
            f"目标图片：{target_names}\n"
            "严格只输出 CrossPageCompletion JSON。"
        )
        return await self._complete_json_with_schema(
            images=[source_image, *target_images],
            user_text=user_text,
            system_prompt=self._configured_prompt("cross_page_prompt_path", self.prompt),
            prefix_messages=build_cross_page_few_shot_messages(self.cross_page_examples),
            parser=parse_cross_page_completion,
            label="cross-page completion",
        )

    async def _complete_json_with_schema(
        self,
        *,
        images: Sequence[ImagePayload],
        user_text: str,
        system_prompt: str,
        prefix_messages: Sequence[dict[str, Any]],
        parser: Callable[[str], Any],
        label: str,
    ) -> Any:
        # Transport retries live in complete(); this second, small retry is for
        # a syntactically valid response that fails the task-specific schema.
        last_error: Exception | None = None
        for schema_attempt in range(2):
            request_text = user_text
            if schema_attempt:
                request_text += "\n上一次输出未通过 JSON schema 校验；请重新输出完整且合法的 JSON，不要解释。"
            try:
                content = await self.complete(
                    images=images,
                    user_text=request_text,
                    system_prompt=system_prompt,
                    prefix_messages=prefix_messages,
                )
                return parser(content)
            except (VLMError, ValueError, TypeError) as exc:
                last_error = exc
                logger.warning("%s schema attempt %d failed: %s", label, schema_attempt + 1, exc)
        raise VLMError(f"{label} response failed schema validation after 2 attempts: {last_error}") from last_error

    def _configured_prompt(self, setting_name: str, fallback: str) -> str:
        path = getattr(self.settings, setting_name, None)
        if path is None:
            from ..core.config import (
                default_page_classification_prompt_path,
                default_page_scan_prompt_path,
            )

            defaults = {
                "classification_prompt_path": default_page_classification_prompt_path,
                "page_scan_prompt_path": default_page_scan_prompt_path,
            }
            from ..core.config import default_cross_page_prompt_path

            defaults["cross_page_prompt_path"] = default_cross_page_prompt_path
            path = defaults.get(setting_name, default_page_scan_prompt_path)()
        if path is not None:
            try:
                if path.is_file():
                    return path.read_text(encoding="utf-8").strip()
            except OSError:
                logger.warning("Unable to read VLM prompt %s", path)
        return fallback

    async def complete(
        self,
        *,
        images: Sequence[ImagePayload],
        user_text: str,
        system_prompt: str | None = None,
        prefix_messages: Sequence[dict[str, Any]] | None = None,
    ) -> str:
        if not images:
            return ""

        payload: dict[str, Any] = {
            "model": self.settings.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt or self.prompt},
                *(prefix_messages or []),
                {"role": "user", "content": _build_user_content(images, user_text)},
            ],
        }
        if self.settings.use_response_format:
            payload["response_format"] = {"type": "json_object"}
        if self.settings.enable_thinking is not None:
            payload["chat_template_kwargs"] = {"enable_thinking": self.settings.enable_thinking}
        if self.settings.max_tokens:
            payload["max_tokens"] = self.settings.max_tokens

        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"

        endpoint = self.settings.chat_completions_url
        timeout = _request_timeout(self.settings.timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(self.settings.retry_count + 1):
                try:
                    response = await client.post(endpoint, headers=headers, json=payload)
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        status_code = exc.response.status_code
                        message = f"VLM request failed: {status_code} {exc.response.text}"
                        if not _retryable_status(status_code) or attempt >= self.settings.retry_count:
                            raise VLMError(message) from exc
                        await _sleep_before_retry(self.settings, attempt, f"HTTP {status_code}")
                        continue

                    try:
                        return _extract_message_content(response.json())
                    except (ValueError, VLMError) as exc:
                        if attempt >= self.settings.retry_count:
                            if isinstance(exc, VLMError):
                                raise
                            raise VLMError("VLM response was not valid JSON.") from exc
                        await _sleep_before_retry(self.settings, attempt, "invalid VLM response")
                except httpx.TimeoutException as exc:
                    if attempt >= self.settings.retry_count:
                        raise VLMError(
                            "VLM request timed out "
                            f"after {self.settings.timeout_seconds:g}s at {endpoint}. "
                            "Increase VLM_TIMEOUT_SECONDS in .env, or lower VLM_REFERENCE_TARGET_LIMIT if the provider struggles with multi-image requests."
                        ) from exc
                    await _sleep_before_retry(self.settings, attempt, "request timeout")
                except httpx.RequestError as exc:
                    if attempt >= self.settings.retry_count:
                        raise VLMError(f"VLM request failed before receiving a response at {endpoint}: {exc}") from exc
                    await _sleep_before_retry(self.settings, attempt, f"{type(exc).__name__}")

        raise VLMError(f"VLM request failed after {self.settings.retry_count + 1} attempts at {endpoint}.")


def build_few_shot_messages(examples: Sequence[FewShotExample]) -> list[dict[str, Any]]:
    """Turn each example into a user turn (drawings) + assistant turn (expected JSON)."""
    messages: list[dict[str, Any]] = []
    for example in examples:
        notes = "；".join(
            f"{image.name}（{image.role or '图纸'}）：{image.note}" if image.note else image.name
            for image in example.images
        )
        text = (
            f"【示例：{example.title}】请读取以下电气原理图图片，按系统提示的字段只返回 JSON 数组。"
            f"图片说明：{notes}"
        )
        content: list[dict[str, Any]] = [{"type": "text", "text": text}]
        for image in example.images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": _to_data_url(image.mime_type, image.content), "detail": "high"},
                }
            )
        messages.append({"role": "user", "content": content})
        messages.append({"role": "assistant", "content": example.expected_json})
    return messages


def build_segment_few_shot_messages(examples: Sequence[FewShotExample]) -> list[dict[str, Any]]:
    """Build multimodal Prompt-S examples: two drawing images -> merge JSON."""
    messages: list[dict[str, Any]] = []
    for example in examples:
        notes = "；".join(
            f"{image.name}（{image.role or '图纸'}）：{image.note}" if image.note else image.name
            for image in example.images
        )
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    f"【分段示例：{example.title}】第一张图是相邻页 A，第二张图是相邻页 B。"
                    "请只依据 Project.NR 和 drawing prefix 判断是否合并。"
                    f"图片说明：{notes}。只输出 Prompt S 要求的 JSON 对象。"
                ),
            }
        ]
        for image in example.images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": _to_data_url(image.mime_type, image.content), "detail": "high"},
                }
            )
        messages.append({"role": "user", "content": content})
        messages.append({"role": "assistant", "content": example.expected_json})
    return messages


def build_page_scan_few_shot_messages(examples: Sequence[FewShotExample]) -> list[dict[str, Any]]:
    """Build image-backed examples for the two-stage final table scanner."""
    return _build_structured_few_shot_messages(
        examples,
        instruction=(
            "这是按页提取最终放线表的示例。第一张图是来源页，后续图是可选目标页；"
            "只输出来源页涉及的最终 connection，目标页可确认的终点要直接填入 end。"
            "请沿实际导线读取放线标记并用它确认连接，不能只按端子或设备的空间邻近关系配对；"
            "图片中的红框、箭头和批注只是人工提示，不是要抄入结果的字段。"
        ),
    )


def build_cross_page_few_shot_messages(examples: Sequence[FewShotExample]) -> list[dict[str, Any]]:
    """Build image-backed examples for one-row cross-page completion."""
    return _build_structured_few_shot_messages(
        examples,
        instruction=(
            "这是跨页补全示例。第一张图是来源页，后续图是目标页；"
            "只补全任务指定的这一条 connection 的 end/intermediate_points，不能提取目标页其他线路；"
            "找不到明确终点时返回 null 和 needs_review。"
        ),
    )


def build_classification_few_shot_messages(examples: Sequence[FewShotExample]) -> list[dict[str, Any]]:
    """Build image-backed examples for stage-one page identity classification."""
    return _build_structured_few_shot_messages(
        examples,
        instruction=(
            "这是页面身份分类示例。只读取 Plant Function、Page Number 和空白/非接线状态，"
            "不要提取线路或端子。只输出 PageClassification JSON。"
        ),
    )


def _build_structured_few_shot_messages(
    examples: Sequence[FewShotExample],
    *,
    instruction: str,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for example in examples:
        input_context = (
            f"\n本示例的结构化输入/task_context：{example.input_json}"
            if example.input_json
            else ""
        )
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": f"【示例：{example.title}】{instruction}{input_context}只输出 JSON。",
            }
        ]
        for image in example.images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": _to_data_url(image.mime_type, image.content), "detail": "high"},
                }
            )
        messages.append({"role": "user", "content": content})
        messages.append({"role": "assistant", "content": example.expected_json})
    return messages


def _build_user_content(images: Sequence[ImagePayload], user_text: str) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [
        {"type": "text", "text": user_text},
    ]
    for image in images:
        content.append({"type": "image_url", "image_url": {"url": _to_data_url(image.mime_type, image.content), "detail": "high"}})
    return content


def _request_timeout(timeout_seconds: float) -> httpx.Timeout:
    connect_timeout = min(30.0, timeout_seconds)
    write_timeout = min(60.0, timeout_seconds)
    pool_timeout = min(30.0, timeout_seconds)
    return httpx.Timeout(
        timeout_seconds,
        connect=connect_timeout,
        read=timeout_seconds,
        write=write_timeout,
        pool=pool_timeout,
    )


def _retryable_status(status_code: int) -> bool:
    return status_code in {408, 429} or status_code >= 500


async def _sleep_before_retry(settings: Settings, attempt: int, reason: str) -> None:
    delay = min(
        settings.retry_max_backoff_seconds,
        settings.retry_backoff_seconds * (2 ** attempt),
    )
    logger.warning(
        "VLM request attempt failed (%s); retrying in %.1fs (%d/%d)",
        reason,
        delay,
        attempt + 1,
        settings.retry_count,
    )
    if delay > 0:
        await asyncio.sleep(delay)


def _to_data_url(mime_type: str, content: bytes) -> str:
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _extract_message_content(response_json: dict[str, Any]) -> str:
    try:
        content = response_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise VLMError("VLM response does not match OpenAI chat completions format.") from exc

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = [part.get("text", "") for part in content if isinstance(part, dict)]
        return "".join(text_parts)
    raise VLMError("VLM response content is not text.")


def parse_vlm_records(
    content: str,
    *,
    terminal_strip_mapping: Mapping[str, str] | None = None,
) -> list[WireRecord]:
    raw = _strip_code_fence(content).strip()
    parsed = _loads_json(raw)

    if isinstance(parsed, dict):
        for key in ("records", "data", "items", "wires", "result"):
            value = parsed.get(key)
            if isinstance(value, list):
                parsed = value
                break
        else:
            if any(key in parsed for key in ("line_number", "start_terminal", "end_terminal")):
                parsed = [parsed]

    if not isinstance(parsed, list):
        raise VLMError("VLM JSON must be an array of wire records or an object containing a records array.")

    records: list[WireRecord] = []
    for item in parsed:
        if not isinstance(item, dict):
            raise VLMError("Each VLM record must be a JSON object.")
        records.append(_normalize_wire_record(WireRecord.model_validate(item), terminal_strip_mapping))
    return records


def parse_page_scan_result(content: str, *, default_pdf_page: int | None = None) -> PageScanResult:
    """Parse a page-scan response and normalize common VLM shape drift."""
    parsed = _loads_json(_strip_code_fence(content).strip())
    if isinstance(parsed, list):
        parsed = {"units": [{"unit_id": "page-unit-1", "connections": parsed}]}
    if not isinstance(parsed, dict):
        raise VLMError("Page scan JSON must be an object.")

    if not isinstance(parsed.get("units"), list):
        records = parsed.get("records") or parsed.get("connections") or parsed.get("items")
        if isinstance(records, list):
            parsed["units"] = [{"unit_id": "page-unit-1", "connections": records}]
        else:
            parsed["units"] = []

    normalized_units: list[dict[str, Any]] = []
    for unit_index, raw_unit in enumerate(parsed["units"], start=1):
        if not isinstance(raw_unit, dict):
            raise VLMError("Each page-scan unit must be a JSON object.")
        unit = dict(raw_unit)
        unit.setdefault("unit_id", f"page-unit-{unit_index}")
        raw_connections = unit.get("connections") or unit.get("records") or []
        if not isinstance(raw_connections, list):
            raise VLMError("Page-scan unit connections must be an array.")
        unit["connections"] = [
            _normalize_connection_payload(item, index)
            for index, item in enumerate(raw_connections, start=1)
            if isinstance(item, dict)
        ]
        normalized_units.append(unit)

    parsed["units"] = normalized_units
    if parsed.get("pdf_page_number") is None:
        parsed["pdf_page_number"] = default_pdf_page
    parsed["page_references"] = [
        _normalize_reference_payload(item)
        for item in _as_object_list(parsed.get("page_references") or parsed.get("references"))
        if isinstance(item, dict)
    ]
    return PageScanResult.model_validate(parsed)


def parse_cross_page_completion(content: str) -> CrossPageCompletion:
    """Parse the strict single-row completion envelope."""
    parsed = _loads_json(_strip_code_fence(content).strip())
    if not isinstance(parsed, dict):
        raise VLMError("Cross-page completion JSON must be an object.")
    nested = parsed.get("completion") or parsed.get("result")
    if isinstance(nested, dict):
        merged = dict(nested)
        for key in ("task_id", "status", "needs_review"):
            if key in parsed and key not in merged:
                merged[key] = parsed[key]
        parsed = merged
    if parsed.get("end") is None and any(key.startswith("end_") for key in parsed):
        parsed["end"] = _endpoint_from_flat(parsed, "end")
    if parsed.get("intermediate_points") is None:
        parsed["intermediate_points"] = []
    return CrossPageCompletion.model_validate(parsed)


def parse_page_classification(content: str) -> PageClassification:
    parsed = _loads_json(_strip_code_fence(content).strip())
    if not isinstance(parsed, dict):
        raise VLMError("Page classification JSON must be an object.")
    function = parsed.get("plant_function") or parsed.get("drawing_function") or parsed.get("function")
    if isinstance(function, str):
        function = function.strip().upper().lstrip("=") or None
    page_number = parsed.get("page_number") or parsed.get("drawing_page_number")
    parsed["plant_function"] = function
    parsed["page_number"] = page_number
    return PageClassification.model_validate(parsed)


def page_scan_result_to_records(
    result: PageScanResult,
    image: ImagePayload,
    *,
    terminal_strip_mapping: Mapping[str, str] | None = None,
) -> list[WireRecord]:
    """Flatten a single page-scan result for the legacy extraction endpoint."""
    records: list[WireRecord] = []
    primary_page = image.page_number
    drawing_label = (
        f"{result.drawing_function}/{result.drawing_page_number}"
        if result.drawing_function and result.drawing_page_number is not None
        else result.drawing_function
    )
    for unit in result.units:
        for connection in unit.connections:
            start = connection.start or Endpoint()
            end = connection.end or Endpoint()
            target_pages = [
                int(reference.target_pdf_page)
                for reference in connection.references
                if reference.target_pdf_page is not None
            ]
            source_pages = sorted({int(primary_page), *target_pages}) if primary_page is not None else sorted(set(target_pages))
            unresolved = connection.status not in {"complete", "resolved"}
            record = WireRecord(
                wire_number=unit.wire_number,
                attribute=unit.attribute,
                model=unit.model,
                spec=unit.spec,
                length=unit.length,
                current=connection.current,
                current_basis=connection.current_basis,
                current_source_text=connection.current_source_text,
                line_number=connection.line_number,
                core_number=connection.core_number,
                color=connection.color,
                start_part=start.part,
                start_location=start.location,
                start_device=start.device,
                start_name=start.name,
                start_terminal_board=start.terminal_board,
                start_terminal_code=start.terminal_code,
                start_terminal=start.terminal,
                end_part=end.part,
                end_location=end.location,
                end_device=end.device,
                end_name=end.name,
                end_terminal_board=end.terminal_board,
                end_terminal_code=end.terminal_code,
                end_terminal=end.terminal,
                terminal_strip=start.terminal_strip,
                start_terminal_strip=start.terminal_strip,
                end_terminal_strip=end.terminal_strip,
                remark=connection.remark,
                confidence=connection.confidence or unit.confidence,
                source_note=connection.source_note,
                source_image=image.name,
                source_pages=source_pages,
                source_type="external" if unresolved and end.terminal is None else "pdf",
                external_source_required=connection.external_source_required or unresolved and end.terminal is None,
                unit_id=unit.unit_id,
                connection_id=connection.connection_id or connection.local_connection_id,
                intermediate_points=[point.model_dump(mode="json", exclude_none=False) for point in connection.intermediate_points],
                references=[reference.model_dump(mode="json", exclude_none=False) for reference in connection.references],
                drawing_function=result.drawing_function,
                drawing_page_number=result.drawing_page_number,
                pdf_page_number=primary_page,
                drawing_source_pages=[drawing_label] if drawing_label else [],
                drawing_page=drawing_label,
                status=connection.status,
                unit_identity_confidence=unit.unit_identity_confidence,
            )
            record.source_note = _append_page_source_note(record.source_note, source_pages, drawing_label)
            records.append(normalize_wire_record(record, terminal_strip_mapping))
    return records


def _append_page_source_note(note: str | None, pages: Sequence[int], drawing_label: str | None) -> str:
    parts = [note] if note else []
    if pages:
        parts.append(f"PDF第{','.join(str(page) for page in pages)}页")
    if drawing_label:
        parts.append(f"图纸页{drawing_label}")
    return "；".join(parts)


def _normalize_connection_payload(value: Mapping[str, Any], index: int) -> dict[str, Any]:
    connection = dict(value)
    connection.setdefault("local_connection_id", f"connection-{index}")
    if connection.get("start") is None and any(key.startswith("start_") for key in connection):
        connection["start"] = _endpoint_from_flat(connection, "start")
    if connection.get("end") is None and any(key.startswith("end_") for key in connection):
        connection["end"] = _endpoint_from_flat(connection, "end")
    connection["references"] = [
        _normalize_reference_payload(item)
        for item in _as_object_list(connection.get("references") or connection.get("reference"))
        if isinstance(item, dict)
    ]
    return connection


def _endpoint_from_flat(value: Mapping[str, Any], prefix: str) -> dict[str, Any]:
    return {
        "part": value.get(f"{prefix}_part"),
        "location": value.get(f"{prefix}_location"),
        "device": value.get(f"{prefix}_device"),
        "name": value.get(f"{prefix}_name"),
        "terminal_board": value.get(f"{prefix}_terminal_board"),
        "terminal_code": value.get(f"{prefix}_terminal_code"),
        "terminal_strip": value.get(f"{prefix}_terminal_strip"),
        "terminal": value.get(f"{prefix}_terminal"),
    }


def _normalize_reference_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    reference = dict(value)
    if reference.get("target_drawing_page") is None:
        reference["target_drawing_page"] = (
            reference.get("target_internal_page")
            or reference.get("target_page")
            or reference.get("drawing_page_number")
        )
    return reference


def _as_object_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def normalize_wire_record(
    record: WireRecord,
    terminal_strip_mapping: Mapping[str, str] | None = None,
) -> WireRecord:
    """Apply deterministic terminal formatting and configured strip mapping."""
    return _normalize_wire_record(record, terminal_strip_mapping)


def attach_source_metadata(records: Sequence[WireRecord], images: Sequence[ImagePayload]) -> list[WireRecord]:
    """Attach deterministic PDF page provenance to VLM records."""
    image_names = [image.name for image in images]
    page_by_name = {
        name: image.page_number or _page_number_from_image_name(name, index + 1)
        for index, (name, image) in enumerate(zip(image_names, images))
    }
    for record in records:
        source_type = (record.source_type or "").strip().lower()
        if source_type not in {"pdf", "external", "mixed", "unknown"}:
            source_type = ""
        mentioned = [name for name in image_names if record.source_image and name in record.source_image]
        if not mentioned and source_type != "external":
            mentioned = image_names
            if not record.source_image:
                record.source_image = ", ".join(image_names) or None
        record.source_pages = (
            sorted({page_by_name[name] for name in mentioned if page_by_name[name] is not None})
            if source_type != "external"
            else []
        )
        if source_type not in {"pdf", "external", "mixed", "unknown"}:
            source_type = "pdf" if record.source_pages else "unknown"
        record.source_type = source_type
        record.external_source_required = source_type in {"external", "mixed"}
        if source_type in {"pdf", "mixed"} and record.source_pages:
            page_note = f"PDF第{','.join(str(page) for page in record.source_pages)}页"
            if not record.source_note:
                record.source_note = page_note
            elif page_note not in record.source_note:
                record.source_note = f"{record.source_note}；{page_note}"
    return list(records)


def _page_number_from_image_name(name: str, fallback: int) -> int | None:
    match = re.search(r"#page=(\d+)", name, flags=re.IGNORECASE) or re.search(r"page[_-](\d+)", name, flags=re.IGNORECASE)
    return int(match.group(1)) if match else fallback


def _normalize_wire_record(
    record: WireRecord,
    terminal_strip_mapping: Mapping[str, str] | None = None,
) -> WireRecord:
    """Normalize terminal formatting without inventing drawing values."""
    line_number = _text(record.line_number)
    if line_number and line_number.upper() == "SPARE":
        record.terminal_strip = None
        record.start_terminal_strip = None
        record.end_terminal_strip = None
        record.start_terminal = "*"
        record.end_terminal = "*"
        record.remark = record.remark or "SPARE"
        return record
    if line_number and line_number.upper() == "PE":
        record.terminal_strip = None
        record.start_terminal_strip = None
        record.end_terminal_strip = None
        record.start_terminal = "PE"
        record.end_terminal = "PE"
        record.color = record.color or "黄绿"
        record.remark = record.remark or "PE"
        return record

    record.start_terminal = _normalize_terminal(record.start_device, record.start_terminal, force_strip_prefix=True)
    record.end_terminal = _normalize_terminal(record.end_device, record.end_terminal, force_strip_prefix=False)
    record.start_terminal_code = _normalize_terminal_code(record.start_terminal_code)
    record.end_terminal_code = _normalize_terminal_code(record.end_terminal_code)
    start_strip = _terminal_strip_for_device(record.start_device, terminal_strip_mapping)
    record.terminal_strip = start_strip or normalize_terminal_strip(
        record.terminal_strip,
        terminal_strip_mapping,
    )
    record.start_terminal_strip = start_strip or normalize_terminal_strip(
        record.start_terminal_strip or record.terminal_strip,
        terminal_strip_mapping,
    )
    record.end_terminal_strip = _terminal_strip_for_device(
        record.end_device,
        terminal_strip_mapping,
    ) or normalize_terminal_strip(record.end_terminal_strip, terminal_strip_mapping)
    return record


def _normalize_terminal(device: Any, terminal: Any, *, force_strip_prefix: bool) -> str | int | None:
    value = _text(terminal)
    if not value:
        return terminal
    if value in {"*", "PE"}:
        return value

    device_text = _text(device)
    device_code = device_text.lstrip("-").upper() if device_text else None
    if _is_terminal_strip_device(device_text):
        suffix = value.rsplit(":", 1)[-1].strip()
        if suffix and not suffix.upper().startswith(("X", "XD")):
            return f"{device_code}:{suffix}"

    normalized = re.sub(r"^-?(XA|XD\d+|XH)\s*[-:]\s*", r"\1:", value, flags=re.IGNORECASE)
    if ":" in normalized and not (force_strip_prefix and _is_terminal_strip_device(device_text)):
        return normalized

    if force_strip_prefix and device_code:
        return f"{device_code}:{value.rsplit(':', 1)[-1].strip()}"
    if _is_terminal_strip_device(device_text):
        return f"{device_code}:{value.rsplit(':', 1)[-1].strip()}"
    return value


def _normalize_terminal_code(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized if normalized in ALLOWED_TERMINAL_CODES else None


def _is_terminal_strip_device(device: str | None) -> bool:
    if not device:
        return False
    code = device.lstrip("-").upper()
    return code == "XA" or code == "XH" or code.startswith("XD")


def _terminal_strip_for_device(device: Any, mapping: Mapping[str, str] | None = None) -> str | None:
    if not _is_terminal_strip_device(_text(device)):
        return None
    return configured_terminal_strip_for_device(device, mapping)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _strip_code_fence(content: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", content, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        return fenced.group(1)
    return content


def _loads_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        candidate = _extract_json_candidate(raw)
        if candidate == raw:
            raise VLMError("VLM did not return valid JSON.")
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise VLMError("VLM did not return valid JSON.") from exc


def _extract_json_candidate(raw: str) -> str:
    array_start = raw.find("[")
    array_end = raw.rfind("]")
    if 0 <= array_start < array_end:
        return raw[array_start : array_end + 1]

    object_start = raw.find("{")
    object_end = raw.rfind("}")
    if 0 <= object_start < object_end:
        return raw[object_start : object_end + 1]
    return raw
